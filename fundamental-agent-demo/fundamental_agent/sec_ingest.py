"""把 SEC companyfacts 写入本地季度缓存。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .models import CacheFile
from .sec_client import SecEdgarClient
from .sec_parser import parse_companyfacts


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取 SEC companyfacts 并写入本地四季度缓存。"
    )
    parser.add_argument(
        "--tickers",
        nargs=3,
        default=["AAPL", "MSFT", "NVDA"],
        metavar=("TICKER1", "TICKER2", "TICKER3"),
        help="必须正好提供三只美股代码。",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        help="point-in-time 截止日期，格式为 YYYY-MM-DD。",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"输出缓存路径。默认值：{DEFAULT_OUT}",
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_USER_AGENT", ""),
        help=(
            "SEC 要求的可识别 User-Agent，也可以通过 "
            "SEC_USER_AGENT 环境变量设置。"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.user_agent.strip():
        raise SystemExit(
            "必须提供 SEC_USER_AGENT。示例："
            "fundamental-agent-demo/0.1 research contact@example.com"
        )

    tickers = [ticker.strip().upper() for ticker in args.tickers]
    client = SecEdgarClient(user_agent=args.user_agent)
    ticker_map = client.ticker_map()
    missing = [ticker for ticker in tickers if ticker not in ticker_map]
    if missing:
        raise SystemExit(f"以下代码未出现在 SEC 映射中：{missing}")

    companies = {}
    for ticker in tickers:
        sec_ticker = ticker_map[ticker]
        print(f"正在抓取 {ticker} 的 CIK {sec_ticker.cik} ...")
        payload = client.companyfacts(sec_ticker.cik)
        companies[ticker] = parse_companyfacts(
            ticker=ticker,
            cik=sec_ticker.cik,
            companyfacts=payload,
            as_of=args.as_of,
        )

    cache = CacheFile(
        as_of=args.as_of,
        currency="USD",
        source=(
            "SEC EDGAR companyfacts via data.sec.gov; "
            f"point-in-time cutoff {args.as_of.isoformat()}"
        ),
        tickers=companies,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(cache.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"已写入 SEC 缓存：{args.out}")
    for ticker, company in companies.items():
        periods = ", ".join(record.period for record in company.quarters)
        print(f"  {ticker}: {periods}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
