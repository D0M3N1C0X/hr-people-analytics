"""Every headline number in the README is one the pipeline produced, and the intervention arithmetic holds.
Run after python3 src/run_all.py."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
FINDINGS = (ROOT / "reports" / "findings.md").read_text(encoding="utf-8")


def bold_numbers(text: str) -> set[str]:
    return set(re.findall(r"-?\d[\d,.]*%?x?", text))


class ReadmeMatchesTheReport(unittest.TestCase):
    def test_headline_figures_appear_in_the_report(self):
        table = README[README.index("## The headline findings"):README.index("## What this project demonstrates")]
        table = table.replace("−", "-")
        figures = {f for f in bold_numbers(table) if any(ch.isdigit() for ch in f) and f not in {"01", "03", "1", "9"}}
        normalised = FINDINGS.replace("−", "-")
        missing = sorted(f for f in figures if f.rstrip(".") not in normalised)
        self.assertEqual(missing, [], f"README quotes figures the report does not contain: {missing}")

    def test_odds_ratios_are_not_called_risk(self):
        self.assertNotIn("more likely to resign", README)
        self.assertIn("the odds of resigning", README)


class Intervention(unittest.TestCase):
    def test_model_based_effect_is_used_and_consistent(self):
        m = re.search(r"resigning within a year at \*\*([\d.]+)%\*\* with the gap and \*\*([\d.]+)%\*\* without it.*?"
                      r"roughly \*\*(\d+) fewer resignations\*\*", FINDINGS, re.S)
        self.assertIsNotNone(m, "the intervention must come from the model's predictions")
        with_gap, without, avoided = float(m.group(1)), float(m.group(2)), int(m.group(3))
        n = int(re.search(r"\*\*Illustrative intervention.\*\* (\d+) active employees", FINDINGS).group(1))
        self.assertGreater(with_gap, without)
        self.assertAlmostEqual(avoided, n * (with_gap - without) / 100, delta=1.0)


class OutOfTimeTest(unittest.TestCase):
    """The validation is run on quarters the model never saw, and the ceiling is the data's own truth."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        import analysis_validation
        cls.v = analysis_validation
        cls.r = analysis_validation.evaluate()

    def test_the_ceiling_is_rebuilt_from_the_same_people(self):
        import csv
        _, truth = self.v.ceiling_scores()
        published = {r["employee_id"]: r["exit_date"] for r in csv.DictReader((ROOT / "data" / "employees.csv").open())}
        self.assertEqual({k: v["exit_date"] for k, v in truth.items()}, published)

    def test_no_test_quarter_overlaps_the_training_outcome(self):
        train_end = self.v.add_months(self.v.TRAIN, self.v.HORIZON)
        self.assertTrue(all(cutoff >= train_end for cutoff in self.v.TESTS))

    def test_the_model_sits_between_the_checklist_and_the_ceiling(self):
        p = self.r["pooled"]
        self.assertGreater(p["model"]["auc"], 0.5)
        self.assertLess(p["model"]["auc"], p["ceiling"]["auc"])

    def test_the_report_quotes_the_out_of_sample_figure(self):
        self.assertIn(f"Out of sample, the AUC is {self.r['pooled']['model']['auc']:.2f}", FINDINGS)


if __name__ == "__main__":
    unittest.main()
