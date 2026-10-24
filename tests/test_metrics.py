from __future__ import annotations

import unittest
from datetime import date

from fundamental_agent.metrics import (
    debt_to_asset_pct,
    free_cash_flow_usd,
    gross_margin_pct,
    qoq_growth,
)
from fundamental_agent.models import QuarterRecord


class MetricsTest(unittest.TestCase):
    def test_qoq_growth(self) -> None:
        self.assertEqual(qoq_growth(110.0, 100.0), 10.0)
        self.assertIsNone(qoq_growth(110.0, None))
        self.assertIsNone(qoq_growth(110.0, 0.0))

    def test_ratio_metrics(self) -> None:
        record = QuarterRecord(
            period="2026-Q3",
            period_end_date=date(2026, 9, 30),
            data_date=date(2026, 10, 5),
            revenue=100.0,
            gross_profit=40.0,
            net_income=10.0,
            operating_cash_flow=30.0,
            capital_expenditure=5.0,
            total_assets=200.0,
            total_liabilities=100.0,
            source="unit-test",
        )

        self.assertEqual(gross_margin_pct(record), 40.0)
        self.assertEqual(free_cash_flow_usd(record), 25.0)
        self.assertEqual(debt_to_asset_pct(record), 50.0)


if __name__ == "__main__":
    unittest.main()
