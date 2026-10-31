"""从 Nasdaq 公共历史行情接口生成日线价格缓存。"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import load_environment
from .risk_models import PriceBar, PriceCache


load_environment()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "data" / "cache" / "prices_daily.json"
NASDAQ_URL = (
    "https://api.nasdaq.com/api/quote/{ticker}/historical"
    "?assetclass=stocks&fromdate={start}&todate={end}&limit=500"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取日线历史行情并写入本地缓存。")
    parser.add_argument(
        "--tickers",
        nargs=3,
        default=["AAPL", "MSFT", "NVDA"],
        metavar=("TICKER1", "TICKER2", "TICKER3"),
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=365,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
    )
    return parser.parse_args()


def fetch_price_payload(ticker: str, start: date, end: date) -> dict[str, Any]:
    url = NASDAQ_URL.format(
        ticker=ticker.upper(),
        start=start.isoformat(),
        end=end.isoformat(),
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nasdaq.com",
            "Referer": "https://www.nasdaq.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_nasdaq_payload(
    *,
    ticker: str,
    payload: dict[str, Any],
    as_of: date,
    source_url: str,
) -> list[PriceBar]:
    table = payload.get("data", {}).get("tradesTable", {})
    rows = table.get("rows") if isinstance(table, dict) else []
    if not isinstance(rows, list):
        return []

    bars: list[PriceBar] = []
    for row in rows:
        try:
            bar_date = datetime.strptime(row["date"], "%m/%d/%Y").date()
        except (KeyError, ValueError):
            continue
        if bar_date > as_of:
            continue
        bars.append(
            PriceBar(
                ticker=ticker.upper(),
                date=bar_date,
                open=_money(row["open"]),
                high=_money(row["high"]),
                low=_money(row["low"]),
                close=_money(row["close"]),
                volume=_volume(row["volume"]),
                source="Nasdaq public historical quote API (demo source)",
                source_url=source_url,
            )
        )
    return sorted(bars, key=lambda bar: bar.date)


def main() -> int:
    args = parse_args()
    if args.lookback_days <= 0:
        raise SystemExit("--lookback-days 必须大于 0")
    start = args.as_of - timedelta(days=args.lookback_days)
    tickers = [ticker.upper() for ticker in args.tickers]
    cache_tickers: dict[str, list[PriceBar]] = {}

    for ticker in tickers:
        url = NASDAQ_URL.format(
            ticker=ticker,
            start=start.isoformat(),
            end=args.as_of.isoformat(),
        )
        print(f"正在抓取 {ticker} 日线行情...")
        payload = fetch_price_payload(ticker, start, args.as_of)
        bars = parse_nasdaq_payload(
            ticker=ticker,
            payload=payload,
            as_of=args.as_of,
            source_url=url,
        )
        if len(bars) < 30:
            raise SystemExit(f"{ticker}: 有效日线数据不足 30 条")
        cache_tickers[ticker] = bars
        print(f"  {ticker}: {len(bars)} 条日线")

    cache = PriceCache(
        as_of=args.as_of,
        source="Nasdaq public historical quote API (demo source)",
        tickers=cache_tickers,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(cache.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"已写入价格缓存：{args.out}")
    return 0


def _money(value: Any) -> float:
    return float(str(value).replace("$", "").replace(",", "").strip())


def _volume(value: Any) -> int:
    return int(str(value).replace(",", "").strip())


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
