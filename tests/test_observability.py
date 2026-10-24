from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fundamental_agent.observability import (
    BudgetConfig,
    CostBudget,
    TraceRecorder,
    estimate_tokens,
)


class ObservabilityTest(unittest.TestCase):
    def test_budget_records_usage_and_rejects_overrun(self) -> None:
        budget = CostBudget(
            config=BudgetConfig(
                max_total_tokens=100,
                max_cost_usd=0.0,
                input_price_per_million=0.0,
                output_price_per_million=0.0,
            )
        )
        allowed, _ = budget.can_call(40, 50)
        self.assertTrue(allowed)

        budget.record(40, 50)
        self.assertEqual(budget.snapshot()["total_tokens"], 90)

        allowed, reason = budget.can_call(10, 10)
        self.assertFalse(allowed)
        self.assertIn("超过预算", reason)

    def test_trace_writes_jsonl_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trace = TraceRecorder(
                run_id="unit-test",
                trace_dir=Path(temp_dir),
            )
            trace.event(
                "llm_call",
                node="llm_summary",
                status="ok",
                metadata={
                    "api_key": "sk-real-key",
                    "authorization": "Bearer secret",
                    "note": "sk-should-be-redacted",
                },
            )
            lines = trace.path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["run_id"], "unit-test")
            self.assertEqual(payload["metadata"]["api_key"], "***")
            self.assertEqual(payload["metadata"]["authorization"], "***")
            self.assertNotIn("sk-real-key", lines[0])
            self.assertNotIn("sk-should-be-redacted", lines[0])

    def test_token_estimate_is_positive(self) -> None:
        self.assertGreater(estimate_tokens("一" * 100), 0)


if __name__ == "__main__":
    unittest.main()
