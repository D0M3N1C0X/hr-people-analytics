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


class ModelCard(unittest.TestCase):
    """The card answers the register's questions for a high-risk in-house system, with the tested numbers."""

    CARD = (ROOT / "docs" / "model_card.md").read_text(encoding="utf-8")

    def test_it_answers_every_question_the_register_asks_of_s07(self):
        asked = [f"V{n:02d}" for n in (*range(1, 12), 14, 15, 16)]
        found = re.findall(r"^## (V\d\d) ·", self.CARD, re.M)
        self.assertEqual(found, asked)

    def test_the_card_quotes_the_tested_figure(self):
        m = re.search(r"Out of sample, the AUC is ([\d.]+)", FINDINGS)
        self.assertIn(f"**{m.group(1)} (", self.CARD)

    def test_pay_and_dismissal_are_ruled_out(self):
        v01 = self.CARD[self.CARD.index("## V01"):self.CARD.index("## V02")]
        for use in ("counter-offers", "promotion", "dismissal"):
            self.assertIn(use, v01)

    def test_the_audit_and_the_card_agree_on_the_widest_miss(self):
        miss = re.search(r"\*\*The widest miss is (\w+)\*\*", FINDINGS).group(1)
        self.assertIn(f"**Known issues.** {miss} is over-predicted", self.CARD)


class SurvivalFindings(unittest.TestCase):
    def test_ignoring_late_entry_overstates_survival(self):
        m = re.search(r"\*\*(\d+)% of hires are still here after a year.*?put the first year at \*\*(\d+)%\*\*", FINDINGS, re.S)
        self.assertIsNotNone(m)
        self.assertGreater(int(m.group(2)), int(m.group(1)))

    def test_readme_survival_figures_are_the_report_s(self):
        for figure in ("77%", "65%", "94%", "22.4 months", "31.3", "3.10"):
            self.assertIn(figure, README)
            self.assertIn(figure, FINDINGS)


class ToolVectors(unittest.TestCase):
    """The committed cases the browser tool is checked on are what the Python reference computes today.

    Compared within 1e-9, not byte for byte: the last digit of an exp or a log differs between platforms.
    """

    def test_the_vectors_are_current(self):
        import json
        import sys
        from datetime import date
        sys.path.insert(0, str(ROOT / "src"))
        import tool_reference as ref

        committed = json.loads((ROOT / "tests" / "fixtures" / "tool_vectors.json").read_text(encoding="utf-8"))

        def close(a, b, path):
            if isinstance(b, dict):
                self.assertEqual(set(a), set(b), path)
                for k in b:
                    close(a[k], b[k], f"{path}.{k}")
            elif isinstance(b, list):
                self.assertEqual(len(a), len(b), path)
                for i, (x, y) in enumerate(zip(a, b)):
                    close(x, y, f"{path}[{i}]")
            elif isinstance(b, float):
                self.assertAlmostEqual(a, b, delta=1e-9 * max(1.0, abs(b)), msg=path)
            else:
                self.assertEqual(a, b, path)

        for case in committed["cases"]:
            if "source" in case:
                rows = ref.canonical_from_repo()
            else:
                f = case["rows"]["fields"]
                rows = [dict(zip(f, vals)) for vals in case["rows"]["values"]]
                for r in rows:
                    for k in ("hire", "exit"):
                        r[k] = date.fromisoformat(r[k]) if r.get(k) else None
            fresh = json.loads(json.dumps(ref.analyse(rows, date.fromisoformat(case["period_end"]))))
            close(fresh, case["result"], case["name"])


if __name__ == "__main__":
    unittest.main()
