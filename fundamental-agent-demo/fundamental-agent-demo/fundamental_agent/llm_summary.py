"""构建 LLM 输入、调用 Provider 并校验摘要结果。"""

from __future__ import annotations

from typing import Any

from .llm_provider import SummaryProvider, TemplateSummaryProvider
from .models import (
    FundamentalBrief,
    SummaryBatch,
    TickerBrief,
)
from .verify import FORBIDDEN_ADVICE_TERMS


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
) -> tuple[FundamentalBrief, list[str], str, str | None]:
    """调用 Provider 并返回更新后的报告、校验记录、来源和模型名。"""

    payload = build_summary_payload(brief)
    notes: list[str] = []

    try:
        batch = provider.summarize(payload)
        validate_summary_batch(batch, brief)
        summary_source = provider.name
        model = provider.model
        notes.append(f"摘要来源：{summary_source}。")
    except Exception as exc:
        batch = TemplateSummaryProvider().summarize(payload)
        validate_summary_batch(batch, brief)
        summary_source = "template"
        model = None
        notes.append(
            "LLM 摘要调用失败，已回退到确定性模板："
            f"{type(exc).__name__}: {str(exc)[:240]}"
        )

    updated = brief.model_copy(
        update={
            "summaries": batch.summaries,
            "summary_source": summary_source,
            "llm_model": model,
            "verification_notes": brief.verification_notes + notes,
        }
    )
    return updated, notes, summary_source, model


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
    lowered = text.lower()
    return any(term in lowered for term in FORBIDDEN_ADVICE_TERMS)
