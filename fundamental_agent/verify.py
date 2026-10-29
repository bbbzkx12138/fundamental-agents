"""用于缓存数据和计算指标的独立校验检查。"""

from __future__ import annotations

import re
from collections import defaultdict

from .metrics import debt_to_asset_pct, free_cash_flow_usd, gross_margin_pct
from .models import MetricPoint, QuarterRecord, TickerBrief


REQUIRED_METRICS = {
    "revenue",
    "revenue_growth_qoq",
    "net_income",
    "net_income_growth_qoq",
    "gross_margin",
    "free_cash_flow",
    "debt_to_asset_ratio",
}

ADVICE_PATTERNS = (
    (re.compile(r"\b(?:buy|sell|hold)\b", re.IGNORECASE), "建议方向词"),
    (re.compile(r"\b(?:overweight|underweight)\b", re.IGNORECASE), "评级词"),
    (re.compile(r"\btarget\s+price\b", re.IGNORECASE), "目标价"),
    (re.compile(r"\brecommend(?:ation|ed)?\b", re.IGNORECASE), "推荐词"),
    (re.compile(r"买入|卖出|持有|目标价|建仓|清仓"), "中文交易建议词"),
)


def verify_quarter_record(ticker: str, record: QuarterRecord) -> list[str]:
    notes: list[str] = []
    if record.revenue <= 0:
        raise ValueError(f"{ticker} {record.period}: revenue must be positive")
    if record.gross_profit < 0:
        raise ValueError(f"{ticker} {record.period}: gross profit must be non-negative")
    if record.gross_profit > record.revenue:
        raise ValueError(f"{ticker} {record.period}: gross profit exceeds revenue")
    if record.capital_expenditure < 0:
        raise ValueError(f"{ticker} {record.period}: capex must be non-negative")
    if record.total_assets <= 0:
        raise ValueError(f"{ticker} {record.period}: total assets must be positive")
    if record.total_liabilities < 0:
        raise ValueError(f"{ticker} {record.period}: total liabilities must be non-negative")
    if not record.source.strip():
        raise ValueError(f"{ticker} {record.period}: source is required")
    provenance = (
        record.source_url,
        record.accession_number,
        record.form_type,
        record.filed_date,
    )
    if any(provenance):
        if not all(provenance):
            raise ValueError(
                f"{ticker} {record.period}: incomplete SEC provenance metadata"
            )
        if record.filed_date and record.filed_date < record.period_end_date:
            raise ValueError(
                f"{ticker} {record.period}: filed_date predates period_end_date"
            )
    notes.append(f"{ticker} {record.period}: record and source validated")
    return notes


def verify_metric_points(ticker: str, points: list[MetricPoint]) -> list[str]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for point in points:
        grouped[point.period].add(point.metric)
        if point.source.strip() == "":
            raise ValueError(f"{ticker} {point.period} {point.metric}: source is required")

    for period, metrics in grouped.items():
        missing = REQUIRED_METRICS - metrics
        if missing:
            raise ValueError(f"{ticker} {period}: missing metrics: {sorted(missing)}")

    return [f"{ticker}: {len(grouped)} periods, {len(points)} metric points verified"]


def verify_ticker_brief(brief: TickerBrief) -> list[str]:
    notes: list[str] = []
    for record in brief.quarters:
        notes.extend(verify_quarter_record(brief.ticker, record))
    notes.extend(verify_metric_points(brief.ticker, brief.metrics))

    point_lookup = {(point.period, point.metric): point for point in brief.metrics}
    for record in brief.quarters:
        expected = {
            "gross_margin": gross_margin_pct(record),
            "free_cash_flow": free_cash_flow_usd(record),
            "debt_to_asset_ratio": debt_to_asset_pct(record),
        }
        for metric, value in expected.items():
            actual = point_lookup[(record.period, metric)].value
            if actual != value:
                raise ValueError(
                    f"{brief.ticker} {record.period} {metric}: "
                    f"expected {value}, got {actual}"
                )

    return notes


def verify_no_trading_advice(markdown: str) -> None:
    body = markdown.split("## 免责声明", maxsplit=1)[0].lower()
    found = contains_advice_terms(body)
    if found:
        raise ValueError(f"possible trading advice terms found: {found}")


def contains_advice_terms(text: str) -> list[str]:
    """返回匹配到的交易建议规则标签，避免 shareholder 等词误报。"""

    return [
        label
        for pattern, label in ADVICE_PATTERNS
        if pattern.search(text)
    ]
