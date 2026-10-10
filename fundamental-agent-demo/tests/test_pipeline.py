from __future__ import annotations

import unittest
from pathlib import Path

from fundamental_agent.pipeline import build_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.json"


class PipelineTest(unittest.TestCase):
    def test_pipeline_generates_three_ticker_brief(self) -> None:
        graph = build_graph(CACHE_PATH, ["AAPL", "MSFT", "NVDA"])
        state = graph.run({})

        self.assertEqual(len(state["brief"].tickers), 3)
        self.assertEqual(
            [ticker.ticker for ticker in state["brief"].tickers],
            ["AAPL", "MSFT", "NVDA"],
        )
        self.assertEqual(len(state["brief"].tickers[0].quarters), 4)
        self.assertEqual(len(state["brief"].tickers[0].metrics), 28)

        markdown = state["markdown"]
        self.assertIn("营收 (USD bn)", markdown)
        self.assertIn("净利润 (USD bn)", markdown)
        self.assertIn("毛利率", markdown)
        self.assertIn("自由现金流 (USD bn)", markdown)
        self.assertIn("资产负债率", markdown)
        self.assertIn("不构成投资建议", markdown)
        self.assertIn("不连接交易系统", markdown)


if __name__ == "__main__":
    unittest.main()
