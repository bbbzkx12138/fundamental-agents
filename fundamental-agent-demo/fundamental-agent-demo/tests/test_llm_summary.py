from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from fundamental_agent.llm_provider import TemplateSummaryProvider, get_summary_provider
from fundamental_agent.llm_summary import summarize_brief, validate_summary_batch
from fundamental_agent.models import SummaryBatch, SummaryEvidence, SummaryObservation, TickerLLMSummary
from fundamental_agent.pipeline import build_brief


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"


class FailingProvider:
    name = "failing-test-provider"
    model = "fake-model"

    def summarize(self, payload):
        raise RuntimeError("simulated provider failure")


class LlmSummaryTest(unittest.TestCase):
    def test_template_summary_has_evidence(self) -> None:
        brief = build_brief(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        updated, _, source, model = summarize_brief(
            brief,
            TemplateSummaryProvider(),
        )

        self.assertEqual(source, "template")
        self.assertIsNone(model)
        self.assertEqual(len(updated.summaries), 3)
        for summary in updated.summaries:
            self.assertTrue(summary.summary)
            self.assertTrue(summary.observations)
            self.assertTrue(summary.observations[0].evidence)

    def test_provider_failure_falls_back_to_template(self) -> None:
        brief = build_brief(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        updated, notes, source, _ = summarize_brief(brief, FailingProvider())

        self.assertEqual(source, "template")
        self.assertEqual(len(updated.summaries), 3)
        self.assertTrue(any("回退" in note for note in notes))

    def test_invalid_evidence_is_rejected(self) -> None:
        brief = build_brief(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        invalid = SummaryBatch(
            summaries=[
                TickerLLMSummary(
                    ticker="AAPL",
                    summary="测试摘要",
                    observations=[
                        SummaryObservation(
                            text="测试观察",
                            evidence=[
                                SummaryEvidence(period="不存在", metric="revenue")
                            ],
                        )
                    ],
                ),
                TickerLLMSummary(ticker="MSFT", summary="测试摘要"),
                TickerLLMSummary(ticker="NVDA", summary="测试摘要"),
            ]
        )

        with self.assertRaises(ValueError):
            validate_summary_batch(invalid, brief)

    def test_auto_mode_without_key_uses_template(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = get_summary_provider("auto")
        self.assertIsInstance(provider, TemplateSummaryProvider)

    def test_api_mode_without_key_fails(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                get_summary_provider("api")


if __name__ == "__main__":
    unittest.main()
