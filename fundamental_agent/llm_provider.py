"""LLM 摘要 Provider 抽象和实现。"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .config import load_environment
from .models import SummaryBatch, SummaryEvidence, SummaryObservation, TickerLLMSummary


load_environment()


class SummaryProvider(Protocol):
    """摘要生成器协议。"""

    name: str
    model: str | None

    def summarize(self, payload: dict[str, Any]) -> "SummaryResult":
        ...


@dataclass(frozen=True)
class SummaryResult:
    """Provider 返回的摘要和用量信息。"""

    batch: SummaryBatch
    provider: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_source: str = "none"


class TemplateSummaryProvider:
    """不调用模型的确定性摘要，用于无 Key 或 API 失败时的降级。"""

    name = "template"
    model = None

    def summarize(self, payload: dict[str, Any]) -> SummaryResult:
        summaries = [
            self._summarize_ticker(ticker)
            for ticker in payload.get("tickers", [])
        ]
        return SummaryResult(
            batch=SummaryBatch(summaries=summaries),
            provider=self.name,
            model=self.model,
            input_tokens=0,
            output_tokens=0,
        )

    def _summarize_ticker(self, ticker: dict[str, Any]) -> TickerLLMSummary:
        quarters = ticker.get("quarters", [])
        if not quarters:
            return TickerLLMSummary(
                ticker=ticker["ticker"],
                summary="没有可用于摘要的季度数据。",
                observations=[],
                uncertainties=["缺少季度数据。"],
            )

        latest = quarters[-1]
        period = latest["period"]
        metrics = latest["metrics"]
        revenue = metrics.get("revenue", {}).get("value")
        revenue_growth = metrics.get("revenue_growth_qoq", {}).get("value")
        net_income = metrics.get("net_income", {}).get("value")
        net_income_growth = metrics.get("net_income_growth_qoq", {}).get("value")
        gross_margin = metrics.get("gross_margin", {}).get("value")
        free_cash_flow = metrics.get("free_cash_flow", {}).get("value")
        debt_ratio = metrics.get("debt_to_asset_ratio", {}).get("value")

        summary = (
            f"{ticker['ticker']} 最新季度 {period} 营收为 {_fmt_bn(revenue)}，"
            f"环比 {_fmt_pct(revenue_growth)}；净利润为 {_fmt_bn(net_income)}，"
            f"环比 {_fmt_pct(net_income_growth)}；毛利率为 {_fmt_pct(gross_margin)}，"
            f"自由现金流为 {_fmt_bn(free_cash_flow)}，"
            f"资产负债率为 {_fmt_pct(debt_ratio)}。"
        )
        observations = [
            SummaryObservation(
                text=f"{period} 营收为 {_fmt_bn(revenue)}，环比 {_fmt_pct(revenue_growth)}。",
                evidence=[
                    SummaryEvidence(period=period, metric="revenue"),
                    SummaryEvidence(period=period, metric="revenue_growth_qoq"),
                ],
            ),
            SummaryObservation(
                text=f"{period} 净利润为 {_fmt_bn(net_income)}，环比 {_fmt_pct(net_income_growth)}。",
                evidence=[
                    SummaryEvidence(period=period, metric="net_income"),
                    SummaryEvidence(period=period, metric="net_income_growth_qoq"),
                ],
            ),
            SummaryObservation(
                text=(
                    f"{period} 毛利率为 {_fmt_pct(gross_margin)}，"
                    f"自由现金流为 {_fmt_bn(free_cash_flow)}，"
                    f"资产负债率为 {_fmt_pct(debt_ratio)}。"
                ),
                evidence=[
                    SummaryEvidence(period=period, metric="gross_margin"),
                    SummaryEvidence(period=period, metric="free_cash_flow"),
                    SummaryEvidence(period=period, metric="debt_to_asset_ratio"),
                ],
            ),
        ]
        return TickerLLMSummary(
            ticker=ticker["ticker"],
            summary=summary,
            observations=observations,
            uncertainties=[
                "单季度环比可能受到季节性和一次性项目影响。",
                "本摘要仅基于本地 SEC 缓存，不包含新闻、行情或未来预测。",
            ],
        )


class OpenAICompatibleProvider:
    """调用 OpenAI-compatible Chat Completions 接口。"""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 180,
        max_tokens: int = 4000,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens

    def summarize(self, payload: dict[str, Any]) -> SummaryResult:
        system_prompt = (
            "你是金融基本面摘要助手。只能使用用户提供的 JSON 指标，"
            "不要计算新数值，不要预测，不要给出买入、卖出、持有或目标价建议。"
            "每只股票只输出 1 条 summary、2 条 observations 和 2 条 uncertainties。"
            "每条 observation 的文字不超过 80 个汉字，evidence 只放 1 到 2 条。"
            "evidence 只能引用输入中存在的 period 和 metric。"
            "输出必须是严格 JSON，不要 Markdown，不要代码块。"
            '结构：{"summaries":[{"ticker":"AAPL","summary":"...",'
            '"observations":[{"text":"...","evidence":[{"period":"...","metric":"..."}]}],'
            '"uncertainties":["..."]}]}'
        )
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))

        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        usage = body.get("usage", {}) or {}
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        usage_source = "reported" if input_tokens is not None or output_tokens is not None else "missing"
        return SummaryResult(
            batch=SummaryBatch.model_validate_json(content),
            provider=self.name,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_source=usage_source,
        )


def get_summary_provider(mode: str = "auto") -> SummaryProvider:
    """根据运行模式选择 Provider。

    auto: 有 LLM_API_KEY/OPENAI_API_KEY 和 LLM_MODEL 时调用 API，否则使用模板。
    api: 强制调用 API，缺少配置时直接报错。
    template: 强制使用确定性模板。
    """

    mode = mode.lower().strip()
    if mode == "template":
        return TemplateSummaryProvider()

    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4000"))
    timeout_seconds = int(os.getenv("LLM_TIMEOUT_SECONDS", "180"))

    if mode == "auto" and not (api_key and model):
        return TemplateSummaryProvider()
    if mode == "api" and not (api_key and model):
        raise ValueError(
            "LLM 模式为 api，但缺少 LLM_API_KEY/OPENAI_API_KEY 或 LLM_MODEL"
        )
    if mode not in {"auto", "api"}:
        raise ValueError(f"不支持的 LLM 模式：{mode}")
    return OpenAICompatibleProvider(
        api_key=api_key or "",
        model=model or "",
        base_url=base_url,
        max_tokens=max_tokens,
        timeout_seconds=timeout_seconds,
    )


def _fmt_bn(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1_000_000_000:,.2f}B USD"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"
