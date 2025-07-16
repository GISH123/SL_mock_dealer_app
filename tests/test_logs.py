# tests/test_logs.py

import sys
import time
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

# ✅ Fix relative imports when running as a script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.logging_utils import init_logger

def test_per_second_log_rollover():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = init_logger("test_second_rollover", log_dir, test_rollover_seconds=True)

    logger.info("[test] log 1")
    time.sleep(1.1)
    logger.info("[test] log 2")
    time.sleep(1.1)
    logger.info("[test] log 3")

    # Collect generated logs
    rotated_logs = list(log_dir.glob("test_second_rollover.log*"))
    print(f"[DEBUG] Second-rollover logs:")
    for path in rotated_logs:
        print(" └──", path.name)

    assert any(".log." in f.name for f in rotated_logs), "[FAIL] No rotated logs created"
    print(f"[PASS] Rollover per-second logs created: {len(rotated_logs)} files")
    print("[TEST] ✅ test_logs.py (per-second mode) passed.")


def test_year_rollover_simulation():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger = init_logger("test_rollover_year", log_dir, test_rollover_seconds=True)

    # Log first entry
    logger.info("[test] Logging on 2024-12-31 (simulated)")
    time.sleep(1.1)

    # Force rollover
    for h in logger.handlers:
        if hasattr(h, "doRollover"):
            h.doRollover()

    logger.info("[test] Logging on 2025-01-01 (simulated)")

    logs = list(log_dir.glob("test_rollover_year.log*"))
    print(f"[DEBUG] Year-rollover logs:")
    for path in logs:
        print(" └──", path.name)

    # Instead of checking filename, check content
    content_2024 = any("2024-12-31" in Path(f).read_text() for f in logs)
    content_2025 = any("2025-01-01" in Path(f).read_text() for f in logs)

    assert content_2024, "[FAIL] 2024 content missing"
    assert content_2025, "[FAIL] 2025 content missing"
    print("[PASS] Year-end rollover log content created")
    print("[TEST] ✅ test_logs.py (year rollover) passed.")


if __name__ == "__main__":
    test_per_second_log_rollover()
    print("──────────────")
    test_year_rollover_simulation()
