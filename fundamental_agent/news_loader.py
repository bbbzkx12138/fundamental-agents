"""新闻事件缓存加载与筛选。"""

from __future__ import annotations

from pathlib import Path

from .models import NewsCache, NewsEvent


def load_news_cache(path: Path) -> NewsCache:
    if not path.exists():
        raise FileNotFoundError(f"新闻缓存不存在：{path}")
    return NewsCache.model_validate_json(path.read_text(encoding="utf-8"))


def select_news(
    cache: NewsCache,
    tickers: list[str],
) -> list[NewsEvent]:
    """筛选指定 ticker、point-in-time 内的事件并去重。"""

    wanted = {ticker.upper() for ticker in tickers}
    selected = [
        event
        for event in cache.events
        if event.ticker in wanted
        and event.filed_date <= cache.as_of
        and event.published_at.date() <= cache.as_of
    ]
    deduped = {event.event_id: event for event in selected}
    return sorted(
        deduped.values(),
        key=lambda event: event.published_at,
        reverse=True,
    )
