"""确定性指标计算。"""

from __future__ import annotations

from datetime import date

from .models import MetricPoint, QuarterRecord


def qoq_growth(current: float, previous: float | None) -> float | None:
    """环比增长，以百分比表示。"""

    if previous is None:
        return None
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100.0, 2)


def gross_margin_pct(record: QuarterRecord) -> float:
    if record.revenue == 0:
        raise ValueError(f"{record.period} revenue is zero")
    return round(record.gross_profit / record.revenue * 100.0, 2)


def free_cash_flow_usd(record: QuarterRecord) -> float:
    return round(record.operating_cash_flow - record.capital_expenditure, 2)


def debt_to_asset_pct(record: QuarterRecord) -> float:
    if record.total_assets == 0:
        raise ValueError(f"{record.period} total assets are zero")
    return round(record.total_liabilities / record.total_assets * 100.0, 2)


def build_metric_points(ticker: str, records: list[QuarterRecord]) -> list[MetricPoint]:
    """为每个季度、每个必需指标构建一个指标点。"""

    ordered = sorted(records, key=lambda item: item.period_end_date)
    points: list[MetricPoint] = []

    for index, record in enumerate(ordered):
        previous = ordered[index - 1] if index > 0 else None
        points.extend(
            [
                _point(
                    ticker,
                    "revenue",
                    record.revenue,
                    "USD",
                    record,
                ),
                _point(
                    ticker,
                    "revenue_growth_qoq",
                    qoq_growth(record.revenue, previous.revenue if previous else None),
                    "percent",
                    record,
                    note="First quarter has no prior quarter in the local cache."
                    if previous is None
                    else None,
                ),
                _point(
                    ticker,
                    "net_income",
                    record.net_income,
                    "USD",
                    record,
                ),
                _point(
                    ticker,
                    "net_income_growth_qoq",
                    qoq_growth(record.net_income, previous.net_income if previous else None),
                    "percent",
                    record,
                    note="First quarter has no prior quarter in the local cache."
                    if previous is None
                    else None,
                ),
                _point(
                    ticker,
                    "gross_margin",
                    gross_margin_pct(record),
                    "percent",
                    record,
                ),
                _point(
                    ticker,
                    "free_cash_flow",
                    free_cash_flow_usd(record),
                    "USD",
                    record,
                ),
                _point(
                    ticker,
                    "debt_to_asset_ratio",
                    debt_to_asset_pct(record),
                    "percent",
                    record,
                ),
            ]
        )

    return points


def _point(
    ticker: str,
    metric: str,
    value: float | None,
    unit: str,
    record: QuarterRecord,
    note: str | None = None,
) -> MetricPoint:
    return MetricPoint(
        ticker=ticker,
        metric=metric,
        value=value,
        unit=unit,
        source=record.source,
        period=record.period,
        data_date=record.data_date,
        note=note,
    )
