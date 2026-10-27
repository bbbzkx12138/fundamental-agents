from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from fundamental_agent.api import create_app
from fundamental_agent.service import ApiSettings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"
AUTH_HEADERS = {"Authorization": "Bearer test-token"}


class ApiTest(unittest.TestCase):
    def test_start_approve_report_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                ApiSettings(
                    cache_path=CACHE_PATH,
                    checkpoint_db=root / "checkpoints.sqlite",
                    trace_dir=root / "traces",
                    report_dir=root / "reports",
                    default_llm_mode="template",
                    auth_token="test-token",
                    require_auth=True,
                )
            )
            client = TestClient(app)

            health = client.get("/health")
            self.assertEqual(health.status_code, 200)

            started = client.post(
                "/runs",
                json={
                    "tickers": ["AAPL", "MSFT", "NVDA"],
                    "llm_mode": "template",
                },
                headers=AUTH_HEADERS,
            )
            self.assertEqual(started.status_code, 200, started.text)
            payload = started.json()
            self.assertEqual(payload["status"], "waiting_approval")
            thread_id = payload["thread_id"]

            status = client.get(f"/runs/{thread_id}", headers=AUTH_HEADERS)
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"], "waiting_approval")

            approved = client.post(
                f"/runs/{thread_id}/approve",
                json={"comment": "单元测试审批"},
                headers=AUTH_HEADERS,
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "approved")

            report = client.get(f"/runs/{thread_id}/report", headers=AUTH_HEADERS)
            self.assertEqual(report.status_code, 200, report.text)
            report_payload = report.json()
            self.assertIn("美股基本面简报", report_payload["markdown"])
            self.assertEqual(report_payload["summary_source"], "template")
            self.assertIn("tickers", report_payload["structured"])

            trace = client.get(f"/runs/{thread_id}/trace", headers=AUTH_HEADERS)
            self.assertEqual(trace.status_code, 200, trace.text)
            self.assertTrue(trace.json()["events"])

    def test_unknown_run_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                ApiSettings(
                    cache_path=CACHE_PATH,
                    checkpoint_db=root / "checkpoints.sqlite",
                    trace_dir=root / "traces",
                    report_dir=root / "reports",
                    default_llm_mode="template",
                    auth_token="test-token",
                    require_auth=True,
                )
            )
            client = TestClient(app)
            response = client.get("/runs/not-found", headers=AUTH_HEADERS)
            self.assertEqual(response.status_code, 404)

    def test_api_requires_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(
                ApiSettings(
                    cache_path=CACHE_PATH,
                    checkpoint_db=root / "checkpoints.sqlite",
                    trace_dir=root / "traces",
                    report_dir=root / "reports",
                    default_llm_mode="template",
                    auth_token="test-token",
                    require_auth=True,
                )
            )
            client = TestClient(app)

            missing = client.post(
                "/runs",
                json={"tickers": ["AAPL", "MSFT", "NVDA"], "llm_mode": "template"},
            )
            self.assertEqual(missing.status_code, 401)

            wrong = client.post(
                "/runs",
                json={"tickers": ["AAPL", "MSFT", "NVDA"], "llm_mode": "template"},
                headers={"Authorization": "Bearer wrong"},
            )
            self.assertEqual(wrong.status_code, 403)


if __name__ == "__main__":
    unittest.main()
