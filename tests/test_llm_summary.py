from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fundamental_agent.llm_provider import (
    OpenAICompatibleProvider,
    TemplateSummaryProvider,
    get_summary_provider,
)
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


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class LlmSummaryTest(unittest.TestCase):
    def test_template_summary_has_evidence(self) -> None:
        brief = build_brief(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        updated, _, source, model, _ = summarize_brief(
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
        updated, notes, source, _, _ = summarize_brief(brief, FailingProvider())

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

    def test_openai_compatible_provider_captures_usage(self) -> None:
        content = json.dumps(
            {
                "summaries": [
                    {
                        "ticker": "AAPL",
                        "summary": "测试摘要",
                        "observations": [],
                        "uncertainties": [],
                    }
                ]
            },
            ensure_ascii=False,
        )
        response = FakeResponse(
            {
                "choices": [{"message": {"content": content}}],
                "usage": {
                    "prompt_tokens": 123,
                    "completion_tokens": 45,
                },
            }
        )
        provider = OpenAICompatibleProvider(
            api_key="sk-test",
            model="fake-model",
        )
        with patch(
            "fundamental_agent.llm_provider.urllib.request.urlopen",
            return_value=response,
        ) as mocked:
            result = provider.summarize({"tickers": []})

        self.assertEqual(result.batch.summaries[0].ticker, "AAPL")
        self.assertEqual(result.input_tokens, 123)
        self.assertEqual(result.output_tokens, 45)
        self.assertEqual(result.usage_source, "reported")
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test")


if __name__ == "__main__":
    unittest.main()
