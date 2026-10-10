"""本地缓存基本面简报演示的数据契约。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class QuarterRecord(BaseModel):
    """一个季度的缓存财务报表数据。"""

    period: str
    period_end_date: date
    data_date: date
    currency: str = "USD"
    revenue: float
    gross_profit: float
    net_income: float
    operating_cash_flow: float
    capital_expenditure: float
    total_assets: float
    total_liabilities: float
    source: str

    @field_validator("period", "currency", "source")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value


class CompanyRecords(BaseModel):
    """单个公司的缓存季度记录。"""

    company_name: str
    quarters: list[QuarterRecord] = Field(min_length=4, max_length=4)


class CacheFile(BaseModel):
    """本地缓存 JSON 的根结构。"""

    as_of: date
    currency: str = "USD"
    source: str
    tickers: dict[str, CompanyRecords]


class MetricPoint(BaseModel):
    """带有自身来源、期间和数据日期的计算指标。"""

    ticker: str
    metric: str
    value: float | None
    unit: str
    source: str
    period: str
    data_date: date
    note: str | None = None


class TickerBrief(BaseModel):
    """单个股票代码的计算指标和来源记录。"""

    ticker: str
    company_name: str
    currency: str
    quarters: list[QuarterRecord]
    metrics: list[MetricPoint]


class FundamentalBrief(BaseModel):
    """顶层结构化输出。"""

    generated_at: str
    data_as_of: date
    cache_source: str
    tickers: list[TickerBrief]
    verification_notes: list[str]
    disclaimer: str
