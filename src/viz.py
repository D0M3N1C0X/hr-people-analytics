"""
Tiny SVG charting library - pure standard library, no matplotlib.

Six chart types, one consistent visual style, written straight to .svg files
that GitHub renders inline in the README. Charts are drawn on an explicit white
canvas so they stay readable in both GitHub light and dark themes.
"""

from __future__ import annotations

import math
from pathlib import Path

# ---- style ---------------------------------------------------------------
W, H = 920, 545
M = {"top": 110, "right": 48, "bottom": 96, "left": 96}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
INK, MUTED, GRID, PAPER = "#1f2933", "#6b7280", "#e5e7eb", "#ffffff"
BLUE, AMBER, GREEN, RED, VIOLET, SLATE = (
    "#2563eb", "#f59e0b", "#10b981", "#dc2626", "#7c3aed", "#94a3b8")
PALETTE = [BLUE, AMBER, GREEN, VIOLET, RED, SLATE]


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _text(x, y, s, size=13, color=INK, anchor="start", weight="normal", rotate=None):
    transform = f' transform="rotate({rotate} {x} {y})"' if rotate else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}" font-weight="{weight}"{transform}>'
            f'{_esc(s)}</text>')


def _nice_ticks(vmax: float, count: int = 5) -> list[float]:
    """Round axis ticks from 0 to just above vmax."""
    if vmax <= 0:
        return [0, 1]
    raw = vmax / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
    ticks, v = [], 0.0
    while v < vmax + step * 0.999:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _frame(title: str, subtitle: str, ylabel: str, ticks: list[float], fmt) -> list[str]:
    """Title block, y-axis gridlines and labels. Returns SVG fragments."""
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"], W - M["right"]
    out = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
           _text(left - 46, 38, title, size=19, weight="600")]
    if subtitle:
        out.append(_text(left - 46, 60, subtitle, size=13, color=MUTED))
    if ylabel:
        out.append(_text(24, (top + bottom) / 2, ylabel, size=12, color=MUTED,
                         anchor="middle", rotate=-90))

    vmax = ticks[-1]
    for t in ticks:
        y = bottom - (t / vmax) * (bottom - top)
        out.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                   f'stroke="{GRID}" stroke-width="1"/>')
        out.append(_text(left - 10, y + 4, fmt(t), size=12, color=MUTED, anchor="end"))
    return out


def _legend(labels: list[str], colors: list[str]) -> list[str]:
    out, x = [], W - M["right"]
    for label, color in reversed(list(zip(labels, colors))):
        width = 9 + 7 * len(label) + 22
        x -= width
        out.append(f'<rect x="{x}" y="78" width="11" height="11" rx="2" fill="{color}"/>')
        out.append(_text(x + 17, 88, label, size=12, color=MUTED))
    return out


def _save(path: Path, body: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'width="{W}" height="{H}" role="img">' + "".join(body) + "</svg>")
    path.write_text(svg, encoding="utf-8")
    return path


def _xlabels(labels: list[str], xs: list[float], rotate_at: int = 7) -> list[str]:
    """X tick labels, rotated when there are too many to sit side by side."""
    bottom = H - M["bottom"]
    rot = len(labels) > rotate_at or max(len(str(x)) for x in labels) > 12
    return [_text(x, bottom + (26 if not rot else 20), lab, size=12, color=INK,
                  anchor="middle" if not rot else "end", rotate=None if not rot else -32)
            for lab, x in zip(labels, xs)]


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------

def bar_chart(path, labels, values, title, subtitle="", ylabel="",
              fmt=lambda v: f"{v:,.0f}", color=BLUE, highlight=None,
              target=None, target_label="") -> Path:
    """Vertical bars; `highlight` recolours the bars whose label is in the set."""
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"], W - M["right"]
    ticks = _nice_ticks(max(values + ([target] if target else [])))
    vmax = ticks[-1]
    body = _frame(title, subtitle, ylabel, ticks, fmt)

    slot = (right - left) / len(values)
    bw = min(slot * 0.62, 76)
    xs = []
    for i, (label, value) in enumerate(zip(labels, values)):
        cx = left + slot * (i + 0.5)
        xs.append(cx)
        h = (value / vmax) * (bottom - top)
        c = RED if (highlight and label in highlight) else color
        body.append(f'<rect x="{cx - bw / 2:.1f}" y="{bottom - h:.1f}" width="{bw:.1f}" '
                    f'height="{h:.1f}" rx="3" fill="{c}"/>')
        body.append(_text(cx, bottom - h - 8, fmt(value), size=12, weight="600", anchor="middle"))

    if target is not None:
        y = bottom - (target / vmax) * (bottom - top)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
                    f'stroke="{RED}" stroke-width="1.5" stroke-dasharray="6 4"/>')
        # Anchor the caption over the shorter end of the series, so it never
        # lands on top of a bar's value label.
        at_left = values[0] < values[-1]
        body.append(_text(left if at_left else right, y - 7,
                          target_label or f"target {fmt(target)}", size=12, color=RED,
                          anchor="start" if at_left else "end", weight="600"))

    body += _xlabels(labels, xs)
    return _save(Path(path), body)


def grouped_bar_chart(path, labels, series: dict, title, subtitle="", ylabel="",
                      fmt=lambda v: f"{v:,.0f}", show_values=True) -> Path:
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"], W - M["right"]
    ticks = _nice_ticks(max(max(v) for v in series.values()))
    vmax = ticks[-1]
    body = _frame(title, subtitle, ylabel, ticks, fmt)
    colors = PALETTE[:len(series)]
    body += _legend(list(series), colors)

    slot = (right - left) / len(labels)
    bw = min(slot * 0.72 / len(series), 46)
    xs = []
    for i, label in enumerate(labels):
        cx = left + slot * (i + 0.5)
        xs.append(cx)
        start = cx - bw * len(series) / 2
        for j, (name, values) in enumerate(series.items()):
            h = (values[i] / vmax) * (bottom - top)
            x = start + j * bw
            body.append(f'<rect x="{x:.1f}" y="{bottom - h:.1f}" width="{bw - 4:.1f}" '
                        f'height="{h:.1f}" rx="3" fill="{colors[j]}"/>')
            if show_values:
                body.append(_text(x + (bw - 4) / 2, bottom - h - 6, fmt(values[i]),
                                  size=11, anchor="middle", color=MUTED))
    body += _xlabels(labels, xs)
    return _save(Path(path), body)


def stacked_share_chart(path, labels, series: dict, title, subtitle="",
                        ylabel="share of headcount") -> Path:
    """100%-stacked bars - used for the pay-quartile composition by gender."""
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"], W - M["right"]
    body = _frame(title, subtitle, ylabel, [0, 25, 50, 75, 100], lambda v: f"{v:.0f}%")
    colors = PALETTE[:len(series)]
    body += _legend(list(series), colors)

    slot = (right - left) / len(labels)
    bw = min(slot * 0.55, 90)
    xs = []
    for i, label in enumerate(labels):
        cx = left + slot * (i + 0.5)
        xs.append(cx)
        total = sum(values[i] for values in series.values()) or 1
        acc = 0.0
        for j, (name, values) in enumerate(series.items()):
            pct = values[i] / total * 100
            h = pct / 100 * (bottom - top)
            y = bottom - (acc + pct) / 100 * (bottom - top)
            body.append(f'<rect x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                        f'height="{h:.1f}" fill="{colors[j]}"/>')
            if pct > 7:
                body.append(_text(cx, y + h / 2 + 5, f"{pct:.0f}%", size=12,
                                  color="#ffffff", anchor="middle", weight="600"))
            acc += pct
    body += _xlabels(labels, xs)
    return _save(Path(path), body)


def line_chart(path, x_labels, series: dict, title, subtitle="", ylabel="",
               fmt=lambda v: f"{v:,.0f}", markers=True) -> Path:
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"], W - M["right"]
    ticks = _nice_ticks(max(max(v) for v in series.values()))
    vmax = ticks[-1]
    body = _frame(title, subtitle, ylabel, ticks, fmt)
    colors = PALETTE[:len(series)]
    if len(series) > 1:
        body += _legend(list(series), colors)

    step = (right - left) / max(len(x_labels) - 1, 1)
    xs = [left + i * step for i in range(len(x_labels))]
    for j, (name, values) in enumerate(series.items()):
        pts = [(x, bottom - (v / vmax) * (bottom - top)) for x, v in zip(xs, values)]
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        body.append(f'<path d="{d}" fill="none" stroke="{colors[j]}" stroke-width="2.6" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>')
        if markers:
            for x, y in pts:
                body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{PAPER}" '
                            f'stroke="{colors[j]}" stroke-width="2.2"/>')
    body += _xlabels(x_labels, xs, rotate_at=8)
    return _save(Path(path), body)


def pareto_chart(path, labels, values, title, subtitle="", ylabel="cases") -> Path:
    """Bars sorted descending plus the cumulative-share line (the 80/20 view)."""
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"], W - M["right"]
    order = sorted(range(len(values)), key=lambda i: -values[i])
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    ticks = _nice_ticks(max(values))
    vmax = ticks[-1]
    body = _frame(title, subtitle, ylabel, ticks, lambda v: f"{v:,.0f}")

    total = sum(values)
    slot = (right - left) / len(values)
    bw = min(slot * 0.6, 66)
    xs, cum, acc = [], [], 0.0
    for i, value in enumerate(values):
        cx = left + slot * (i + 0.5)
        xs.append(cx)
        h = (value / vmax) * (bottom - top)
        body.append(f'<rect x="{cx - bw / 2:.1f}" y="{bottom - h:.1f}" width="{bw:.1f}" '
                    f'height="{h:.1f}" rx="3" fill="{BLUE}"/>')
        acc += value / total * 100
        cum.append(acc)

    pts = [(x, bottom - c / 100 * (bottom - top)) for x, c in zip(xs, cum)]
    d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    body.append(f'<path d="{d}" fill="none" stroke="{AMBER}" stroke-width="2.6"/>')
    for (x, y), c in zip(pts, cum):
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{PAPER}" '
                    f'stroke="{AMBER}" stroke-width="2.2"/>')
        body.append(_text(x, y - 11, f"{c:.0f}%", size=11, color=AMBER,
                          anchor="middle", weight="600"))
    body += _legend(["cases", "cumulative %"], [BLUE, AMBER])
    body += _xlabels(labels, xs, rotate_at=5)
    return _save(Path(path), body)


def lollipop_chart(path, labels, values, title, subtitle="", xlabel="",
                   fmt=lambda v: f"{v:+.2f}", reference=0.0) -> Path:
    """Horizontal dot-and-stem chart - used for regression odds ratios."""
    top, bottom, left, right = M["top"], H - M["bottom"], M["left"] + 150, W - M["right"]
    lo, hi = min(min(values), reference), max(max(values), reference)
    span = (hi - lo) or abs(hi) or 1.0
    vmin, vmax = lo - 0.20 * span, hi + 0.10 * span   # padding leaves room for labels
    body = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
            _text(M["left"] - 46, 38, title, size=19, weight="600")]
    if subtitle:
        body.append(_text(M["left"] - 46, 60, subtitle, size=13, color=MUTED))

    def sx(v):
        return left + (v - vmin) / (vmax - vmin) * (right - left)

    for t in _nice_ticks(vmax, 5):
        if t < vmin:
            continue
        body.append(f'<line x1="{sx(t):.1f}" y1="{top}" x2="{sx(t):.1f}" y2="{bottom}" '
                    f'stroke="{GRID}" stroke-width="1"/>')
        body.append(_text(sx(t), bottom + 22, f"{t:g}", size=12, color=MUTED, anchor="middle"))

    body.append(f'<line x1="{sx(reference):.1f}" y1="{top}" x2="{sx(reference):.1f}" '
                f'y2="{bottom}" stroke="{MUTED}" stroke-width="1.5" stroke-dasharray="5 4"/>')

    slot = (bottom - top) / len(values)
    for i, (label, value) in enumerate(zip(labels, values)):
        y = top + slot * (i + 0.5)
        color = RED if value > reference else GREEN
        body.append(f'<line x1="{sx(reference):.1f}" y1="{y:.1f}" x2="{sx(value):.1f}" '
                    f'y2="{y:.1f}" stroke="{color}" stroke-width="2.4" opacity="0.55"/>')
        body.append(f'<circle cx="{sx(value):.1f}" cy="{y:.1f}" r="6.5" fill="{color}"/>')
        body.append(_text(left - 14, y + 5, label, size=12.5, anchor="end"))
        outward = 13 if value >= reference else -13
        body.append(_text(sx(value) + outward, y + 5, fmt(value), size=12, weight="600",
                          color=color, anchor="start" if value >= reference else "end"))

    if xlabel:
        body.append(_text((left + right) / 2, H - 34, xlabel, size=12,
                          color=MUTED, anchor="middle"))
    return _save(Path(path), body)
