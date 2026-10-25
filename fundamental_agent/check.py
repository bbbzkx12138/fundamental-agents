"""项目统一检查入口。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ],
        [
            sys.executable,
            "-m",
            "fundamental_agent.eval_runner",
        ],
    ]
    for command in commands:
        print(f"\n>>> {' '.join(command)}", flush=True)
        completed = subprocess.run(command, cwd=PROJECT_ROOT)
        if completed.returncode != 0:
            print("CHECK FAIL", flush=True)
            return completed.returncode
    print("\nCHECK PASS", flush=True)
    return 0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
