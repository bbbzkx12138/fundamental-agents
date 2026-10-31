"""Risk Agent 的输入和输出数据契约。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class PriceBar(BaseModel):
    """一只股票的单个日线价格记录。"""

    ticker: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str
    source_url: str

    @field_validator("ticker", "source", "source_url")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field must not be empty")
        return value

    @field_validator("open", "high", "low", "close")
    @classmethod
    def positive_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price must be positive")
        return value


class PriceCache(BaseModel):
    """本地日线价格缓存。"""

    as_of: date
    source: str
    tickers: dict[str, list[PriceBar]]


class PortfolioPosition(BaseModel):
    """组合中的单个持仓权重。"""

    ticker: str
    weight: float = Field(ge=0, le=1)


class PortfolioSnapshot(BaseModel):
    """用于风险计算的组合快照。"""

    as_of: date
    currency: str = "USD"
    positions: list[PortfolioPosition]

    @field_validator("positions")
    @classmethod
    def weights_sum_to_one(cls, positions: list[PortfolioPosition]) -> list[PortfolioPosition]:
        total = sum(position.weight for position in positions)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"portfolio weights must sum to 1, got {total}")
        if len({position.ticker for position in positions}) != len(positions):
            raise ValueError("portfolio contains duplicate tickers")
        return positions


class TickerRiskMetrics(BaseModel):
    """单只资产的确定性风险指标。"""

    ticker: str
    weight: float
    annualized_volatility: float
    cumulative_return: float
    max_drawdown: float
    historical_var_95: float


class RiskSnapshot(BaseModel):
    """风险引擎的结构化输出。"""

    as_of: date
    lookback_days: int
    observation_count: int
    portfolio_annualized_volatility: float
    portfolio_cumulative_return: float
    portfolio_max_drawdown: float
    portfolio_historical_var_95: float
    concentration_hhi: float
    correlations: dict[str, dict[str, float]]
    positions: list[TickerRiskMetrics]
    data_source: str
