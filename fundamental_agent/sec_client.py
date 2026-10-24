"""用于抓取 SEC EDGAR companyfacts 的小型客户端。"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


@dataclass(frozen=True)
class SecTicker:
    ticker: str
    cik: str
    title: str


class SecEdgarClient:
    """带限速的 SEC JSON 客户端。

    SEC 要求提供可识别的 User-Agent。演示中显式传入，
    不在代码里硬编码个人邮箱地址。
    """

    def __init__(self, user_agent: str, timeout_seconds: int = 60) -> None:
        user_agent = user_agent.strip()
        if not user_agent:
            raise ValueError("SEC user agent is required")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds

    def ticker_map(self) -> dict[str, SecTicker]:
        payload = self._get_json(SEC_TICKERS_URL)
        result: dict[str, SecTicker] = {}
        for item in payload.values():
            ticker = str(item["ticker"]).upper()
            result[ticker] = SecTicker(
                ticker=ticker,
                cik=str(item["cik_str"]).zfill(10),
                title=str(item["title"]),
            )
        return result

    def companyfacts(self, cik: str) -> dict[str, Any]:
        payload = self._get_json(SEC_COMPANYFACTS_URL.format(cik=cik))
        time.sleep(0.2)
        return payload

    def _get_json(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
