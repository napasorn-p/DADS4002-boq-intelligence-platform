"""Shared logger: writes to logs/app.log (the logs/ folder is git-ignored).

Usage in any module:

    from logger import get_logger
    log = get_logger(__name__)
    log.info("imported %s rows", count)
"""

import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"


def get_logger(name="boq"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        LOG_DIR.mkdir(exist_ok=True)
        handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
