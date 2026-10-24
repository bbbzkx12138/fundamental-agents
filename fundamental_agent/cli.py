"""基本面简报演示的 CLI 入口。"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .config import load_environment
from .langgraph_pipeline import build_langgraph
from .models import FundamentalBrief
from .observability import TraceRecorder
from .pipeline import build_graph


load_environment()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.sec.json"
DEFAULT_CHECKPOINT_DB = PROJECT_ROOT / "data" / "checkpoints.sqlite"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="基于本地缓存数据生成四季度基本面简报。"
    )
    parser.add_argument(
        "--engine",
        choices=("langgraph", "daglite"),
        default="langgraph",
        help="执行引擎。默认使用带 checkpoint 和人工审批的 LangGraph。",
    )
    parser.add_argument(
        "--llm-mode",
        choices=("auto", "api", "template"),
        default=os.environ.get("LLM_MODE", "auto"),
        help=(
            "摘要生成模式。auto 有 API Key 时调用模型，否则使用模板；"
            "api 强制调用模型；template 强制使用模板。"
        ),
    )
    parser.add_argument(
        "--tickers",
        nargs=3,
        default=["AAPL", "MSFT", "NVDA"],
        metavar=("TICKER1", "TICKER2", "TICKER3"),
        help="本地缓存中必须存在的三只美股代码。",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"本地缓存 JSON 路径。默认值：{DEFAULT_CACHE}",
    )
    parser.add_argument(
        "--md-output",
        type=Path,
        default=PROJECT_ROOT / "sample_report.md",
        help="Markdown 报告输出路径。",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT / "sample_report.json",
        help="结构化 JSON 输出路径。",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="LangGraph checkpoint 线程 ID。首次运行可省略。",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="恢复指定 thread-id 并批准生成最终报告。",
    )
    parser.add_argument(
        "--reject",
        action="store_true",
        help="恢复指定 thread-id 并拒绝生成最终报告。",
    )
    parser.add_argument(
        "--approval-comment",
        default="CLI 审批通过",
        help="写入审批记录的人工备注。",
    )
    parser.add_argument(
        "--checkpoint-db",
        type=Path,
        default=DEFAULT_CHECKPOINT_DB,
        help=f"SQLite checkpoint 路径。默认值：{DEFAULT_CHECKPOINT_DB}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.approve and args.reject:
        raise SystemExit("--approve 和 --reject 不能同时使用")

    if args.engine == "daglite":
        graph = build_graph(cache_path=args.cache, tickers=args.tickers)
        state = graph.run({})
        _write_outputs(state, args)
        return 0

    if (args.approve or args.reject) and not args.thread_id:
        raise SystemExit("恢复审批时必须提供 --thread-id")

    thread_id = args.thread_id or f"fundamental-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}
    args.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    trace = TraceRecorder(
        run_id=thread_id,
        trace_dir=PROJECT_ROOT / "data" / "traces",
    )
    trace.event("run_start", metadata={"thread_id": thread_id})

    try:
        with SqliteSaver.from_conn_string(str(args.checkpoint_db)) as saver:
            graph = build_langgraph(
                cache_path=args.cache,
                tickers=args.tickers,
                checkpointer=saver,
                llm_mode=args.llm_mode,
                run_id=thread_id,
                trace_recorder=trace,
            )
            if args.approve or args.reject:
                state = graph.invoke(
                    Command(
                        resume={
                            "approved": args.approve,
                            "comment": args.approval_comment,
                        }
                    ),
                    config=config,
                )
            else:
                state = graph.invoke({}, config=config)
    except Exception as exc:
        trace.event(
            "run_error",
            status="error",
            metadata={"error_type": type(exc).__name__, "error": str(exc)[:300]},
        )
        raise

    if state.get("__interrupt__"):
        trace.event("run_interrupted", status="waiting_approval")
        print("已暂停，等待人工审批。")
        print(f"thread_id: {thread_id}")
        print("批准：")
        print(
            f'  .\\.venv\\Scripts\\python.exe -m fundamental_agent.cli '
            f'--thread-id {thread_id} --approve'
        )
        print("拒绝：")
        print(
            f'  .\\.venv\\Scripts\\python.exe -m fundamental_agent.cli '
            f'--thread-id {thread_id} --reject'
        )
        return 0

    if not state.get("approved"):
        trace.event("run_finished", status="rejected")
        print("审批未通过，未生成最终报告。")
        print(f"thread_id: {thread_id}")
        return 0

    _write_outputs(state, args)
    trace.event(
        "run_finished",
        status="approved",
        metadata={
            "summary_source": state.get("summary_source"),
            "llm_model": state.get("llm_model"),
            "budget": state.get("budget_snapshot", {}),
            "trace_path": str(trace.path),
        },
    )
    print(f"Trace: {trace.path}")
    print(f"thread_id: {thread_id}")
    return 0


def _write_outputs(state: dict, args: argparse.Namespace) -> None:
    brief = state["brief"]
    if isinstance(brief, dict):
        brief = FundamentalBrief.model_validate(brief)

    args.md_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.write_text(state["markdown"], encoding="utf-8")
    args.json_output.write_text(state["json"] + "\n", encoding="utf-8")

    print(f"Markdown report: {args.md_output}")
    print(f"Structured JSON: {args.json_output}")
    print(f"Tickers: {', '.join(ticker.ticker for ticker in brief.tickers)}")
    print(f"Summary source: {state.get('summary_source', 'N/A')}")
    budget = state.get("budget_snapshot", {})
    print(
        "Budget: "
        f"{budget.get('total_tokens', 0)} tokens, "
        f"estimated ${budget.get('estimated_cost_usd', 0.0):.6f}"
    )
    print(f"Verification notes: {len(state['verification_notes'])}")


if __name__ == "__main__":
    raise SystemExit(main())
