"""基本面简报的 Markdown 渲染。"""

from __future__ import annotations

from .models import FundamentalBrief, MetricPoint, TickerBrief, TickerLLMSummary


def render_markdown(brief: FundamentalBrief) -> str:
    lines: list[str] = [
        "# 美股基本面简报",
        "",
        f"- 生成时间：{brief.generated_at}",
        f"- 数据截止：{brief.data_as_of.isoformat()}",
        f"- 缓存来源：{brief.cache_source}",
        "- 数据范围：每只股票最近 4 个季度",
        "- 增速口径：环比 QoQ，因为本地缓存只有 4 个季度",
        *(
            [f"- 摘要来源：{brief.summary_source}"]
            if brief.summary_source
            else []
        ),
        "",
        *_source_note(brief.cache_source),
        "> 报告仅做基本面信息整理，不构成投资建议，不包含买卖建议，不连接交易系统。",
        "",
    ]

    summaries = {summary.ticker: summary for summary in brief.summaries}
    for ticker in brief.tickers:
        lines.extend(_render_ticker(ticker, summaries.get(ticker.ticker)))
        lines.append("")

    if brief.compliance is not None:
        lines.extend(
            [
                "## 合规检查",
                "",
                f"- 结果：{'通过' if brief.compliance.passed else '未通过'}",
                f"- 规则版本：{brief.compliance.rules_version}",
                f"- 检查时间：{brief.compliance.checked_at}",
            ]
        )
        if brief.compliance.violations:
            lines.append("")
            lines.append("违规项：")
            lines.extend(f"- {item}" for item in brief.compliance.violations)
        if brief.compliance.warnings:
            lines.append("")
            lines.append("警告：")
            lines.extend(f"- {item}" for item in brief.compliance.warnings)
        lines.append("")

    lines.extend(
        [
            "## 校验记录",
            "",
        ]
    )
    lines.extend(f"- {note}" for note in brief.verification_notes)
    lines.extend(
        [
            "",
            "## 免责声明",
            "",
            brief.disclaimer,
            "",
            "本报告不包含买入、卖出或持有建议，也没有任何交易执行接口。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_ticker(
    ticker: TickerBrief,
    summary: TickerLLMSummary | None = None,
) -> list[str]:
    lines = [
        f"## {ticker.ticker} - {ticker.company_name}",
        "",
        "| 财报期间 | 数据日期 | 营收 (USD bn) | 营收环比 | 净利润 (USD bn) | 净利润环比 | 毛利率 | 自由现金流 (USD bn) | 资产负债率 | 数据来源 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    lookup = _metric_lookup(ticker.metrics)
    for record in sorted(ticker.quarters, key=lambda item: item.period_end_date):
        revenue = lookup[(record.period, "revenue")].value
        revenue_growth = lookup[(record.period, "revenue_growth_qoq")].value
        net_income = lookup[(record.period, "net_income")].value
        net_income_growth = lookup[(record.period, "net_income_growth_qoq")].value
        gross_margin = lookup[(record.period, "gross_margin")].value
        free_cash_flow = lookup[(record.period, "free_cash_flow")].value
        debt_ratio = lookup[(record.period, "debt_to_asset_ratio")].value

        lines.append(
            "| "
            + " | ".join(
                [
                    record.period,
                    record.data_date.isoformat(),
                    _fmt_usd_bn(revenue),
                    _fmt_pct(revenue_growth),
                    _fmt_usd_bn(net_income),
                    _fmt_pct(net_income_growth),
                    _fmt_pct(gross_margin),
                    _fmt_usd_bn(free_cash_flow),
                    _fmt_pct(debt_ratio),
                    record.source,
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "说明：同一行的全部指标均来自该行标注的财报期间、数据日期和数据来源；指标由确定性公式计算得到。",
            "",
            "### 来源追溯",
            "",
            "| 财报期间 | 数据日期 | 申报日期 | 表单 | Accession | Frame | Source URL |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for record in sorted(ticker.quarters, key=lambda item: item.period_end_date):
        source_url = (
            f"[SEC companyfacts]({record.source_url})"
            if record.source_url
            else "N/A"
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    record.period,
                    record.data_date.isoformat(),
                    record.filed_date.isoformat() if record.filed_date else "N/A",
                    record.form_type or "N/A",
                    record.accession_number or "N/A",
                    record.frame or "N/A",
                    source_url,
                ]
            )
            + " |"
        )

    if summary is not None:
        lines.extend(
            [
                "",
                "### 摘要与解释",
                "",
                summary.summary,
                "",
            ]
        )
        if summary.observations:
            lines.append("重点观察：")
            lines.append("")
            for observation in summary.observations:
                evidence_text = "；".join(
                    f"{item.period}/{item.metric}"
                    for item in observation.evidence
                )
                lines.append(f"- {observation.text}（依据：{evidence_text}）")
            lines.append("")
        if summary.uncertainties:
            lines.append("不确定性：")
            lines.append("")
            lines.extend(f"- {item}" for item in summary.uncertainties)
            lines.append("")

    return lines


def _metric_lookup(points: list[MetricPoint]) -> dict[tuple[str, str], MetricPoint]:
    return {(point.period, point.metric): point for point in points}


def _fmt_usd_bn(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value / 1_000_000_000:,.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _source_note(cache_source: str) -> list[str]:
    if "SEC EDGAR" in cache_source:
        return [
            "> 数据来源：SEC EDGAR companyfacts。",
            "> 单季数据优先使用原始 filing；缺失的单季值由 SEC 累计值差分推导。",
        ]
    return [
        "> 本 Demo 使用本地 illustrative fixture，仅用于验证系统结构和计算口径。",
        "> 这些数字不是实时行情，也不是经审计的正式财报数据。",
    ]
