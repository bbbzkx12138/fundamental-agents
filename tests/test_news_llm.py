from __future__ import annotations

import unittest
from pathlib import Path

from fundamental_agent.models import NewsExplanationBatch, NewsInsight
from fundamental_agent.news_agent import build_news_brief
from fundamental_agent.news_llm import (
    build_news_explanation_payload,
    explain_news,
    validate_news_explanations,
)
from fundamental_agent.news_loader import load_news_cache
from fundamental_agent.news_provider import (
    NewsExplanationResult,
    TemplateNewsExplanationProvider,
)
from fundamental_agent.observability import BudgetConfig, CostBudget


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEWS_CACHE = PROJECT_ROOT / "data" / "cache" / "news_events.sec.json"
TICKERS = ["AAPL", "MSFT", "NVDA"]


class FailingNewsProvider:
    name = "failing-news-provider"
    model = "fake-model"
    max_tokens = 1000

    def explain(self, payload):
        raise RuntimeError("simulated news provider failure")


class NeverCallNewsProvider:
    name = "openai-compatible-news"
    model = "fake-model"
    max_tokens = 10000

    def explain(self, payload):
        raise AssertionError("预算超限时不应调用新闻 Provider")


class NewsLlmTest(unittest.TestCase):
    def _news(self):
        return build_news_brief(load_news_cache(NEWS_CACHE), TICKERS)

    def test_template_news_explanation_has_event_ids(self) -> None:
        news = self._news()
        updated, _, source, model, _ = explain_news(
            news,
            TemplateNewsExplanationProvider(),
        )

        self.assertEqual(source, "deterministic_news")
        self.assertIsNone(model)
        self.assertEqual(len(updated.explanations), 3)
        known = {event.event_id for event in updated.events}
        for explanation in updated.explanations:
            for insight in explanation.insights:
                self.assertTrue(set(insight.event_ids).issubset(known))

    def test_invalid_event_id_is_rejected(self) -> None:
        news = self._news()
        batch = TemplateNewsExplanationProvider().explain(
            build_news_explanation_payload(news)
        ).batch
        broken = batch.explanations[0].model_copy(
            update={
                "insights": [
                    NewsInsight(text="错误解释", event_ids=["missing-event"])
                ]
            }
        )
        bad_batch = NewsExplanationBatch(
            explanations=[broken, *batch.explanations[1:]]
        )

        with self.assertRaises(ValueError):
            validate_news_explanations(bad_batch, news)

    def test_provider_failure_falls_back(self) -> None:
        news = self._news()
        updated, notes, source, _, _ = explain_news(
            news,
            FailingNewsProvider(),
        )

        self.assertEqual(source, "deterministic_news")
        self.assertTrue(any("回退" in note for note in notes))
        self.assertEqual(len(updated.explanations), 3)

    def test_budget_exceeded_falls_back(self) -> None:
        news = self._news()
        budget = CostBudget(
            config=BudgetConfig(
                max_total_tokens=100,
                max_cost_usd=0.0,
                input_price_per_million=0.0,
                output_price_per_million=0.0,
            )
        )
        updated, notes, source, _, _ = explain_news(
            news,
            NeverCallNewsProvider(),
            budget=budget,
        )

        self.assertEqual(source, "deterministic_news")
        self.assertTrue(any("预算检查未通过" in note for note in notes))
        self.assertEqual(len(updated.explanations), 3)


if __name__ == "__main__":
    unittest.main()
