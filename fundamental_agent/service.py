"""FastAPI 和 CLI 共用的运行服务。"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .config import PROJECT_ROOT, load_environment
from .langgraph_pipeline import build_langgraph
from .observability import TraceRecorder


load_environment()


class RunNotFoundError(KeyError):
    """指定 thread_id 不存在。"""


@dataclass(frozen=True)
class ApiSettings:
    """内部 API 的文件路径和执行配置。"""

    cache_path: Path
    checkpoint_db: Path
    trace_dir: Path
    report_dir: Path
    news_cache_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "cache" / "news_events.sec.json"
    )
    default_llm_mode: str = "auto"
    auth_token: str = ""
    require_auth: bool = True

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(
            cache_path=_path_from_env(
                "API_CACHE_PATH",
                PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json",
            ),
            checkpoint_db=_path_from_env(
                "API_CHECKPOINT_DB",
                PROJECT_ROOT / "data" / "checkpoints.api.sqlite",
            ),
            trace_dir=_path_from_env(
                "API_TRACE_DIR",
                PROJECT_ROOT / "data" / "traces",
            ),
            report_dir=_path_from_env(
                "API_REPORT_DIR",
                PROJECT_ROOT / "data" / "reports",
            ),
            news_cache_path=_path_from_env(
                "API_NEWS_CACHE_PATH",
                PROJECT_ROOT / "data" / "cache" / "news_events.sec.json",
            ),
            default_llm_mode="auto",
            auth_token=os.getenv("API_AUTH_TOKEN", ""),
            require_auth=os.getenv("API_REQUIRE_AUTH", "true").strip().lower()
            not in {"0", "false", "no"},
        )


class RunService:
    """封装 LangGraph 运行、审批、报告和 Trace。"""

    def __init__(self, settings: ApiSettings) -> None:
        self.settings = settings
        self._lock = threading.RLock()

    def start_run(
        self,
        tickers: list[str],
        llm_mode: str | None = None,
    ) -> dict[str, Any]:
        if len(tickers) != 3:
            raise ValueError("必须正好提供三只股票代码")
        thread_id = f"run-{uuid4().hex[:16]}"
        mode = llm_mode or self.settings.default_llm_mode
        trace = self._trace(thread_id)
        trace.event("run_start", metadata={"tickers": tickers, "llm_mode": mode})

        try:
            with self._saver() as saver:
                graph = self._graph(thread_id, tickers, mode, saver, trace)
                state = graph.invoke({}, config=self._config(thread_id))
        except Exception as exc:
            trace.event(
                "run_error",
                status="error",
                metadata={"error_type": type(exc).__name__, "error": str(exc)[:300]},
            )
            raise

        if state.get("__interrupt__"):
            trace.event("run_interrupted", status="waiting_approval")
        return self._payload(thread_id, state, trace)

    def get_run(self, thread_id: str) -> dict[str, Any]:
        with self._lock, self._saver() as saver:
            graph = self._graph(thread_id, [], "template", saver, self._trace(thread_id))
            snapshot = graph.get_state(self._config(thread_id))
            values = dict(snapshot.values or {})
            if not values:
                raise RunNotFoundError(thread_id)
            state = dict(values)
            state["__interrupt__"] = bool(snapshot.interrupts)
            return self._payload(thread_id, state, self._trace(thread_id))

    def approve(self, thread_id: str, comment: str = "API 审批通过") -> dict[str, Any]:
        return self._resume(thread_id, approved=True, comment=comment)

    def reject(self, thread_id: str, comment: str = "API 审批拒绝") -> dict[str, Any]:
        return self._resume(thread_id, approved=False, comment=comment)

    def report(self, thread_id: str) -> dict[str, Any]:
        with self._lock, self._saver() as saver:
            graph = self._graph(thread_id, [], "template", saver, self._trace(thread_id))
            snapshot = graph.get_state(self._config(thread_id))
            values = dict(snapshot.values or {})
        if not values:
            raise RunNotFoundError(thread_id)
        if values.get("approved") is not True:
            raise ValueError("报告尚未通过人工审批")

        safe_id = _safe_id(thread_id)
        markdown_path = self.settings.report_dir / f"{safe_id}.md"
        json_path = self.settings.report_dir / f"{safe_id}.json"
        if markdown_path.exists() and json_path.exists():
            markdown = markdown_path.read_text(encoding="utf-8")
            structured = json.loads(json_path.read_text(encoding="utf-8"))
        else:
            markdown = values["markdown"]
            structured = json.loads(values["json"])
        return {
            "thread_id": thread_id,
            "status": "approved",
            "markdown": markdown,
            "structured": structured,
            "summary_source": values.get("summary_source"),
            "llm_model": values.get("llm_model"),
            "budget": values.get("budget_snapshot", {}),
            "compliance": values.get("compliance"),
            "trace_path": str(self._trace_path(thread_id)),
        }

    def trace(self, thread_id: str) -> dict[str, Any]:
        path = self._trace_path(thread_id)
        if not path.exists():
            raise RunNotFoundError(thread_id)
        events = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return {"thread_id": thread_id, "events": events}

    def _resume(
        self,
        thread_id: str,
        *,
        approved: bool,
        comment: str,
    ) -> dict[str, Any]:
        trace = self._trace(thread_id)
        trace.event(
            "run_resume",
            metadata={"approved": approved, "comment": comment},
        )
        with self._lock, self._saver() as saver:
            graph = self._graph(thread_id, [], "template", saver, trace)
            try:
                state = graph.invoke(
                    Command(
                        resume={
                            "approved": approved,
                            "comment": comment,
                        }
                    ),
                    config=self._config(thread_id),
                )
            except Exception as exc:
                trace.event(
                    "run_error",
                    status="error",
                    metadata={"error_type": type(exc).__name__, "error": str(exc)[:300]},
                )
                raise

        if state.get("approved") is True:
            self._save_report(thread_id, state)
        trace.event(
            "run_finished",
            status="approved" if state.get("approved") else "rejected",
            metadata={
                "summary_source": state.get("summary_source"),
                "llm_model": state.get("llm_model"),
                "budget": state.get("budget_snapshot", {}),
            },
        )
        return self._payload(thread_id, state, trace)

    def _save_report(self, thread_id: str, state: dict[str, Any]) -> None:
        self.settings.report_dir.mkdir(parents=True, exist_ok=True)
        safe_id = _safe_id(thread_id)
        (self.settings.report_dir / f"{safe_id}.md").write_text(
            state["markdown"],
            encoding="utf-8",
        )
        (self.settings.report_dir / f"{safe_id}.json").write_text(
            state["json"] + "\n",
            encoding="utf-8",
        )

    def _graph(self, thread_id, tickers, llm_mode, saver, trace):
        return build_langgraph(
            cache_path=self.settings.cache_path,
            tickers=tickers,
            checkpointer=saver,
            llm_mode=llm_mode,
            progress=False,
            run_id=thread_id,
            trace_recorder=trace,
            news_cache_path=self.settings.news_cache_path,
        )

    def _saver(self):
        self.settings.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
        return SqliteSaver.from_conn_string(str(self.settings.checkpoint_db))

    def _trace(self, thread_id: str) -> TraceRecorder:
        return TraceRecorder(
            run_id=thread_id,
            trace_dir=self.settings.trace_dir,
        )

    def _trace_path(self, thread_id: str) -> Path:
        return self.settings.trace_dir / f"{_safe_id(thread_id)}.jsonl"

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _payload(
        thread_id: str,
        state: dict[str, Any],
        trace: TraceRecorder,
    ) -> dict[str, Any]:
        if state.get("__interrupt__"):
            status = "waiting_approval"
        elif state.get("compliance") and not state["compliance"].get("passed"):
            status = "compliance_failed"
        elif state.get("approved") is True:
            status = "approved"
        elif state.get("approved") is False:
            status = "rejected"
        else:
            status = "running"
        preview = state.get("markdown")
        return {
            "thread_id": thread_id,
            "status": status,
            "summary_source": state.get("summary_source"),
            "llm_model": state.get("llm_model"),
            "budget": state.get("budget_snapshot", {}),
            "compliance": state.get("compliance"),
            "draft_preview": preview[:1200] if preview else None,
            "trace_path": str(trace.path),
        }


def _path_from_env(name: str, default: Path) -> Path:
    value = Path(os.environ.get(name, str(default)))
    return value if value.is_absolute() else PROJECT_ROOT / value


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    if safe in {"", ".", ".."}:
        raise ValueError("非法 thread_id")
    return safe
