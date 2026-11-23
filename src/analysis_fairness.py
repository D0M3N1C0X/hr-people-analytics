"""
Module 1c - Is the attrition model fair to the people it scores?

Sex, age and country are not inputs, and that proves nothing on its own: a model can learn them back
through the factors it does use, and it can be right on average while wrong for a group. So the scores
from the two unseen quarters are broken down by the groups an impact assessment has to look at (AI Act
Art. 27(1)(c); GDPR Art. 35), asking three questions of each:

  - calibration: does the model predict as many resignations in the group as there are?
  - ranking: inside the group, does it still put resigners above stayers (AUC)?
  - flags: at one company-wide cut, the top 10% of scores, how often is a member flagged, how many of
    the group's resigners are caught, and how many of its stayers are flagged for nothing?
"""

from __future__ import annotations

import viz
from analysis_validation import evaluate
from hrlib import FIGURES, md_table
import math

from statsx import auc, mean, quantile

FLAG_SHARE = 0.10
COUNTRY_NAMES = {"IT": "Italy", "PL": "Poland", "DE": "Germany", "ES": "Spain"}


def age_band(age: int) -> str:
    return "under 30" if age < 30 else "30-44" if age < 45 else "45 and over"


GROUPS = {
    "Sex": lambda r: "women" if r["gender"] == "F" else "men",
    "Age": lambda r: age_band(r["age"]),
    "Country": lambda r: r["country"],
    "Working time": lambda r: "full time" if r["fte"] >= 1 else "part time",
}
ORDER = {"Age": ["under 30", "30-44", "45 and over"], "Country": ["IT", "PL", "DE", "ES"],
         "Sex": ["women", "men"], "Working time": ["full time", "part time"]}


def audit(scored: list[tuple[dict, float, int]]) -> dict:
    cut = quantile([p for _, p, _ in scored], 1 - FLAG_SHARE)
    out = {"cut": cut, "groups": {}}
    for dimension, key in GROUPS.items():
        rows = {}
        for level in ORDER[dimension]:
            members = [(p, y) for r, p, y in scored if key(r) == level]
            if not members:
                continue
            probs, ys = [p for p, _ in members], [y for _, y in members]
            flagged = [p >= cut for p in probs]
            leavers = [f for f, y in zip(flagged, ys) if y]
            stayers = [f for f, y in zip(flagged, ys) if not y]
            spread = math.sqrt(sum(p * (1 - p) for p in probs))
            rows[level] = {
                # how many standard errors the observed count sits from the predicted one
                "z": (sum(ys) - sum(probs)) / spread if spread else float("nan"),
                "n": len(members), "events": sum(ys), "observed": mean(ys), "predicted": mean(probs),
                "auc": auc(probs, ys) if 0 < sum(ys) < len(ys) else float("nan"),
                "flag_rate": mean(flagged), "caught": mean(leavers) if leavers else float("nan"),
                "false_flags": mean(stayers) if stayers else float("nan"),
            }
        out["groups"][dimension] = rows
    return out


def worst_calibration(a: dict) -> tuple[str, str, dict]:
    """The group whose resignations the model misses by the widest relative margin, either way."""
    cands = [(dim, lvl, g) for dim, rows in a["groups"].items() for lvl, g in rows.items() if g["events"] >= 20]
    return max(cands, key=lambda t: abs(t[2]["predicted"] / t[2]["observed"] - 1))


def proxies(scored: list[tuple[dict, float, int]], drivers: dict) -> list[tuple[str, float, float]]:
    """How common each input is among women and men: an input that differs a lot can carry sex back in."""
    women = [r for r, _, _ in scored if r["gender"] == "F"]
    men = [r for r, _, _ in scored if r["gender"] == "M"]
    return [(name, mean([float(test(r)) for r in women]), mean([float(test(r)) for r in men]))
            for name, test in drivers.items()]


def run() -> str:
    v = evaluate()
    a = audit(v["scored"])
    dim, lvl, g = worst_calibration(a)

    labels, observed, predicted = [], [], []
    for d in ("Sex", "Age", "Country"):
        for level, row in a["groups"][d].items():
            labels.append(level)
            observed.append(100 * row["observed"])
            predicted.append(100 * row["predicted"])
    viz.grouped_bar_chart(
        FIGURES / "16_fairness_calibration.svg", labels, {"predicted": predicted, "observed": observed},
        "Predicted against observed resignations, by group",
        "Two unseen quarters - a gap means the model misreads that group's risk",
        "resigned within the quarter %", fmt=lambda v: f"{v:.1f}")

    table = []
    for d, rows in a["groups"].items():
        for level, row in rows.items():
            table.append([d, level, f"{row['n']:,}", str(row["events"]), f"{row['observed']:.1%}",
                          f"{row['predicted']:.1%}", f"{row['auc']:.2f}", f"{row['flag_rate']:.0%}",
                          f"{row['caught']:.0%}", f"{row['false_flags']:.1%}"])

    sex = a["groups"]["Sex"]
    age = a["groups"]["Age"]
    flag_ratio = min(r["flag_rate"] for r in age.values()) / max(r["flag_rate"] for r in age.values())
    proxy_rows = proxies(v["scored"], v["drivers"])
    widest = max(proxy_rows, key=lambda t: abs(t[1] - t[2]))
    poland = a["groups"]["Country"]["PL"]
    part_time = [r for r, _, _ in v["scored"] if r["fte"] < 1]
    part_time_women = mean([float(r["gender"] == "F") for r in part_time])
    direction = "under" if g["predicted"] < g["observed"] else "over"

    md = [
        "### Is it fair to the people it scores?",
        "",
        "Sex, age and country are not inputs, which proves nothing on its own: a model can learn them back "
        "through what it does use, and it can be right on average while wrong for a group. So the scores from the "
        "two unseen quarters are broken down by the groups an impact assessment has to look at. Flags use one "
        f"company-wide cut, the top {FLAG_SHARE:.0%} of scores.",
        "",
        md_table(["Group", "", "At risk", "Resigned", "Observed", "Predicted", "AUC", "Flagged", "Resigners caught",
                  "Stayers flagged"], table, align="llrrrrrrrr"),
        "",
        "![Calibration by group](figures/16_fairness_calibration.svg)",
        "",
        f"**The widest miss is {COUNTRY_NAMES.get(lvl, lvl)}** ({dim.lower()}): the model predicts **{g['predicted']:.1%}** a quarter "
        f"where **{g['observed']:.1%}** resign, so it {direction}-reads that group's risk by "
        f"{abs(g['predicted'] / g['observed'] - 1):.0%}. "
        + (f"Country of work is not an input, and in this data Poland carries a higher exit hazard of its own "
           f"({poland['observed']:.1%} observed against {poland['predicted']:.1%} predicted): a model that leaves "
           "country out spreads Poland's risk across everyone else, and the country with the fewest resignations "
           f"is over-read. The gap is {abs(g['z']):.1f} standard errors wide on {g['events']} resignations: "
           + ("not noise. " if abs(g["z"]) >= 2 else "within what chance could produce, so worth watching. ") +
           "Country of work is not a protected characteristic, and adding it is the first change for the model's "
           "next version; it is left as tested above so the published figures stay the ones that were tested."
           if dim == "Country" else
           "That gap is the first item for the model's next version."),
        "",
        f"**Sex.** Women and men are predicted at {sex['women']['predicted']:.1%} and {sex['men']['predicted']:.1%} "
        f"against {sex['women']['observed']:.1%} and {sex['men']['observed']:.1%} observed; the model catches "
        f"{sex['women']['caught']:.0%} of resigning women and {sex['men']['caught']:.0%} of resigning men. Of the "
        f"eight inputs, the one that differs most by sex is *{widest[0].lower()}* ({widest[1]:.0%} of women, "
        f"{widest[2]:.0%} of men): an input to watch, because it can carry sex into the score.",
        "",
        f"**Age.** The score leans on first-year tenure and fixed-term contracts, which are commoner among younger "
        f"staff, so younger people are flagged far more often: the lowest flag rate is **{flag_ratio:.0%}** of the "
        "highest. Whether that is a harm depends entirely on what a flag leads to. A stay conversation offered to "
        "more young people is not; fewer promotions or less training for people marked as likely to leave would be.",
        "",
        "**What this audit cannot see.** Disability, origin and other characteristics are not in the data, and "
        "should not be added to it just to test the model; the impact assessment asks the people concerned and "
        f"their representatives instead. The groups also overlap: part-time staff are {part_time_women:.0%} women.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    print(run())
