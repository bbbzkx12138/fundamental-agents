"""基本面简报演示的 CLI 入口。"""

from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import build_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = PROJECT_ROOT / "data" / "cache" / "quarterly_fundamentals.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="基于本地缓存数据生成四季度基本面简报。"
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph = build_graph(cache_path=args.cache, tickers=args.tickers)
    state = graph.run({})

    args.md_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.md_output.write_text(state["markdown"], encoding="utf-8")
    args.json_output.write_text(state["json"] + "\n", encoding="utf-8")

    print(f"Markdown report: {args.md_output}")
    print(f"Structured JSON: {args.json_output}")
    print(f"Tickers: {', '.join(ticker.ticker for ticker in state['brief'].tickers)}")
    print(f"Verification notes: {len(state['verification_notes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
