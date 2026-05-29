"""
Aarya StockSense Pro — applog.py
Shared rotating-file logger used across engine, notifier, monitor, bot_poll.
Logs to logs/app.log (rotating, 1 MB × 3 backups). Falls back silently to a
console-only logger if the filesystem is read-only (some hosts).
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")
_FMT      = logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")


def get_logger(name: str = "aarya") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:                      # already configured
        return logger
    logger.setLevel(logging.INFO)
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        fh = RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000,
                                 backupCount=3, encoding="utf-8")
        fh.setFormatter(_FMT)
        logger.addHandler(fh)
    except Exception:
        pass                                  # read-only FS — skip file handler
    logger.propagate = False
    return logger
