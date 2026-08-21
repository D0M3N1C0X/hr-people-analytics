"""
Synthetic HR dataset generator.

Creates two linked, deliberately *messy but realistic* datasets for a European
shared-services organisation (~4,000 people across IT / PL / DE / ES):

    data/employees.csv  - one row per employee, snapshot 2026-06-30
    data/hr_cases.csv   - one row per HR service-desk case, 12-month window

No real people are involved. The generator plants a handful of known effects
(pay-level segregation, promotion stagnation, case-handling friction) so the
analyses in `src/analysis_*.py` have something true to find; the strength of
each effect is documented in data/README.md.

Everything is stdlib + a fixed seed, so the datasets are byte-identical on
every machine.
"""

from __future__ import annotations

import csv
import math
import random
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SEED = 42
SNAPSHOT = date(2026, 6, 30)          # "today" for the headcount snapshot
WINDOW_START = date(2025, 7, 1)       # analysis window: 12 months to snapshot
N_EMPLOYEES = 4000

rng = random.Random(SEED)

# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

# Country -> (share of workforce, L1 annual base salary EUR, site name)
COUNTRIES = {
    "IT": (0.30, 26_000, "Milan"),
    "PL": (0.34, 21_000, "Krakow"),
    "DE": (0.21, 38_000, "Munich"),
    "ES": (0.15, 25_000, "Barcelona"),
}

# Department -> (share, pay multiplier, share of women)
DEPARTMENTS = {
    "Customer Service": (0.30, 0.90, 0.62),
    "Operations": (0.24, 0.95, 0.42),
    "Tech": (0.15, 1.25, 0.28),
    "Sales": (0.13, 1.05, 0.45),
    "Finance": (0.10, 1.10, 0.52),
    "HR": (0.08, 1.00, 0.72),
}

# Level -> (share, pay multiplier, share of women at this level)
# The declining female share up the ladder is the vertical segregation that
# drives most of the raw pay gap - the point the pay-equity analysis makes.
LEVELS = {
    "L1": (0.26, 1.00, 0.62),
    "L2": (0.30, 1.25, 0.57),
    "L3": (0.22, 1.60, 0.46),
    "L4": (0.13, 2.10, 0.34),
    "L5": (0.07, 2.90, 0.24),
    "L6": (0.02, 4.00, 0.15),
}

CONTRACTS = {"Permanent": 0.86, "Fixed-term": 0.14}
WORK_MODELS = {"Hybrid": 0.52, "Onsite": 0.31, "Remote": 0.17}

VOLUNTARY_REASONS = [
    "Better external offer",
    "Career progression",
    "Compensation",
    "Manager / leadership",
    "Work-life balance",
    "Relocation",
    "Personal reasons",
]

CASE_CATEGORIES = {
    # category -> (share of volume, SLA target in hours, base difficulty)
    "Payroll": (0.26, 24, 1.20),
    "Leave & Absence": (0.21, 24, 0.85),
    "Contract & Documents": (0.15, 48, 1.00),
    "Benefits": (0.11, 48, 0.90),
    "Systems & Access": (0.10, 8, 0.70),
    "Onboarding & Offboarding": (0.08, 48, 1.10),
    "Performance & Development": (0.05, 72, 1.30),
    "Employee Relations": (0.04, 72, 1.80),
}

CHANNELS = {"Portal": 0.54, "Phone": 0.28, "Chat": 0.18}
PRIORITIES = {"Standard": 0.72, "High": 0.22, "Critical": 0.06}

# Seasonality multipliers by calendar month (1-12) per category family.
# Payroll spikes at year-end/tax season, leave spikes before summer and Christmas.
PAYROLL_SEASON = {1: 2.10, 2: 1.70, 3: 1.15, 4: 0.90, 5: 0.85, 6: 0.90,
                  7: 0.95, 8: 0.80, 9: 0.90, 10: 0.95, 11: 1.05, 12: 1.45}
LEAVE_SEASON = {1: 0.85, 2: 0.80, 3: 0.90, 4: 1.00, 5: 1.15, 6: 1.25,
                7: 1.10, 8: 0.70, 9: 0.90, 10: 0.90, 11: 1.05, 12: 1.20}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def pick(weights: dict) -> str:
    """Weighted choice over a {key: (share, ...)} or {key: share} mapping."""
    keys = list(weights)
    w = [weights[k][0] if isinstance(weights[k], tuple) else weights[k] for k in keys]
    return rng.choices(keys, weights=w, k=1)[0]


def months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    year, month = d.year + m // 12, m % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                      else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------
# Employees
# --------------------------------------------------------------------------

def make_employees() -> list[dict]:
    employees: list[dict] = []

    for i in range(1, N_EMPLOYEES + 1):
        country = pick(COUNTRIES)
        department = pick(DEPARTMENTS)
        level = pick(LEVELS)

        # Gender: blend of the department mix and the level mix, so both
        # horizontal and vertical segregation show up in the data.
        p_female = 0.35 * DEPARTMENTS[department][2] + 0.65 * LEVELS[level][2]
        gender = "F" if rng.random() < clamp(p_female, 0.05, 0.95) else "M"

        # Tenure: skewed towards recent hires, capped at ~14 years.
        tenure_months = int(min(168, rng.expovariate(1 / 42) + rng.random() * 6))
        hire_date = add_months(SNAPSHOT, -tenure_months) + timedelta(days=rng.randint(0, 27))
        if hire_date > SNAPSHOT:
            hire_date = SNAPSHOT - timedelta(days=rng.randint(1, 30))
        tenure_months = months_between(hire_date, SNAPSHOT)

        age = int(clamp(rng.gauss(24 + tenure_months / 12 * 1.4 + rng.random() * 12, 6), 20, 63))

        contract = "Fixed-term" if (tenure_months < 18 and rng.random() < 0.32) else pick(CONTRACTS)
        work_model = pick(WORK_MODELS)

        # ---- Pay -------------------------------------------------------
        band_mid = COUNTRIES[country][1] * LEVELS[level][1] * DEPARTMENTS[department][1]
        band_mid = round(band_mid / 100) * 100

        seniority_uplift = clamp(0.0045 * tenure_months, 0, 0.13)  # progression in band
        noise = rng.gauss(0, 0.085)
        # Residual, unexplained gender effect *within* level and country.
        # Deliberately small (~2%): the interesting story is the level mix.
        gender_residual = -0.021 if gender == "F" else 0.0
        salary = band_mid * (0.90 + seniority_uplift + noise + gender_residual)
        salary = round(salary / 50) * 50
        compa_ratio = round(salary / band_mid, 3)

        # ---- Career / engagement ---------------------------------------
        # Time since last promotion (or since hire for those never promoted).
        never_promoted = rng.random() < 0.42
        if never_promoted or tenure_months < 14:
            months_since_promotion = tenure_months
        else:
            months_since_promotion = int(rng.triangular(1, min(tenure_months, 54), 16))

        performance = rng.choices([1, 2, 3, 4, 5], weights=[4, 14, 55, 22, 5], k=1)[0]

        # "hr_friction" is a latent trait: people whose HR issues keep coming
        # back. It feeds BOTH the case data and the attrition hazard, which is
        # what lets the cross-dataset finding in analysis_attrition.py exist.
        hr_friction = clamp(rng.gauss(0.5, 0.22)
                            + (0.10 if country == "IT" else 0)
                            + (0.08 if contract == "Fixed-term" else 0), 0.02, 0.98)

        engagement = (72
                      - 16 * (compa_ratio < 0.92)
                      - 11 * (months_since_promotion > 24)
                      - 7 * hr_friction
                      + 5 * (performance >= 4)
                      + 4 * (work_model == "Hybrid")
                      - 4 * (department == "Customer Service")
                      + rng.gauss(0, 8))
        engagement = int(clamp(engagement, 5, 100))

        employees.append({
            "employee_id": f"E{i:05d}",
            "hire_date": hire_date.isoformat(),
            "exit_date": "",
            "exit_type": "",
            "exit_reason": "",
            "country": country,
            "site": COUNTRIES[country][2],
            "department": department,
            "job_level": level,
            "gender": gender,
            "age": age,
            "contract_type": contract,
            "work_model": work_model,
            "fte": 1.0 if rng.random() > 0.07 else 0.8,
            "base_salary_eur": salary,
            "salary_band_mid_eur": band_mid,
            "compa_ratio": compa_ratio,
            "tenure_months": tenure_months,
            "months_since_promotion": months_since_promotion,
            "performance_rating": performance,
            "engagement_score": engagement,
            "_hr_friction": hr_friction,   # latent, dropped before writing
        })

    simulate_exits(employees)
    return employees


def simulate_exits(employees: list[dict]) -> None:
    """Month-by-month exit hazard over the 12-month analysis window."""
    for e in employees:
        hire = date.fromisoformat(e["hire_date"])

        for m in range(12):
            month_start = add_months(WINDOW_START, m)
            if hire > month_start:
                continue

            tenure_at_month = months_between(hire, month_start)
            msp = max(0, e["months_since_promotion"] - (12 - m))

            logit = (-6.90
                     + 0.85 * (e["compa_ratio"] < 0.92)
                     + 0.70 * (msp > 24 and e["job_level"] in ("L1", "L2", "L3"))
                     + 1.10 * (e["engagement_score"] <= 45)
                     + 0.55 * (45 < e["engagement_score"] <= 62)
                     + 0.90 * (tenure_at_month < 12)
                     + 0.50 * (e["contract_type"] == "Fixed-term")
                     + 0.45 * (e["department"] == "Customer Service")
                     + 0.25 * (e["work_model"] == "Onsite")
                     + 0.30 * (e["country"] == "PL")
                     + 1.80 * e["_hr_friction"]
                     - 0.30 * (e["performance_rating"] <= 2))

            if rng.random() < logistic(logit):
                exit_day = month_start + timedelta(days=rng.randint(0, 27))
                if exit_day <= hire:
                    continue
                voluntary = rng.random() < 0.84
                e["exit_date"] = exit_day.isoformat()
                e["exit_type"] = "Voluntary" if voluntary else "Involuntary"
                e["exit_reason"] = _exit_reason(e) if voluntary else rng.choice(
                    ["Performance", "Restructuring", "End of fixed-term contract", "Conduct"])
                # Freeze the clocks at the exit date: a leaver's tenure and
                # time-since-promotion must not keep running to the snapshot.
                months_after_exit = months_between(exit_day, SNAPSHOT)
                e["tenure_months"] = months_between(hire, exit_day)
                e["months_since_promotion"] = max(0, e["months_since_promotion"] - months_after_exit)
                break


def _exit_reason(e: dict) -> str:
    """Leaving reason, weighted by what was actually wrong for that person."""
    w = {
        "Better external offer": 1.0,
        "Career progression": 1.0 + 1.6 * (e["months_since_promotion"] > 24),
        "Compensation": 1.0 + 1.8 * (e["compa_ratio"] < 0.92),
        "Manager / leadership": 1.0 + 1.2 * (e["engagement_score"] <= 45),
        "Work-life balance": 1.0 + 0.8 * (e["department"] == "Customer Service"),
        "Relocation": 0.6,
        "Personal reasons": 0.7,
    }
    return rng.choices(list(w), weights=list(w.values()), k=1)[0]


# --------------------------------------------------------------------------
# HR service-desk cases
# --------------------------------------------------------------------------

def make_agents(n: int = 42) -> list[dict]:
    agents = []
    for i in range(1, n + 1):
        tenure = int(clamp(rng.expovariate(1 / 22) + 1, 1, 96))
        agents.append({
            "agent_id": f"A{i:03d}",
            "agent_tenure_months": tenure,
            "language": rng.choice(["IT", "PL", "DE", "ES", "EN"]),
        })
    return agents


def make_cases(employees: list[dict], agents: list[dict]) -> list[dict]:
    """Two passes: draw the demand, then let a fixed-capacity desk struggle with it.

    Pass 1 draws every case and its intrinsic difficulty. Pass 2 applies a
    congestion factor: agent capacity is flat across the year, so when monthly
    demand runs above average, handling time stretches super-linearly - the
    ordinary queueing behaviour of a service desk. SLA, first-contact
    resolution, reopens and CSAT are all resolved after congestion is known,
    because in reality they are consequences of it.
    """
    drafts: list[dict] = []

    for e in employees:
        hire = date.fromisoformat(e["hire_date"])
        exit_d = date.fromisoformat(e["exit_date"]) if e["exit_date"] else None

        # Contact volume: everyone contacts HR sometimes, frustrated people more.
        expected = (7.5 * (0.55 + e["_hr_friction"])
                    + 3.0 * (months_between(hire, SNAPSHOT) < 12)
                    + 2.0 * (e["contract_type"] == "Fixed-term"))
        n_cases = max(0, int(rng.gauss(expected, 3)))

        for _ in range(n_cases):
            created = _draw_created_date()
            if created < hire or (exit_d and created > exit_d + timedelta(days=30)):
                continue

            category = _seasonal_category(created.month)
            _share, sla_hours, difficulty = CASE_CATEGORIES[category]
            priority = pick(PRIORITIES)
            agent = rng.choice(agents)

            base_hours = rng.lognormvariate(math.log(sla_hours * 0.42 * difficulty), 0.8)
            base_hours *= 0.65 if priority == "Critical" else (0.85 if priority == "High" else 1.0)
            base_hours *= 1.25 if agent["agent_tenure_months"] < 6 else 1.0
            base_hours *= 1 + 0.5 * e["_hr_friction"]

            drafts.append({
                "employee": e, "agent": agent, "created": created,
                "category": category, "priority": priority, "channel": pick(CHANNELS),
                "sla_hours": sla_hours, "difficulty": difficulty, "base_hours": base_hours,
            })

    # ---- pass 2: congestion ------------------------------------------
    volume = Counter(d["created"].month for d in drafts)
    avg_volume = sum(volume.values()) / 12
    # Capacity is not perfectly flat either - holidays, sickness, a good month.
    # Without this, SLA would be a deterministic function of volume.
    capacity_shock = {m: math.exp(rng.gauss(0, 0.11)) for _y, m in WINDOW_MONTHS}

    cases: list[dict] = []
    for i, d in enumerate(sorted(drafts, key=lambda d: d["created"]), start=1):
        e, agent = d["employee"], d["agent"]
        month = d["created"].month
        load = (volume[month] / avg_volume * capacity_shock[month]) ** 1.7
        resolution_hours = round(clamp(d["base_hours"] * load, 0.2, 400), 1)
        sla_met = int(resolution_hours <= d["sla_hours"])

        fcr = int(rng.random() < clamp(0.80 - 0.30 * d["difficulty"] / 2
                                       - 0.22 * (agent["agent_tenure_months"] < 6)
                                       - 0.18 * (1 - sla_met), 0.15, 0.95))
        reopened = int((not fcr) and rng.random() < clamp(0.02 + 0.62 * e["_hr_friction"]
                                                         + 0.15 * (1 - sla_met), 0, 0.6))

        # CSAT is only collected on ~45% of cases (survey response bias is real).
        csat = ""
        if rng.random() < 0.45:
            score = (4.55
                     - 1.30 * (1 - sla_met)
                     - 0.95 * reopened
                     + 0.35 * fcr
                     - 0.30 * (d["category"] == "Employee Relations")
                     + rng.gauss(0, 0.55))
            csat = int(clamp(round(score), 1, 5))

        created_dt = datetime.combine(d["created"], time(rng.randint(8, 17), rng.randint(0, 59)))
        cases.append({
            "case_id": f"C{i:06d}",
            "employee_id": e["employee_id"],
            "created_date": d["created"].isoformat(),
            "resolved_date": (created_dt + timedelta(hours=resolution_hours)).date().isoformat(),
            "country": e["country"],
            "department": e["department"],
            "category": d["category"],
            "priority": d["priority"],
            "channel": d["channel"],
            "agent_id": agent["agent_id"],
            "agent_tenure_months": agent["agent_tenure_months"],
            "sla_target_hours": d["sla_hours"],
            "resolution_hours": resolution_hours,
            "sla_met": sla_met,
            "first_contact_resolution": fcr,
            "reopened": reopened,
            "csat": csat,
        })
    return cases


WINDOW_MONTHS = [(2025, 7 + i) if 7 + i <= 12 else (2026, i - 5) for i in range(12)]
DAYS_IN_MONTH = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def _month_demand(month: int) -> float:
    """Relative case demand for a calendar month, summed over all categories."""
    total = 0.0
    for cat, (cat_share, _sla, _diff) in CASE_CATEGORIES.items():
        w = cat_share
        if cat == "Payroll":
            w *= PAYROLL_SEASON[month]
        elif cat == "Leave & Absence":
            w *= LEAVE_SEASON[month]
        elif cat == "Onboarding & Offboarding" and month in (1, 9):
            w *= 1.35
        total += w
    return total


def _draw_created_date() -> date:
    """Case date drawn from the seasonal demand curve, not uniformly."""
    weights = [_month_demand(m) for _y, m in WINDOW_MONTHS]
    year, month = rng.choices(WINDOW_MONTHS, weights=weights, k=1)[0]
    return date(year, month, rng.randint(1, DAYS_IN_MONTH[month]))


def _seasonal_category(month: int) -> str:
    """Category draw with month-of-year seasonality applied."""
    keys, weights = [], []
    for cat, (share, _sla, _diff) in CASE_CATEGORIES.items():
        w = share
        if cat == "Payroll":
            w *= PAYROLL_SEASON[month]
        elif cat == "Leave & Absence":
            w *= LEAVE_SEASON[month]
        elif cat == "Onboarding & Offboarding" and month in (1, 9):
            w *= 1.35
        keys.append(cat)
        weights.append(w)
    return rng.choices(keys, weights=weights, k=1)[0]


# --------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict], drop: tuple[str, ...] = ()) -> None:
    fields = [f for f in rows[0] if f not in drop]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)

    employees = make_employees()
    agents = make_agents()
    cases = make_cases(employees, agents)

    write_csv(DATA / "employees.csv", employees, drop=("_hr_friction",))
    write_csv(DATA / "hr_cases.csv", cases)

    leavers = [e for e in employees if e["exit_date"]]
    active = len(employees) - len(leavers)
    print(f"employees.csv : {len(employees):>6,} rows ({active:,} active at {SNAPSHOT}, "
          f"{len(leavers):,} exits in the 12-month window)")
    print(f"hr_cases.csv  : {len(cases):>6,} rows "
          f"({WINDOW_START} to {SNAPSHOT})")


if __name__ == "__main__":
    main()
