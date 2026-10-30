"""确定性 Compliance Agent 规则。"""

from __future__ import annotations

import re
from datetime import datetime

from .models import ComplianceDecision, FundamentalBrief
from .verify import contains_advice_terms


RULES_VERSION = "1.0"

GUARANTEE_PATTERNS = (
    re.compile(r"保证收益|稳赚|必涨|必然上涨|一定上涨|无风险收益"),
    re.compile(r"\bguaranteed\s+return\b", re.IGNORECASE),
    re.compile(r"\brisk[- ]free\s+return\b", re.IGNORECASE),
)


def evaluate_compliance(
    brief: FundamentalBrief,
    markdown: str,
) -> ComplianceDecision:
    """检查报告是否满足当前内部合规规则。"""

    violations: list[str] = []
    warnings: list[str] = []
    markdown_body = markdown.split("## 免责声明", maxsplit=1)[0]

    if not brief.disclaimer.strip() or "不构成投资建议" not in markdown:
        violations.append("报告缺少明确的投资建议免责声明")

    if not brief.summaries:
        violations.append("报告缺少结构化摘要")

    narrative = "\n".join(
        [summary.summary for summary in brief.summaries]
        + [
            observation.text
            for summary in brief.summaries
            for observation in summary.observations
        ]
    )
    if contains_advice_terms(markdown_body) or contains_advice_terms(narrative):
        violations.append("报告包含买入、卖出、持有或目标价类表述")

    if _matches_any(GUARANTEE_PATTERNS, markdown_body) or _matches_any(
        GUARANTEE_PATTERNS, narrative
    ):
        violations.append("报告包含收益保证或无风险类表述")

    evidence_lookup = {
        ticker.ticker: {(point.period, point.metric) for point in ticker.metrics}
        for ticker in brief.tickers
    }
    for summary in brief.summaries:
        for observation in summary.observations:
            for evidence in observation.evidence:
                if (evidence.period, evidence.metric) not in evidence_lookup.get(
                    summary.ticker, set()
                ):
                    violations.append(
                        f"{summary.ticker}: evidence 不存在 "
                        f"{evidence.period}/{evidence.metric}"
                    )

    for ticker in brief.tickers:
        for record in ticker.quarters:
            if not (
                record.source
                and record.source_url
                and record.accession_number
                and record.form_type
                and record.filed_date
            ):
                violations.append(
                    f"{ticker.ticker} {record.period}: SEC provenance 不完整"
                )
            if record.filed_date and record.filed_date < record.period_end_date:
                violations.append(
                    f"{ticker.ticker} {record.period}: filed_date 早于 period_end_date"
                )

    if brief.news is not None:
        known_event_ids = {event.event_id for event in brief.news.events}
        for event in brief.news.events:
            if not event.accession_number or not event.source_url.startswith(
                "https://www.sec.gov/"
            ):
                violations.append(f"{event.event_id}: 新闻来源不可追溯")
        for summary in brief.news.summaries:
            for event_id in summary.event_ids:
                if event_id not in known_event_ids:
                    violations.append(
                        f"{summary.ticker}: 新闻摘要引用未知事件 {event_id}"
                    )
        for explanation in brief.news.explanations:
            for insight in explanation.insights:
                for event_id in insight.event_ids:
                    if event_id not in known_event_ids:
                        violations.append(
                            f"{explanation.ticker}: 新闻解释引用未知事件 {event_id}"
                        )
            if explanation.insights and explanation.ticker not in {
                event.ticker for event in brief.news.events
            }:
                violations.append(
                    f"{explanation.ticker}: 新闻解释没有对应事件"
                )

    if brief.summary_source == "template":
        warnings.append("当前摘要来自确定性模板，不是模型生成")
    elif brief.summary_source not in {"template", "openai-compatible"}:
        warnings.append(f"未知摘要来源：{brief.summary_source}")

    return ComplianceDecision(
        passed=not violations,
        violations=violations,
        warnings=warnings,
        rules_version=RULES_VERSION,
        checked_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


def _matches_any(patterns, text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)
