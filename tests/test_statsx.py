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


class ScoringAClassifier(unittest.TestCase):
    """The validation metrics against values that can be worked out by hand."""

    def test_auc_is_the_mann_whitney_probability(self):
        scores = [0.1, 0.4, 0.35, 0.8, 0.4, 0.2, 0.9]
        labels = [0, 0, 1, 1, 1, 0, 1]
        pos = [s for s, y in zip(scores, labels) if y]
        neg = [s for s, y in zip(scores, labels) if not y]
        brute = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
        self.assertAlmostEqual(statsx.auc(scores, labels), brute)
        self.assertEqual(statsx.auc([1, 2, 3, 4], [0, 0, 1, 1]), 1.0)
        self.assertEqual(statsx.auc([1, 2, 3, 4], [1, 1, 0, 0]), 0.0)
        self.assertEqual(statsx.auc([5, 5, 5, 5], [0, 1, 0, 1]), 0.5)

    def test_hanley_mcneil_interval(self):
        lo, hi = statsx.auc_ci(0.75, 100, 900)
        q1, q2 = 0.75 / 1.25, 2 * 0.75 ** 2 / 1.75
        se = ((0.75 * 0.25 + 99 * (q1 - 0.5625) + 899 * (q2 - 0.5625)) / 90000) ** 0.5
        self.assertAlmostEqual(lo, 0.75 - 1.96 * se)
        self.assertAlmostEqual(hi, 0.75 + 1.96 * se)

    def test_brier_and_capture(self):
        self.assertAlmostEqual(statsx.brier([0.2, 0.9], [0, 1]), (0.04 + 0.01) / 2)
        scores, labels = [9, 8, 7, 6, 5, 4, 3, 2, 1, 0], [1, 0, 1, 0, 0, 0, 0, 0, 0, 1]
        self.assertAlmostEqual(statsx.capture(scores, labels, 0.3), 2 / 3)
        # a tie straddling the cut is counted pro rata, not by row order
        self.assertAlmostEqual(statsx.capture([1, 1, 1, 1], [1, 0, 0, 0], 0.5), 0.5)

    def test_a_perfectly_calibrated_score_has_slope_one(self):
        import random
        rng = random.Random(7)
        probs = [rng.uniform(0.02, 0.6) for _ in range(6000)]
        labels = [int(rng.random() < p) for p in probs]
        _, slope = statsx.calibration_slope(probs, labels)
        self.assertAlmostEqual(slope, 1.0, delta=0.12)


class Survival(unittest.TestCase):
    """Kaplan-Meier, log-rank and Cox against results worked out by hand."""

    # Six subjects, no delayed entry: events at 2, 3, 5; censored at 3, 4, 6.
    DATA = [(0, 2, 1), (0, 3, 1), (0, 3, 0), (0, 4, 0), (0, 5, 1), (0, 6, 0)]

    def test_kaplan_meier_by_hand(self):
        curve = statsx.kaplan_meier(self.DATA)
        # at 2: 6 at risk, 1 event -> 5/6; at 3: 5 at risk, 1 event -> 5/6 * 4/5; at 5: 2 at risk -> * 1/2
        self.assertEqual([t for t, *_ in curve], [2, 3, 5])
        self.assertAlmostEqual(curve[0][1], 5 / 6)
        self.assertAlmostEqual(curve[1][1], 4 / 6)
        self.assertAlmostEqual(curve[2][1], 2 / 6)
        greenwood = (4 / 6) * math.sqrt(1 / (6 * 5) + 1 / (5 * 4))
        self.assertAlmostEqual(curve[1][2], greenwood)
        self.assertAlmostEqual(statsx.restricted_mean(curve, 6), 2 + 3 * 5 / 6 / 3 * 1 + 2 * 4 / 6 + 1 * 2 / 6)

    def test_delayed_entry_keeps_late_joiners_out_of_early_risk_sets(self):
        # the second subject enters at 3, so it is not at risk at the event at 2
        curve = statsx.kaplan_meier([(0, 2, 1), (3, 5, 0), (0, 4, 0)])
        self.assertEqual(curve[0][3], 2)
        self.assertAlmostEqual(curve[0][1], 0.5)

    def test_cox_score_test_with_one_binary_covariate_is_the_logrank_test(self):
        rng = random.Random(3)
        subjects, groups = [], []
        for _ in range(300):
            g = int(rng.random() < 0.5)
            t = rng.expovariate(0.10 * (1.8 if g else 1.0))
            c = rng.uniform(0, 15)
            subjects.append((0.0, min(t, c), int(t <= c)))      # continuous: no ties, where the two agree exactly
            groups.append(g)
        chi2, _ = statsx.logrank(subjects, groups)
        # score test at beta = 0: score^2 / information, taken from one Newton step's quantities
        fit = statsx.cox(subjects, [[float(g)] for g in groups], ["group"], max_iter=1)
        score_stat = (fit.coef[0] / fit.se[0]) ** 2   # after one step from 0, coef = U/I and se = 1/sqrt(I)
        self.assertAlmostEqual(score_stat, chi2, places=6)

    def test_cox_recovers_a_known_hazard_ratio(self):
        rng = random.Random(11)
        subjects, X = [], []
        for _ in range(3000):
            x = int(rng.random() < 0.4)
            t = rng.expovariate(0.05 * (2.5 if x else 1.0))
            subjects.append((0.0, min(t, 20.0), int(t <= 20)))
            X.append([float(x)])
        fit = statsx.cox(subjects, X, ["x"])
        self.assertAlmostEqual(math.exp(fit.coef[0]), 2.5, delta=0.2)

    def test_cox_with_delayed_entry_matches_the_naive_risk_sets(self):
        rng = random.Random(5)
        subjects, X = [], []
        for _ in range(200):
            a = rng.choice([0, 0, 2, 5])
            b = a + rng.randint(1, 12)
            subjects.append((a, b, int(rng.random() < 0.4)))
            X.append([float(rng.random() < 0.5), rng.gauss(0, 1)])
        fit = statsx.cox(subjects, X, ["g", "x"])
        # the score at the fitted beta must be zero when computed the slow, obvious way
        w = [math.exp(fit.coef[0] * x[0] + fit.coef[1] * x[1]) for x in X]
        for j in range(2):
            u = 0.0
            for t in sorted({b for _, b, e in subjects if e}):
                rs = [i for i, (a, b, _) in enumerate(subjects) if a < t <= b]
                ds = [i for i, (a, b, e) in enumerate(subjects) if e and b == t and a < b]
                u += sum(X[i][j] for i in ds) - len(ds) * sum(w[i] * X[i][j] for i in rs) / sum(w[i] for i in rs)
            self.assertAlmostEqual(u, 0.0, places=6)
