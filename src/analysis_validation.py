"""
Module 1b - Does the attrition model predict, or only explain?

The driver model in module 1 is fitted and read on the same people. That says which factors go with
leaving; it does not say whether the model would have warned anyone in time. This module runs it the
way an HR team would: fitted once, on the quarter starting 1 October 2025, then scored on the next two
quarters, which it has never seen, with every predictor frozen at the start of the quarter it predicts.

Two reference points keep the result honest:
  - a checklist that simply counts the same eight warning signs, unweighted: what HR could do without
    any model at all;
  - the ceiling: the generator's own exit hazard, including the latent "HR friction" trait no HRIS
    holds. No model built on the data can rank people better than this.
"""

from __future__ import annotations

import importlib.util
import math
from collections import Counter
from datetime import date

import viz
from analysis_attrition import build_drivers
from hrlib import FIGURES, ROOT, WINDOW_START, group_by, load_cases, load_employees, md_table, months_between
from statsx import auc, auc_ci, brier, calibration_slope, capture, logistic_regression, mean, quantile

TRAIN = date(2025, 10, 1)
TESTS = (date(2026, 1, 1), date(2026, 4, 1))
HORIZON = 3                       # months each scoring run looks ahead
VOLUNTARY_SHARE = 0.84            # of all exits in the generator; scales the ceiling's probability


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def frame_at(employees: list[dict], cases: list[dict], cutoff: date, eng_q1: float) -> list[dict]:
    """Everyone employed on `cutoff`, with features as they stood that day and the next quarter's outcome."""
    lookback, end = add_months(cutoff, -3), add_months(cutoff, HORIZON)
    reopened = Counter(c["employee_id"] for c in cases if c["reopened"] and lookback <= c["created_dt"] < cutoff)
    rows = []
    for e in employees:
        if e["hire_dt"] >= cutoff or (e["exit_dt"] and e["exit_dt"] < cutoff):
            continue
        reference = e["exit_dt"] or date(2026, 6, 30)
        r = dict(e)
        r["tenure_at_cutoff"] = months_between(e["hire_dt"], cutoff)
        r["msp_at_cutoff"] = max(0, e["months_since_promotion"] - months_between(cutoff, reference))
        r["_eng_q1"] = eng_q1
        r["reopened_q1"] = reopened.get(e["employee_id"], 0)
        r["y"] = int(e["is_voluntary_leaver"] and cutoff <= e["exit_dt"] < end)
        rows.append(r)
    return rows


def training_department(employees: list[dict]) -> str:
    """The department with the highest voluntary exit rate before the training cutoff: chosen without the test."""
    early = [e for e in employees if e["hire_dt"] < WINDOW_START]
    by = group_by(early, "department")
    rate = {d: sum(1 for e in rows if e["is_voluntary_leaver"] and e["exit_dt"] < TRAIN) / len(rows)
            for d, rows in by.items()}
    return max(rate, key=rate.get)


def ceiling_scores() -> dict[str, dict]:
    """The generator rebuilt in memory, latent traits included, keyed by employee id."""
    spec = importlib.util.spec_from_file_location("_generator_truth", ROOT / "src" / "generate_data.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)               # a fresh module, so a fresh random stream: the same people
    return gen, {e["employee_id"]: e for e in gen.make_employees()}


def ceiling_probability(gen, e: dict, cutoff: date) -> float:
    """Chance of a voluntary exit in the quarter from the generator's own monthly hazard."""
    hire, stay = date.fromisoformat(e["hire_date"]), 1.0
    for k in range(HORIZON):
        month_start = add_months(cutoff, k)
        if hire > month_start:
            continue
        m = months_between(WINDOW_START, month_start)
        msp = max(0, e["_msp_snapshot"] - (12 - m))
        stay *= 1 - 1 / (1 + math.exp(-gen.exit_logit(e, months_between(hire, month_start), msp)))
    return VOLUNTARY_SHARE * (1 - stay)


def scorecard(probs: list[float], labels: list[int]) -> dict:
    a = auc(probs, labels)
    n1 = sum(labels)
    return {"n": len(labels), "events": n1, "auc": a, "ci": auc_ci(a, n1, len(labels) - n1),
            "brier": brier(probs, labels), "predicted": mean(probs), "observed": n1 / len(labels),
            "slope": calibration_slope(probs, labels)[1], "top10": capture(probs, labels, 0.10),
            "top20": capture(probs, labels, 0.20)}


def gains(scores: list[float], labels: list[int]) -> list[tuple[float, float]]:
    return [(s, 100 * capture(scores, labels, s / 100)) if s else (0.0, 0.0) for s in range(0, 101, 2)]


def evaluate() -> dict:
    employees, cases = load_employees(), load_cases()
    eng_q1 = quantile([e["engagement_score"] for e in frame_at(employees, cases, TRAIN, 0.0)], 0.25)
    dept = training_department(employees)
    drivers = build_drivers(dept)
    names = ["intercept"] + list(drivers)

    def design(rows):
        return [[1.0] + [float(test(r)) for test in drivers.values()] for r in rows]

    train = frame_at(employees, cases, TRAIN, eng_q1)
    model = logistic_regression(design(train), [r["y"] for r in train], names)

    def predict(rows):
        return [1 / (1 + math.exp(-sum(b * v for b, v in zip(model.coef, x)))) for x in design(rows)]

    gen, truth = ceiling_scores()
    result = {"model": model, "department": dept, "train": scorecard(predict(train), [r["y"] for r in train]),
              "tests": {}, "pooled": None}
    pooled = {"model": [], "checklist": [], "ceiling": [], "y": []}
    for cutoff in TESTS:
        rows = frame_at(employees, cases, cutoff, eng_q1)
        y = [r["y"] for r in rows]
        p = predict(rows)
        checklist = [sum(test(r) for test in drivers.values()) for r in rows]
        ceiling = [ceiling_probability(gen, truth[r["employee_id"]], cutoff) for r in rows]
        result["tests"][cutoff] = {"model": scorecard(p, y), "checklist_auc": auc(checklist, y),
                                   "checklist_top10": capture(checklist, y, 0.10),
                                   "ceiling": scorecard(ceiling, y)}
        for key, values in (("model", p), ("checklist", checklist), ("ceiling", ceiling), ("y", y)):
            pooled[key] += values
    y = pooled["y"]
    result["pooled"] = {"model": scorecard(pooled["model"], y), "checklist_auc": auc(pooled["checklist"], y),
                        "checklist_top10": capture(pooled["checklist"], y, 0.10),
                        "checklist_top20": capture(pooled["checklist"], y, 0.20),
                        "ceiling": scorecard(pooled["ceiling"], y)}
    result["curves"] = {"model": gains(pooled["model"], y), "checklist": gains(pooled["checklist"], y),
                        "ceiling": gains(pooled["ceiling"], y)}
    # Calibration in tenths of predicted risk, pooled over the two test quarters
    ranked = sorted(zip(pooled["model"], y))
    tenth = len(ranked) / 10
    bins = [ranked[round(i * tenth):round((i + 1) * tenth)] for i in range(10)]
    result["deciles"] = [(100 * mean([p for p, _ in b]), 100 * mean([t for _, t in b])) for b in bins]
    return result


def fmt_ci(card: dict) -> str:
    lo, hi = card["ci"]
    return f"{card['auc']:.2f} ({lo:.2f}-{hi:.2f})"


def run() -> str:
    r = evaluate()
    pooled, train = r["pooled"], r["train"]
    m, c = pooled["model"], pooled["ceiling"]

    viz.xy_chart(
        FIGURES / "14_out_of_time_gains.svg",
        {"model": r["curves"]["model"], "eight-sign checklist": r["curves"]["checklist"],
         "ceiling (generator's truth)": r["curves"]["ceiling"]},
        "Resignations caught next quarter, by share of staff flagged",
        "Fitted on Oct-Dec 2025, scored on Jan-Mar and Apr-Jun 2026 - quarters the model never saw",
        xlabel="share of employees flagged, highest risk first", ylabel="share of resignations caught",
        dashed={"ceiling (generator's truth)"})
    viz.grouped_bar_chart(
        FIGURES / "15_calibration.svg", [f"{i + 1}" for i in range(10)],
        {"predicted": [p for p, _ in r["deciles"]], "observed": [o for _, o in r["deciles"]]},
        "Predicted against observed resignation rate",
        "Two unseen quarters, employees in tenths of predicted risk (1 = lowest)",
        "resigned within the quarter %", fmt=lambda v: f"{v:.1f}")

    reach = (m["auc"] - 0.5) / (c["auc"] - 0.5)
    lift = m["top10"] / 0.10
    rows = [["Fitted on (in sample)", "Oct-Dec 2025", f"{train['n']:,}", str(train["events"]), fmt_ci(train),
             f"{train['top10']:.0%}", f"{train['brier']:.4f}"]]
    for cutoff, t in r["tests"].items():
        q = f"{cutoff:%b}-{add_months(cutoff, 2):%b %Y}"
        rows.append([f"Unseen quarter", q, f"{t['model']['n']:,}", str(t["model"]["events"]), fmt_ci(t["model"]),
                     f"{t['model']['top10']:.0%}", f"{t['model']['brier']:.4f}"])
    rows.append(["Both unseen quarters", "Jan-Jun 2026", f"{m['n']:,}", str(m["events"]), fmt_ci(m),
                 f"{m['top10']:.0%}", f"{m['brier']:.4f}"])

    slope_note = (
        f"The calibration slope is **{m['slope']:.2f}**: "
        + ("close to 1, so the probabilities can be read as probabilities, not only as a ranking."
           if 0.8 <= m["slope"] <= 1.2 else
           "below 1, so the model is overconfident out of sample: its high scores are too high and its low scores "
           "too low. Use it to rank people, not to quote anyone's chance of leaving."
           if m["slope"] < 0.8 else
           "above 1, so the model is too cautious out of sample: the real spread of risk is wider than it says."))

    md = [
        "### Does the model predict? An out-of-time test",
        "",
        "The odds ratios above come from a model fitted and read on the same people, which shows what goes with "
        "leaving but not whether the model would have warned anyone in time. So it is run here the way an HR team "
        "would run it: **fitted once on the quarter starting 1 October 2025**, then **scored at the start of each of "
        "the next two quarters**, on people and months it never saw, with every predictor frozen on the day of "
        f"scoring. The department term is fixed before the test too: {r['department']}, the highest exit rate "
        "before 1 October.",
        "",
        md_table(["", "Quarter", "At risk", "Resigned", "AUC (95% CI)", "Caught in top 10%", "Brier"],
                 rows, align="llrrrrr"),
        "",
        f"**Out of sample, the AUC is {m['auc']:.2f}** against {train['auc']:.2f} in sample: a random resigner "
        f"outranks a random stayer {m['auc']:.0%} of the time. Flagging the **top 10% of risk scores catches "
        f"{m['top10']:.0%} of the next quarter's resignations**, {lift:.1f} times what picking at random would, "
        f"and the top 20% catches {m['top20']:.0%}.",
        "",
        "![Resignations caught by share flagged](figures/14_out_of_time_gains.svg)",
        "",
        "**Against what HR could do without a model.** Counting the same eight warning signs, unweighted, reaches "
        f"an AUC of **{pooled['checklist_auc']:.2f}** and catches **{pooled['checklist_top10']:.0%}** in the top "
        f"10%. The weights are worth {m['auc'] - pooled['checklist_auc']:+.2f} of AUC and "
        f"{(m['top10'] - pooled['checklist_top10']) * 100:+.0f} points of capture: "
        + ("a real gain, but most of the value is in knowing which signs to watch, not in the arithmetic."
           if m["auc"] - pooled["checklist_auc"] < 0.05 else
           "enough to justify the model over a checklist."),
        "",
        "**Against the ceiling.** The generator's own hazard, which knows each person's latent tendency to have "
        f"HR problems that keep coming back, reaches **{c['auc']:.2f}** and catches **{c['top10']:.0%}** in the "
        f"top 10%. No model built on HRIS fields can beat that. The driver model closes **{reach:.0%} of the gap "
        "between chance and the ceiling**; the rest sits mostly in a trait the data only sees indirectly, "
        "through reopened cases.",
        "",
        "![Calibration](figures/15_calibration.svg)",
        "",
        f"**Calibration.** Across the two unseen quarters the model predicted **{m['predicted']:.1%}** would resign "
        f"in a quarter and **{m['observed']:.1%}** did. {slope_note}",
        "",
        "The pooled row counts person-quarters: most people appear in both unseen quarters, so its interval is a "
        "little narrower than truly independent data would give.",
        "",
        "**How to read it.** Even the best tenth of scores misses most resignations, and most people it flags "
        "stay. A score like this can decide where a manager's next stay conversation goes; it should never decide "
        "anything about the person scored.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
