"""本地缓存加载和校验辅助工具。"""

from __future__ import annotations

from pathlib import Path

from .models import CacheFile, CompanyRecords


def load_cache(path: Path) -> CacheFile:
    if not path.exists():
        raise FileNotFoundError(f"cache file not found: {path}")
    return CacheFile.model_validate_json(path.read_text(encoding="utf-8"))


def select_tickers(cache: CacheFile, tickers: list[str]) -> dict[str, CompanyRecords]:
    if len(tickers) != 3:
        raise ValueError("exactly three tickers are required for this demo")

    normalized = [ticker.strip().upper() for ticker in tickers]
    missing = [ticker for ticker in normalized if ticker not in cache.tickers]
    if missing:
        raise ValueError(f"tickers missing from cache: {missing}")

    selected = {ticker: cache.tickers[ticker] for ticker in normalized}
    for ticker, company in selected.items():
        if len(company.quarters) != 4:
            raise ValueError(f"{ticker} must have exactly four cached quarters")
        company.quarters.sort(key=lambda item: item.period_end_date)
    return selected
