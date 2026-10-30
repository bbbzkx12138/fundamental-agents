"""News LLM Provider。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from .llm_provider import OpenAICompatibleProvider
from .models import (
    NewsExplanationBatch,
    NewsInsight,
    TickerNewsExplanation,
)


@dataclass(frozen=True)
class NewsExplanationResult:
    """新闻解释 Provider 的统一返回。"""

    batch: NewsExplanationBatch
    provider: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_source: str = "none"


class NewsExplanationProvider(Protocol):
    name: str
    model: str | None
    max_tokens: int

    def explain(self, payload: dict[str, Any]) -> NewsExplanationResult:
        ...


class TemplateNewsExplanationProvider:
    """确定性新闻解释，作为无 Key 或 API 失败时的降级。"""

    name = "deterministic_news"
    model = None
    max_tokens = 0

    def explain(self, payload: dict[str, Any]) -> NewsExplanationResult:
        explanations = [
            self._explain_ticker(ticker)
            for ticker in payload.get("tickers", [])
        ]
        return NewsExplanationResult(
            batch=NewsExplanationBatch(explanations=explanations),
            provider=self.name,
            model=self.model,
            input_tokens=0,
            output_tokens=0,
        )

    def _explain_ticker(self, ticker: dict[str, Any]) -> TickerNewsExplanation:
        events = ticker.get("events", [])
        deterministic_summary = ticker.get("deterministic_summary") or (
            f"{ticker['ticker']} 暂无可用的近期事件摘要。"
        )
        insights = [
            NewsInsight(
                text=(
                    f"{event['filed_date']} 提交的 {event['form_type']} "
                    f"事件类型为 {event['event_type']}。"
                ),
                event_ids=[event["event_id"]],
            )
            for event in events[:2]
        ]
        return TickerNewsExplanation(
            ticker=ticker["ticker"],
            summary=deterministic_summary,
            insights=insights,
            uncertainties=[
                "当前解释只基于 SEC 8-K，不包含媒体新闻或市场传闻。",
                "事件解释不构成对公司未来业绩的预测。",
            ],
        )


class OpenAINewsExplanationProvider:
    """通过 OpenAI-compatible 接口解释已验证的 NewsEvent。"""

    name = "openai-compatible-news"

    def __init__(
        self,
        provider: OpenAICompatibleProvider,
        max_tokens: int = 2000,
    ) -> None:
        self.provider = provider
        self.model = provider.model
        self.max_tokens = max_tokens

    def explain(self, payload: dict[str, Any]) -> NewsExplanationResult:
        system_prompt = (
            "你是金融事件解释助手。只能使用用户提供的已验证 NewsEvent。"
            "不要输出买入、卖出、持有、目标价或收益保证。"
            "不要预测股价或未来业绩。"
            "每只股票输出 1 条 summary、1 到 2 条 insights 和 1 到 2 条 uncertainties。"
            "每条 insight 必须引用输入中存在的一个或多个 event_id。"
            "输出必须是严格 JSON，不要 Markdown，不要代码块。"
            '结构：{"explanations":[{"ticker":"AAPL","summary":"...",'
            '"insights":[{"text":"...","event_ids":["sec-8k-..."]}],'
            '"uncertainties":["..."]}]}'
        )
        response = self.provider.complete_json(
            system_prompt=system_prompt,
            payload=payload,
            max_tokens=self.max_tokens,
        )
        return NewsExplanationResult(
            batch=NewsExplanationBatch.model_validate_json(response.content),
            provider=self.name,
            model=self.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            usage_source=response.usage_source,
        )


def get_news_provider(mode: str = "auto") -> NewsExplanationProvider:
    """根据模式选择新闻解释 Provider。"""

    mode = mode.lower().strip()
    if mode == "template":
        return TemplateNewsExplanationProvider()

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    if mode == "auto" and not (api_key and model):
        return TemplateNewsExplanationProvider()
    if mode == "api" and not (api_key and model):
        raise ValueError(
            "新闻解释模式为 api，但缺少 LLM_API_KEY/OPENAI_API_KEY 或 LLM_MODEL"
        )
    if mode not in {"auto", "api"}:
        raise ValueError(f"不支持的新闻 LLM 模式：{mode}")

    max_tokens = int(os.getenv("NEWS_LLM_MAX_TOKENS", "2000"))
    timeout_seconds = int(os.getenv("NEWS_LLM_TIMEOUT_SECONDS", "180"))
    provider = OpenAICompatibleProvider(
        api_key=api_key or "",
        model=model or "",
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )
    return OpenAINewsExplanationProvider(provider, max_tokens=max_tokens)
