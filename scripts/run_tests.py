#!/usr/bin/env python
"""Run all project tests — backend + frontend.

Usage:
    python scripts/run_tests.py              # all tests
    python scripts/run_tests.py --backend     # backend only
    python scripts/run_tests.py --frontend    # frontend only
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_backend():
    print("=" * 60)
    print("  Backend tests")
    print("=" * 60)
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "flask_app/tests/test_job_queue.py",
            "flask_app/tests/test_jobs_results_api.py",
            "flask_app/tests/test_storage_adapter.py",
            "flask_app/tests/test_s3_adapter.py",
            "flask_app/tests/test_api_routes_smoke.py",
            "-v", "--tb=short",
        ],
        cwd=str(ROOT),
    )
    return result.returncode


def run_frontend():
    print("=" * 60)
    print("  Frontend tests")
    print("=" * 60)
    test_result = subprocess.run(
        ["npm", "run", "test"],
        cwd=str(ROOT / "frontend"),
        shell=True,
    )
    print()
    print("=" * 60)
    print("  Frontend build")
    print("=" * 60)
    build_result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(ROOT / "frontend"),
        shell=True,
    )
    return test_result.returncode or build_result.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", action="store_true")
    parser.add_argument("--frontend", action="store_true")
    args = parser.parse_args()

    run_all = not args.backend and not args.frontend
    exit_code = 0

    if run_all or args.backend:
        if run_backend() != 0:
            exit_code = 1

    if run_all or args.frontend:
        if run_frontend() != 0:
            exit_code = 1

    print()
    if exit_code == 0:
        print("[OK] All tests passed")
    else:
        print("[FAIL] Some tests failed")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
