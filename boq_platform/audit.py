"""Append-only JSON Lines audit logs for imports and material matching.

Events raised inside a database transaction (``db.connection()``) are buffered
and written only when the transaction ends, so the log never claims a change
that was rolled back. Rolled-back events are still written, but tagged with
``"transaction": "rolled_back"`` so nothing is silently lost.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import json
import threading

from .config import LOG_DIR

_LOCK = threading.Lock()
_BUFFER = ContextVar("audit_buffer", default=None)
# Fixed UTC+7 offset: avoids needing the tzdata package on Windows.
_BANGKOK = timezone(timedelta(hours=7), "Asia/Bangkok")

AUDIT_FILE = "audit.jsonl"
MATCH_FILE = "match_audit.jsonl"


def _now():
    return datetime.now(_BANGKOK).isoformat(timespec="seconds")


def _write(filename, record):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _LOCK, (LOG_DIR / filename).open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()


def _emit(filename, record):
    buffer = _BUFFER.get()
    if buffer is None:
        _write(filename, record)
    else:
        buffer.append((filename, record))
    return record


@contextmanager
def transaction_buffer():
    """Hold log lines until the surrounding DB transaction commits or rolls back."""
    buffer = []
    token = _BUFFER.set(buffer)
    committed = False
    try:
        yield
        committed = True
    finally:
        _BUFFER.reset(token)
        for filename, record in buffer:
            if not committed:
                record = {**record, "transaction": "rolled_back"}
            _write(filename, record)


def append_event(event_type, **fields):
    return _emit(AUDIT_FILE, {"timestamp": _now(), "event": event_type, **fields})


def append_match_event(**fields):
    return _emit(MATCH_FILE, {"timestamp": _now(), "event": "material_match", **fields})
