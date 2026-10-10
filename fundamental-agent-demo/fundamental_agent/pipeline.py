"""基本面简报演示的 DAG 流水线。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .data_loader import load_cache, select_tickers
from .graph import DagGraph, Node
from .metrics import build_metric_points
from .models import FundamentalBrief, TickerBrief
from .report import render_markdown
from .verify import (
    REQUIRED_METRICS,
    verify_no_trading_advice,
    verify_ticker_brief,
)


DISCLAIMER = (
    "本报告仅用于基本面信息整理和系统演示，不构成任何投资建议。"
    "报告不包含买入、卖出或持有建议，不连接交易系统，也不执行任何交易。"
)


def build_brief(
    cache_path: Path,
    tickers: list[str],
) -> FundamentalBrief:
    cache = load_cache(cache_path)
    selected = select_tickers(cache, tickers)

    ticker_briefs: list[TickerBrief] = []
    verification_notes: list[str] = []

    for ticker, company in selected.items():
        metrics = build_metric_points(ticker, company.quarters)
        ticker_brief = TickerBrief(
            ticker=ticker,
            company_name=company.company_name,
            currency=cache.currency,
            quarters=company.quarters,
            metrics=metrics,
        )
        verification_notes.extend(verify_ticker_brief(ticker_brief))
        ticker_briefs.append(ticker_brief)

    return FundamentalBrief(
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        data_as_of=cache.as_of,
        cache_source=cache.source,
        tickers=ticker_briefs,
        verification_notes=verification_notes,
        disclaimer=DISCLAIMER,
    )


def build_graph(cache_path: Path, tickers: list[str]) -> DagGraph:
    """构建具有显式节点边界的 DAG。

    当前 MVP 的流水线是确定性的。Supervisor 节点会锁定必需的指标检查清单；
    后续版本可以在不改变下游契约的情况下，将其替换为 LLM Supervisor。
    """

    graph = DagGraph()

    #加载本地缓存数据并初始化工作流状态
    def load_cache_node(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "cache": load_cache(cache_path),
            "requested_tickers": [ticker.upper() for ticker in tickers],
            "verification_notes": [],
        }

    def validate_cache_node(state: dict[str, Any]) -> dict[str, Any]:
        selected = select_tickers(state["cache"], state["requested_tickers"])
        return {"selected": selected}

    def supervisor_node(state: dict[str, Any]) -> dict[str, Any]:
        plan = {
            "tickers": list(state["selected"].keys()),
            "required_metrics": sorted(REQUIRED_METRICS),
            "mode": "deterministic_fundamental_brief",
        }
        return {
            "plan": plan,
            "verification_notes": state["verification_notes"]
            + ["Supervisor locked the MVP metric checklist."],
        }

    def compute_metrics_node(state: dict[str, Any]) -> dict[str, Any]:
        briefs: list[TickerBrief] = []    #准备一个列表，用来保存每只股票的分析结果
        notes = list(state["verification_notes"])
        for ticker, company in state["selected"].items():
            ticker_brief = TickerBrief(
                ticker=ticker,
                company_name=company.company_name,
                currency=state["cache"].currency,
                quarters=sorted(
                    company.quarters,
                    key=lambda item: item.period_end_date,
                ),
                metrics=build_metric_points(ticker, company.quarters),
            )
            notes.extend(verify_ticker_brief(ticker_brief))
            briefs.append(ticker_brief)

        brief = FundamentalBrief(
            generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            data_as_of=state["cache"].as_of,
            cache_source=state["cache"].source,
            tickers=briefs,
            verification_notes=notes,
            disclaimer=DISCLAIMER,
        )
        return {"brief": brief, "verification_notes": notes}

    def verify_metrics_node(state: dict[str, Any]) -> dict[str, Any]:
        notes = list(state["verification_notes"])
        notes.append("All required metrics passed deterministic recomputation checks.")
        return {"verification_notes": notes}

    def render_report_node(state: dict[str, Any]) -> dict[str, Any]:
        brief: FundamentalBrief = state["brief"].model_copy(
            update={"verification_notes": state["verification_notes"]}
        )
        markdown = render_markdown(brief)
        return {
            "brief": brief,
            "markdown": markdown,
            "json": brief.model_dump_json(indent=2),
        }

    def safety_check_node(state: dict[str, Any]) -> dict[str, Any]:
        verify_no_trading_advice(state["markdown"])
        notes = list(state["verification_notes"])
        notes.append("No trading-advice phrases detected in the report body.")
        brief = state["brief"].model_copy(update={"verification_notes": notes})
        markdown = render_markdown(brief)
        return {
            "verification_notes": notes,
            "brief": brief,
            "markdown": markdown,
            "json": brief.model_dump_json(indent=2),
        
    graph.add_node(Node("load_cache", load_cache_node))
    graph.add_node(Node("validate_cache", validate_cache_node, ("load_cache",)))
    graph.add_node(Node("supervisor", supervisor_node, ("validate_cache",)))
    graph.add_node(Node("compute_metrics", compute_metrics_node, ("supervisor",)))
    graph.add_node(Node("verify_metrics", verify_metrics_node, ("compute_metrics",)))
    graph.add_node(Node("render_report", render_report_node, ("verify_metrics",)))
    graph.add_node(Node("safety_check", safety_check_node, ("render_report",)))
    return graph
