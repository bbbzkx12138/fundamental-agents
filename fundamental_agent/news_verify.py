"""NewsEvent 的确定性校验。"""

from __future__ import annotations

from datetime import date

from .models import NewsEvent


def verify_news_events(
    events: list[NewsEvent],
    *,
    tickers: list[str],
    as_of: date,
) -> list[str]:
    """校验新闻事件并返回可写入 Trace/报告的说明。"""

    wanted = {ticker.upper() for ticker in tickers}
    seen: set[str] = set()
    notes: list[str] = []

    for event in events:
        if event.event_id in seen:
            raise ValueError(f"重复 event_id：{event.event_id}")
        seen.add(event.event_id)
        if event.ticker not in wanted:
            raise ValueError(f"{event.event_id}: ticker 不在请求范围内")
        if event.form_type not in {"8-K", "8-K/A"}:
            raise ValueError(f"{event.event_id}: 不支持的 form_type")
        if not event.source_url.startswith("https://www.sec.gov/"):
            raise ValueError(f"{event.event_id}: source_url 不是 SEC URL")
        if not event.accession_number:
            raise ValueError(f"{event.event_id}: 缺少 accession_number")
        if event.filed_date > as_of:
            raise ValueError(f"{event.event_id}: filed_date 晚于 as_of")
        if event.published_at.date() > as_of:
            raise ValueError(f"{event.event_id}: published_at 晚于 as_of")

    for ticker in sorted(wanted):
        count = sum(1 for event in events if event.ticker == ticker)
        notes.append(f"{ticker}: 通过校验的 8-K 事件 {count} 条")
    return notes
