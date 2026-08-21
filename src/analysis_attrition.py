"""
Module 1 - Attrition & retention.

Four questions a People leadership team actually asks:
  1. How much are we losing, and is it concentrated anywhere?
  2. At what point in the employee lifecycle do we lose them?
  3. Which factors predict leaving, holding the others constant?
  4. What is it costing us, and where would an intervention pay back?

Method note: the driver model is fitted on a *feature window* (Jul-Sep 2025)
and an *outcome window* (Oct 2025 - Jun 2026). Predictors are therefore always
measured before the exit they are used to predict, and everyone in the sample
is exposed to the same 9 months of risk.
"""

from __future__ import annotations

import math
from collections import Counter

import viz
from hrlib import (FEATURE_END, FIGURES, REPLACEMENT_COST_RATE, SNAPSHOT,
                   average_headcount, eur, group_by, load_cases, load_employees,
                   md_table, months_between, pct, tenure_hazard, turnover_rate)
from statsx import logistic_regression, mean, quantile

def build_drivers(worst_dept: str) -> dict:
    """Model terms: report label -> predicate evaluated at FEATURE_END.

    The department term is whichever department has the highest headline
    turnover, so the model always tests the department the descriptive
    analysis just pointed at.
    """
    return {
        "Paid below band (compa-ratio < 0.92)": lambda e: e["compa_ratio"] < 0.92,
        "No promotion in 24+ months": lambda e: e["msp_at_cutoff"] > 24,
        "Engagement in bottom quartile": lambda e: e["engagement_score"] <= e["_eng_q1"],
        "Fixed-term contract": lambda e: e["contract_type"] == "Fixed-term",
        "First year of tenure": lambda e: e["tenure_at_cutoff"] < 12,
        "Fully onsite": lambda e: e["work_model"] == "Onsite",
        f"Works in {worst_dept}": lambda e: e["department"] == worst_dept,
        "Reopened HR case in Q1": lambda e: e["reopened_q1"] >= 1,
    }


def build_model_frame(employees: list[dict], cases: list[dict]) -> list[dict]:
    """Population at risk on 1 Oct 2025, with features frozen at that date."""
    reopened = Counter(c["employee_id"] for c in cases
                       if c["reopened"] and c["created_dt"] < FEATURE_END)
    breached = Counter(c["employee_id"] for c in cases
                       if not c["sla_met"] and c["created_dt"] < FEATURE_END)

    eng_q1 = quantile([e["engagement_score"] for e in employees], 0.25)

    frame = []
    for e in employees:
        if e["hire_dt"] >= FEATURE_END:
            continue                                    # not yet employed
        if e["exit_dt"] and e["exit_dt"] < FEATURE_END:
            continue                                    # already gone
        reference = e["exit_dt"] or SNAPSHOT
        e = dict(e)
        e["tenure_at_cutoff"] = months_between(e["hire_dt"], FEATURE_END)
        e["msp_at_cutoff"] = max(0, e["months_since_promotion"]
                                 - months_between(FEATURE_END, reference))
        e["_eng_q1"] = eng_q1
        e["reopened_q1"] = reopened.get(e["employee_id"], 0)
        e["breached_q1"] = breached.get(e["employee_id"], 0)
        e["left_in_outcome_window"] = int(e["is_voluntary_leaver"])
        frame.append(e)
    return frame


def fit_driver_model(frame: list[dict], drivers: dict):
    names = ["intercept"] + list(drivers)
    X = [[1.0] + [float(test(e)) for test in drivers.values()] for e in frame]
    y = [e["left_in_outcome_window"] for e in frame]
    return logistic_regression(X, y, names)


def run() -> str:
    employees = load_employees()
    cases = load_cases()

    avg_hc = average_headcount(employees)
    voluntary = [e for e in employees if e["is_voluntary_leaver"]]
    regretted = [e for e in voluntary if e["performance_rating"] >= 4]
    vol_rate = turnover_rate(employees)
    all_rate = turnover_rate(employees, voluntary_only=False)

    # ---- 1. where -----------------------------------------------------
    depts = group_by(employees, "department")
    dept_rates = sorted(((d, turnover_rate(rows)) for d, rows in depts.items()),
                        key=lambda kv: -kv[1])
    worst_dept, worst_rate = dept_rates[0]
    worst_share = sum(1 for e in voluntary if e["department"] == worst_dept) / len(voluntary)

    viz.bar_chart(
        FIGURES / "01_turnover_by_department.svg",
        [d for d, _ in dept_rates], [r for _, r in dept_rates],
        "Voluntary turnover by department",
        f"12 months to Jun 2026 - exits as % of average headcount ({avg_hc:,.0f} employees)",
        "turnover %", fmt=lambda v: f"{v:.1f}%",
        highlight={worst_dept}, target=vol_rate,
        target_label=f"company average {vol_rate:.1f}%")

    # ---- 2. when ------------------------------------------------------
    hazard = tenure_hazard(employees)
    rate = dict(hazard)
    first_year = mean([r for b, r in hazard if b in ("0-5 m", "6-11 m")])
    settled = mean([r for b, r in hazard if b in ("2-5 y", "5 y +")])
    dip = min(hazard, key=lambda kv: kv[1])

    viz.bar_chart(
        FIGURES / "02_turnover_by_tenure.svg",
        [b for b, _ in hazard], [r for _, r in hazard],
        "Voluntary exit rate by tenure band",
        "Annualised, on person-months at risk - not on end-of-period headcount",
        "annualised exit rate %", fmt=lambda v: f"{v:.1f}%", color=viz.VIOLET)

    # ---- 3. drivers ---------------------------------------------------
    frame = build_model_frame(employees, cases)
    drivers = build_drivers(worst_dept)
    model = fit_driver_model(frame, drivers)
    terms = sorted(((name, math.exp(model.get(name)), model.p(name)) for name in drivers),
                   key=lambda t: -t[1])

    viz.lollipop_chart(
        FIGURES / "03_turnover_drivers.svg",
        [t[0] for t in terms], [t[1] for t in terms],
        "What predicts a voluntary exit",
        f"Logistic regression, n = {model.n:,} at risk - odds ratios, other factors held constant",
        xlabel="odds ratio  (1.0 = no effect)", fmt=lambda v: f"{v:.2f}x", reference=1.0)

    reasons = Counter(e["exit_reason"] for e in voluntary).most_common()
    pay_and_career = sum(c for r, c in reasons if r in ("Compensation", "Career progression"))
    viz.bar_chart(
        FIGURES / "04_exit_reasons.svg",
        [r for r, _ in reasons], [c for _, c in reasons],
        "Stated reasons for voluntary exit",
        f"{len(voluntary)} leavers - pay and progression together account for "
        f"{pay_and_career / len(voluntary):.0%} of exits",
        "leavers", color=viz.AMBER)

    # ---- 4. cost ------------------------------------------------------
    cost_all = sum(e["base_salary_eur"] for e in voluntary) * REPLACEMENT_COST_RATE
    cost_regretted = sum(e["base_salary_eur"] for e in regretted) * REPLACEMENT_COST_RATE

    below_band = [e for e in employees if e["active"] and e["compa_ratio"] < 0.92]
    uplift_cost = sum(e["salary_band_mid_eur"] * 0.95 - e["base_salary_eur"] for e in below_band)
    or_pay = math.exp(model.get("Paid below band (compa-ratio < 0.92)"))
    avoided = len(below_band) * (vol_rate / 100) * (1 - 1 / or_pay)
    avoided_cost = avoided * mean([e["base_salary_eur"] for e in below_band]) * REPLACEMENT_COST_RATE

    # Composition vs culture: is the worst department still worse once the
    # model controls for who works there and how they are paid?
    dept_term = f"Works in {worst_dept}"
    or_dept = math.exp(model.get(dept_term))
    p_dept = model.p(dept_term)
    composition_note = (
        f"Note what the model does to {worst_dept}. On its own it is the worst performer in "
        f"the company; inside the regression the department term falls to **{or_dept:.2f}x** "
        f"(p = {p_dept:.2f}), which is not distinguishable from the rest of the business. "
        f"{worst_dept} does not have a culture problem - it has a composition problem: it holds "
        "a disproportionate share of below-band salaries, fixed-term contracts and first-year "
        "staff. Fix those three and the department gap closes on its own."
        if p_dept >= 0.05 else
        f"{worst_dept} keeps a significant effect of **{or_dept:.2f}x** (p = {p_dept:.3f}) even "
        "after controlling for pay position, contract type and tenure, so something specific to "
        "that function - workload, scheduling or management - is driving exits beyond composition.")

    or_case = math.exp(model.get("Reopened HR case in Q1"))
    p_case = model.p("Reopened HR case in Q1")
    case_verdict = (
        f"the effect survives the regression at **{or_case:.2f}x** (p = {p_case:.3f})"
        if p_case < 0.05 else
        f"in the model the effect is directionally the same ({or_case:.2f}x) but not "
        f"statistically distinguishable from zero at this sample size (p = {p_case:.2f}), "
        "so it belongs on a watch-list rather than in a business case")
    friction = [e for e in frame if e["reopened_q1"] >= 1]
    clean = [e for e in frame if e["reopened_q1"] == 0]
    friction_rate = sum(e["left_in_outcome_window"] for e in friction) / len(friction) * 100
    clean_rate = sum(e["left_in_outcome_window"] for e in clean) / len(clean) * 100

    md = [
        "## 1. Attrition & retention",
        "",
        f"**Headline.** Average headcount over the window is **{avg_hc:,.0f}**. Voluntary "
        f"turnover is **{pct(vol_rate)}** ({len(voluntary)} exits); total turnover, including "
        f"dismissals and end-of-contract, is **{pct(all_rate)}**. **{len(regretted)}** voluntary "
        f"leavers - **{len(regretted) / len(voluntary):.0%}** of them - held a performance rating "
        "of 4 or 5, so a quarter of the loss sits in the population you least want to lose.",
        "",
        f"**Where it is concentrated.** {worst_dept} runs at **{pct(worst_rate)}**, "
        f"**{worst_rate - vol_rate:+.1f} pp** against the company average. It carries "
        f"{len(depts[worst_dept]) / len(employees):.0%} of the workforce but produces "
        f"**{worst_share:.0%}** of all voluntary exits.",
        "",
        "![Voluntary turnover by department](figures/01_turnover_by_department.svg)",
        "",
        md_table(["Department", "Headcount share", "Voluntary turnover", "vs average"],
                 [[d, f"{len(depts[d]) / len(employees):.0%}", pct(r), f"{r - vol_rate:+.1f} pp"]
                  for d, r in dept_rates], align="lrrr"),
        "",
        f"**When people leave.** On person-months at risk, the first year runs at "
        f"**{first_year:.1f}%** annualised against **{settled:.1f}%** for staff past two years - "
        f"a **{first_year / settled:.1f}x** difference. Early attrition is an onboarding, "
        "manager-quality and expectation-setting problem; it is rarely solved with money.",
        "",
        "![Voluntary exit rate by tenure](figures/02_turnover_by_tenure.svg)",
        "",
        f"The curve is not a straight line down. It bottoms out at **{dip[1]:.1f}%** in the "
        f"{dip[0]} band and then climbs again to **{rate['5 y +']:.1f}%** for the longest-serving "
        "staff. Those are two different problems wearing the same number: the first year is "
        "onboarding and expectation-setting, the later rise is promotion stagnation. A single "
        "retention programme aimed at 'attrition' would miss both.",
        "",
        "### Driver analysis",
        "",
        f"Logistic regression on the **{model.n:,} employees at risk on 1 Oct 2025**, predicting "
        "a voluntary exit in the following nine months from factors measured *before* that date. "
        "Odds ratios are read against a colleague who does not have the factor, with everything "
        "else in the model held constant - so overlapping effects (people below band are often "
        "also people waiting on a promotion) are not counted twice.",
        "",
        "![Odds ratios](figures/03_turnover_drivers.svg)",
        "",
        md_table(["Factor", "Odds ratio", "p-value", "% of population"],
                 [[name, f"{od:.2f}x", f"{p:.3f}" if p >= 0.001 else "<0.001",
                   f"{sum(1 for e in frame if drivers[name](e)) / len(frame):.0%}"]
                  for name, od, p in terms], align="lrrr"),
        "",
        f"Pseudo-R2 (McFadden) = {model.r2:.3f}. The model ranks risk; it does not prove "
        "causation, and every factor here is something HR can act on.",
        "",
        composition_note,
        "",
        f"**Cross-dataset finding.** Employees who had an HR case **reopened** in the feature "
        f"window went on to resign at **{friction_rate:.1f}%** over the next nine months, "
        f"against **{clean_rate:.1f}%** for everyone else; {case_verdict}. "
        "A reopened case is rarely about the case: it signals an unresolved problem with pay, "
        "contract or manager. HR service quality is a retention variable, not only an "
        "efficiency one.",
        "",
        "![Exit reasons](figures/04_exit_reasons.svg)",
        "",
        "### What it costs",
        "",
        f"At **{REPLACEMENT_COST_RATE:.0%} of annual base salary** per replacement - the "
        "mid-point of the 20-40% range commonly cited for non-executive roles, covering "
        f"recruiting, onboarding and lost productivity - the {len(voluntary)} voluntary exits "
        f"carry an estimated **{eur(cost_all)}**, of which **{eur(cost_regretted)}** sits with "
        "the high-performer group.",
        "",
        f"**Illustrative intervention.** {len(below_band)} active employees "
        f"({len(below_band) / sum(1 for e in employees if e['active']):.0%} of the active "
        f"population) sit below 0.92 compa-ratio. Bringing them to 0.95 of band costs "
        f"**{eur(uplift_cost)}** a year. Applying the estimated odds ratio to the base rate, "
        f"that population would produce roughly **{avoided:.0f} fewer resignations**, worth "
        f"about **{eur(avoided_cost)}** in avoided replacement cost - it recovers "
        f"**{avoided_cost / uplift_cost:.0%}** of the uplift bill in year one, before the "
        "productivity of the people who stay. Read honestly, that says a blanket uplift does "
        "not pay for itself: the version worth piloting is the targeted one, taking the "
        f"below-band population inside {worst_dept} and the fixed-term cohort, where the odds "
        "ratios are highest and the salaries lowest. The estimate comes from an observational "
        "model and sizes the prize; it is not a causal guarantee.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
