"""Append-only JSON Lines audit logs for imports and material matching."""
from datetime import datetime
import json
import threading
from zoneinfo import ZoneInfo

from .config import LOG_DIR

_LOCK = threading.Lock()


def append_event(event_type, **fields):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds"),
        "event": event_type,
        **fields,
    }
    path = LOG_DIR / "audit.jsonl"
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _LOCK, path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
    return record


def append_match_event(**fields):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(ZoneInfo("Asia/Bangkok")).isoformat(timespec="seconds"),
        "event": "material_match",
        **fields,
    }
    path = LOG_DIR / "match_audit.jsonl"
    with _LOCK, path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        stream.flush()
    return record
