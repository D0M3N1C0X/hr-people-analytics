"""
Module 2 - Pay equity, framed on the EU Pay Transparency Directive.

Directive (EU) 2023/970 had to be transposed into national law by 7 June 2026.
Employers with 250+ workers report by 7 June 2027 and every year after that
(Art. 9(2)), on the preceding calendar year. Article 9 asks for the mean and median
gender pay gap, the gap by category of workers, and the share of each gender in
each pay quartile. Article 10 adds the sting: a gap of 5% or more in any
category of workers that is not justified on objective, gender-neutral criteria
and not corrected within six months triggers a joint pay assessment with
workers' representatives.

So the analysis answers the two questions an HR director has to answer:
what will our numbers look like, and which categories will trip the 5% wire?

(Illustrative exercise on synthetic data - not legal advice.)
"""

from __future__ import annotations

import math
from collections import defaultdict

import viz
from hrlib import FIGURES, eur, group_by, load_employees, md_table
from statsx import mean, median, ols, quantile, welch_t

THRESHOLD = 5.0        # Article 10 joint-pay-assessment trigger, in %
MIN_CATEGORY = 30      # don't report a category smaller than this
MIN_PER_GENDER = 8

LEVEL_ORDER = ["L1", "L2", "L3", "L4", "L5", "L6"]


def raw_gap(rows: list[dict], stat=mean) -> float:
    """Unadjusted pay gap in %, men as the reference (Art. 9 definition)."""
    f = [e["base_salary_eur"] for e in rows if e["gender"] == "F"]
    m = [e["base_salary_eur"] for e in rows if e["gender"] == "M"]
    if not f or not m:
        return float("nan")
    return (stat(m) - stat(f)) / stat(m) * 100


def pay_quartiles(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Headcount by gender in each quartile pay band (Art. 9(1)(f))."""
    salaries = [e["base_salary_eur"] for e in rows]
    cuts = [quantile(salaries, q) for q in (0.25, 0.5, 0.75)]
    out = {q: defaultdict(int) for q in ("Q1 (lowest)", "Q2", "Q3", "Q4 (highest)")}
    for e in rows:
        s = e["base_salary_eur"]
        band = ("Q1 (lowest)" if s <= cuts[0] else "Q2" if s <= cuts[1]
                else "Q3" if s <= cuts[2] else "Q4 (highest)")
        out[band][e["gender"]] += 1
    return out


def nested_models(rows: list[dict]) -> list[tuple[str, float, float]]:
    """
    Add controls one block at a time and watch the female coefficient move.

    Each step answers 'how much of the raw gap was that block explaining?'.
    The final model is the adjusted (like-for-like) gap.
    """
    levels = LEVEL_ORDER[1:]                       # L1 is the reference level
    depts = sorted({e["department"] for e in rows} - {"Operations"})
    countries = sorted({e["country"] for e in rows} - {"IT"})

    blocks = [
        ("Unadjusted gap", []),
        ("+ job level", [("level", levels)]),
        ("+ department", [("level", levels), ("dept", depts)]),
        ("+ country, tenure",
         [("level", levels), ("dept", depts), ("country", countries), ("extras", None)]),
    ]

    results = []
    for label, spec in blocks:
        names = ["intercept", "female"]
        for kind, values in spec:
            if kind == "extras":
                names += ["tenure_years", "tenure_years_sq", "part_time", "fixed_term"]
            else:
                names += [f"{kind}={v}" for v in values]

        X, y = [], []
        for e in rows:
            row = [1.0, float(e["gender"] == "F")]
            for kind, values in spec:
                if kind == "level":
                    row += [float(e["job_level"] == v) for v in values]
                elif kind == "dept":
                    row += [float(e["department"] == v) for v in values]
                elif kind == "country":
                    row += [float(e["country"] == v) for v in values]
                elif kind == "extras":
                    t = e["tenure_months"] / 12
                    row += [t, t * t, float(e["fte"] < 1.0),
                            float(e["contract_type"] == "Fixed-term")]
            X.append(row)
            y.append(math.log(e["base_salary_eur"]))

        model = ols(X, y, names)
        gap_pct = (1 - math.exp(model.get("female"))) * 100
        results.append((label, gap_pct, model.p("female")))
    return results


def category_gaps(rows: list[dict]) -> list[tuple[str, float, int, float]]:
    """Gap by 'category of workers' - here department x job level.

    Each category also gets a Welch test on log salaries: a 12% gap in a group
    of 40 people and a 6% gap in a group of 400 are not the same evidence, and
    the difference matters when the employer has to justify the number.
    """
    out = []
    for (dept, level), group in group_by_pair(rows).items():
        f = [e for e in group if e["gender"] == "F"]
        m = [e for e in group if e["gender"] == "M"]
        if len(group) < MIN_CATEGORY or len(f) < MIN_PER_GENDER or len(m) < MIN_PER_GENDER:
            continue
        _, pval = welch_t([math.log(e["base_salary_eur"]) for e in m],
                          [math.log(e["base_salary_eur"]) for e in f])
        out.append((f"{dept} - {level}", raw_gap(group), len(group), pval))
    return sorted(out, key=lambda t: -t[1])


def group_by_pair(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in rows:
        out[(e["department"], e["job_level"])].append(e)
    return out


def run() -> str:
    employees = [e for e in load_employees() if e["active"]]     # snapshot population
    women = [e for e in employees if e["gender"] == "F"]
    men = [e for e in employees if e["gender"] == "M"]

    gap_mean, gap_median = raw_gap(employees), raw_gap(employees, median)

    # ---- by country ---------------------------------------------------
    countries = sorted(group_by(employees, "country"))
    med_f = [median([e["base_salary_eur"] for e in employees
                     if e["country"] == c and e["gender"] == "F"]) for c in countries]
    med_m = [median([e["base_salary_eur"] for e in employees
                     if e["country"] == c and e["gender"] == "M"]) for c in countries]
    viz.grouped_bar_chart(
        FIGURES / "05_pay_gap_by_country.svg", countries,
        {"Women": med_f, "Men": med_m},
        "Median base salary by country and gender",
        "Unadjusted - reflects who sits in which job, not pay for the same job",
        "EUR (annual)", fmt=lambda v: f"{v / 1000:.1f}k")

    # ---- quartiles ----------------------------------------------------
    quartiles = pay_quartiles(employees)
    labels = list(quartiles)
    viz.stacked_share_chart(
        FIGURES / "06_pay_quartiles.svg", labels,
        {"Women": [quartiles[q]["F"] for q in labels],
         "Men": [quartiles[q]["M"] for q in labels]},
        "Share of each gender in each pay quartile",
        "Reporting item required by Article 9(1)(f) of Directive (EU) 2023/970")

    top_f = quartiles["Q4 (highest)"]["F"] / sum(quartiles["Q4 (highest)"].values()) * 100
    bottom_f = quartiles["Q1 (lowest)"]["F"] / sum(quartiles["Q1 (lowest)"].values()) * 100

    # ---- decomposition ------------------------------------------------
    steps = nested_models(employees)
    viz.bar_chart(
        FIGURES / "07_pay_gap_decomposition.svg",
        [s[0] for s in steps], [round(s[1], 2) for s in steps],
        "What is left of the pay gap as controls are added",
        "OLS on log(base salary); the female coefficient after each block of controls",
        "gender pay gap %", fmt=lambda v: f"{v:.1f}%", color=viz.VIOLET,
        target=THRESHOLD, target_label=f"Art. 10 trigger {THRESHOLD:.0f}%")

    adjusted_label, adjusted, adjusted_p = steps[-1]
    model_raw = steps[0][1]
    explained = (model_raw - adjusted) / model_raw * 100

    # ---- categories over the trigger ----------------------------------
    cats = category_gaps(employees)
    flagged = [c for c in cats if c[1] >= THRESHOLD]
    shown = cats[:12]
    viz.lollipop_chart(
        FIGURES / "08_pay_gap_by_category.svg",
        [c[0] for c in shown], [round(c[1], 2) for c in shown],
        "Pay gap by category of workers",
        f"Department x job level, categories of {MIN_CATEGORY}+ employees - "
        f"red sits above the {THRESHOLD:.0f}% joint-pay-assessment trigger",
        xlabel=f"gap % (men as reference) - dashed line = {THRESHOLD:.0f}% trigger",
        fmt=lambda v: f"{v:+.1f}%", reference=THRESHOLD)

    md = [
        "## 2. Pay equity under the EU Pay Transparency Directive",
        "",
        f"Population: **{len(employees):,} active employees**, "
        f"{len(women) / len(employees):.0%} women / {len(men) / len(employees):.0%} men. "
        "At this size - 250 workers or more - the organisation reports **by 7 June 2027 and "
        "every year thereafter** (Art. 9(2)), on the preceding calendar year. What follows is "
        "computed on a **snapshot of active employees at 30 June 2026**, which is the shape of "
        "the exercise rather than a statutory submission. Gaps are expressed with men as the "
        "reference, as in the Directive.",
        "",
        md_table(["Article 9 reporting item", "Value"],
                 [["Mean gender pay gap", f"**{gap_mean:.1f}%**"],
                  ["Median gender pay gap", f"**{gap_median:.1f}%**"],
                  ["Women in the highest pay quartile", f"{top_f:.0f}%"],
                  ["Women in the lowest pay quartile", f"{bottom_f:.0f}%"],
                  ["Median salary, women", eur(median([e['base_salary_eur'] for e in women]))],
                  ["Median salary, men", eur(median([e['base_salary_eur'] for e in men]))]],
                 align="lr"),
        "",
        "*Scope: these are the Article 9 items this dataset can support, and they cover "
        "**base pay only**. A real submission also has to report the gap in complementary "
        "and variable components - bonus, allowances, benefits in kind - together with the "
        "proportion of each gender receiving them. Those components are frequently where the "
        "widest gaps sit, and they are not modelled here.*",
        "",
        "![Median salary by country and gender](figures/05_pay_gap_by_country.svg)",
        "",
        "### Where the gap actually comes from",
        "",
        f"The headline number is **{gap_mean:.1f}%**, but a headline gap does not say whether "
        "women are underpaid for the same work or under-represented in the jobs that pay more. "
        "Adding controls one block at a time separates the two.",
        "",
        "![Decomposition](figures/07_pay_gap_decomposition.svg)",
        "",
        md_table(["Model", "Gender pay gap", "p-value"],
                 [[label, f"{g:.1f}%", f"{p:.3f}" if p >= 0.001 else "<0.001"]
                  for label, g, p in steps], align="lrr"),
        "",
        f"*The regression works on log salary, so it estimates the ratio of geometric means: "
        f"{model_raw:.1f}% where the arithmetic mean gap is {gap_mean:.1f}%. Same story, "
        "slightly different lens - the Article 9 figures reported above are the arithmetic ones.*",
        "",
        f"Job level alone absorbs most of it. Fully adjusted - same level, same department, "
        f"same country, comparable tenure and contract - the residual gap is **{adjusted:.1f}%** "
        f"({'p < 0.001' if adjusted_p < 0.001 else f'p = {adjusted_p:.3f}'}). In other words **{explained:.0f}% of the headline gap is "
        "structural**: it is where women sit in the hierarchy, not what they are paid for the "
        "same job.",
        "",
        f"The quartile split says the same thing in plain language: women are **{bottom_f:.0f}%** "
        f"of the lowest pay quartile and **{top_f:.0f}%** of the highest.",
        "",
        "![Pay quartiles](figures/06_pay_quartiles.svg)",
        "",
        "### Categories that would trip Article 10",
        "",
        f"A category of workers showing a gap of **{THRESHOLD:.0f}% or more** that the employer "
        "cannot justify on objective, gender-neutral criteria - and does not remedy within six "
        "months - triggers a **joint pay assessment** with workers' representatives. Taking "
        "department x job level as the category definition, with a floor of "
        f"{MIN_CATEGORY} employees and {MIN_PER_GENDER} per gender:",
        "",
        "![Gap by category](figures/08_pay_gap_by_category.svg)",
        "",
        md_table(["Category (department x level)", "Gap", "Employees", "p", "Status"],
                 [[name, f"{g:+.1f}%", n, f"{pv:.3f}" if pv >= 0.001 else "<0.001",
                   ("**Above trigger**" if pv < 0.05 else "Above trigger (small sample)")
                   if g >= THRESHOLD else "Within tolerance"]
                  for name, g, n, pv in shown], align="lrrrl"),
        "",
        f"**{len(flagged)} of {len(cats)} reportable categories** sit at or above the trigger, "
        f"of which **{sum(1 for c in flagged if c[3] < 0.05)}** are statistically distinguishable "
        "from zero at conventional levels. The rest are small groups where a handful of salaries "
        "moves the number - which is exactly why the category definition matters: too granular "
        "and the report is noise, too coarse and it hides real gaps. Either way each category "
        "needs a documented, gender-neutral justification - measurable differences in seniority, "
        "scope or performance - or a correction plan, and both are cheaper to prepare now than "
        "after the first report is published.",
        "",
        "### What this means in practice",
        "",
        "1. **The remediation bill is small; the pipeline problem is not.** Closing the residual "
        f"like-for-like gap of {adjusted:.1f}% is a rounding error next to the payroll. Changing "
        f"who gets promoted - women are {top_f:.0f}% of the top quartile - is the work that "
        "actually moves the headline number, and it takes two to three promotion cycles.",
        "2. **Fix the categories over the trigger first**, in the order shown above. Document the "
        "justification where one genuinely exists; where it does not, correct the salary.",
        "3. **Instrument hiring and promotion decisions now.** From June 2027 the numbers are "
        "published, and the explanation has to be ready at the same time as the number.",
        "4. **Run this quarterly, not annually.** The report is the deadline; the management "
        "information is the point.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
