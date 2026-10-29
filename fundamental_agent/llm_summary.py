"""构建 LLM 输入、调用 Provider 并校验摘要结果。"""

from __future__ import annotations

import json
from typing import Any

from .llm_provider import SummaryProvider, TemplateSummaryProvider
from .models import (
    FundamentalBrief,
    SummaryBatch,
    TickerBrief,
)
from .observability import CostBudget, TraceRecorder, estimate_tokens
from .verify import contains_advice_terms


def build_summary_payload(brief: FundamentalBrief) -> dict[str, Any]:
    """只发送经过验证的结构化指标，不发送原始 SEC 数据。"""

    return {
        "tickers": [
            _ticker_payload(ticker)
            for ticker in brief.tickers
        ]
    }


def summarize_brief(
    brief: FundamentalBrief,
    provider: SummaryProvider,
    budget: CostBudget | None = None,
    trace: TraceRecorder | None = None,
) -> tuple[FundamentalBrief, list[str], str, str | None, dict[str, Any]]:
    """调用 Provider 并返回更新后的报告、校验记录、来源、模型和预算快照。"""

    payload = build_summary_payload(brief)
    notes: list[str] = []
    budget = budget or CostBudget()
    payload_text = json.dumps(payload, ensure_ascii=False)
    estimated_input_tokens = estimate_tokens(payload_text)
    result = None
    fallback_reason = None

    try:
        if provider.name != "template":
            max_output_tokens = getattr(provider, "max_tokens", 4000)
            allowed, reason = budget.can_call(
                estimated_input_tokens,
                max_output_tokens,
            )
            if trace is not None:
                trace.event(
                    "budget_check",
                    node="llm_summary",
                    status="ok" if allowed else "exceeded",
                    metadata={
                        "reason": reason,
                        "estimated_input_tokens": estimated_input_tokens,
                        "max_output_tokens": max_output_tokens,
                        **budget.snapshot(),
                    },
                )
            if not allowed:
                fallback_reason = f"预算检查未通过：{reason}"
                if trace is not None:
                    trace.event(
                        "fallback",
                        node="llm_summary",
                        status="budget_exceeded",
                        metadata={"reason": reason},
                    )
            else:
                result = provider.summarize(payload)
        else:
            result = provider.summarize(payload)
    except Exception as exc:
        fallback_reason = (
            "LLM 摘要调用失败，已回退到确定性模板："
            f"{type(exc).__name__}: {str(exc)[:240]}"
        )
        if trace is not None:
            trace.event(
                "llm_error",
                node="llm_summary",
                status="error",
                metadata={
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )

    if result is None:
        result = TemplateSummaryProvider().summarize(payload)
        notes.append(fallback_reason or "已回退到确定性模板。")
        summary_source = "template"
        model = None
    else:
        summary_source = result.provider
        model = result.model
        notes.append(f"摘要来源：{summary_source}。")

    batch = result.batch
    validate_summary_batch(batch, brief)

    if result.provider != "template":
        input_tokens = result.input_tokens
        output_tokens = result.output_tokens
        if input_tokens is None:
            input_tokens = estimated_input_tokens
        if output_tokens is None:
            output_tokens = estimate_tokens(
                json.dumps(batch.model_dump(mode="json"), ensure_ascii=False)
            )
        budget.record(input_tokens, output_tokens)
        if result.usage_source != "reported":
            notes.append("Token 用量由估算器计算，模型未返回 usage。")
        if trace is not None:
            trace.event(
                "llm_call",
                node="llm_summary",
                status="ok",
                metadata={
                    "provider": summary_source,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "usage_source": result.usage_source,
                    **budget.snapshot(),
                },
            )

    updated = brief.model_copy(
        update={
            "summaries": batch.summaries,
            "summary_source": summary_source,
            "llm_model": model,
            "verification_notes": brief.verification_notes + notes,
        }
    )
    return updated, notes, summary_source, model, budget.snapshot()


def validate_summary_batch(batch: SummaryBatch, brief: FundamentalBrief) -> None:
    tickers = {ticker.ticker for ticker in brief.tickers}
    returned = {summary.ticker for summary in batch.summaries}
    if returned != tickers:
        raise ValueError(
            f"摘要 ticker 不匹配，期望 {sorted(tickers)}，实际 {sorted(returned)}"
        )

    evidence_lookup = {
        ticker.ticker: {(point.period, point.metric) for point in ticker.metrics}
        for ticker in brief.tickers
    }
    for summary in batch.summaries:
        if not summary.summary.strip():
            raise ValueError(f"{summary.ticker}: summary 不能为空")
        if _contains_advice(summary.summary):
            raise ValueError(f"{summary.ticker}: 摘要包含交易建议词")
        for observation in summary.observations:
            if _contains_advice(observation.text):
                raise ValueError(f"{summary.ticker}: observation 包含交易建议词")
            for evidence in observation.evidence:
                if (evidence.period, evidence.metric) not in evidence_lookup[summary.ticker]:
                    raise ValueError(
                        f"{summary.ticker}: evidence 不存在 "
                        f"{evidence.period}/{evidence.metric}"
                    )


def _ticker_payload(ticker: TickerBrief) -> dict[str, Any]:
    periods = sorted({point.period for point in ticker.metrics})
    quarters = []
    for period in periods:
        metrics = {
            point.metric: {
                "value": point.value,
                "unit": point.unit,
            }
            for point in ticker.metrics
            if point.period == period
        }
        quarters.append(
            {
                "period": period,
                "data_date": next(
                    point.data_date.isoformat()
                    for point in ticker.metrics
                    if point.period == period
                ),
                "metrics": metrics,
            }
        )
    return {
        "ticker": ticker.ticker,
        "company_name": ticker.company_name,
        "quarters": quarters,
    }


def _contains_advice(text: str) -> bool:
    return bool(contains_advice_terms(text))
