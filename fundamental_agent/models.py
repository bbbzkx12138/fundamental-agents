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
    source_url: str | None = None
    accession_number: str | None = None
    form_type: str | None = None
    filed_date: date | None = None
    frame: str | None = None

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


class SummaryEvidence(BaseModel):
    """LLM 摘要引用的单条指标证据。"""

    period: str
    metric: str


class SummaryObservation(BaseModel):
    """LLM 摘要中的一个可追溯观察。"""

    text: str
    evidence: list[SummaryEvidence] = Field(min_length=1)


class TickerLLMSummary(BaseModel):
    """单只股票的结构化摘要结果。"""

    ticker: str
    summary: str
    observations: list[SummaryObservation] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class SummaryBatch(BaseModel):
    """LLM Provider 的统一返回结构。"""

    summaries: list[TickerLLMSummary]


class FundamentalBrief(BaseModel):
    """顶层结构化输出。"""

    generated_at: str
    data_as_of: date
    cache_source: str
    tickers: list[TickerBrief]
    verification_notes: list[str]
    disclaimer: str
    summaries: list[TickerLLMSummary] = Field(default_factory=list)
    summary_source: str | None = None
    llm_model: str | None = None
