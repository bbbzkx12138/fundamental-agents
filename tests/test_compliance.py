from __future__ import annotations

import unittest
from pathlib import Path

from fundamental_agent.compliance import evaluate_compliance
from fundamental_agent.llm_provider import TemplateSummaryProvider
from fundamental_agent.llm_summary import summarize_brief
from fundamental_agent.models import TickerLLMSummary
from fundamental_agent.pipeline import build_brief
from fundamental_agent.report import render_markdown


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"


class ComplianceTest(unittest.TestCase):
    def _brief_with_summary(self):
        brief = build_brief(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        updated, _, _, _, _ = summarize_brief(
            brief,
            TemplateSummaryProvider(),
        )
        return updated

    def test_current_report_passes_compliance(self) -> None:
        brief = self._brief_with_summary()
        decision = evaluate_compliance(brief, render_markdown(brief))

        self.assertTrue(decision.passed)
        self.assertEqual(decision.violations, [])
        self.assertIn("模板", decision.warnings[0])

    def test_advice_wording_is_blocked(self) -> None:
        brief = self._brief_with_summary()
        bad_summary = brief.summaries[0].model_copy(
            update={"summary": "建议买入该股票，目标价 200 美元。"}
        )
        broken = brief.model_copy(
            update={"summaries": [bad_summary, *brief.summaries[1:]]}
        )
        decision = evaluate_compliance(broken, render_markdown(broken))

        self.assertFalse(decision.passed)
        self.assertTrue(any("买入" in item for item in decision.violations))

    def test_missing_provenance_is_blocked(self) -> None:
        brief = self._brief_with_summary()
        ticker = brief.tickers[0]
        broken_quarter = ticker.quarters[0].model_copy(
            update={"accession_number": None}
        )
        broken_ticker = ticker.model_copy(
            update={"quarters": [broken_quarter, *ticker.quarters[1:]]}
        )
        broken = brief.model_copy(
            update={"tickers": [broken_ticker, *brief.tickers[1:]]}
        )
        decision = evaluate_compliance(broken, render_markdown(broken))

        self.assertFalse(decision.passed)
        self.assertTrue(any("provenance" in item for item in decision.violations))


if __name__ == "__main__":
    unittest.main()
