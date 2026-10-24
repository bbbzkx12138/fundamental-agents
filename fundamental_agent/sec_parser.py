"""把 SEC companyfacts 解析为本地季度缓存契约。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable

from .models import CompanyRecords, QuarterRecord


DURATION_TAG_FALLBACKS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "gross_profit": ("GrossProfit",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capital_expenditure": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
    ),
}

INSTANT_TAG_FALLBACKS: dict[str, tuple[str, ...]] = {
    "total_assets": ("Assets",),
    "total_liabilities": ("Liabilities",),
}

METRIC_ORDER = (
    "revenue",
    "gross_profit",
    "net_income",
    "operating_cash_flow",
    "capital_expenditure",
    "total_assets",
    "total_liabilities",
)


@dataclass(frozen=True)
class Fact:
    metric: str
    tag: str
    tag_priority: int
    start: date | None
    end: date
    value: float
    filed: date
    form: str
    fy: int | None
    fp: str | None
    frame: str | None
    accession: str
    days: int
    derived: bool = False
    related_accession: str | None = None


def parse_companyfacts(
    *,
    ticker: str,
    cik: str,
    companyfacts: dict[str, Any],
    as_of: date,
) -> CompanyRecords:
    """把一份 SEC companyfacts 数据转换为四个季度记录。"""

    duration_facts: dict[str, list[Fact]] = {}
    for metric, tags in DURATION_TAG_FALLBACKS.items():
        facts = _collect_duration_facts(companyfacts, metric, tags, as_of)
        duration_facts[metric] = facts + _derive_flow_quarters(metric, facts)

    instant_facts: dict[str, list[Fact]] = {}
    for metric, tags in INSTANT_TAG_FALLBACKS.items():
        instant_facts[metric] = _collect_instant_facts(companyfacts, metric, tags, as_of)

    quarter_ends = _latest_four_quarter_ends(duration_facts["revenue"], as_of)
    quarters: list[QuarterRecord] = []

    for end in quarter_ends:
        selected: dict[str, Fact] = {}
        for metric in DURATION_TAG_FALLBACKS:
            fact = _best_duration_fact(duration_facts[metric], end)
            if fact is None:
                raise ValueError(f"{ticker}: missing {metric} for quarter ending {end}")
            selected[metric] = fact
        for metric in INSTANT_TAG_FALLBACKS:
            fact = _best_instant_fact(instant_facts[metric], end)
            if fact is None:
                raise ValueError(f"{ticker}: missing {metric} for quarter ending {end}")
            selected[metric] = fact

        quarters.append(
            _build_quarter_record(
                ticker=ticker,
                cik=cik,
                end=end,
                selected=selected,
            )
        )

    company_name = _company_name(companyfacts) or f"{ticker} SEC registrant"
    return CompanyRecords(company_name=company_name, quarters=quarters)


def _collect_duration_facts(
    companyfacts: dict[str, Any],
    metric: str,
    tags: Iterable[str],
    as_of: date,
) -> list[Fact]:
    facts: list[Fact] = []
    for priority, tag in enumerate(tags):
        for raw in _raw_usd_facts(companyfacts, tag):
            parsed = _parse_duration_fact(metric, tag, priority, raw, as_of)
            if parsed is not None:
                facts.append(parsed)
    return facts


def _collect_instant_facts(
    companyfacts: dict[str, Any],
    metric: str,
    tags: Iterable[str],
    as_of: date,
) -> list[Fact]:
    facts: list[Fact] = []
    for priority, tag in enumerate(tags):
        for raw in _raw_usd_facts(companyfacts, tag):
            parsed = _parse_instant_fact(metric, tag, priority, raw, as_of)
            if parsed is not None:
                facts.append(parsed)
    return facts


def _raw_usd_facts(companyfacts: dict[str, Any], tag: str) -> list[dict[str, Any]]:
    facts = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag, {})
    units = facts.get("units", {}) if isinstance(facts, dict) else {}
    usd = units.get("USD", []) if isinstance(units, dict) else []
    return usd if isinstance(usd, list) else []


def _parse_duration_fact(
    metric: str,
    tag: str,
    priority: int,
    raw: dict[str, Any],
    as_of: date,
) -> Fact | None:
    start_raw = raw.get("start")
    end_raw = raw.get("end")
    filed_raw = raw.get("filed")
    if not start_raw or not end_raw or not filed_raw:
        return None

    start = date.fromisoformat(start_raw)
    end = date.fromisoformat(end_raw)
    filed = date.fromisoformat(filed_raw)
    if filed > as_of or end > as_of:
        return None

    return Fact(
        metric=metric,
        tag=tag,
        tag_priority=priority,
        start=start,
        end=end,
        value=float(raw["val"]),
        filed=filed,
        form=str(raw.get("form", "")),
        fy=_optional_int(raw.get("fy")),
        fp=_optional_str(raw.get("fp")),
        frame=_optional_str(raw.get("frame")),
        accession=str(raw.get("accn", "")),
        days=(end - start).days,
    )


def _parse_instant_fact(
    metric: str,
    tag: str,
    priority: int,
    raw: dict[str, Any],
    as_of: date,
) -> Fact | None:
    if raw.get("start"):
        return None
    end_raw = raw.get("end")
    filed_raw = raw.get("filed")
    if not end_raw or not filed_raw:
        return None

    end = date.fromisoformat(end_raw)
    filed = date.fromisoformat(filed_raw)
    if filed > as_of or end > as_of:
        return None

    return Fact(
        metric=metric,
        tag=tag,
        tag_priority=priority,
        start=None,
        end=end,
        value=float(raw["val"]),
        filed=filed,
        form=str(raw.get("form", "")),
        fy=_optional_int(raw.get("fy")),
        fp=_optional_str(raw.get("fp")),
        frame=_optional_str(raw.get("frame")),
        accession=str(raw.get("accn", "")),
        days=0,
    )


def _derive_flow_quarters(metric: str, facts: list[Fact]) -> list[Fact]:
    """从年初至今的累计值推导单季度值。

    SEC 常把现金流项目披露为 Q1、6 个月累计、9 个月累计和全年。
    当缺少单独的三个季度值时，这里推导 Q2、Q3 和 Q4。
    """

    ytd = [fact for fact in facts if fact.start is not None and fact.days >= 70]
    derived: list[Fact] = []

    for current in ytd:
        fiscal_period = _fiscal_period_for_ytd(current.days)
        if fiscal_period is None:
            continue

        candidates = [
            fact
            for fact in ytd
            if fact.start == current.start
            and fact.end < current.end
            and 70 <= (current.end - fact.end).days <= 120
        ]
        if not candidates:
            continue
        previous = max(candidates, key=lambda fact: fact.end)
        same_end = [fact for fact in candidates if fact.end == previous.end]
        previous = min(same_end, key=lambda fact: (fact.filed, fact.tag_priority))
        derived_start = previous.end + timedelta(days=1)
        derived.append(
            Fact(
                metric=metric,
                tag=current.tag,
                tag_priority=current.tag_priority,
                start=derived_start,
                end=current.end,
                value=current.value - previous.value,
                filed=max(current.filed, previous.filed),
                form=current.form,
                fy=current.fy,
                fp=fiscal_period,
                frame=None,
                accession=current.accession,
                days=(current.end - derived_start).days,
                derived=True,
                related_accession=previous.accession,
            )
        )

    return derived


def _fiscal_period_for_ytd(days: int) -> str | None:
    if 150 <= days <= 200:
        return "Q2"
    if 250 <= days <= 290:
        return "Q3"
    if 330 <= days <= 380:
        return "Q4"
    return None


def _latest_four_quarter_ends(revenue_facts: list[Fact], as_of: date) -> list[date]:
    ends = sorted(
        {
            fact.end
            for fact in revenue_facts
            if 70 <= fact.days <= 100 and fact.end <= as_of
        }
    )
    if len(ends) < 4:
        raise ValueError(f"expected at least four quarterly revenue periods, got {len(ends)}")

    latest = ends[-4:]
    for previous, current in zip(latest, latest[1:]):
        if (current - previous).days > 120:
            raise ValueError(f"quarter gap too large: {previous} to {current}")
    return latest


def _best_duration_fact(facts: list[Fact], end: date) -> Fact | None:
    candidates = [
        fact
        for fact in facts
        if fact.end == end and fact.start is not None and 70 <= fact.days <= 100
    ]
    return _best_fact(candidates)


def _best_instant_fact(facts: list[Fact], end: date) -> Fact | None:
    candidates = [fact for fact in facts if fact.end == end and fact.start is None]
    return _best_fact(candidates)


def _best_fact(candidates: list[Fact]) -> Fact | None:
    if not candidates:
        return None
    direct = [fact for fact in candidates if not fact.derived]
    pool = direct or candidates
    return min(pool, key=lambda fact: (fact.tag_priority, fact.filed, fact.value))


def _build_quarter_record(
    *,
    ticker: str,
    cik: str,
    end: date,
    selected: dict[str, Fact],
) -> QuarterRecord:
    revenue = selected["revenue"]
    latest_fact = max(selected.values(), key=lambda fact: (fact.filed, fact.end))
    source_details = []
    for metric in METRIC_ORDER:
        fact = selected[metric]
        derivation = f"derived {fact.fp}" if fact.derived and fact.fp else "reported"
        source_details.append(
            f"{metric}: {fact.tag} {fact.form} filed {fact.filed.isoformat()} "
            f"accn {fact.accession or 'N/A'} ({derivation})"
        )

    return QuarterRecord(
        period=_period_label(revenue),
        period_end_date=end,
        data_date=latest_fact.filed,
        currency="USD",
        revenue=selected["revenue"].value,
        gross_profit=selected["gross_profit"].value,
        net_income=selected["net_income"].value,
        operating_cash_flow=selected["operating_cash_flow"].value,
        capital_expenditure=selected["capital_expenditure"].value,
        total_assets=selected["total_assets"].value,
        total_liabilities=selected["total_liabilities"].value,
        source="SEC EDGAR companyfacts; " + "; ".join(source_details),
        source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
        accession_number=latest_fact.accession or None,
        form_type=latest_fact.form or None,
        filed_date=latest_fact.filed,
        frame=latest_fact.frame,
    )


def _period_label(fact: Fact) -> str:
    fiscal_year = fact.fy if fact.fy is not None else "UNKNOWN"
    fiscal_period = fact.fp or ("Q4" if fact.derived else "NA")
    return f"FY{fiscal_year}-{fiscal_period}"


def _company_name(companyfacts: dict[str, Any]) -> str | None:
    name = companyfacts.get("entityName")
    return str(name) if name else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
