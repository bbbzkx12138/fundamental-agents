"""本地 Trace 和成本预算。"""

from __future__ import annotations

import json
import math
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from .config import load_environment


load_environment()


@dataclass(frozen=True)
class BudgetConfig:
    """一次工作流的预算配置。"""

    max_total_tokens: int = 12000
    max_cost_usd: float = 0.0
    input_price_per_million: float = 0.0
    output_price_per_million: float = 0.0

    @classmethod
    def from_env(cls) -> "BudgetConfig":
        return cls(
            max_total_tokens=int(os.getenv("LLM_RUN_TOKEN_BUDGET", "12000")),
            max_cost_usd=float(os.getenv("LLM_COST_BUDGET_USD", "0")),
            input_price_per_million=float(
                os.getenv("LLM_INPUT_PRICE_PER_MILLION", "0")
            ),
            output_price_per_million=float(
                os.getenv("LLM_OUTPUT_PRICE_PER_MILLION", "0")
            ),
        )


@dataclass
class CostBudget:
    """记录 token 用量并判断预算是否超限。"""

    config: BudgetConfig = field(default_factory=BudgetConfig.from_env)
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return round(
            self.input_tokens / 1_000_000 * self.config.input_price_per_million
            + self.output_tokens / 1_000_000 * self.config.output_price_per_million,
            6,
        )

    def can_call(self, estimated_input_tokens: int, max_output_tokens: int) -> tuple[bool, str]:
        projected = self.total_tokens + estimated_input_tokens + max_output_tokens
        if self.config.max_total_tokens > 0 and projected > self.config.max_total_tokens:
            return (
                False,
                f"调用预计达到 {projected} tokens，超过预算 "
                f"{self.config.max_total_tokens}",
            )
        if self.config.max_cost_usd > 0:
            projected_cost = (
                (self.input_tokens + estimated_input_tokens)
                / 1_000_000
                * self.config.input_price_per_million
                + (self.output_tokens + max_output_tokens)
                / 1_000_000
                * self.config.output_price_per_million
            )
            if projected_cost > self.config.max_cost_usd:
                return (
                    False,
                    f"调用预计成本 ${projected_cost:.4f}，超过预算 "
                    f"${self.config.max_cost_usd:.4f}",
                )
        return True, "预算检查通过"

    def record(self, input_tokens: int | None, output_tokens: int | None) -> None:
        self.calls += 1
        self.input_tokens += max(0, input_tokens or 0)
        self.output_tokens += max(0, output_tokens or 0)

    def snapshot(self) -> dict[str, Any]:
        exceeded = (
            self.config.max_total_tokens > 0
            and self.total_tokens > self.config.max_total_tokens
        ) or (
            self.config.max_cost_usd > 0
            and self.estimated_cost_usd > self.config.max_cost_usd
        )
        return {
            "max_total_tokens": self.config.max_total_tokens,
            "max_cost_usd": self.config.max_cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "calls": self.calls,
            "exceeded": exceeded,
        }


class TraceRecorder:
    """追加写入本地 JSONL Trace。"""

    def __init__(
        self,
        *,
        run_id: str,
        trace_dir: Path,
        enabled: bool = True,
    ) -> None:
        self.run_id = run_id
        self.trace_dir = trace_dir
        self.enabled = enabled
        safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id)
        self.path = trace_dir / f"{safe_run_id}.jsonl"

    def event(
        self,
        event: str,
        *,
        node: str | None = None,
        status: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        record = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "event": event,
            "node": node,
            "status": status,
            "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            "metadata": _redact(metadata or {}),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @contextmanager
    def node(self, name: str) -> Iterator[None]:
        start = perf_counter()
        self.event("node_start", node=name, status="started")
        try:
            yield
        except Exception as exc:
            elapsed = (perf_counter() - start) * 1000
            status = "interrupted" if type(exc).__name__ == "GraphInterrupt" else "error"
            self.event(
                "node_end",
                node=name,
                status=status,
                duration_ms=elapsed,
                metadata={"error_type": type(exc).__name__},
            )
            raise
        else:
            elapsed = (perf_counter() - start) * 1000
            self.event("node_end", node=name, status="ok", duration_ms=elapsed)


def estimate_tokens(text: str) -> int:
    """无 tokenizer 时的保守估算。"""

    return max(1, math.ceil(len(text) / 3))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("api_key", "authorization", "secret")):
                result[key] = "***"
            else:
                result[key] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-***", value)
    return value
