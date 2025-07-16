import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from logging.handlers import TimedRotatingFileHandler

# ─── Log Format ─────────────────────────────────────────────
_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)7s | %(message)s", "%H:%M:%S"
)

# ─── Enhanced Rotating FileHandler (Safe for CentOS/Windows) ──────────────────
class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    def emit(self, record):
        try:
            if self.shouldRollover(record):
                self.doRollover()
        except Exception:
            pass  # Prevent crash due to rollover error
        super().emit(record)

# ─── Logger Initializer ─────────────────────────────────────
def init_logger(
    name: str,
    log_dir: Optional[Path] = None,
    test_rollover_seconds: bool = False,
    daily: bool = False
) -> logging.Logger:
    """
    Initialize a rotating logger with:
    - Default: hourly rotation
    - test_rollover_seconds=True: rotate every second (for tests)
    - daily=True: rotate at midnight
    """

    if log_dir is None:
        log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{name}.log"
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Prevent duplicate handlers

    logger.setLevel(logging.INFO)

    # Determine rotation granularity
    if test_rollover_seconds:
        when = "s"
        suffix = "%Y-%m-%d_%H-%M-%S"
    elif daily:
        when = "midnight"
        suffix = "%Y-%m-%d"
    else:
        when = "H"
        suffix = "%Y-%m-%d_%H"

    fh = SafeTimedRotatingFileHandler(
        filename=log_file,
        when=when,
        interval=1,
        backupCount=48 if when == "H" else 7,
        encoding="utf-8",
        utc=False
    )
    fh.suffix = suffix
    fh.setFormatter(_FMT)

    # StreamHandler for stdout (console)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(_FMT)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger
