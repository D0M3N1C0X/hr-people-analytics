"""
Minimal statistics toolkit - pure standard library.

Everything the analyses need (OLS with standard errors, logistic regression by
Newton-Raphson, quantiles) implemented from scratch, so the repository runs on
a bare Python install with no packages to download.

The APIs mirror what statsmodels would give you: a table of coefficients with
standard errors, test statistics and p-values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# Descriptive helpers
# --------------------------------------------------------------------------

def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs: list[float]) -> float:
    return quantile(xs, 0.5)


def quantile(xs: list[float], q: float) -> float:
    """Linear-interpolation quantile (same convention as numpy's default)."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def share(flags: list[int]) -> float:
    return sum(flags) / len(flags) if flags else float("nan")


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient."""
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else float("nan")


def welch_t(a: list[float], b: list[float]) -> tuple[float, float]:
    """Welch's unequal-variance t-test. Returns (t, p) using a normal approximation
    for the p-value, which is accurate enough at the group sizes used here."""
    if len(a) < 2 or len(b) < 2:
        return float("nan"), float("nan")
    va = sum((x - mean(a)) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mean(b)) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    if se == 0:
        return float("nan"), float("nan")
    t = (mean(a) - mean(b)) / se
    return t, two_sided_p(t)


def two_sided_p(z: float) -> float:
    """p-value of |z| under the standard normal."""
    return math.erfc(abs(z) / math.sqrt(2))


def stars(p: float) -> str:
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""


# --------------------------------------------------------------------------
# Linear algebra (small, dense, well-conditioned systems only)
# --------------------------------------------------------------------------

def invert(matrix: list[list[float]]) -> list[list[float]]:
    """Gauss-Jordan inverse with partial pivoting."""
    n = len(matrix)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]

    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("singular matrix - check for perfectly collinear predictors")
        a[col], a[pivot] = a[pivot], a[col]

        div = a[col][col]
        a[col] = [v / div for v in a[col]]
        for r in range(n):
            if r != col and a[r][col] != 0.0:
                factor = a[r][col]
                a[r] = [v - factor * p for v, p in zip(a[r], a[col])]

    return [row[n:] for row in a]


def _xtx_xty(X: list[list[float]], y: list[float]) -> tuple[list[list[float]], list[float]]:
    k = len(X[0])
    xtx = [[0.0] * k for _ in range(k)]
    xty = [0.0] * k
    for row, target in zip(X, y):
        for i in range(k):
            xty[i] += row[i] * target
            for j in range(i, k):
                xtx[i][j] += row[i] * row[j]
    for i in range(k):
        for j in range(i):
            xtx[i][j] = xtx[j][i]
    return xtx, xty


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

@dataclass
class ModelResult:
    names: list[str]
    coef: list[float]
    se: list[float]
    stat: list[float]          # t (OLS) or z (logit)
    pvalue: list[float]
    n: int
    r2: float = float("nan")
    kind: str = "OLS"
    extra: dict = field(default_factory=dict)

    def get(self, name: str) -> float:
        return self.coef[self.names.index(name)]

    def p(self, name: str) -> float:
        return self.pvalue[self.names.index(name)]

    def table(self, transform=None, transform_label: str = "") -> str:
        """Coefficient table as plain text, ready for a report."""
        head = f"{'term':<34}{'coef':>10}{'std err':>10}"
        head += f"{transform_label:>12}" if transform else ""
        head += f"{'p':>9}"
        lines = [head, "-" * len(head)]
        for i, name in enumerate(self.names):
            line = f"{name:<34}{self.coef[i]:>10.4f}{self.se[i]:>10.4f}"
            if transform:
                line += f"{transform(self.coef[i]):>12.3f}"
            line += f"{self.pvalue[i]:>9.3f} {stars(self.pvalue[i])}"
            lines.append(line)
        lines.append(f"n = {self.n:,}" + (f"   R2 = {self.r2:.3f}" if self.r2 == self.r2 else ""))
        return "\n".join(lines)


def ols(X: list[list[float]], y: list[float], names: list[str]) -> ModelResult:
    """Ordinary least squares via the normal equations."""
    n, k = len(X), len(X[0])
    xtx, xty = _xtx_xty(X, y)
    inv = invert(xtx)
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]

    fitted = [sum(b * v for b, v in zip(beta, row)) for row in X]
    resid = [yi - fi for yi, fi in zip(y, fitted)]
    rss = sum(r * r for r in resid)
    ybar = mean(y)
    tss = sum((yi - ybar) ** 2 for yi in y)
    sigma2 = rss / (n - k)

    se = [math.sqrt(sigma2 * inv[i][i]) for i in range(k)]
    tstat = [b / s if s else float("nan") for b, s in zip(beta, se)]
    return ModelResult(names, beta, se, tstat, [two_sided_p(t) for t in tstat],
                       n=n, r2=1 - rss / tss, kind="OLS")


def logistic_regression(X: list[list[float]], y: list[int], names: list[str],
                        max_iter: int = 50, tol: float = 1e-8) -> ModelResult:
    """Binary logit fitted by Newton-Raphson (IRLS)."""
    n, k = len(X), len(X[0])
    beta = [0.0] * k
    loglik = float("-inf")

    for _ in range(max_iter):
        eta = [sum(b * v for b, v in zip(beta, row)) for row in X]
        mu = [1 / (1 + math.exp(-max(-35, min(35, e)))) for e in eta]
        w = [max(m * (1 - m), 1e-9) for m in mu]

        # Hessian (X'WX) and score (X'(y - mu))
        hess = [[0.0] * k for _ in range(k)]
        score = [0.0] * k
        for row, yi, mi, wi in zip(X, y, mu, w):
            for i in range(k):
                score[i] += row[i] * (yi - mi)
                for j in range(i, k):
                    hess[i][j] += wi * row[i] * row[j]
        for i in range(k):
            for j in range(i):
                hess[i][j] = hess[j][i]

        inv = invert(hess)
        step = [sum(inv[i][j] * score[j] for j in range(k)) for i in range(k)]
        beta = [b + s for b, s in zip(beta, step)]

        new_ll = sum(yi * math.log(max(mi, 1e-12)) + (1 - yi) * math.log(max(1 - mi, 1e-12))
                     for yi, mi in zip(y, mu))
        if abs(new_ll - loglik) < tol:
            loglik = new_ll
            break
        loglik = new_ll

    se = [math.sqrt(inv[i][i]) for i in range(k)]
    z = [b / s if s else float("nan") for b, s in zip(beta, se)]

    # McFadden pseudo-R2 against the intercept-only model
    ybar = sum(y) / n
    ll_null = sum(yi * math.log(ybar) + (1 - yi) * math.log(1 - ybar) for yi in y)
    return ModelResult(names, beta, se, z, [two_sided_p(zi) for zi in z],
                       n=n, r2=1 - loglik / ll_null, kind="Logit",
                       extra={"loglik": loglik})


# --------------------------------------------------------------------------
# Design-matrix helpers
# --------------------------------------------------------------------------

def dummy_columns(rows: list[dict], column: str, base: str) -> tuple[list[str], list[str]]:
    """Category levels (excluding the reference level) and their column names."""
    levels = sorted({r[column] for r in rows} - {base})
    return levels, [f"{column}={lvl}" for lvl in levels]


# --------------------------------------------------------------------------
# Scoring a classifier: how well a risk score separates and how honest it is
# --------------------------------------------------------------------------

def auc(scores: list[float], labels: list[int]) -> float:
    """Area under the ROC curve: the chance a random leaver outscores a random stayer (ties count half).

    Computed from ranks (the Mann-Whitney U statistic), so it is exact and O(n log n).
    """
    pairs = sorted(zip(scores, labels))
    n1 = sum(labels)
    n0 = len(labels) - n1
    if not n1 or not n0:
        return float("nan")
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        mid_rank = (i + 1 + j) / 2                # average rank of the tied block, 1-based
        rank_sum += mid_rank * sum(lab for _, lab in pairs[i:j])
        i = j
    return (rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0)


def auc_ci(a: float, n1: int, n0: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for an AUC by Hanley and McNeil (1982): wide when leavers are few."""
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt((a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0))
    return max(0.0, a - z * se), min(1.0, a + z * se)


def brier(probs: list[float], labels: list[int]) -> float:
    """Mean squared error of a predicted probability: 0 is perfect, lower is better."""
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels)


def calibration_slope(probs: list[float], labels: list[int]) -> tuple[float, float]:
    """(intercept, slope) of a logit of the outcome on the logit of the prediction.

    A model that is right out of sample has slope 1: below 1 it is overconfident, its
    high scores too high and its low scores too low, the usual sign of overfitting.
    """
    lp = [math.log(max(p, 1e-9) / max(1 - p, 1e-9)) for p in probs]
    fit = logistic_regression([[1.0, v] for v in lp], labels, ["intercept", "slope"])
    return fit.coef[0], fit.coef[1]


def capture(scores: list[float], labels: list[int], share: float) -> float:
    """Share of all positives found in the top `share` of scores.

    Where the cut falls inside a group of tied scores, that group is counted pro rata, which is what
    breaking the tie at random would give on average: a coarse score cannot win by the order of rows.
    """
    total = sum(labels)
    if not total:
        return float("nan")
    ranked = sorted(zip(scores, labels), key=lambda t: -t[0])
    room, found, i = len(ranked) * share, 0.0, 0
    while i < len(ranked) and room > 0:
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        size, hits = j - i, sum(lab for _, lab in ranked[i:j])
        found += hits * min(1.0, room / size)
        room -= size
        i = j
    return found / total


# --------------------------------------------------------------------------
# Survival: when people leave, not only whether
# --------------------------------------------------------------------------
# Each subject is (entry, exit, event): at risk from `entry` (exclusive) to `exit` (inclusive), with
# event = 1 if the exit is the outcome and 0 if observation simply stopped (censoring). A late `entry`
# is delayed entry, or left truncation: someone hired years before the data starts only enters the
# risk set at the tenure they had when observation began. Ignoring it overstates survival.

def kaplan_meier(subjects: list[tuple[float, float, int]]) -> list[tuple[float, float, float, int]]:
    """Product-limit estimate with delayed entry. Returns (time, survival, Greenwood se, at risk) at each event time."""
    times = sorted({t for _, t, e in subjects if e})
    out, s, var_sum = [], 1.0, 0.0
    for t in times:
        at_risk = sum(1 for a, b, _ in subjects if a < t <= b)
        deaths = sum(1 for _, b, e in subjects if e and b == t)
        if not at_risk:
            continue
        s *= 1 - deaths / at_risk
        if at_risk > deaths:
            var_sum += deaths / (at_risk * (at_risk - deaths))
        out.append((t, s, s * math.sqrt(var_sum), at_risk))
    return out


def survival_at(curve: list[tuple[float, float, float, int]], t: float) -> float:
    s = 1.0
    for time, surv, _, _ in curve:
        if time > t:
            break
        s = surv
    return s


def restricted_mean(curve: list[tuple[float, float, float, int]], horizon: float) -> float:
    """Area under the survival curve up to `horizon`: expected time stayed within it."""
    area, last_t, last_s = 0.0, 0.0, 1.0
    for t, s, _, _ in curve:
        if t > horizon:
            break
        area += last_s * (t - last_t)
        last_t, last_s = t, s
    return area + last_s * (horizon - last_t)


def logrank(subjects: list[tuple[float, float, int]], groups: list[int]) -> tuple[float, float]:
    """Two-group log-rank test (groups coded 0/1). Returns (chi-square, p) on one degree of freedom."""
    times = sorted({t for _, t, e in subjects if e})
    o_minus_e, var = 0.0, 0.0
    for t in times:
        n = n1 = d = d1 = 0
        for (a, b, e), g in zip(subjects, groups):
            if a < t <= b:
                n += 1
                n1 += g
                if e and b == t:
                    d += 1
                    d1 += g
        if n < 2:
            continue
        o_minus_e += d1 - d * n1 / n
        var += d * (n1 / n) * (1 - n1 / n) * (n - d) / (n - 1)
    chi2 = o_minus_e ** 2 / var if var else float("nan")
    return chi2, math.erfc(math.sqrt(chi2 / 2)) if chi2 == chi2 else float("nan")


def cox(subjects: list[tuple[float, float, int]], X: list[list[float]], names: list[str],
        max_iter: int = 30, tol: float = 1e-9) -> ModelResult:
    """Cox proportional hazards by Newton-Raphson on the partial likelihood (Breslow ties, delayed entry).

    Hazard ratios are exp(coef). No intercept: the baseline hazard is left unspecified, which is the point.
    The risk-set sums are kept running while time is walked backwards, so each iteration is one pass.
    """
    n, k = len(subjects), len(names)
    entry = [a for a, _, _ in subjects]
    exit_ = [b for _, b, _ in subjects]
    by_exit = sorted(range(n), key=lambda i: -exit_[i])
    by_entry = sorted(range(n), key=lambda i: -entry[i])
    deaths: dict[float, list[int]] = {}
    for i, (a, b, e) in enumerate(subjects):
        if e and a < b:
            deaths.setdefault(b, []).append(i)
    times = sorted(deaths, reverse=True)

    beta, loglik = [0.0] * k, float("-inf")
    for _ in range(max_iter):
        w = [math.exp(sum(b * x for b, x in zip(beta, row))) for row in X]
        s0, s1, s2 = 0.0, [0.0] * k, [[0.0] * k for _ in range(k)]

        def shift(i: int, sign: float) -> None:
            nonlocal s0
            s0 += sign * w[i]
            for j in range(k):
                s1[j] += sign * w[i] * X[i][j]
                for l in range(k):
                    s2[j][l] += sign * w[i] * X[i][j] * X[i][l]

        score, info, new_ll, pe, pn = [0.0] * k, [[0.0] * k for _ in range(k)], 0.0, 0, 0
        for t in times:
            while pe < n and exit_[by_exit[pe]] >= t:       # still in the data at t
                shift(by_exit[pe], 1.0)
                pe += 1
            while pn < n and entry[by_entry[pn]] >= t:      # not yet entered at t
                shift(by_entry[pn], -1.0)
                pn += 1
            ds, d = deaths[t], len(deaths[t])
            new_ll += sum(math.log(w[i]) for i in ds) - d * math.log(s0)
            for j in range(k):
                score[j] += sum(X[i][j] for i in ds) - d * s1[j] / s0
                for l in range(k):
                    info[j][l] += d * (s2[j][l] / s0 - s1[j] * s1[l] / s0 ** 2)
        inv = invert(info)
        beta = [b + sum(inv[j][l] * score[l] for l in range(k)) for j, b in enumerate(beta)]
        if abs(new_ll - loglik) < tol:
            loglik = new_ll
            break
        loglik = new_ll
    se = [math.sqrt(inv[j][j]) for j in range(k)]
    z = [b / s if s else float("nan") for b, s in zip(beta, se)]
    return ModelResult(names, beta, se, z, [two_sided_p(v) for v in z], n=n, kind="Cox",
                       extra={"loglik": loglik, "events": sum(len(v) for v in deaths.values())})
