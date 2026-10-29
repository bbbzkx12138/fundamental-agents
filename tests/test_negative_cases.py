from __future__ import annotations

import unittest
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from fundamental_agent.data_loader import load_cache, select_tickers
from fundamental_agent.llm_provider import TemplateSummaryProvider
from fundamental_agent.llm_summary import summarize_brief
from fundamental_agent.models import CacheFile, SummaryBatch
from fundamental_agent.observability import BudgetConfig, CostBudget
from fundamental_agent.pipeline import build_brief
from fundamental_agent.verify import contains_advice_terms, verify_quarter_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"


class NeverCallProvider:
    name = "budget-test-provider"
    model = "fake-model"
    max_tokens = 10000

    def summarize(self, payload):
        raise AssertionError("budget 超限时不应调用 Provider")


class NegativeCaseTest(unittest.TestCase):
    def test_missing_quarter_is_rejected(self) -> None:
        cache = load_cache(CACHE_PATH)
        raw = cache.model_dump(mode="json")
        raw["tickers"]["AAPL"]["quarters"].pop()

        with self.assertRaises(ValidationError):
            broken = CacheFile.model_validate(raw)
            select_tickers(broken, ["AAPL", "MSFT", "NVDA"])

    def test_missing_provenance_is_rejected(self) -> None:
        cache = load_cache(CACHE_PATH)
        record = cache.tickers["AAPL"].quarters[0].model_copy(
            update={"accession_number": None}
        )

        with self.assertRaises(ValueError):
            verify_quarter_record("AAPL", record)

    def test_filed_date_before_period_end_is_rejected(self) -> None:
        cache = load_cache(CACHE_PATH)
        quarter = cache.tickers["AAPL"].quarters[0]
        record = quarter.model_copy(
            update={"filed_date": quarter.period_end_date - timedelta(days=1)}
        )

        with self.assertRaises(ValueError):
            verify_quarter_record("AAPL", record)

    def test_malformed_summary_json_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            SummaryBatch.model_validate_json('{"summaries": [')

    def test_budget_exceeded_falls_back_to_template(self) -> None:
        brief = build_brief(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        budget = CostBudget(
            config=BudgetConfig(
                max_total_tokens=100,
                max_cost_usd=0.0,
                input_price_per_million=0.0,
                output_price_per_million=0.0,
            )
        )

        updated, notes, source, _, snapshot = summarize_brief(
            brief,
            NeverCallProvider(),
            budget=budget,
        )

        self.assertEqual(source, "template")
        self.assertEqual(len(updated.summaries), 3)
        self.assertTrue(any("预算检查未通过" in note for note in notes))
        self.assertFalse(snapshot["exceeded"])

    def test_shareholder_is_not_flagged_as_hold_advice(self) -> None:
        self.assertEqual(contains_advice_terms("shareholder vote event"), [])
        self.assertTrue(contains_advice_terms("hold the stock"))


if __name__ == "__main__":
    unittest.main()
