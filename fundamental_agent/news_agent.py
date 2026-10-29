"""确定性 News Agent 第一版。"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .models import NewsBrief, NewsCache, NewsEvent, TickerNewsSummary
from .news_loader import select_news
from .news_verify import verify_news_events


def build_news_brief(
    cache: NewsCache,
    tickers: list[str],
) -> NewsBrief:
    """基于已验证的 SEC 8-K 事件生成结构化近期事件摘要。"""

    events = select_news(cache, tickers)
    notes = verify_news_events(events, tickers=tickers, as_of=cache.as_of)
    summaries = [
        _summarize_ticker(ticker, events)
        for ticker in tickers
    ]
    return NewsBrief(
        as_of=cache.as_of,
        source=cache.source,
        events=events,
        summaries=summaries,
        verification_notes=notes,
    )


def _summarize_ticker(ticker: str, events: Iterable[NewsEvent]) -> TickerNewsSummary:
    ticker_events = [event for event in events if event.ticker == ticker]
    if not ticker_events:
        return TickerNewsSummary(
            ticker=ticker,
            event_count=0,
            summary=f"{ticker} 在缓存窗口内没有可用的 SEC 8-K 重大事件。",
            warnings=["没有近期 SEC 8-K 事件，报告仅依据财务数据。"],
        )

    ticker_events = sorted(
        ticker_events,
        key=lambda event: event.published_at,
        reverse=True,
    )
    latest = ticker_events[0]
    type_counts = Counter(event.event_type for event in ticker_events)
    type_text = "、".join(
        f"{event_type} {count} 条"
        for event_type, count in type_counts.most_common()
    )
    summary = (
        f"{ticker} 最近 180 天内共有 {len(ticker_events)} 条 SEC 8-K 事件，"
        f"类型分布为 {type_text}。最近一条为 {latest.headline}，"
        f"提交日期为 {latest.filed_date.isoformat()}。"
    )
    return TickerNewsSummary(
        ticker=ticker,
        event_count=len(ticker_events),
        summary=summary,
        event_ids=[event.event_id for event in ticker_events],
        warnings=["本摘要只使用 SEC 8-K，不包含通用新闻或市场传言。"],
    )
