"""Golden Eval Runner。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .data_loader import load_cache, select_tickers
from .llm_provider import TemplateSummaryProvider
from .llm_summary import summarize_brief, validate_summary_batch
from .pipeline import assemble_brief


NUMERIC_FIELDS = (
    "revenue",
    "gross_profit",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "total_assets",
    "total_liabilities",
)

CORE_FIELDS = (
    "period",
    "period_end_date",
    "data_date",
    "accession_number",
    "form_type",
    "filed_date",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行基本面 Golden Eval。")
    parser.add_argument(
        "--case",
        type=Path,
        default=PROJECT_ROOT / "evals" / "cases" / "normal_three_tickers.json",
        help="评测用例路径。",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "evals" / "reports" / "latest.json",
        help="评测报告输出路径。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case_path = _resolve(args.case)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    cache_path = _resolve(Path(case["cache"]))
    golden_path = _resolve(Path(case["golden"]))
    tolerance = float(case.get("tolerance", 0.01))

    checks: list[dict[str, Any]] = []
    try:
        cache = load_cache(cache_path)
        golden = json.loads(golden_path.read_text(encoding="utf-8"))
        selected = select_tickers(cache, case["tickers"])

        _check(
            checks,
            "as_of",
            cache.as_of.isoformat() == golden["as_of"],
            f"cache={cache.as_of.isoformat()} golden={golden['as_of']}",
        )

        for ticker, company in selected.items():
            golden_company = golden["tickers"][ticker]
            actual_quarters = sorted(
                company.quarters,
                key=lambda item: item.period_end_date,
            )
            expected_quarters = sorted(
                golden_company["quarters"],
                key=lambda item: item["period_end_date"],
            )
            _check(
                checks,
                f"{ticker}:quarter_count",
                len(actual_quarters) == 4 == len(expected_quarters),
                f"actual={len(actual_quarters)} expected={len(expected_quarters)}",
            )

            for actual, expected in zip(actual_quarters, expected_quarters):
                prefix = f"{ticker}:{expected['period']}"
                for field in CORE_FIELDS:
                    actual_value = _record_value(actual, field)
                    _check(
                        checks,
                        f"{prefix}:{field}",
                        actual_value == expected[field],
                        f"actual={actual_value} expected={expected[field]}",
                    )
                for field in NUMERIC_FIELDS:
                    actual_value = float(_record_value(actual, field))
                    expected_value = float(expected[field])
                    _check(
                        checks,
                        f"{prefix}:{field}",
                        math.isclose(
                            actual_value,
                            expected_value,
                            rel_tol=1e-9,
                            abs_tol=tolerance,
                        ),
                        f"actual={actual_value} expected={expected_value}",
                    )
                _check(
                    checks,
                    f"{prefix}:provenance",
                    bool(actual.source)
                    and bool(actual.source_url)
                    and bool(actual.accession_number)
                    and actual.filed_date is not None
                    and actual.filed_date <= cache.as_of,
                    "SEC provenance complete and point-in-time",
                )

        brief, _ = assemble_brief(cache, selected)
        summary_brief, _, summary_source, llm_model, budget = summarize_brief(
            brief,
            TemplateSummaryProvider(),
        )
        _check(
            checks,
            "summary:source",
            summary_source == "template" and llm_model is None,
            f"source={summary_source} model={llm_model}",
        )
        validate_summary_batch(
            type("Batch", (), {"summaries": summary_brief.summaries})(),
            brief,
        )
        _check(
            checks,
            "summary:evidence",
            len(summary_brief.summaries) == 3
            and all(summary.observations for summary in summary_brief.summaries),
            f"summaries={len(summary_brief.summaries)}",
        )
        _check(
            checks,
            "budget:snapshot",
            "total_tokens" in budget and budget["exceeded"] is False,
            json.dumps(budget, ensure_ascii=False),
        )
        passed = all(check["passed"] for check in checks)
    except Exception as exc:
        passed = False
        checks.append(
            {
                "name": "eval_runner",
                "passed": False,
                "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
        )

    result = {
        "case": case.get("name", case_path.stem),
        "eval_version": case.get("eval_version", "1.0"),
        "passed": passed,
        "checks": checks,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for check in checks:
        marker = "PASS" if check["passed"] else "FAIL"
        print(f"{marker} {check['name']}: {check['detail']}")
    print(f"RESULT {'PASS' if passed else 'FAIL'}")
    print(f"Report: {args.report}")
    return 0 if passed else 1


def _check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    detail: str,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def _record_value(record: Any, field: str) -> Any:
    value = getattr(record, field)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
