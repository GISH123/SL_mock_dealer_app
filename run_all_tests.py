# run_all_tests.py

import subprocess
import sys

TESTS = [
    "tests/test_log_creation.py",
    "tests/test_logs.py",
    "tests/test_config.py",
    "tests/test_integration_FM.py",
    "tests/test_integration_DVR.py"
]

def run_test(path: str) -> bool:
    print(f"\n[▶] Running {path} ...")
    try:
        subprocess.run(["python", path], check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"[✘] {path} failed.")
        return False

def main():
    passed = []
    failed = []

    for test in TESTS:
        (passed if run_test(test) else failed).append(test)

    print("\n\n========= TEST SUMMARY =========")
    print(f"[✓] Passed: {len(passed)}")
    for t in passed:
        print(f"   └── {t}")
    if failed:
        print(f"[✘] Failed: {len(failed)}")
        for t in failed:
            print(f"   └── {t}")
        sys.exit(1)
    else:
        print("[✅] All tests passed.")

if __name__ == "__main__":
    main()
