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


if __name__ == "__main__":
    unittest.main()
