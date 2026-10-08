"""The statistics are written from scratch (no dependencies), so they are checked here against results
that have a closed form. Run with: python3 -m unittest discover -s tests"""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import statsx  # noqa: E402


class Descriptive(unittest.TestCase):
    def test_quantile_matches_numpy_linear_convention(self):
        xs = [1, 2, 3, 4, 10]
        self.assertEqual(statsx.median(xs), 3)
        self.assertAlmostEqual(statsx.quantile(xs, 0.25), 2.0)
        self.assertAlmostEqual(statsx.quantile([1, 2, 3, 4], 0.5), 2.5)

    def test_pearson_bounds(self):
        xs = list(range(10))
        self.assertAlmostEqual(statsx.pearson(xs, [2 * x + 1 for x in xs]), 1.0)
        self.assertAlmostEqual(statsx.pearson(xs, [-x for x in xs]), -1.0)

    def test_two_sided_p(self):
        self.assertAlmostEqual(statsx.two_sided_p(1.959964), 0.05, places=6)
        self.assertAlmostEqual(statsx.two_sided_p(0), 1.0)


class Welch(unittest.TestCase):
    def test_statistic_matches_its_definition(self):
        a, b = [5.1, 4.9, 5.6, 5.8, 6.0, 5.2], [4.0, 4.4, 4.1, 4.9, 3.8]
        va = sum((x - statsx.mean(a)) ** 2 for x in a) / (len(a) - 1)
        vb = sum((x - statsx.mean(b)) ** 2 for x in b) / (len(b) - 1)
        t, p = statsx.welch_t(a, b)
        self.assertAlmostEqual(t, (statsx.mean(a) - statsx.mean(b)) / math.sqrt(va / len(a) + vb / len(b)))
        self.assertAlmostEqual(statsx.welch_t(b, a)[0], -t)
        self.assertTrue(0 < p < 0.01)


class Regression(unittest.TestCase):
    def test_ols_recovers_an_exact_line(self):
        X = [[1.0, float(x)] for x in range(20)]
        y = [2 + 3 * x for x in range(20)]
        m = statsx.ols(X, y, ["intercept", "x"])
        self.assertAlmostEqual(m.get("intercept"), 2, places=9)
        self.assertAlmostEqual(m.get("x"), 3, places=9)

    def test_ols_matches_the_simple_regression_formula(self):
        rng = random.Random(1)
        xs = [rng.uniform(0, 10) for _ in range(200)]
        ys = [1.5 + 0.7 * x + rng.gauss(0, 1) for x in xs]
        mx, my = statsx.mean(xs), statsx.mean(ys)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
        m = statsx.ols([[1.0, x] for x in xs], ys, ["intercept", "x"])
        self.assertAlmostEqual(m.get("x"), slope, places=9)
        self.assertAlmostEqual(m.get("intercept"), my - slope * mx, places=9)

    def test_logit_with_one_binary_predictor_gives_the_table_odds_ratio(self):
        # 2x2 table: exposed 30 events of 100, unexposed 10 of 100. The MLE is closed form:
        # intercept = log odds of the unexposed, slope = log of the odds ratio.
        X = [[1.0, 1.0]] * 100 + [[1.0, 0.0]] * 100
        y = [1] * 30 + [0] * 70 + [1] * 10 + [0] * 90
        m = statsx.logistic_regression(X, y, ["intercept", "exposed"])
        self.assertAlmostEqual(m.get("intercept"), math.log(10 / 90), places=7)
        self.assertAlmostEqual(m.get("exposed"), math.log((30 / 70) / (10 / 90)), places=7)
        # standard error of a log odds ratio: sqrt(1/a + 1/b + 1/c + 1/d)
        self.assertAlmostEqual(m.se[1], math.sqrt(1 / 30 + 1 / 70 + 1 / 10 + 1 / 90), places=5)


if __name__ == "__main__":
    unittest.main()
