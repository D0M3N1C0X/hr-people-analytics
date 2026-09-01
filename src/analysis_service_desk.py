"""
Module 3 - HR service-desk performance.

The operational half of the picture: 12 months of HR cases through a
shared-services desk. It answers what a service-delivery manager is asked in
every monthly review - are we hitting SLA, where is the volume coming from,
what makes employees unhappy, and what would we have to change to fix it.

Assumptions that carry weight are stated inline: average agent handling effort
per case, and the productive hours behind one full-time equivalent.
"""

from __future__ import annotations

from collections import Counter

import viz
from hrlib import (FIGURES, MONTH_LABELS, MONTH_NAMES, group_by, load_cases,
                   load_employees, md_table)
from statsx import mean, median, pearson, share

SLA_TARGET = 90.0          # % of cases resolved inside their SLA
HANDLING_HOURS = 0.67      # ~40 minutes of agent effort per case (not elapsed time)
FTE_HOURS = 1_600          # productive agent hours per FTE per year
DEFLECTION_RATE = 0.25     # share of top-category volume a good self-service flow absorbs


def attainment(cases: list[dict]) -> float:
    return share([c["sla_met"] for c in cases]) * 100


def csat_of(cases: list[dict]) -> float:
    scores = [c["csat"] for c in cases if c["csat"] is not None]
    return mean(scores) if scores else float("nan")


def run() -> str:
    cases = load_cases()
    employees = load_employees()
    active = sum(1 for e in employees if e["active"])

    scored = [c for c in cases if c["csat"] is not None]
    overall_sla = attainment(cases)
    overall_csat = csat_of(cases)

    # ---- volume and seasonality ---------------------------------------
    by_month = [0] * 12
    payroll_month = [0] * 12
    leave_month = [0] * 12
    sla_month: list[list[int]] = [[] for _ in range(12)]
    for c in cases:
        by_month[c["month"]] += 1
        sla_month[c["month"]].append(c["sla_met"])
        if c["category"] == "Payroll":
            payroll_month[c["month"]] += 1
        elif c["category"] == "Leave & Absence":
            leave_month[c["month"]] += 1

    sla_by_month = [share(m) * 100 for m in sla_month]
    peak = by_month.index(max(by_month))
    trough = by_month.index(min(by_month))
    corr = pearson(by_month, sla_by_month)

    viz.line_chart(
        FIGURES / "09_case_volume_trend.svg", MONTH_LABELS,
        {"All cases": by_month, "Payroll": payroll_month, "Leave & Absence": leave_month},
        "HR case volume by month",
        f"Peak ({MONTH_NAMES[peak]}) runs {max(by_month) / min(by_month) - 1:+.0%} above the "
        f"quietest month - the annual pay review and tax documents land together",
        "cases")

    viz.line_chart(
        FIGURES / "10_sla_by_month.svg", MONTH_LABELS,
        {"SLA attainment": sla_by_month},
        "SLA attainment by month",
        f"Correlation with monthly volume: r = {corr:.2f} - the desk misses SLA exactly when "
        "employees need it most", "% of cases inside SLA", fmt=lambda v: f"{v:.0f}%")

    # ---- category mix --------------------------------------------------
    cats = Counter(c["category"] for c in cases)
    ordered = cats.most_common()
    viz.pareto_chart(
        FIGURES / "11_case_pareto.svg",
        [c for c, _ in ordered], [n for _, n in ordered],
        "Where the case volume sits",
        f"Top three categories carry "
        f"{sum(n for _, n in ordered[:3]) / len(cases):.0%} of all cases", "cases")

    by_cat_sla = sorted(((c, attainment(rows)) for c, rows in group_by(cases, "category").items()),
                        key=lambda kv: kv[1])
    viz.bar_chart(
        FIGURES / "12_sla_by_category.svg",
        [c for c, _ in by_cat_sla], [r for _, r in by_cat_sla],
        "SLA attainment by case category",
        f"Company-wide attainment is {overall_sla:.0f}% against a {SLA_TARGET:.0f}% target",
        "% inside SLA", fmt=lambda v: f"{v:.0f}%",
        highlight={c for c, r in by_cat_sla if r < SLA_TARGET - 15},
        target=SLA_TARGET, target_label=f"target {SLA_TARGET:.0f}%")

    # ---- satisfaction --------------------------------------------------
    csat_groups = {
        "SLA met": [c for c in scored if c["sla_met"]],
        "SLA missed": [c for c in scored if not c["sla_met"]],
        "Solved first contact": [c for c in scored if c["first_contact_resolution"]],
        "Reopened": [c for c in scored if c["reopened"]],
        "New agent (<6 m)": [c for c in scored if c["agent_tenure_months"] < 6],
        "Experienced agent": [c for c in scored if c["agent_tenure_months"] >= 6],
    }
    # The two failure modes overlap, so the honest comparison is the joint case
    # against a clean one - not one penalty stacked on the other.
    both_failures = [c for c in scored if not c["sla_met"] and c["reopened"]]
    clean_cases = [c for c in scored if c["sla_met"] and not c["reopened"]]

    viz.bar_chart(
        FIGURES / "13_csat_drivers.svg",
        list(csat_groups), [csat_of(g) for g in csat_groups.values()],
        "Average CSAT by case experience",
        f"1-5 scale, {len(scored):,} rated cases ({len(scored) / len(cases):.0%} response rate) "
        f"- overall average {overall_csat:.2f}",
        "CSAT", fmt=lambda v: f"{v:.2f}", color=viz.GREEN,
        highlight={"SLA missed", "Reopened"})

    # ---- the numbers that drive the recommendations --------------------
    reopen_rate = share([c["reopened"] for c in cases]) * 100
    fcr = share([c["first_contact_resolution"] for c in cases]) * 100
    breaches = [c for c in cases if not c["sla_met"]]

    new_agent = [c for c in cases if c["agent_tenure_months"] < 6]
    exp_agent = [c for c in cases if c["agent_tenure_months"] >= 6]

    top_two = [c for c, _ in ordered[:2]]
    deflectable = sum(cats[c] for c in top_two) * DEFLECTION_RATE
    hours_saved = deflectable * HANDLING_HOURS
    fte_saved = hours_saved / FTE_HOURS
    rework_hours = sum(1 for c in cases if c["reopened"]) * HANDLING_HOURS

    md = [
        "## 3. HR service-desk performance",
        "",
        md_table(["Metric", "Value", "Read"],
                 [["Cases handled", f"{len(cases):,}",
                   f"{len(cases) / active:.1f} per employee per year"],
                  ["SLA attainment", f"**{overall_sla:.1f}%**",
                   f"{SLA_TARGET - overall_sla:.1f} pp below the {SLA_TARGET:.0f}% target"],
                  ["Median time to resolve", f"{median([c['resolution_hours'] for c in cases]):.1f} h",
                   f"mean {mean([c['resolution_hours'] for c in cases]):.1f} h - a long tail"],
                  ["First-contact resolution", f"{fcr:.1f}%", "cases closed without a hand-off"],
                  ["Reopen rate", f"{reopen_rate:.1f}%", "cases the employee had to chase again"],
                  ["CSAT", f"{overall_csat:.2f} / 5",
                   f"{len(scored) / len(cases):.0%} response rate"]],
                 align="lrl"),
        "",
        "### Volume is seasonal, and the desk breaks exactly at the peak",
        "",
        f"{MONTH_NAMES[peak]} carries **{max(by_month):,}** cases against **{min(by_month):,}** "
        f"in {MONTH_NAMES[trough]} - **{max(by_month) / min(by_month) - 1:+.0%}**. Payroll alone "
        f"moves from {min(payroll_month):,} to {max(payroll_month):,} cases a month around the "
        "annual pay review and tax documentation.",
        "",
        "![Case volume by month](figures/09_case_volume_trend.svg)",
        "",
        f"Attainment moves the opposite way: the correlation between monthly volume and SLA "
        f"attainment is **r = {corr:.2f}**. Capacity is flat while demand is not, so the desk "
        "misses its promise in the months when the questions matter most - pay, tax, contracts.",
        "",
        "![SLA attainment by month](figures/10_sla_by_month.svg)",
        "",
        "### Volume concentration",
        "",
        f"**{sum(n for _, n in ordered[:3]) / len(cases):.0%}** of all cases sit in three "
        f"categories: {', '.join(c for c, _ in ordered[:3])}. That concentration is an "
        "opportunity, not a complaint: a small number of question types is what self-service and "
        "templated answers are good at.",
        "",
        "![Pareto of case categories](figures/11_case_pareto.svg)",
        "",
        "![SLA attainment by category](figures/12_sla_by_category.svg)",
        "",
        f"{by_cat_sla[0][0]} is the weakest category at **{by_cat_sla[0][1]:.0f}%** attainment. "
        "Categories with the tightest SLA targets are missed most often, which usually means the "
        "target was set by ambition rather than by measured handling time.",
        "",
        "### What employees actually react to",
        "",
        "![CSAT drivers](figures/13_csat_drivers.svg)",
        "",
        f"Missing the SLA costs **{csat_of(csat_groups['SLA met']) - csat_of(csat_groups['SLA missed']):.2f} "
        f"CSAT points** ({csat_of(csat_groups['SLA met']):.2f} against "
        f"{csat_of(csat_groups['SLA missed']):.2f}); having to reopen a case costs "
        f"**{csat_of(csat_groups['Solved first contact']) - csat_of(csat_groups['Reopened']):.2f}** "
        f"({csat_of(csat_groups['Solved first contact']):.2f} against "
        f"{csat_of(csat_groups['Reopened']):.2f}). Those two penalties are measured against "
        "different baselines and they overlap heavily - a breached case is far more likely to "
        f"be reopened - so they cannot be added up. What can be said is where the floor is: "
        f"cases that both missed SLA **and** were reopened average **{csat_of(both_failures):.2f}**, "
        f"against **{csat_of(clean_cases):.2f}** for a clean resolution. And Module 1 showed the "
        "same reopened cases predicting exits nine months later.",
        "",
        f"Cases handled by agents with less than six months' tenure resolve first contact "
        f"{share([c['first_contact_resolution'] for c in new_agent]) * 100:.0f}% of the time "
        f"against {share([c['first_contact_resolution'] for c in exp_agent]) * 100:.0f}% for "
        "experienced agents. Ramp-up is a quality variable and belongs in the capacity plan.",
        "",
        "### Three things worth doing",
        "",
        f"1. **Flex capacity to the curve.** {len(breaches):,} cases missed SLA this year and "
        f"they cluster in the peak months. Moving even part of the team's leave and training out "
        f"of {MONTH_NAMES[peak]}, plus a seasonal contract, addresses the largest single cause "
        "of breach without adding permanent headcount.",
        f"2. **Deflect the repetitive volume.** Moving {DEFLECTION_RATE:.0%} of "
        f"{' and '.join(top_two)} cases to guided self-service removes about "
        f"**{deflectable:,.0f} cases** a year - roughly **{hours_saved:,.0f} agent hours**, or "
        f"**{fte_saved:.1f} FTE** at {HANDLING_HOURS * 60:.0f} minutes of handling effort per "
        f"case and {FTE_HOURS:,} productive hours per FTE. That is capacity released for the "
        "advisory work, not a headcount cut.",
        f"3. **Attack rework before speed.** Reopened cases consume about "
        f"**{rework_hours:,.0f} hours** of pure rework a year and carry the worst satisfaction "
        "scores in the dataset. Root-causing the top reopen reasons is cheaper than any staffing "
        "change and improves both numbers at once.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
