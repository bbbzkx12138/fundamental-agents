from __future__ import annotations

import math
import unittest
from datetime import date, timedelta
from pathlib import Path

from fundamental_agent.market_data_ingest import parse_nasdaq_payload
from fundamental_agent.risk_metrics import calculate_risk_snapshot
from fundamental_agent.risk_models import (
    PortfolioPosition,
    PortfolioSnapshot,
    PriceBar,
    PriceCache,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RiskDataTest(unittest.TestCase):
    def test_parse_nasdaq_payload(self) -> None:
        payload = {
            "data": {
                "tradesTable": {
                    "rows": [
                        {
                            "date": "10/28/2026",
                            "open": "$100.00",
                            "high": "$102.00",
                            "low": "$99.00",
                            "close": "$101.50",
                            "volume": "1,234,567",
                        },
                        {
                            "date": "11/01/2026",
                            "open": "$103.00",
                            "high": "$104.00",
                            "low": "$102.00",
                            "close": "$103.50",
                            "volume": "2,000,000",
                        },
                    ]
                }
            }
        }
        bars = parse_nasdaq_payload(
            ticker="AAPL",
            payload=payload,
            as_of=date(2026, 10, 30),
            source_url="https://example.test/aapl",
        )

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].close, 101.5)
        self.assertEqual(bars[0].volume, 1234567)

    def test_calculate_risk_snapshot(self) -> None:
        start = date(2026, 1, 1)
        tickers = ["AAPL", "MSFT", "NVDA"]
        price_cache = PriceCache(
            as_of=date(2026, 3, 31),
            source="unit-test",
            tickers={
                ticker: self._bars(ticker, start, ticker_index)
                for ticker_index, ticker in enumerate(tickers)
            },
        )
        portfolio = PortfolioSnapshot(
            as_of=date(2026, 3, 31),
            positions=[
                PortfolioPosition(ticker="AAPL", weight=0.4),
                PortfolioPosition(ticker="MSFT", weight=0.35),
                PortfolioPosition(ticker="NVDA", weight=0.25),
            ],
        )

        snapshot = calculate_risk_snapshot(price_cache, portfolio)

        self.assertEqual(snapshot.observation_count, 60)
        self.assertEqual(len(snapshot.positions), 3)
        self.assertAlmostEqual(snapshot.concentration_hhi, 0.345, places=6)
        self.assertLessEqual(snapshot.portfolio_max_drawdown, 0)
        self.assertGreaterEqual(snapshot.portfolio_historical_var_95, 0)
        self.assertEqual(snapshot.correlations["AAPL"]["AAPL"], 1.0)

    def test_real_risk_cache_if_present(self) -> None:
        price_path = PROJECT_ROOT / "data" / "cache" / "prices_daily.json"
        portfolio_path = PROJECT_ROOT / "data" / "portfolio.example.json"
        if not price_path.exists() or not portfolio_path.exists():
            self.skipTest("real risk cache not generated yet")
        prices = PriceCache.model_validate_json(
            price_path.read_text(encoding="utf-8")
        )
        portfolio = PortfolioSnapshot.model_validate_json(
            portfolio_path.read_text(encoding="utf-8")
        )
        snapshot = calculate_risk_snapshot(prices, portfolio)
        self.assertEqual(len(snapshot.positions), 3)
        self.assertGreater(snapshot.observation_count, 30)

    @staticmethod
    def _bars(ticker: str, start: date, index: int) -> list[PriceBar]:
        bars: list[PriceBar] = []
        for offset in range(60):
            day = start + timedelta(days=offset)
            base = 100.0 + index * 20.0
            close = base + offset * 0.1 + math.sin(offset / 5.0) * 2.0
            bars.append(
                PriceBar(
                    ticker=ticker,
                    date=day,
                    open=close - 1.0,
                    high=close + 1.0,
                    low=close - 1.5,
                    close=close,
                    volume=1_000_000 + index * 100_000,
                    source="unit-test",
                    source_url="https://example.test",
                )
            )
        return bars


if __name__ == "__main__":
    unittest.main()
