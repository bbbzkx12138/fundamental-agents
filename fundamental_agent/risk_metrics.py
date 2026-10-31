"""确定性风险指标计算。"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .risk_models import (
    PortfolioSnapshot,
    PriceCache,
    RiskSnapshot,
    TickerRiskMetrics,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "data" / "cache" / "risk_snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="计算确定性的组合风险指标。")
    parser.add_argument(
        "--prices",
        type=Path,
        default=PROJECT_ROOT / "data" / "cache" / "prices_daily.json",
    )
    parser.add_argument(
        "--portfolio",
        type=Path,
        default=PROJECT_ROOT / "data" / "portfolio.example.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
    )
    return parser.parse_args()


def calculate_risk_snapshot(
    prices: PriceCache,
    portfolio: PortfolioSnapshot,
) -> RiskSnapshot:
    """使用共同交易日计算资产和组合风险。"""

    tickers = [position.ticker for position in portfolio.positions]
    missing = [ticker for ticker in tickers if ticker not in prices.tickers]
    if missing:
        raise ValueError(f"价格缓存缺少 tickers：{missing}")

    close_by_ticker = {
        ticker: {
            bar.date: bar.close
            for bar in prices.tickers[ticker]
            if bar.date <= prices.as_of
        }
        for ticker in tickers
    }
    common_dates = sorted(
        set.intersection(*(set(values) for values in close_by_ticker.values()))
    )
    if len(common_dates) < 30:
        raise ValueError(f"共同交易日不足 30 天，实际 {len(common_dates)} 天")

    returns_by_ticker: dict[str, list[float]] = {}
    positions: list[TickerRiskMetrics] = []
    for position in portfolio.positions:
        closes = [close_by_ticker[position.ticker][day] for day in common_dates]
        returns = [
            closes[index] / closes[index - 1] - 1.0
            for index in range(1, len(closes))
            if closes[index - 1] != 0
        ]
        returns_by_ticker[position.ticker] = returns
        positions.append(
            TickerRiskMetrics(
                ticker=position.ticker,
                weight=position.weight,
                annualized_volatility=round(_annualized_volatility(returns), 6),
                cumulative_return=round(_cumulative_return(closes), 6),
                max_drawdown=round(_max_drawdown(closes), 6),
                historical_var_95=round(_historical_var_95(returns), 6),
            )
        )

    portfolio_returns = [
        sum(
            position.weight * returns_by_ticker[position.ticker][index]
            for position in portfolio.positions
        )
        for index in range(len(common_dates) - 1)
    ]
    portfolio_closes = [1.0]
    for value in portfolio_returns:
        portfolio_closes.append(portfolio_closes[-1] * (1.0 + value))

    correlations = {
        ticker: {
            other: round(_correlation(returns_by_ticker[ticker], returns_by_ticker[other]), 6)
            for other in tickers
        }
        for ticker in tickers
    }

    return RiskSnapshot(
        as_of=prices.as_of,
        lookback_days=(common_dates[-1] - common_dates[0]).days,
        observation_count=len(common_dates),
        portfolio_annualized_volatility=round(
            _annualized_volatility(portfolio_returns),
            6,
        ),
        portfolio_cumulative_return=round(
            _cumulative_return(portfolio_closes),
            6,
        ),
        portfolio_max_drawdown=round(_max_drawdown(portfolio_closes), 6),
        portfolio_historical_var_95=round(
            _historical_var_95(portfolio_returns),
            6,
        ),
        concentration_hhi=round(
            sum(position.weight ** 2 for position in portfolio.positions),
            6,
        ),
        correlations=correlations,
        positions=positions,
        data_source=prices.source,
    )


def main() -> int:
    args = parse_args()
    prices = PriceCache.model_validate_json(
        args.prices.read_text(encoding="utf-8")
    )
    portfolio = PortfolioSnapshot.model_validate_json(
        args.portfolio.read_text(encoding="utf-8")
    )
    snapshot = calculate_risk_snapshot(prices, portfolio)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"已写入风险快照：{args.out}")
    print(
        json.dumps(
            {
                "as_of": snapshot.as_of.isoformat(),
                "portfolio_annualized_volatility": snapshot.portfolio_annualized_volatility,
                "portfolio_max_drawdown": snapshot.portfolio_max_drawdown,
                "portfolio_historical_var_95": snapshot.portfolio_historical_var_95,
                "concentration_hhi": snapshot.concentration_hhi,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _annualized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        raise ValueError("returns require at least two observations")
    return statistics.pstdev(returns) * math.sqrt(252)


def _cumulative_return(values: list[float]) -> float:
    if not values:
        return 0.0
    return values[-1] / values[0] - 1.0


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = value / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def _historical_var_95(returns: list[float]) -> float:
    if not returns:
        return 0.0
    ordered = sorted(returns)
    index = max(0, int(len(ordered) * 0.05) - 1)
    return max(0.0, -ordered[index])


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(right) < 2:
        return 0.0
    try:
        return statistics.correlation(left, right)
    except statistics.StatisticsError:
        return 0.0


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
