"""News LLM 解释与确定性回退。"""

from __future__ import annotations

import json
import os
from typing import Any

from .models import (
    NewsBrief,
    NewsExplanationBatch,
    TickerNewsExplanation,
)
from .news_provider import (
    NewsExplanationProvider,
    TemplateNewsExplanationProvider,
)
from .observability import BudgetConfig, CostBudget, TraceRecorder, estimate_tokens
from .verify import contains_advice_terms


def build_news_explanation_payload(news: NewsBrief) -> dict[str, Any]:
    summaries = {summary.ticker: summary for summary in news.summaries}
    tickers = []
    for ticker, summary in summaries.items():
        ticker_events = [
            event for event in news.events if event.ticker == ticker
        ]
        tickers.append(
            {
                "ticker": ticker,
                "deterministic_summary": summary.summary,
                "events": [
                    {
                        "event_id": event.event_id,
                        "form_type": event.form_type,
                        "event_type": event.event_type,
                        "headline": event.headline,
                        "filed_date": event.filed_date.isoformat(),
                        "items": event.items,
                    }
                    for event in ticker_events
                ],
            }
        )
    return {"tickers": tickers}


def explain_news(
    news: NewsBrief,
    provider: NewsExplanationProvider,
    budget: CostBudget | None = None,
    trace: TraceRecorder | None = None,
) -> tuple[NewsBrief, list[str], str, str | None, dict[str, Any]]:
    """调用新闻解释 Provider，并在失败时回退到确定性摘要。"""

    payload = build_news_explanation_payload(news)
    payload_text = json.dumps(payload, ensure_ascii=False)
    estimated_input_tokens = estimate_tokens(payload_text)
    budget = budget or news_budget_from_env()
    notes: list[str] = []
    result = None
    fallback_reason = None

    try:
        if provider.name != "deterministic_news":
            allowed, reason = budget.can_call(
                estimated_input_tokens,
                provider.max_tokens,
            )
            if trace is not None:
                trace.event(
                    "news_budget_check",
                    node="news_llm",
                    status="ok" if allowed else "exceeded",
                    metadata={
                        "reason": reason,
                        "estimated_input_tokens": estimated_input_tokens,
                        **budget.snapshot(),
                    },
                )
            if not allowed:
                fallback_reason = f"新闻预算检查未通过：{reason}"
            else:
                result = provider.explain(payload)
        else:
            result = provider.explain(payload)
    except Exception as exc:
        fallback_reason = (
            "新闻 LLM 解释失败，已回退到确定性摘要："
            f"{type(exc).__name__}: {str(exc)[:240]}"
        )
        if trace is not None:
            trace.event(
                "news_llm_error",
                node="news_llm",
                status="error",
                metadata={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )

    if result is None:
        result = TemplateNewsExplanationProvider().explain(payload)
        notes.append(fallback_reason or "已回退到确定性新闻摘要。")
        explanation_source = "deterministic_news"
        model = None
    else:
        explanation_source = result.provider
        model = result.model
        notes.append(f"新闻解释来源：{explanation_source}。")

    validate_news_explanations(result.batch, news)

    if result.provider != "deterministic_news":
        input_tokens = result.input_tokens or estimated_input_tokens
        output_tokens = result.output_tokens or estimate_tokens(
            json.dumps(result.batch.model_dump(mode="json"), ensure_ascii=False)
        )
        budget.record(input_tokens, output_tokens)
        if result.usage_source != "reported":
            notes.append("新闻 Token 用量由估算器计算，模型未返回 usage。")
        if trace is not None:
            trace.event(
                "news_llm_call",
                node="news_llm",
                status="ok",
                metadata={
                    "provider": explanation_source,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "usage_source": result.usage_source,
                    **budget.snapshot(),
                },
            )

    updated = news.model_copy(
        update={
            "explanations": result.batch.explanations,
            "explanation_source": explanation_source,
            "llm_model": model,
            "verification_notes": news.verification_notes + notes,
        }
    )
    return updated, notes, explanation_source, model, budget.snapshot()


def validate_news_explanations(
    batch: NewsExplanationBatch,
    news: NewsBrief,
) -> None:
    tickers = {summary.ticker for summary in news.summaries}
    returned = {item.ticker for item in batch.explanations}
    if returned != tickers:
        raise ValueError(
            f"新闻解释 ticker 不匹配，期望 {sorted(tickers)}，实际 {sorted(returned)}"
        )

    events_by_ticker = {
        ticker: {event.event_id for event in news.events if event.ticker == ticker}
        for ticker in tickers
    }
    for explanation in batch.explanations:
        if not explanation.summary.strip():
            raise ValueError(f"{explanation.ticker}: 新闻解释 summary 不能为空")
        if contains_advice_terms(explanation.summary):
            raise ValueError(f"{explanation.ticker}: 新闻解释包含交易建议词")
        for insight in explanation.insights:
            if contains_advice_terms(insight.text):
                raise ValueError(f"{explanation.ticker}: 新闻 insight 包含交易建议词")
            for event_id in insight.event_ids:
                if event_id not in events_by_ticker[explanation.ticker]:
                    raise ValueError(
                        f"{explanation.ticker}: 新闻 insight 引用了不存在的事件 {event_id}"
                    )


def news_budget_from_env() -> CostBudget:
    config = BudgetConfig(
        max_total_tokens=int(os.getenv("NEWS_LLM_TOKEN_BUDGET", "4000")),
        max_cost_usd=0.0,
        input_price_per_million=float(
            os.getenv("LLM_INPUT_PRICE_PER_MILLION", "0")
        ),
        output_price_per_million=float(
            os.getenv("LLM_OUTPUT_PRICE_PER_MILLION", "0")
        ),
    )
    return CostBudget(config=config)
