from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EvalRunnerTest(unittest.TestCase):
    def test_golden_eval_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = Path(temp_dir) / "eval.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "fundamental_agent.eval_runner",
                    "--report",
                    str(report),
                ],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RESULT PASS", result.stdout)
            self.assertTrue(report.exists())


if __name__ == "__main__":
    unittest.main()
