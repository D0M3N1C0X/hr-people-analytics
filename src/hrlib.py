"""Shared loading, typing and HR-metric helpers used by all three analyses."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIGURES = ROOT / "reports" / "figures"

SNAPSHOT = date(2026, 6, 30)
WINDOW_START = date(2025, 7, 1)

# The driver model uses a feature window (first 3 months) and a separate
# outcome window (the following 9 months). Measuring predictors before the
# period in which the exit can happen is what keeps the model free of
# look-ahead bias and of the exposure bias that would otherwise make
# short-tenure leavers look like light users of HR services.
FEATURE_END = date(2025, 10, 1)

# Assumption used for the cost of attrition. Published estimates for the fully
# loaded cost of replacing an employee (recruiting, onboarding, lost
# productivity) sit around 20-40% of annual salary for non-executive roles;
# this analysis takes the mid-point and states it openly.
REPLACEMENT_COST_RATE = 0.30

MONTH_LABELS = ["Jul 25", "Aug", "Sep", "Oct", "Nov", "Dec",
                "Jan 26", "Feb", "Mar", "Apr", "May", "Jun"]
# Same twelve months spelled out, for use in sentences rather than on an axis.
MONTH_NAMES = ["July 2025", "August", "September", "October", "November", "December",
               "January 2026", "February", "March", "April", "May", "June"]

INT_FIELDS = ("age", "tenure_months", "months_since_promotion",
              "performance_rating", "engagement_score")
FLOAT_FIELDS = ("fte", "base_salary_eur", "salary_band_mid_eur", "compa_ratio")


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def month_index(d: date) -> int:
    """0-11 position of a date inside the analysis window."""
    return (d.year - WINDOW_START.year) * 12 + (d.month - WINDOW_START.month)


def load_employees() -> list[dict]:
    rows = []
    for r in csv.DictReader((DATA / "employees.csv").open(encoding="utf-8")):
        for f in INT_FIELDS:
            r[f] = int(r[f])
        for f in FLOAT_FIELDS:
            r[f] = float(r[f])
        r["hire_dt"] = date.fromisoformat(r["hire_date"])
        r["exit_dt"] = date.fromisoformat(r["exit_date"]) if r["exit_date"] else None
        r["is_leaver"] = r["exit_dt"] is not None
        r["is_voluntary_leaver"] = r["exit_type"] == "Voluntary"
        r["active"] = not r["is_leaver"]
        # Tenure measured at the start of the window: using tenure at exit as a
        # predictor would leak the outcome into the model.
        r["tenure_at_window_start"] = max(
            0, (WINDOW_START.year - r["hire_dt"].year) * 12
            + (WINDOW_START.month - r["hire_dt"].month))
        r["tenure_band"] = tenure_band(r["tenure_months"])
        rows.append(r)
    return rows


def load_cases() -> list[dict]:
    rows = []
    for r in csv.DictReader((DATA / "hr_cases.csv").open(encoding="utf-8")):
        r["resolution_hours"] = float(r["resolution_hours"])
        for f in ("sla_target_hours", "sla_met", "first_contact_resolution",
                  "reopened", "agent_tenure_months"):
            r[f] = int(r[f])
        r["csat"] = int(r["csat"]) if r["csat"] else None
        r["created_dt"] = date.fromisoformat(r["created_date"])
        r["month"] = month_index(r["created_dt"])
        rows.append(r)
    return rows


def tenure_band(months: int) -> str:
    if months < 6:
        return "0-5 m"
    if months < 12:
        return "6-11 m"
    if months < 24:
        return "1-2 y"
    if months < 60:
        return "2-5 y"
    return "5 y +"


TENURE_ORDER = ["0-5 m", "6-11 m", "1-2 y", "2-5 y", "5 y +"]


def monthly_headcount(employees: list[dict]) -> list[int]:
    """Active headcount at the end of each of the 12 months in the window."""
    counts = []
    for m in range(12):
        y, mo = divmod(WINDOW_START.month - 1 + m, 12)
        month_end = date(WINDOW_START.year + y, mo + 1, 28)
        counts.append(sum(1 for e in employees
                          if e["hire_dt"] <= month_end
                          and (e["exit_dt"] is None or e["exit_dt"] > month_end)))
    return counts


def average_headcount(employees: list[dict]) -> float:
    counts = monthly_headcount(employees)
    return sum(counts) / len(counts)


def turnover_rate(group: list[dict], voluntary_only: bool = True) -> float:
    """Exits over the window as a share of that group's average headcount."""
    avg = average_headcount(group)
    if not avg:
        return 0.0
    leavers = sum(1 for e in group
                  if e["is_leaver"] and (e["is_voluntary_leaver"] or not voluntary_only))
    return leavers / avg * 100


def group_by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return dict(out)


def tenure_hazard(employees: list[dict]) -> list[tuple[str, float]]:
    """Annualised voluntary-exit rate per tenure band, on person-months at risk.

    Dividing leavers by end-of-period headcount would misattribute people who
    age from one band into the next; exposure time is the correct denominator.
    """
    exposure: dict[str, float] = defaultdict(float)
    exits: dict[str, int] = defaultdict(int)

    for m in range(12):
        y, mo = divmod(WINDOW_START.month - 1 + m, 12)
        month_start = date(WINDOW_START.year + y, mo + 1, 1)
        for e in employees:
            if e["hire_dt"] <= month_start and (e["exit_dt"] is None or e["exit_dt"] >= month_start):
                exposure[tenure_band(months_between(e["hire_dt"], month_start))] += 1

    for e in employees:
        if e["is_voluntary_leaver"]:
            exits[tenure_band(months_between(e["hire_dt"], e["exit_dt"]))] += 1

    return [(b, exits[b] / exposure[b] * 12 * 100)
            for b in TENURE_ORDER if exposure.get(b)]


def pct(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}%"


def eur(x: float) -> str:
    return f"EUR {x:,.0f}"


def md_table(headers: list[str], rows: list[list], align: str = "") -> str:
    """Markdown table; `align` is a string of l/r/c, one char per column."""
    align = align or "l" * len(headers)
    sep = {"l": ":---", "r": "---:", "c": ":---:"}
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "| " + " | ".join(sep[a] for a in align) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)
