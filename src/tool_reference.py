"""
The browser tool's calculations, in Python, so the JavaScript in web/engine.js can be checked against them.

The tool works on any HRIS export, so it cannot assume this repository's window or columns. It takes
canonical rows (one per employee, already parsed) and the last month of the period, and returns what the
page shows: turnover over the twelve months, by department; survival on tenure time with delayed entry;
what predicts a resignation; warning signs per department, never per person; and the pay gap.

    python3 src/tool_reference.py    writes tests/fixtures/tool_vectors.json

Every definition matches the report's: exits over the average of twelve month-end headcounts; tenure in
months of 30.4375 days; a person enters the survival risk set at the tenure they had when the period began.
"""

from __future__ import annotations

import json
import math
import random
from calendar import monthrange
from datetime import date, timedelta

from hrlib import ROOT, load_employees
from statsx import kaplan_meier, logistic_regression, median, survival_at

VECTORS = ROOT / "tests" / "fixtures" / "tool_vectors.json"
MONTH = 30.4375
SMALL_GROUP = 5            # departments with fewer active people are not shown in the team view


def month_end(y: int, m: int) -> date:
    return date(y, m, monthrange(y, m)[1])


def window(period_end: date) -> tuple[date, list[date]]:
    """First day of the period and the twelve month-ends it is measured on."""
    ends = []
    for back in range(11, -1, -1):
        y, m = divmod(period_end.year * 12 + period_end.month - 1 - back, 12)
        ends.append(month_end(y, m + 1))
    return ends[0].replace(day=1), ends


def months(a: date, b: date) -> float:
    return (b - a).days / MONTH


def whole_months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def signs(r: dict, at: date, reference: date) -> dict[str, bool]:
    """The warning signs a row carries on `at`, for the columns the file has."""
    out = {}
    if r.get("compa") is not None:
        out["below_band"] = r["compa"] < 0.92
    if r.get("msp") is not None:
        out["no_promotion"] = r["msp"] - whole_months(at, reference) > 24
    if r.get("contract") is not None:
        out["fixed_term"] = r["contract"] == "fixed"
    out["first_year"] = whole_months(r["hire"], at) < 12
    if r.get("work_model") is not None:
        out["onsite"] = r["work_model"] == "onsite"
    return out


def analyse(rows: list[dict], period_end: date) -> dict:
    start, ends = window(period_end)
    end = ends[-1]
    in_window = lambda r: r["exit"] is not None and start <= r["exit"] <= end
    active_on = lambda r, d: r["hire"] <= d and (r["exit"] is None or r["exit"] > d)

    def turnover(group):
        avg = sum(sum(1 for r in group if active_on(r, d)) for d in ends) / 12
        vol = sum(1 for r in group if in_window(r) and r["voluntary"])
        allx = sum(1 for r in group if in_window(r))
        return avg, vol, allx

    avg, vol, allx = turnover(rows)
    out = {"start": start.isoformat(), "end": end.isoformat(), "employees": len(rows),
           "active_end": sum(1 for r in rows if active_on(r, end)), "avg_headcount": avg,
           "voluntary": vol, "exits": allx,
           "voluntary_rate": vol / avg if avg else None, "exit_rate": allx / avg if avg else None}

    depts = sorted({r["department"] for r in rows})
    by = []
    for d in depts:
        a, v, _ = turnover([r for r in rows if r["department"] == d])
        by.append({"department": d, "avg_headcount": a, "voluntary": v, "rate": v / a if a else None})
    by.sort(key=lambda x: (-(x["rate"] or 0), x["department"]))
    out["departments"] = by

    # Survival on tenure time, delayed entry at the start of the period
    def subject(r):
        entry = max(0.0, months(r["hire"], start))
        stop = r["exit"] if in_window(r) else end
        if r["exit"] is not None and r["exit"] < start:
            return None
        t = months(r["hire"], stop)
        return (entry, t, int(in_window(r) and r["voluntary"])) if t > entry else None

    subjects = [(s, r) for r in rows if (s := subject(r)) is not None]

    def surv(group):
        curve = kaplan_meier([s for s, _ in group])
        return {str(t): survival_at(curve, t) for t in (12, 24, 36)} if curve else None

    out["survival"] = surv(subjects)
    if any(r.get("compa") is not None for _, r in subjects):
        out["survival_below"] = surv([(s, r) for s, r in subjects if r.get("compa") is not None and r["compa"] < 0.92])
        out["survival_at"] = surv([(s, r) for s, r in subjects if r.get("compa") is not None and r["compa"] >= 0.92])

    # Drivers: people employed on the first day, signs as they stood then, resignations within the period
    top = by[0]["department"] if by and by[0]["rate"] else None
    frame = [r for r in rows if r["hire"] < start and (r["exit"] is None or r["exit"] >= start)]
    feats = [dict(signs(r, start, r["exit"] if in_window(r) else end), **({"top_department": r["department"] == top} if top else {}))
             for r in frame]
    y = [int(in_window(r) and r["voluntary"]) for r in frame]
    names = [k for k in ("below_band", "no_promotion", "fixed_term", "first_year", "onsite", "top_department")
             if feats and all(k in f for f in feats) and 0.01 <= sum(f[k] for f in feats) / len(feats) <= 0.99]
    out["drivers"] = None
    if names and len(frame) >= 50 and 10 <= sum(y) < len(y):
        try:
            fit = logistic_regression([[1.0] + [float(f[k]) for k in names] for f in feats], y, ["intercept"] + names)
            out["drivers"] = {"n": len(frame), "events": sum(y), "top_department": top,
                              "terms": [{"term": k, "odds_ratio": math.exp(fit.get(k)), "p": fit.p(k)} for k in names]}
        except ValueError:
            out["drivers"] = None

    # Team view: active at the end of the period, how many carry two or more signs. Small teams are not shown.
    team = []
    for d in depts:
        members = [r for r in rows if r["department"] == d and active_on(r, end)]
        if len(members) < SMALL_GROUP:
            team.append({"department": d, "active": len(members), "two_or_more": None})
            continue
        flagged = sum(1 for r in members if sum(signs(r, end, end).values()) >= 2)
        team.append({"department": d, "active": len(members), "two_or_more": flagged})
    out["team"] = team

    # Pay gap among active staff at the end, men as the reference, as the Directive measures it
    pay = [r for r in rows if active_on(r, end) and r.get("salary") is not None and r.get("gender") in ("F", "M")]
    women = [r["salary"] for r in pay if r["gender"] == "F"]
    men = [r["salary"] for r in pay if r["gender"] == "M"]
    out["pay"] = None
    if len(women) >= SMALL_GROUP and len(men) >= SMALL_GROUP:
        ordered = sorted(pay, key=lambda r: (r["salary"], r["id"]))
        q = lambda i: 4 * i // len(ordered)
        share = lambda k: (sum(1 for i, r in enumerate(ordered) if q(i) == k and r["gender"] == "F")
                           / sum(1 for i in range(len(ordered)) if q(i) == k))
        mean_m, mean_f = sum(men) / len(men), sum(women) / len(women)
        out["pay"] = {"women": len(women), "men": len(men), "mean_gap": (mean_m - mean_f) / mean_m,
                      "median_gap": (median(men) - median(women)) / median(men),
                      "women_bottom": share(0), "women_top": share(3)}
    return out


# ------------------------------------------------------------------ vectors

def canonical_from_repo() -> list[dict]:
    rows = []
    for e in load_employees():
        rows.append({"id": e["employee_id"], "hire": e["hire_dt"], "exit": e["exit_dt"],
                     "voluntary": e["exit_type"] == "Voluntary", "department": e["department"],
                     "gender": e["gender"], "salary": e["base_salary_eur"], "compa": e["compa_ratio"],
                     "msp": e["months_since_promotion"], "contract": "fixed" if e["contract_type"] == "Fixed-term" else "permanent",
                     "work_model": e["work_model"].lower(), "country": e["country"]})
    return rows


def random_case(rng: random.Random, n: int) -> tuple[list[dict], date]:
    end = month_end(2026, rng.randint(1, 12))
    keep = {k: rng.random() < 0.75 for k in ("compa", "msp", "contract", "work_model", "gender", "salary")}
    depts = rng.sample(["Sales", "Ops", "Tech", "HR", "Finance", "Care"], rng.randint(1, 5))
    rows = []
    for i in range(n):
        hire = end - timedelta(days=rng.randint(1, 3000))
        exit_ = None
        if rng.random() < 0.45:
            exit_ = hire + timedelta(days=rng.randint(1, 3200))
            exit_ = None if exit_ > end + timedelta(days=200) else exit_
        r = {"id": f"R{i:04d}", "hire": hire, "exit": exit_, "voluntary": exit_ is not None and rng.random() < 0.8,
             "department": rng.choice(depts)}
        if keep["compa"]:
            r["compa"] = round(rng.uniform(0.78, 1.2), 3)
        if keep["msp"]:
            r["msp"] = rng.randint(0, 60)
        if keep["contract"]:
            r["contract"] = rng.choice(["fixed", "permanent", "permanent"])
        if keep["work_model"]:
            r["work_model"] = rng.choice(["onsite", "hybrid", "remote"])
        if keep["gender"]:
            r["gender"] = rng.choice(["F", "M", "F", "M", "X"])
        if keep["salary"]:
            r["salary"] = round(rng.uniform(20000, 90000), 2)
        rows.append(r)
    return rows, end


def jsonable(rows: list[dict]) -> dict:
    """Rows as one header and lists of values: the same content in about half the bytes."""
    fields = list(rows[0])
    cell = lambda v: v.isoformat() if isinstance(v, date) else v
    return {"fields": fields, "values": [[cell(r.get(k)) for k in fields] for r in rows]}


def write_vectors() -> int:
    rng = random.Random(2026)
    cases = [{"name": "repository data", "source": "data/employees.csv", "period_end": "2026-06-30",
              "result": analyse(canonical_from_repo(), date(2026, 6, 30))}]
    for k in range(30):
        rows, end = random_case(rng, rng.choice([8, 60, 250, 500]))
        cases.append({"name": f"random {k + 1}", "rows": jsonable(rows), "period_end": end.isoformat(),
                      "result": analyse(rows, end)})
    VECTORS.parent.mkdir(parents=True, exist_ok=True)
    VECTORS.write_text(json.dumps({"cases": cases}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return len(cases)


if __name__ == "__main__":
    print(f"     tests/fixtures/tool_vectors.json ({write_vectors()} cases)")
