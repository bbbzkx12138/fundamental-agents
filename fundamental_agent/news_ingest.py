"""抓取 SEC 8-K/8-K/A 并写入 NewsEvent 本地缓存。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import load_environment
from .models import NewsCache, NewsEvent
from .sec_client import SecEdgarClient


load_environment()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "data" / "cache" / "news_events.sec.json"


ITEM_LABELS = {
    "1.01": "material_agreement",
    "2.02": "earnings",
    "5.02": "leadership",
    "5.03": "bylaw_amendment",
    "5.07": "shareholder_vote",
    "7.01": "regulation_fd",
    "8.01": "other_event",
    "9.01": "financial_exhibits",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取 SEC 8-K/8-K/A 并生成 NewsEvent 本地缓存。"
    )
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
        help="point-in-time 截止日期，格式 YYYY-MM-DD。",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=180,
        help="只保留截止日期之前最近多少天的事件。",
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
        help="SEC 要求的可识别 User-Agent，也可通过 SEC_USER_AGENT 设置。",
    )
    return parser.parse_args()


def parse_submissions(
    *,
    ticker: str,
    cik: str,
    company_name: str,
    payload: dict[str, Any],
    as_of: date,
    lookback_days: int,
) -> list[NewsEvent]:
    """把 SEC submissions 的最近 filings 转换为结构化 NewsEvent。"""

    recent = payload.get("filings", {}).get("recent")
    if not isinstance(recent, dict):
        return []

    forms = recent.get("form", [])
    if not isinstance(forms, list):
        return []

    lower_bound = as_of - timedelta(days=lookback_days)
    events: list[NewsEvent] = []
    seen_accessions: set[str] = set()

    for index, form in enumerate(forms):
        if form not in {"8-K", "8-K/A"}:
            continue
        accession = _row_value(recent, "accessionNumber", index)
        filing_date_raw = _row_value(recent, "filingDate", index)
        if not accession or not filing_date_raw or accession in seen_accessions:
            continue

        filed_date = date.fromisoformat(filing_date_raw)
        if filed_date > as_of or filed_date < lower_bound:
            continue

        items = [
            item.strip()
            for item in str(_row_value(recent, "items", index) or "").split(",")
            if item.strip()
        ]
        published_at = _parse_acceptance_datetime(
            _row_value(recent, "acceptanceDateTime", index),
            fallback=filed_date,
        )
        report_date = _optional_date(_row_value(recent, "reportDate", index))
        primary_document = _row_value(recent, "primaryDocument", index)
        event_type = _event_type(form, items)
        seen_accessions.add(accession)
        events.append(
            NewsEvent(
                event_id=f"sec-8k-{accession}",
                ticker=ticker,
                company_name=company_name,
                event_type=event_type,
                headline=_headline(company_name, form, items),
                source="SEC EDGAR submissions (8-K/8-K/A)",
                source_url=_filing_url(cik, accession, primary_document),
                accession_number=accession,
                form_type=form,
                published_at=published_at,
                filed_date=filed_date,
                report_date=report_date,
                items=items,
                primary_document=primary_document,
            )
        )

    return sorted(events, key=lambda event: event.published_at, reverse=True)


def main() -> int:
    args = parse_args()
    if not args.user_agent.strip():
        raise SystemExit("必须提供 SEC_USER_AGENT 或 --user-agent")

    tickers = [ticker.strip().upper() for ticker in args.tickers]
    client = SecEdgarClient(user_agent=args.user_agent)
    ticker_map = client.ticker_map()
    missing = [ticker for ticker in tickers if ticker not in ticker_map]
    if missing:
        raise SystemExit(f"以下代码未出现在 SEC 映射中：{missing}")

    all_events: list[NewsEvent] = []
    for ticker in tickers:
        sec_ticker = ticker_map[ticker]
        print(f"正在抓取 {ticker} CIK {sec_ticker.cik} 的 8-K ...")
        payload = client.submissions(sec_ticker.cik)
        events = parse_submissions(
            ticker=ticker,
            cik=sec_ticker.cik,
            company_name=sec_ticker.title,
            payload=payload,
            as_of=args.as_of,
            lookback_days=args.lookback_days,
        )
        print(f"  {ticker}: {len(events)} 条事件")
        all_events.extend(events)

    all_events = list(
        {
            event.event_id: event
            for event in sorted(
                all_events,
                key=lambda event: event.published_at,
                reverse=True,
            )
        }.values()
    )
    validation_errors = validate_news_events(all_events, args.as_of)
    if validation_errors:
        raise SystemExit("新闻缓存校验失败：\n- " + "\n- ".join(validation_errors))
    cache = NewsCache(
        as_of=args.as_of,
        source=(
            "SEC EDGAR submissions (8-K/8-K/A); "
            f"point-in-time cutoff {args.as_of.isoformat()}"
        ),
        events=all_events,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(cache.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"已写入新闻缓存：{args.out}")
    print(f"事件总数：{len(all_events)}")
    return 0


def validate_news_events(events: list[NewsEvent], as_of: date) -> list[str]:
    """校验 NewsEvent 的时间、来源、URL 和唯一性。"""

    errors: list[str] = []
    seen: set[str] = set()
    for event in events:
        if event.event_id in seen:
            errors.append(f"重复 event_id：{event.event_id}")
        seen.add(event.event_id)
        if event.filed_date > as_of:
            errors.append(f"{event.event_id}: filed_date 晚于 as_of")
        if event.published_at.date() > as_of:
            errors.append(f"{event.event_id}: published_at 晚于 as_of")
        if not event.source_url.startswith("https://www.sec.gov/"):
            errors.append(f"{event.event_id}: source_url 不是 SEC URL")
        if not event.accession_number:
            errors.append(f"{event.event_id}: 缺少 accession_number")
        if not event.ticker:
            errors.append(f"{event.event_id}: 缺少 ticker")
    return errors


def _row_value(recent: dict[str, Any], key: str, index: int) -> Any:
    values = recent.get(key, [])
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _parse_acceptance_datetime(value: Any, *, fallback: date) -> datetime:
    if value:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return datetime.combine(fallback, time.min, tzinfo=timezone.utc)


def _optional_date(value: Any) -> date | None:
    return date.fromisoformat(str(value)) if value else None


def _event_type(form: str, items: list[str]) -> str:
    if form == "8-K/A":
        return "amendment"
    for item in items:
        if item in ITEM_LABELS:
            return ITEM_LABELS[item]
    return "material_event"


def _headline(company_name: str, form: str, items: list[str]) -> str:
    item_text = ", ".join(items) if items else "no item codes"
    return f"{company_name} files {form} ({item_text})"


def _filing_url(cik: str, accession: str, primary_document: str | None) -> str:
    cik_path = str(int(cik))
    accession_path = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_path}/{accession_path}"
    if primary_document:
        return f"{base}/{primary_document}"
    return f"{base}/{accession}-index.html"


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
