from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from fundamental_agent.models import NewsCache
from fundamental_agent.news_ingest import parse_submissions, validate_news_events


class NewsIngestTest(unittest.TestCase):
    def test_parses_recent_8k_and_filters_future_old_and_non_8k(self) -> None:
        payload = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-Q", "8-K", "8-K", "8-K"],
                    "filingDate": [
                        "2026-09-01",
                        "2026-09-02",
                        "2026-11-01",
                        "2025-01-01",
                        "2026-04-20",
                    ],
                    "reportDate": [
                        "2026-09-01",
                        "2026-09-02",
                        "2026-11-01",
                        "2025-01-01",
                        "2026-04-17",
                    ],
                    "acceptanceDateTime": [
                        "2026-09-01T20:30:35.000Z",
                        "2026-09-02T20:30:35.000Z",
                        "2026-11-01T20:30:35.000Z",
                        "2025-01-01T20:30:35.000Z",
                        "2026-04-20T21:29:51.000Z",
                    ],
                    "accessionNumber": [
                        "0000320193-26-000018",
                        "0000320193-26-000019",
                        "0000320193-26-000020",
                        "0000320193-25-000001",
                        "0001140361-26-015711",
                    ],
                    "primaryDocument": [
                        "aapl-20260901.htm",
                        "aapl-20260902.htm",
                        "aapl-20261101.htm",
                        "aapl-20250101.htm",
                        "ef20071035_8k.htm",
                    ],
                    "primaryDocDescription": [
                        "8-K",
                        "10-Q",
                        "8-K",
                        "8-K",
                        "8-K",
                    ],
                    "items": [
                        "2.02,9.01",
                        "",
                        "2.02",
                        "2.02",
                        "5.02",
                    ],
                }
            }
        }

        events = parse_submissions(
            ticker="AAPL",
            cik="0000320193",
            company_name="Apple Inc.",
            payload=payload,
            as_of=date(2026, 10, 28),
            lookback_days=200,
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].form_type, "8-K")
        self.assertEqual(events[0].event_type, "earnings")
        self.assertEqual(events[0].items, ["2.02", "9.01"])
        self.assertEqual(events[0].filed_date, date(2026, 9, 1))
        self.assertTrue(events[0].source_url.startswith("https://www.sec.gov/Archives/"))
        self.assertEqual(events[1].event_type, "leadership")

    def test_duplicate_accession_is_deduplicated(self) -> None:
        payload = {
            "filings": {
                "recent": {
                    "form": ["8-K", "8-K"],
                    "filingDate": ["2026-09-01", "2026-09-01"],
                    "reportDate": ["2026-09-01", "2026-09-01"],
                    "acceptanceDateTime": [
                        "2026-09-01T20:30:35.000Z",
                        "2026-09-01T20:30:35.000Z",
                    ],
                    "accessionNumber": [
                        "0000320193-26-000018",
                        "0000320193-26-000018",
                    ],
                    "primaryDocument": ["aapl-20260901.htm", "aapl-20260901.htm"],
                    "primaryDocDescription": ["8-K", "8-K"],
                    "items": ["2.02", "2.02"],
                }
            }
        }
        events = parse_submissions(
            ticker="AAPL",
            cik="0000320193",
            company_name="Apple Inc.",
            payload=payload,
            as_of=date(2026, 10, 28),
            lookback_days=180,
        )
        self.assertEqual(len(events), 1)

    def test_real_news_cache_is_valid(self) -> None:
        cache_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "cache"
            / "news_events.sec.json"
        )
        cache = NewsCache.model_validate_json(cache_path.read_text(encoding="utf-8"))
        self.assertGreater(len(cache.events), 0)
        self.assertEqual(validate_news_events(cache.events, cache.as_of), [])


if __name__ == "__main__":
    unittest.main()
