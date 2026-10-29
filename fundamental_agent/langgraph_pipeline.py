"""基于 LangGraph 的状态图流水线。"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .compliance import evaluate_compliance
from .config import PROJECT_ROOT
from .data_loader import load_cache, select_tickers
from .llm_provider import get_summary_provider
from .llm_summary import summarize_brief
from .models import CacheFile, CompanyRecords, FundamentalBrief
from .news_agent import build_news_brief
from .news_loader import load_news_cache
from .observability import CostBudget, TraceRecorder
from .pipeline import assemble_brief
from .report import render_markdown
from .verify import REQUIRED_METRICS, verify_no_trading_advice


class PipelineState(TypedDict, total=False):
    """LangGraph 状态。

    这里只存放 JSON 可序列化对象，确保 checkpointer 可以持久化。
    """

    cache: dict[str, Any]
    requested_tickers: list[str]
    selected: dict[str, dict[str, Any]]
    plan: dict[str, Any]
    brief: dict[str, Any]
    markdown: str
    json: str
    verification_notes: list[str]
    summaries: list[dict[str, Any]]
    summary_source: str | None
    llm_model: str | None
    budget_snapshot: dict[str, Any]
    compliance: dict[str, Any]
    news: dict[str, Any]
    approved: bool
    approval_comment: str


def build_langgraph(
    cache_path: Path,
    tickers: list[str],
    checkpointer: Any | None = None,
    llm_mode: str = "auto",
    progress: bool = True,
    trace_enabled: bool = True,
    trace_dir: Path | None = None,
    run_id: str | None = None,
    trace_recorder: TraceRecorder | None = None,
    budget: CostBudget | None = None,
    news_cache_path: Path | None = None,
):
    """构建带人工审批中断点的 LangGraph 状态图。"""

    graph = StateGraph(PipelineState)
    summary_provider = get_summary_provider(llm_mode)
    trace = trace_recorder or TraceRecorder(
        run_id=run_id or f"fundamental-{uuid4().hex[:12]}",
        trace_dir=trace_dir or (PROJECT_ROOT / "data" / "traces"),
        enabled=trace_enabled,
    )
    budget = budget or CostBudget()
    news_cache_path = news_cache_path or (
        PROJECT_ROOT / "data" / "cache" / "news_events.sec.json"
    )

    def log_progress(message: str) -> None:
        if progress:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)

    def load_cache_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在加载 SEC 缓存...")
        cache = load_cache(cache_path)
        return {
            "cache": cache.model_dump(mode="json"),
            "requested_tickers": [ticker.upper() for ticker in tickers],
            "verification_notes": [],
        }

    def validate_cache_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在验证数据...")
        cache = CacheFile.model_validate(state["cache"])
        selected = select_tickers(cache, state["requested_tickers"])
        return {
            "selected": {
                ticker: company.model_dump(mode="json")
                for ticker, company in selected.items()
            }
        }

    def supervisor_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在准备任务计划...")
        plan = {
            "tickers": list(state["selected"].keys()),
            "required_metrics": sorted(REQUIRED_METRICS),
            "mode": "deterministic_fundamental_brief",
        }
        notes = list(state["verification_notes"])
        notes.append("Supervisor 已锁定 MVP 指标检查清单。")
        return {"plan": plan, "verification_notes": notes}

    def compute_metrics_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在计算指标...")
        cache = CacheFile.model_validate(state["cache"])
        selected = {
            ticker: CompanyRecords.model_validate(record)
            for ticker, record in state["selected"].items()
        }
        brief, notes = assemble_brief(
            cache,
            selected,
            verification_notes=state["verification_notes"],
        )
        return {
            "brief": brief.model_dump(mode="json"),
            "verification_notes": notes,
        }

    def verify_metrics_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在验证指标...")
        notes = list(state["verification_notes"])
        notes.append("所有必需指标均通过确定性重算校验。")
        brief = FundamentalBrief.model_validate(state["brief"])
        brief = brief.model_copy(update={"verification_notes": notes})
        return {
            "brief": brief.model_dump(mode="json"),
            "verification_notes": notes,
        }

    def news_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在加载并校验新闻事件...")
        brief = FundamentalBrief.model_validate(state["brief"])
        notes = list(state["verification_notes"])
        news_brief = None
        try:
            news_cache = load_news_cache(news_cache_path)
            news_brief = build_news_brief(
                news_cache,
                state["requested_tickers"],
            )
            notes.extend(news_brief.verification_notes)
        except Exception as exc:
            notes.append(
                "新闻事件已跳过："
                f"{type(exc).__name__}: {str(exc)[:240]}"
            )
        brief = brief.model_copy(
            update={
                "news": news_brief,
                "verification_notes": notes,
            }
        )
        return {
            "brief": brief.model_dump(mode="json"),
            "news": news_brief.model_dump(mode="json") if news_brief else {},
            "verification_notes": notes,
        }

    def llm_summary_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在调用 LLM 摘要...")
        log_progress("llm_summary 开始")
        brief = FundamentalBrief.model_validate(state["brief"])
        brief, _, summary_source, llm_model, budget_snapshot = summarize_brief(
            brief,
            summary_provider,
            budget=budget,
            trace=trace,
        )
        log_progress(f"llm_summary 完成，来源：{summary_source}")
        return {
            "brief": brief.model_dump(mode="json"),
            "summaries": [
                summary.model_dump(mode="json")
                for summary in brief.summaries
            ],
            "summary_source": summary_source,
            "llm_model": llm_model,
            "budget_snapshot": budget_snapshot,
            "verification_notes": brief.verification_notes,
        }

    def render_report_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在生成报告草稿...")
        log_progress("render_report 开始")
        brief = FundamentalBrief.model_validate(state["brief"])
        brief = brief.model_copy(
            update={"verification_notes": state["verification_notes"]}
        )
        result = {
            "brief": brief.model_dump(mode="json"),
            "markdown": render_markdown(brief),
            "json": brief.model_dump_json(indent=2),
        }
        log_progress("render_report 完成")
        return result

    def compliance_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在执行合规检查...")
        brief = FundamentalBrief.model_validate(state["brief"])
        draft_markdown = render_markdown(brief)
        decision = evaluate_compliance(brief, draft_markdown)
        notes = list(state["verification_notes"])
        if decision.passed:
            notes.append("合规检查通过。")
        else:
            notes.append(
                "合规检查未通过："
                + "；".join(decision.violations)
            )
        brief = brief.model_copy(
            update={
                "compliance": decision,
                "verification_notes": notes,
            }
        )
        return {
            "brief": brief.model_dump(mode="json"),
            "compliance": decision.model_dump(mode="json"),
            "markdown": render_markdown(brief),
            "verification_notes": notes,
        }

    def human_approval_node(state: PipelineState) -> dict[str, Any]:
        """暂停并等待人工审批。

        LangGraph 会在该节点 checkpoint 并中断。再次调用时传入
        Command(resume={"approved": True/False, "comment": "..."}).
        """

        log_progress("human_approval 等待中")
        log_progress("等待人工审批...")
        decision = interrupt(
            {
                "question": "是否批准生成最终基本面简报？",
                "tickers": list(state["selected"].keys()),
                "required_metrics": state["plan"]["required_metrics"],
                "draft_preview": state["markdown"][:1200],
            }
        )
        if isinstance(decision, dict):
            approved = bool(decision.get("approved"))
            comment = str(decision.get("comment", ""))
        else:
            approved = bool(decision)
            comment = ""
        return {"approved": approved, "approval_comment": comment}

    def safety_check_node(state: PipelineState) -> dict[str, Any]:
        log_progress("正在执行安全校验...")
        if not state.get("approved"):
            return {"verification_notes": state["verification_notes"]}

        verify_no_trading_advice(state["markdown"])
        notes = list(state["verification_notes"])
        notes.append("人工审批已通过。")
        notes.append("报告正文未检测到交易建议表述。")
        brief = FundamentalBrief.model_validate(state["brief"])
        brief = brief.model_copy(update={"verification_notes": notes})
        return {
            "brief": brief.model_dump(mode="json"),
            "verification_notes": notes,
            "markdown": render_markdown(brief),
            "json": brief.model_dump_json(indent=2),
        }

    def approval_route(state: PipelineState) -> str:
        return "approved" if state.get("approved") else "rejected"

    def compliance_route(state: PipelineState) -> str:
        return "passed" if state.get("compliance", {}).get("passed") else "blocked"

    def traced(name: str, node_fn):
        def wrapped(state: PipelineState):
            with trace.node(name):
                return node_fn(state)

        return wrapped

    graph.add_node("load_cache", traced("load_cache", load_cache_node))
    graph.add_node("validate_cache", traced("validate_cache", validate_cache_node))
    graph.add_node("supervisor", traced("supervisor", supervisor_node))
    graph.add_node("compute_metrics", traced("compute_metrics", compute_metrics_node))
    graph.add_node("verify_metrics", traced("verify_metrics", verify_metrics_node))
    graph.add_node("news", traced("news", news_node))
    graph.add_node("llm_summary", traced("llm_summary", llm_summary_node))
    graph.add_node("compliance", traced("compliance", compliance_node))
    graph.add_node("render_report", traced("render_report", render_report_node))
    graph.add_node("human_approval", traced("human_approval", human_approval_node))
    graph.add_node("safety_check", traced("safety_check", safety_check_node))

    graph.add_edge(START, "load_cache")
    graph.add_edge("load_cache", "validate_cache")
    graph.add_edge("validate_cache", "supervisor")
    graph.add_edge("supervisor", "compute_metrics")
    graph.add_edge("compute_metrics", "verify_metrics")
    graph.add_edge("verify_metrics", "news")
    graph.add_edge("news", "llm_summary")
    graph.add_edge("llm_summary", "compliance")
    graph.add_conditional_edges(
        "compliance",
        compliance_route,
        {"passed": "render_report", "blocked": END},
    )
    graph.add_edge("render_report", "human_approval")
    graph.add_conditional_edges(
        "human_approval",
        approval_route,
        {"approved": "safety_check", "rejected": END},
    )
    graph.add_edge("safety_check", END)
    return graph.compile(checkpointer=checkpointer)
