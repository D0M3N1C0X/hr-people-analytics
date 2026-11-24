"""
Module 1d - When people leave, not only whether: survival analysis.

The tenure curve in module 1 counts exits per person-month in each tenure band. Survival analysis
asks the question a workforce plan needs: of a hundred people hired today, how many are still here
after one, two, three years, and how much does pay position change that?

Time is tenure in months. The data covers twelve calendar months, so someone hired in 2019 only
enters observation with six years of tenure: that is delayed entry (left truncation), and the
estimator has to start counting them there. Treating them as if observed since their first day
would credit the organisation with every early leaver it never saw.
"""

from __future__ import annotations

import math
from datetime import date

import viz
from hrlib import FIGURES, SNAPSHOT, WINDOW_START, load_employees, md_table
from statsx import cox, kaplan_meier, logrank, quantile, restricted_mean, survival_at

MONTH = 30.4375
HORIZON = 36            # months: the window for the expected time stayed


def months(a: date, b: date) -> float:
    return (b - a).days / MONTH


def subjects_of(employees: list[dict], delayed_entry: bool = True) -> list[tuple[float, float, int]]:
    """(entry, exit, voluntary exit) in tenure months; involuntary exits and the snapshot censor."""
    out = []
    for e in employees:
        start = max(0.0, months(e["hire_dt"], WINDOW_START)) if delayed_entry else 0.0
        end = months(e["hire_dt"], e["exit_dt"] or SNAPSHOT)
        if end > start:
            out.append((start, end, int(e["is_voluntary_leaver"])))
    return out


def curve_points(curve, xmax: float = 60) -> list[tuple[float, float]]:
    pts, s = [(0.0, 100.0)], 100.0
    for t, surv, _, _ in curve:
        if t > xmax:
            break
        pts += [(t, s), (t, 100 * surv)]            # steps, as a survival curve is
        s = 100 * surv
    return pts + [(xmax, s)]


def split_at(subjects, X, at: float):
    """Episode-split each subject at `at` months, adding a flag for the later episode (for time-varying effects)."""
    s2, x2 = [], []
    for (a, b, e), row in zip(subjects, X):
        if a < at < b:
            s2 += [(a, at, 0), (at, b, e)]
            x2 += [row + [0.0], row + [1.0]]
        else:
            s2.append((a, b, e))
            x2.append(row + [float(a >= at)])
    return s2, x2


def first_year() -> float:
    """Share of hires still employed after twelve months (voluntary exits, delayed entry): the report's headline."""
    employees = load_employees()
    eligible = [e for e in employees if months(e["hire_dt"], e["exit_dt"] or SNAPSHOT) > max(0.0, months(e["hire_dt"], WINDOW_START))]
    return survival_at(kaplan_meier(subjects_of(eligible)), 12)


def run() -> str:
    employees = load_employees()
    eligible = [e for e in employees if months(e["hire_dt"], e["exit_dt"] or SNAPSHOT) > max(0.0, months(e["hire_dt"], WINDOW_START))]
    subjects = subjects_of(eligible)
    naive = subjects_of(eligible, delayed_entry=False)
    km, km_naive = kaplan_meier(subjects), kaplan_meier(naive)

    below = [int(e["compa_ratio"] < 0.92) for e in eligible]
    fixed = [int(e["contract_type"] == "Fixed-term") for e in eligible]
    km_below = kaplan_meier([s for s, g in zip(subjects, below) if g])
    km_at = kaplan_meier([s for s, g in zip(subjects, below) if not g])
    chi_pay, p_pay = logrank(subjects, below)
    chi_fix, p_fix = logrank(subjects, fixed)
    rm_below, rm_at = restricted_mean(km_below, HORIZON), restricted_mean(km_at, HORIZON)

    eng_q1 = quantile([e["engagement_score"] for e in eligible], 0.25)
    worst = "Customer Service"
    terms = {
        "Paid below band (compa-ratio < 0.92)": lambda e: e["compa_ratio"] < 0.92,
        "Fixed-term contract": lambda e: e["contract_type"] == "Fixed-term",
        "Engagement in bottom quartile": lambda e: e["engagement_score"] <= eng_q1,
        "Fully onsite": lambda e: e["work_model"] == "Onsite",
        f"Works in {worst}": lambda e: e["department"] == worst,
    }
    X = [[float(f(e)) for f in terms.values()] for e in eligible]
    fit = cox(subjects, X, list(terms))
    hrs = sorted(((n, math.exp(fit.get(n)), fit.p(n)) for n in terms), key=lambda t: -t[1])

    # Does being paid below band matter as much in the first year as later? Split tenure at 12 months.
    pay = 0
    s2, x2 = split_at(subjects, [[row[pay]] for row in X], 12.0)
    # "after year one" alone is a function of time, the same for everyone at risk at any moment, so the
    # baseline hazard absorbs it; only its interaction with pay can be estimated.
    x2 = [[r[0], r[0] * r[1]] for r in x2]
    tv = cox(s2, x2, ["below band", "below band x after year one"])
    hr_first = math.exp(tv.get("below band"))
    hr_later = math.exp(tv.get("below band") + tv.get("below band x after year one"))
    p_inter = tv.p("below band x after year one")

    viz.xy_chart(
        FIGURES / "17_survival_by_pay.svg",
        {"paid at or above 0.92 of band": curve_points(km_at), "paid below 0.92 of band": curve_points(km_below),
         "everyone, ignoring late entry (wrong)": curve_points(km_naive)},
        "Still here, by months of tenure",
        "Kaplan-Meier with delayed entry; voluntary exits only - the dashed line is what ignoring late entry would say",
        xlabel="months since hire", ylabel="still employed", xmax=60, xticks=[0, 12, 24, 36, 48, 60],
        xfmt=lambda v: f"{v:.0f}", ymin=0, diagonal=False, dashed={"everyone, ignoring late entry (wrong)"})
    viz.lollipop_chart(
        FIGURES / "18_hazard_ratios.svg", [n for n, _, _ in hrs], [h for _, h, _ in hrs],
        "What speeds up a resignation",
        f"Cox model on tenure time, {fit.extra['events']} voluntary exits - hazard ratios, other factors held constant",
        xlabel="hazard ratio  (1.0 = no effect)", fmt=lambda v: f"{v:.2f}x", reference=1.0)

    s12, s24, s36 = (survival_at(km, t) for t in (12, 24, 36))
    n12 = survival_at(km_naive, 12)
    rows = [[f"{t} months", f"{survival_at(km, t):.0%}", f"{survival_at(km_at, t):.0%}", f"{survival_at(km_below, t):.0%}"]
            for t in (6, 12, 24, 36, 60)]

    md = [
        "### When people leave: survival on tenure time",
        "",
        "Odds ratios say who is more likely to leave within a window. A workforce plan needs the other "
        "question: of a hundred people hired, how many are still here after one, two, three years? Time here is "
        "tenure in months, and the twelve months of data are used for what they are: someone hired in 2019 "
        "enters observation with six years behind them, so they only count from there (delayed entry).",
        "",
        md_table(["Tenure", "Everyone", "Paid at or above 0.92 of band", "Paid below"], rows, align="lrrr"),
        "",
        "![Survival by pay position](figures/17_survival_by_pay.svg)",
        "",
        f"**{s12:.0%} of hires are still here after a year, {s24:.0%} after two and {s36:.0%} after three** "
        f"(voluntary exits only). Counting everyone from their first day, as if the data had always been there, "
        f"would put the first year at **{n12:.0%}**: it credits the organisation with every early leaver who left "
        "before July 2025 and so never appears in the data.",
        "",
        f"**Pay position is visible in the curves from the first months.** Over the first {HORIZON} months, people "
        f"paid below 0.92 of band stay **{rm_below:.1f} months** on average against **{rm_at:.1f}** for the rest "
        f"(log-rank chi-square {chi_pay:.1f}, p {'< 0.001' if p_pay < 0.001 else f'= {p_pay:.3f}'}). Fixed-term "
        f"contracts separate as clearly (chi-square {chi_fix:.1f}).",
        "",
        "![Hazard ratios](figures/18_hazard_ratios.svg)",
        "",
        md_table(["Factor", "Hazard ratio", "p-value"],
                 [[n, f"{h:.2f}x", "<0.001" if p < 0.001 else f"{p:.3f}"] for n, h, p in hrs], align="lrr"),
        "",
        "A hazard ratio reads as how much faster resignations come, at any given tenure, for someone with the factor "
        "than for an otherwise similar colleague without it. Tenure is the time axis itself here, so the first-year "
        "effect the logistic model needed a term for is absorbed into the baseline.",
        "",
        f"**Does pay matter as much in the first year?** Splitting each person's tenure at twelve months, in a model "
        f"with pay position alone, being paid below band multiplies the resignation hazard by **{hr_first:.2f}** in the first year and **{hr_later:.2f}** "
        "after it "
        + (f"(difference p = {p_inter:.2f}): the effect is the same throughout, so a pay fix helps new and long-serving "
           "staff alike." if p_inter >= 0.05 else
           f"(difference p = {p_inter:.3f}): the effect changes with tenure, so the proportional-hazards assumption "
           "does not hold for pay and the single hazard ratio above is an average of two different effects."),
        "",
        "*One limit is specific to this data: pay position is a single value per person, applied across their "
        "whole tenure. In a real HRIS it changes with every raise and band review, and has to enter the model as a "
        "time-varying covariate, split at each change the way tenure is split at twelve months above.*",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
