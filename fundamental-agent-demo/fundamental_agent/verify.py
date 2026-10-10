"""用于缓存数据和计算指标的独立校验检查。"""

from __future__ import annotations

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

FORBIDDEN_ADVICE_TERMS = {
    "buy",
    "sell",
    "hold",
    "target price",
    "recommend",
    "overweight",
    "underweight",
    "买入",
    "卖出",
    "持有",
    "目标价",
    "建仓",
    "清仓",
}


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
    found = sorted(term for term in FORBIDDEN_ADVICE_TERMS if term in body)
    if found:
        raise ValueError(f"possible trading advice terms found: {found}")
