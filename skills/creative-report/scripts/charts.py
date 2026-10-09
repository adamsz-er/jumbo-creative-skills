"""Inline-SVG charts for the dashboard. Standard library only.

Every chart carries its labels, units and a <title> on each mark, uses the
template's CSS classes for colour (so light, dark and print all work) and is
safe to embed: every string that came from data is escaped.
"""
from __future__ import annotations

import html
import math
import datetime as dt
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def bar_chart(items: Sequence[Tuple[str, float, str, str]], label: str, unit: str, width: int = 420) -> str:
    """Horizontal bars: (name, value, css class, value text). Every bar carries its label and value."""
    if not items:
        return ""
    left, right, row = 150, 50, 28
    top = max(v for _, v, _, _ in items) or 1
    height = row * len(items) + 34
    parts = ['<figure class="chart"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for i, (name, value, css, text) in enumerate(items):
        y = i * row + 6
        length = max((width - left - right) * value / top, 2)
        shown = name if len(name) <= 22 else name[:21] + "..."
        parts.append('<text class="lbl" x="%d" y="%d" text-anchor="end">%s</text>' % (left - 9, y + 16, esc(shown)))
        parts.append('<rect class="bar %s" x="%d" y="%d" width="%.1f" height="20" rx="6"><title>%s: %s</title></rect>'
                     % (esc(css), left, y, length, esc(name), esc(text)))
        parts.append('<text x="%.1f" y="%d">%s</text>' % (left + length + 8, y + 15, esc(text)))
    parts.append('<line class="axis" x1="%d" y1="2" x2="%d" y2="%d"/>' % (left, left, height - 28))
    parts.append('<text x="%d" y="%d">%s</text>' % (left, height - 8, esc(unit)))
    parts.append("</svg><figcaption>%s</figcaption></figure>" % esc(label))
    return "".join(parts)


def _ticks(low: float, high: float, count: int = 4) -> List[float]:
    return [low + (high - low) * i / count for i in range(count + 1)]


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def scatter(points: Sequence[Tuple[float, float, str]], xlabel: str, ylabel: str, label: str) -> str:
    """Dots with labelled axes and dashed medians of the plotted ads."""
    if len(points) < 2:
        return ""
    width, height, left, bottom, top, right = 480, 340, 50, 46, 14, 14
    xs, ys = [p[0] for p in points], [p[1] for p in points]

    def span(values):
        low, high = min(values), max(values)
        pad = (high - low) * 0.08 or 1.0
        return low - pad, high + pad

    (x0, x1), (y0, y1) = span(xs), span(ys)

    def px(x):
        return left + (x - x0) / (x1 - x0) * (width - left - right)

    def py(y):
        return height - bottom - (y - y0) / (y1 - y0) * (height - bottom - top)

    parts = ['<figure class="chart"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, top, left, height - bottom))
    for value in _ticks(x0, x1):
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%.1f</text>' % (px(value), height - bottom + 16, value))
    for value in _ticks(y0, y1):
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%.1f</text>' % (left - 8, py(value) + 4, value))
    mx, my = _median(xs), _median(ys)
    parts.append('<line class="guide" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (px(mx), top, px(mx), height - bottom))
    parts.append('<line class="guide" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, py(my), width - right, py(my)))
    for x, y, name in points:
        parts.append('<circle class="dot" cx="%.1f" cy="%.1f" r="6"><title>%s: %s %.1f, %s %.1f</title></circle>'
                     % (px(x), py(y), esc(name), esc(xlabel), x, esc(ylabel), y))
    parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % ((left + width - right) / 2, height - 6, esc(xlabel)))
    parts.append('<text transform="rotate(-90 14 %.1f)" x="14" y="%.1f" text-anchor="middle">%s</text>'
                 % ((top + height - bottom) / 2, (top + height - bottom) / 2, esc(ylabel)))
    parts.append("</svg><figcaption>%s. Dashed lines mark the median of the plotted ads.</figcaption></figure>" % esc(label))
    return "".join(parts)


def legend(items: Sequence[Tuple[str, str]]) -> str:
    """A visible key under a chart: (css class of the swatch, what it shows). Text, so it prints and reads at any width."""
    return '<ul class="legend">%s</ul>' % "".join('<li><span class="sw %s"></span>%s</li>' % (esc(css), esc(text)) for css, text in items)


SPARK_AVERAGE_DAYS = 7  # the faint second line on a tile's sparkline: a rolling average over this many days
ROLLING_MIN_VALUES = 5  # arbitrary default: a rolling average needs this many real values inside its window, else it is a gap


def rolling(values: Sequence[Optional[float]], window: int = SPARK_AVERAGE_DAYS, need: int = ROLLING_MIN_VALUES) -> List[Optional[float]]:
    """Mean of the last `window` values at each point, skipping gaps; None when fewer than `need` real values fall in the window."""
    out: List[Optional[float]] = []
    for i in range(len(values)):
        real = [v for v in values[max(0, i - window + 1):i + 1] if v is not None]
        out.append(sum(real) / len(real) if len(real) >= need else None)
    return out


def day_label(day: str) -> str:
    """"2026-09-07" -> "7 Sep"; anything that is not an ISO date is shown as it came."""
    try:
        d = dt.date.fromisoformat(str(day)[:10])
    except ValueError:
        return str(day)
    return "%d %s" % (d.day, d.strftime("%b"))


def sparkline(values: Sequence[Optional[float]], label: str, width: int = 120, height: int = 32,
              tips: Optional[Sequence[str]] = None, average: Optional[Sequence[Optional[float]]] = None) -> str:
    """A tiny line with no axes; "" with fewer than two real points. A gap (None) breaks the line.

    `tips` (one text per point) adds an invisible hover column per point; `average` draws a faint second line on the same scale.
    """
    real = [v for v in values if v is not None]
    if len(real) < 2:
        return ""
    both = real + [v for v in (average or []) if v is not None]
    low, high = min(both), max(both)
    span = (high - low) or 1.0
    step = (width - 4) / (len(values) - 1)

    def path_of(series: Sequence[Optional[float]]) -> str:
        path, pen = [], False
        for i, value in enumerate(series):
            if value is None:
                pen = False
                continue
            path.append("%s%.1f %.1f" % ("L" if pen else "M", 2 + i * step, height - 3 - (value - low) / span * (height - 6)))
            pen = True
        return " ".join(path)

    faint = '<path class="avg" d="%s"/>' % path_of(average) if average and any(v is not None for v in average) else ""
    hits = "".join('<rect class="hit" x="%.1f" y="0" width="%.1f" height="%d" data-tip="%s"/>' % (2 + i * step - step / 2, max(step, 1), height, esc(t))
                   for i, t in enumerate(tips or []) if t)
    return ('<svg class="spark" viewBox="0 0 %d %d" preserveAspectRatio="none" role="img" aria-label="%s">%s<path d="%s"/>%s</svg>'
            % (width, height, esc(label), faint, path_of(values), hits))


def _axis_text(value: float) -> str:
    if value == 0:
        return "0"
    return "{:,.0f}".format(value) if abs(value) >= 100 else "{:,.2f}".format(value)


ZERO_DECIMAL_CURRENCIES = frozenset(("JPY", "KRW", "VND", "CLP", "ISK", "UGX", "XAF", "XOF", "XPF", "PYG", "RWF", "VUV", "DJF", "GNF", "KMF", "BIF"))


def _trim(value: float) -> str:
    """Two decimals, trimmed; a value under 0.1 keeps its significant digits so neighbouring small ticks never read the same."""
    if value and abs(value) < 0.1:
        return "%.6g" % value
    return ("%.2f" % value).rstrip("0").rstrip(".")


def axis_format(kind: str, currency: Optional[str] = None):
    """A tick formatter in the axis unit: money keeps the currency's own digits, a rate reads 0.8%, a ratio 2.45x; zero is a plain 0 or 0x."""
    if kind == "money":
        whole = (currency or "").upper() in ZERO_DECIMAL_CURRENCIES
        return lambda v: "0" if v == 0 else "{:,.0f}".format(v) if whole or abs(v) >= 100 else "{:,.2f}".format(v)
    suffix = {"pct": "%", "x": "x"}[kind]
    return lambda v: "0" + suffix if v == 0 else _trim(v) + suffix


def combo_chart(labels: Sequence[str], bars: Optional[Sequence[Optional[float]]], line: Optional[Sequence[Optional[float]]],
                bar_unit: str, line_unit: str, label: str, width: int = 880, height: int = 300,
                bar_fmt=_axis_text, line_fmt=_axis_text) -> str:
    """Bars on the left axis and a line on the right axis over the same x labels; either may be absent.

    A None value is a gap: no bar is drawn and the line breaks, so a missing day never reads as 0. `bar_fmt` and `line_fmt`
    write the ticks in each axis's unit; when both axes start at zero the right axis leaves its zero to the left one.
    """
    count = len(labels)
    if not count or not ((bars and any(v is not None for v in bars)) or (line and any(v is not None for v in line))):
        return ""
    left, right, top, bottom = 56, 56 if line else 14, 16, 44
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / count
    parts = ['<figure class="chart wide"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    if bars:
        peak = max((v for v in bars if v is not None), default=0) or 1.0
        for frac in (0.0, 0.5, 1.0):
            y = height - bottom - frac * plot_h
            parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, y + 4, bar_fmt(peak * frac)))
        for i, value in enumerate(bars):
            if value is None:
                continue
            h = max(plot_h * value / peak, 1)
            parts.append('<rect class="bar" x="%.1f" y="%.1f" width="%.1f" height="%.1f"><title>%s: %s %s</title></rect>'
                         % (left + i * slot + slot * 0.15, height - bottom - h, slot * 0.7, h, esc(labels[i]), bar_fmt(value), esc(bar_unit)))
        parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">%s</text>'
                     % (top + plot_h / 2, top + plot_h / 2, esc(bar_unit)))
    if line:
        real = [v for v in line if v is not None]
        if real:
            low, high = min(real + [0.0]), max(real)
            span = (high - low) or 1.0
            for frac in (0.0, 0.5, 1.0):
                if frac == 0.0 and low == 0 and bars:
                    continue
                y = height - bottom - frac * plot_h
                parts.append('<text x="%d" y="%.1f">%s</text>' % (width - right + 6, y + 4, line_fmt(low + span * frac)))
            path, pen, dots = [], False, []
            for i, value in enumerate(line):
                if value is None:
                    pen = False
                    continue
                x, y = left + i * slot + slot / 2, height - bottom - (value - low) / span * plot_h
                path.append("%s%.1f %.1f" % ("L" if pen else "M", x, y))
                pen = True
                dots.append('<circle class="dot line-dot" cx="%.1f" cy="%.1f" r="3"><title>%s: %s %s</title></circle>'
                            % (x, y, esc(labels[i]), line_fmt(value), esc(line_unit)))
            parts.append('<path class="line" d="%s"/>' % " ".join(path))
            parts.extend(dots)
            parts.append('<text transform="rotate(90 %d %.1f)" x="%d" y="%.1f" text-anchor="middle">%s</text>'
                         % (width - 10, top + plot_h / 2, width - 10, top + plot_h / 2, esc(line_unit)))
    tick_every = max(1, -(-count // (3 if width < 400 else 6)))
    for i in range(0, count, tick_every):
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (left + i * slot + slot / 2, height - bottom + 16, esc(labels[i][5:] or labels[i])))
    key = legend([("bar", bar_unit), ("line", line_unit)]) if (bars and line) else ""
    parts.append("</svg>%s<figcaption>%s</figcaption></figure>" % (key, esc(label)))
    return "".join(parts)


def pareto_chart(spend: Sequence[float], cum_spend: Sequence[float], cum_value: Optional[Sequence[float]],
                 cut: Optional[int], label: str, currency: str, width: int = 880, height: int = 300) -> str:
    """Ads ranked by spend as bars, with cumulative share of spend and of purchase value as lines (percent axis).

    `cut` is the count of top ads to mark with a vertical line (None for no mark).
    """
    count = len(spend)
    if not count:
        return ""
    left, right, top, bottom = 56, 52, 16, 46
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / count
    peak = max(spend) or 1.0
    parts = ['<figure class="chart wide"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    for frac in (0.0, 0.5, 1.0):
        y = height - bottom - frac * plot_h
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, y + 4, _axis_text(peak * frac)))
        parts.append('<text x="%d" y="%.1f">%d%%</text>' % (width - right + 6, y + 4, round(frac * 100)))
    for i, value in enumerate(spend):
        h = max(plot_h * value / peak, 0.5)
        parts.append('<rect class="bar" x="%.2f" y="%.1f" width="%.2f" height="%.1f"><title>Rank %d: %s %s spend</title></rect>'
                     % (left + i * slot + slot * 0.1, height - bottom - h, max(slot * 0.8, 0.6), h, i + 1, _axis_text(value), esc(currency)))

    def line_path(series: Sequence[float], css: str) -> str:
        pts = " ".join("%s%.1f %.1f" % ("L" if i else "M", left + i * slot + slot / 2, height - bottom - min(v, 100) / 100 * plot_h)
                       for i, v in enumerate(series))
        return '<path class="line %s" d="%s"/>' % (css, pts)

    parts.append(line_path(cum_spend, "spend-line"))
    if cum_value:
        parts.append(line_path(cum_value, "value-line"))
    if cut:
        x = left + cut * slot
        parts.append('<line class="guide cut" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (x, top, x, height - bottom))
        parts.append('<text x="%.1f" y="%d" text-anchor="%s">top %d</text>' % (x + (4 if x < width / 2 else -4), top + 10, "start" if x < width / 2 else "end", cut))
    parts.append('<text x="%.1f" y="%d" text-anchor="middle">Ads ranked by spend (1 = most spend)</text>' % (left + plot_w / 2, height - 8))
    parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">Spend (%s)</text>'
                 % (top + plot_h / 2, top + plot_h / 2, esc(currency)))
    key = legend([("bar", "Spend per ad (bars, left axis, %s)" % currency), ("spend-line", "Cumulative share of spend (right axis, percent)")]
                 + ([("value-line", "Cumulative share of purchase value (right axis, percent)")] if cum_value else []))
    parts.append("</svg>%s<figcaption>%s%s</figcaption></figure>"
                 % (key, esc(label), "" if cum_value else ". There is no purchase value in the data, so only spend is shown."))
    return "".join(parts)


def gauge(value: Optional[float], label: str, caption: str) -> str:
    """A horizontal meter for a percentage; an unknown value draws an empty track, never a zero fill."""
    shown = "n/a" if value is None else "%.0f%%" % value
    fill = 0 if value is None else max(0.0, min(value, 100.0))
    return ('<figure class="chart gauge"><svg viewBox="0 0 300 54" role="img" aria-label="%s: %s">'
            '<rect class="track" x="0" y="8" width="300" height="18" rx="9"/>'
            '<rect class="bar" x="0" y="8" width="%.1f" height="18" rx="9"><title>%s: %s</title></rect>'
            '<text x="0" y="46">0%%</text><text x="300" y="46" text-anchor="end">100%%</text>'
            '<text class="lbl" x="150" y="46" text-anchor="middle">%s</text></svg><figcaption>%s</figcaption></figure>'
            % (esc(label), shown, fill * 3, esc(label), shown, shown, esc(caption)))


def _short(name: str, limit: int) -> str:
    return name if len(name) <= limit else name[:limit - 1] + "..."


def bubble_chart(points: Sequence[Tuple[float, float, float, str, bool]], xlabel: str, ylabel: str, label: str,
                 x_median: Optional[float], y_median: float, quadrants: Sequence[str], width: int = 560, height: int = 380,
                 colours: Optional[Mapping[str, str]] = None, size_words: str = "spend", note: str = "") -> str:
    """Bubbles at (x, y) with area following size, dashed lines at the two medians and the four quadrants named in words.

    points are (x, y, size, name, show_label); quadrants run top-left, top-right, bottom-left, bottom-right.
    """
    if not points:
        return ""
    left, right, top, bottom, rmax = 54, 16, 16, 46, 18.0
    xs = [p[0] for p in points] + ([x_median] if x_median is not None else [])
    ys = [p[1] for p in points] + [y_median]

    def span(values):
        low, high = min(values), max(values)
        pad = (high - low) * 0.12 or 1.0
        return low - pad, high + pad

    (x0, x1), (y0, y1) = span(xs), span(ys)
    x0, x1, xticks = nice_scale(x0, x1)
    y0, y1, yticks = nice_scale(y0, y1)
    biggest = max(p[2] for p in points) or 1.0

    def px(x):
        return left + (x - x0) / (x1 - x0) * (width - left - right)

    def py(y):
        return height - bottom - (y - y0) / (y1 - y0) * (height - bottom - top)

    parts = ['<figure class="chart wide"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, top, left, height - bottom))
    for value in xticks:
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (px(value), height - bottom + 16, _trim(value)))
    for value in yticks:
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 8, py(value) + 4, _trim(value)))
    if x_median is not None:
        parts.append('<line class="guide" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (px(x_median), top, px(x_median), height - bottom))
    parts.append('<line class="guide" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, py(y_median), width - right, py(y_median)))
    corners = ((left + 6, top + 14, "start"), (width - right - 6, top + 14, "end"),
               (left + 6, height - bottom - 8, "start"), (width - right - 6, height - bottom - 8, "end"))
    quadrants = quadrants if len(quadrants) == 4 else ()
    for (x, y, anchor), words in zip(corners, quadrants):
        parts.append('<text class="quad" x="%d" y="%d" text-anchor="%s">%s</text>' % (x, y, anchor, esc(words)))
    ordered = sorted(points, key=lambda p: -p[2])
    discs = [(px(x), py(y), max(rmax * math.sqrt(max(size, 0) / biggest), 3.0)) for x, y, size, _, _ in ordered]
    taken = []
    for (cx0, cy0, anchor), words in zip(corners, quadrants):
        w0 = 6.6 * len(words)
        taken.append((cx0 if anchor == "start" else cx0 - w0, cy0 - 12, cx0 + w0 if anchor == "start" else cx0, cy0 + 3))
    texts = []
    for (x, y, size, name, show), (cx, cy, r) in zip(ordered, discs):
        paint = ' style="fill:%s;stroke:%s"' % (colours[name], colours[name]) if colours and name in colours else ""
        words = "%s: %s %.2f, %s %.2f, %s %s" % (name, xlabel, x, ylabel, y, size_words, _axis_text(size))
        parts.append('<circle class="bub" cx="%.1f" cy="%.1f" r="%.2f"%s tabindex="0"%s><title>%s</title></circle>' % (cx, cy, r, paint, tip(words), esc(words)))
        if not show:
            continue
        short = _short(name.split(" \u00b7 ")[0], 16)
        w = 6.4 * len(short)
        spots = [(cx + r + 4, cy + 4, "start", cx + r + 4), (cx - r - 4, cy + 4, "end", cx - r - 4 - w),
                 (cx, cy - r - 5, "middle", cx - w / 2), (cx, cy + r + 13, "middle", cx - w / 2)]
        for tx, ty, anchor, x0 in spots:
            box = (x0, ty - 12, x0 + w, ty + 3)
            clear = left <= box[0] and box[2] <= width - right and not any(
                box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3] for b in taken) and not any(
                (min(max(ox, box[0]), box[2]) - ox) ** 2 + (min(max(oy, box[1]), box[3]) - oy) ** 2 < orr ** 2 for ox, oy, orr in discs if (ox, oy) != (cx, cy))
            if clear:
                taken.append(box)
                texts.append('<text class="blabel" x="%.1f" y="%.1f" text-anchor="%s">%s<title>%s</title></text>' % (tx, ty, anchor, esc(short), esc(name)))
                break
    parts.extend(texts)
    parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % ((left + width - right) / 2, height - 6, esc(xlabel)))
    parts.append('<text transform="rotate(-90 14 %.1f)" x="14" y="%.1f" text-anchor="middle">%s</text>'
                 % ((top + height - bottom) / 2, (top + height - bottom) / 2, esc(ylabel)))
    parts.append("</svg><figcaption>%s</figcaption></figure>" % (esc(note) if note else "%s. Bubble area is %s; dashed lines are the median of the ads shown." % (esc(label), esc(size_words))))
    return "".join(parts)


def retention_chart(series: Sequence[Tuple[str, Sequence[float]]], steps: Sequence[str], ylabel: str, label: str,
                    width: int = 560, height: int = 300) -> str:
    """One line per ad through raw counts at each watch step; the axis is a count, never a percentage. Each line also has its own dash pattern."""
    if not series or not steps:
        return ""
    left, right, top, bottom = 64, 44, 16, 52
    plot_w, plot_h = width - left - right, height - top - bottom
    peak = max(max(values) for _, values in series) or 1.0
    step_w = plot_w / (len(steps) - 1) if len(steps) > 1 else 0

    def px(i):
        return left + i * step_w

    def py(value):
        return height - bottom - value / peak * plot_h

    parts = ['<figure class="chart wide"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, top, left, height - bottom))
    for frac in (0.0, 0.5, 1.0):
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, py(peak * frac) + 4, _axis_text(peak * frac)))
    for i, step in enumerate(steps):
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (px(i), height - bottom + 16, esc(step)))
    for n, (name, values) in enumerate(series, 1):
        path = " ".join("%s%.1f %.1f" % ("L" if i else "M", px(i), py(v)) for i, v in enumerate(values))
        parts.append('<path class="line s%d" d="%s"/>' % (n, path))
        for i, v in enumerate(values):
            parts.append('<circle class="dot ret-dot s%d" cx="%.1f" cy="%.1f" r="3.5"><title>%s at %s: %s people</title></circle>'
                         % (n, px(i), py(v), esc(name), esc(steps[i]), _axis_text(v)))
    parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">%s</text>'
                 % (top + plot_h / 2, top + plot_h / 2, esc(ylabel)))
    key = legend([("line s%d" % n, name) for n, (name, _) in enumerate(series, 1)])
    parts.append("</svg>%s<figcaption>%s</figcaption></figure>" % (key, esc(label)))
    return "".join(parts)


def heatmap(row_labels: Sequence[str], col_labels: Sequence[str], cells: Sequence[Sequence[Tuple[int, float]]],
            gaps: Dict[Tuple[int, int], int], label: str, uid: str, currency: str) -> str:
    """Rows by columns of (ad count, spend): shade follows spend, the number is the ad count, an empty cell is hatched and a
    gap cell is outlined with its number in the gap list."""
    if not row_labels or not col_labels:
        return ""
    left, head, cw, rh = 156, 46, 84, 28
    width, height = left + cw * len(col_labels) + 8, head + rh * len(row_labels) + 8
    peak = max((spend for line in cells for _, spend in line), default=0) or 1.0
    parts = ['<figure class="chart wide heat"><svg viewBox="0 0 %d %d" width="%d" role="img" aria-label="%s">' % (width, height, width, esc(label))]
    parts.append('<defs><pattern id="hatch-%s" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
                 '<line class="hatch-line" x1="0" y1="0" x2="0" y2="7"/></pattern></defs>' % esc(uid))
    for j, name in enumerate(col_labels):
        parts.append('<text class="hm-col-label" x="%d" y="%d" text-anchor="middle"><title>%s</title>%s</text>'
                     % (left + j * cw + cw / 2, head - 12, esc(name), esc(_short(name, 13))))
    for i, name in enumerate(row_labels):
        y = head + i * rh
        parts.append('<text class="hm-row-label" x="%d" y="%d" text-anchor="end"><title>%s</title>%s</text>'
                     % (left - 8, y + rh / 2 + 4, esc(name), esc(_short(name, 22))))
        for j in range(len(col_labels)):
            count, spend = cells[i][j]
            x = left + j * cw
            title = "%s in %s: %s, %s %s spend" % (name, col_labels[j], "no ad" if not count else "%d ad%s" % (count, "" if count == 1 else "s"),
                                                  _axis_text(spend), esc(currency))
            if count:
                level = 0.14 + 0.86 * (spend / peak)
                parts.append('<rect class="hm-cell" x="%d" y="%d" width="%d" height="%d" rx="5" fill-opacity="%.2f"><title>%s</title></rect>'
                             % (x + 2, y + 2, cw - 4, rh - 4, level, esc(title)))
                parts.append('<text class="hm-count %s" x="%.1f" y="%d" text-anchor="middle">%d</text>'
                             % ("t-light" if level > 0.55 else "t-ink", x + cw / 2, y + rh / 2 + 4, count))
            else:
                parts.append('<rect class="hm-cell hm-empty" x="%d" y="%d" width="%d" height="%d" rx="5" fill="url(#hatch-%s)"><title>%s</title></rect>'
                             % (x + 2, y + 2, cw - 4, rh - 4, esc(uid), esc(title)))
            if (i, j) in gaps:
                parts.append('<rect class="hm-gap" x="%d" y="%d" width="%d" height="%d" rx="6"/>' % (x + 1, y + 1, cw - 2, rh - 2))
                parts.append('<text class="hm-gap-num" x="%d" y="%d" text-anchor="end">#%d</text>' % (x + cw - 5, y + 11, gaps[(i, j)]))
    key = legend([("hm-sw", "Darker shade = more spend"), ("hm-sw hatch", "Hatched = no ad"), ("hm-sw outline", "Outlined with a number = a gap worth testing")])
    parts.append("</svg>%s<figcaption>%s. The number in a cell is how many ads sit there.</figcaption></figure>" % (key, esc(label)))
    return "".join(parts)


# ---------- shared plumbing for the format and time charts ----------

SERIES_VARS = tuple("var(--series-%d)" % n for n in range(1, 7))
OTHER_COLOUR = "var(--series-other)"
TICKS_WIDE = 8  # arbitrary default: the most x labels a time axis writes
TICKS_NARROW = 5  # arbitrary default: the most x labels under 480px, picked from the wide set so they never collide
POINT_FOCUS_MAX = 60  # arbitrary: charts with more points than this get hover tips only, not a tab stop per point
MIN_WEEK_IMPRESSIONS = 1000  # arbitrary default: a format-week with fewer impressions is left off its line, set it from your own account


def format_colours(formats: Mapping[str, float]) -> Dict[str, str]:
    """One colour per format for the whole page: formats by total spend (largest first) take series 1 to 6, the rest the muted tone."""
    ranked = sorted(formats, key=lambda name: (-(formats[name] or 0), str(name)))
    return {name: SERIES_VARS[i] if i < len(SERIES_VARS) else OTHER_COLOUR for i, name in enumerate(ranked)}


def tip(text: str) -> str:
    return ' data-tip="%s"' % esc(text)


LABEL_SLOT = 70  # arbitrary: the width in svg units one x label is given, so a narrow chart writes fewer labels


def x_ticks(count: int, plot_w: float = 10 ** 6) -> Tuple[List[int], List[int]]:
    """Indices of the x labels to write: (wide set of at most TICKS_WIDE, the narrow subset of at most TICKS_NARROW).

    A chart with a narrow plot writes fewer labels, so neighbours never touch.
    """
    if count <= 0:
        return [], []
    limit = max(2, min(TICKS_WIDE, int(plot_w // LABEL_SLOT)))
    every = max(1, -(-count // limit))
    wide = list(range(0, count, every))
    narrow = wide
    while len(narrow) > min(TICKS_NARROW, limit):
        narrow = narrow[::2]
    return wide, narrow


def nice_scale(low: float, high: float, intervals: int = 4) -> Tuple[float, float, List[float]]:
    """A domain rounded out to a step of 1, 2, 2.5 or 5 times a power of ten, with at most `intervals` steps: (low, high, ticks)."""
    if high <= low:
        high = low + 1.0
    raw = (high - low) / intervals
    exp = math.floor(math.log10(raw))
    for power in range(exp - 1, exp + 3):
        for mantissa in (1, 2, 2.5, 5):
            step = mantissa * 10.0 ** power
            lo, hi = math.floor(low / step + 1e-9) * step, math.ceil(high / step - 1e-9) * step
            count = round((hi - lo) / step)
            if count <= intervals:
                digits = max(0, 3 - math.floor(math.log10(step)))
                if hi <= lo:
                    hi, count = lo + step, 1
                return round(lo, digits), round(hi, digits), [round(lo + i * step, digits) for i in range(count + 1)]
    return low, low + 1.0, [low, low + 1.0]


def chips(names: Sequence[Tuple[str, str]]) -> str:
    """Legend chips: (series name, colour). Each is a button that toggles that series; with scripts off the row is a plain key."""
    return '<div class="legend-chips">%s</div>' % "".join(
        '<button type="button" class="legend-chip" data-series="%s" aria-pressed="true"><span class="sw" style="background:%s"></span>%s</button>'
        % (esc(name), colour, esc(name)) for name, colour in names)


def switcher(uid: str, options: Sequence[Tuple[str, str, str]], default: Optional[str] = None) -> str:
    """A metric switcher over pre-rendered views: options are (key, button text, view html). With scripts off every view shows, stacked under its heading."""
    chosen = default or options[0][0]
    bar = "".join('<button type="button" aria-pressed="%s" data-pick="%s">%s</button>' % ("true" if key == chosen else "false", esc(key), esc(text))
                  for key, text, _ in options)
    views = "".join('<div class="pick" data-view="%s"><h4 class="pick-title">%s</h4>%s</div>' % (esc(key), esc(text), html) for key, text, html in options)
    return '<div class="switch" data-switch="%s"><div class="seg" role="group" aria-label="Choose a measure">%s</div>%s</div>' % (esc(uid), bar, views)


def _figure(svg: str, caption: str, legend_html: str = "", wide: bool = True, fit: bool = False, key_html: str = "") -> str:
    """A figure around one svg; a figure with legend chips is the scope those chips toggle within. `fit` never scrolls sideways."""
    return '<figure class="chart%s%s"%s>%s%s%s<figcaption>%s</figcaption></figure>' % (
        " wide" if wide else "", " fit" if fit else "", ' data-scope="1"' if legend_html else "", legend_html, key_html, svg, caption)


def _points(values: Sequence[Optional[float]], px: Callable[[int], float], py: Callable[[float], float]) -> str:
    path, pen = [], False
    for i, value in enumerate(values):
        if value is None:
            pen = False
            continue
        path.append("%s%.1f %.1f" % ("L" if pen else "M", px(i), py(value)))
        pen = True
    return " ".join(path)


def line_chart(labels: Sequence[str], lines: Sequence[Dict[str, Any]], label: str, fmt: Callable[[float], str], unit: str,
               bars: Optional[Sequence[Optional[float]]] = None, bar_fmt: Optional[Callable[[float], str]] = None, bar_name: str = "", bar_unit: str = "",
               tip_fmt: Optional[Callable[[float], str]] = None, bar_tip_fmt: Optional[Callable[[float], str]] = None,
               x_text: Callable[[str], str] = day_label, width: int = 880, height: int = 300, legend: bool = True, caption: str = "") -> str:
    """Time lines over shared x labels, with optional faint background bars on a second (right) axis.

    Each line is {"name", "values", "colour", "kind"}; kind is "line" or "daily" (dots with tips; daily is a light tint), "avg"
    (thick, no dots) or "dashed" (an account-wide reference). A None value is a gap, never a zero. Every series sits in its own
    <g data-series>. Both axes use rounded steps (nice_scale).
    """
    count = len(labels)
    real = [v for ln in lines for v in ln["values"] if v is not None]
    if not count or not real:
        return ""
    left, right, top, bottom = 52, 52 if bars else 14, 14, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    _, high, ticks = nice_scale(0, max(real))
    slot = plot_w / count

    def px(i: int) -> float:
        return left + i * slot + slot / 2

    def py(v: float) -> float:
        return height - bottom - v / high * plot_h

    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for t in ticks:
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, py(t), width - right, py(t)))
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, py(t) + 4, esc(fmt(t))))
    if bars and any(v is not None for v in bars):
        _, bhigh, bticks = nice_scale(0, max(v for v in bars if v is not None))
        rects = []
        for i, v in enumerate(bars):
            if v is None:
                continue
            h = max(plot_h * v / bhigh, 1)
            rects.append('<rect class="bar-bg" x="%.1f" y="%.1f" width="%.1f" height="%.1f"%s/>'
                         % (left + i * slot + slot * 0.18, height - bottom - h, slot * 0.64, h, tip("%s: %s %s" % (x_text(labels[i]), (bar_tip_fmt or bar_fmt or fmt)(v), bar_name))))
        parts.append('<g data-series="%s">%s</g>' % (esc(bar_name), "".join(rects)))
        for t in bticks[1:]:
            parts.append('<text x="%d" y="%.1f">%s</text>' % (width - right + 6, height - bottom - t / bhigh * plot_h + 4, esc((bar_fmt or fmt)(t))))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    focus = count <= POINT_FOCUS_MAX
    for ln in lines:
        kind, colour = ln.get("kind", "line"), ln.get("colour", SERIES_VARS[0])
        inner = '<path class="line %s" style="stroke:%s" d="%s"/>' % (kind, colour, _points(ln["values"], px, py))
        if kind in ("line", "daily"):
            for i, v in enumerate(ln["values"]):
                if v is not None:
                    inner += ('<circle class="pt%s" style="fill:%s" cx="%.1f" cy="%.1f" r="3"%s%s/>'
                              % (" daily" if kind == "daily" else "", colour, px(i), py(v), ' tabindex="0"' if focus else "",
                                 tip("%s, %s: %s" % (ln["name"], x_text(labels[i]), (tip_fmt or fmt)(v)))))
        parts.append('<g data-series="%s">%s</g>' % (esc(ln["name"]), inner))
    wide, narrow = x_ticks(count, plot_w)
    for i in wide:
        parts.append('<text class="tk%s" x="%.1f" y="%d" text-anchor="middle">%s</text>' % ("" if i in narrow else " tk-wide", px(i), height - bottom + 16, esc(x_text(labels[i]))))
    if width >= 500:
        parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">%s</text>' % (top + plot_h / 2, top + plot_h / 2, esc(unit)))
    if bars:
        parts.append('<text transform="rotate(90 %d %.1f)" x="%d" y="%.1f" text-anchor="middle">%s</text>'
                     % (width - 8, top + plot_h / 2, width - 8, top + plot_h / 2, esc(bar_unit or bar_name)))
    names = ([(bar_name, "var(--series-neutral)")] if bars and bar_name else []) + [(ln["name"], ln.get("colour", SERIES_VARS[0])) for ln in lines]
    return _figure("".join(parts) + "</svg>", esc(caption or label), chips(names) if legend and len(names) > 1 else "")


def stacked_area(labels: Sequence[str], series: Sequence[Tuple[str, Sequence[float], str]], label: str, caption: str = "",
                 x_text: Callable[[str], str] = day_label, width: int = 880, height: int = 300) -> str:
    """Share of the whole by day: series are (name, shares in percent that sum to 100 each day, colour). Hover a day for every share."""
    count = len(labels)
    if count < 2 or len(series) < 2:
        return ""
    left, right, top, bottom = 52, 14, 14, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    step = plot_w / (count - 1)

    def px(i: int) -> float:
        return left + i * step

    def py(v: float) -> float:
        return height - bottom - v / 100.0 * plot_h

    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for frac in (0.0, 0.5, 1.0):
        y = height - bottom - frac * plot_h
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, y, width - right, y))
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%d%%</text>' % (left - 6, y + 4, round(frac * 100)))
    floor = [0.0] * count
    for name, shares, colour in series:
        ceil = [floor[i] + shares[i] for i in range(count)]
        top_edge = " ".join("%s%.1f %.1f" % ("L" if i else "M", px(i), py(ceil[i])) for i in range(count))
        back = " ".join("L%.1f %.1f" % (px(i), py(floor[i])) for i in range(count - 1, -1, -1))
        parts.append('<g data-series="%s" data-dim="1"><path class="area" style="fill:%s" d="%s %s Z"/></g>' % (esc(name), colour, top_edge, back))
        floor = ceil
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    for i in range(count):
        text = "%s: %s" % (x_text(labels[i]), ", ".join("%s %.0f%%" % (n, sh[i]) for n, sh, _ in series if sh[i] >= 0.5))
        parts.append('<rect class="hit" x="%.1f" y="%d" width="%.1f" height="%.1f"%s/>' % (px(i) - step / 2, top, max(step, 1), plot_h, tip(text)))
    wide, narrow = x_ticks(count, plot_w)
    for i in wide:
        parts.append('<text class="tk%s" x="%.1f" y="%d" text-anchor="middle">%s</text>' % ("" if i in narrow else " tk-wide", px(i), height - bottom + 16, esc(x_text(labels[i]))))
    parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">Share of spend (%%)</text>' % (top + plot_h / 2, top + plot_h / 2))
    return _figure("".join(parts) + "</svg>", esc(caption or label), chips([(n, c) for n, _, c in series]))


def stacked_bars(labels: Sequence[str], series: Sequence[Tuple[str, Sequence[float], str]], label: str, unit: str, caption: str = "",
                 width: int = 880, height: int = 300) -> str:
    """Counts per x slot stacked by series: series are (name, counts, colour)."""
    count = len(labels)
    totals = [sum(sh[i] for _, sh, _ in series) for i in range(count)]
    if not count or not any(totals):
        return ""
    left, right, top, bottom = 52, 14, 14, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / count
    _, peak, ticks = nice_scale(0, max(totals))
    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for t in ticks:
        y = height - bottom - t / peak * plot_h
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, y, width - right, y))
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, y + 4, "{:,.0f}".format(t)))
    bases = [0.0] * count
    for name, counts, colour in series:
        rects = []
        for i, v in enumerate(counts):
            if not v:
                continue
            h = plot_h * v / peak
            rects.append('<rect class="seg-bar" style="fill:%s" x="%.1f" y="%.1f" width="%.1f" height="%.1f"%s%s/>'
                         % (colour, left + i * slot + slot * 0.18, height - bottom - (bases[i] + v) / peak * plot_h, slot * 0.64, h,
                            ' tabindex="0"' if count <= POINT_FOCUS_MAX else "", tip("%s, %s: %d new %s" % (labels[i], name, v, "ad" if v == 1 else "ads"))))
            bases[i] += v
        parts.append('<g data-series="%s" data-dim="1">%s</g>' % (esc(name), "".join(rects)))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    wide, narrow = x_ticks(count, plot_w)
    for i in wide:
        parts.append('<text class="tk%s" x="%.1f" y="%d" text-anchor="middle">%s</text>' % ("" if i in narrow else " tk-wide", left + i * slot + slot / 2, height - bottom + 16, esc(labels[i])))
    parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">%s</text>' % (top + plot_h / 2, top + plot_h / 2, esc(unit)))
    return _figure("".join(parts) + "</svg>", esc(caption or label), chips([(n, c) for n, _, c in series]))


def benchmark_rows(rows: Sequence[Dict[str, Any]], median: Optional[float], fmt: Callable[[float], str], label: str, unit: str,
                   width: int = 440, tip_fmt: Optional[Callable[[float], str]] = None) -> str:
    """One row per format: a dot for the account's value, a shaded band or tick for a cited public figure, a line for the account median.

    rows are {"name", "value" (None = no value), "colour", "band" (benchmarks.lookup result or None)}. The chart is narrow enough
    to fit a phone without scrolling; its scale covers every value and band, rounded out (nice_scale).
    """
    shown = list(rows)
    say = tip_fmt or fmt
    if not any(r["value"] is not None for r in shown):
        return ""
    left, right, top, row = 112, 56, 24, 44
    height = top + row * len(shown) + 40
    plot_w = width - left - right
    nums = [r["value"] for r in shown if r["value"] is not None] + [b for r in shown if r.get("band") for b in (r["band"]["low"], r["band"]["high"])]
    nums += [median] if median is not None else []
    _, high, ticks = nice_scale(0, max(nums))

    def px(v: float) -> float:
        return left + v / high * plot_w

    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for t in ticks:
        parts.append('<line class="grid" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (px(t), top, px(t), height - 38))
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (px(t), height - 24, esc(fmt(t))))
    if median is not None:
        parts.append('<line class="guide" x1="%.1f" y1="%d" x2="%.1f" y2="%d"%s/>' % (px(median), top, px(median), height - 38, tip("Median across your formats: %s" % say(median))))
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">Your median %s</text>' % (min(max(px(median), left + 50), width - 60), height - 6, esc(say(median))))
    names: List[str] = []
    for i, r in enumerate(shown):
        y = top + i * row + row / 2 + 6
        names.append('<text class="lbl" x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 10, y + 4, esc(_short(r["name"], 14))))
        inner = ""
        band = r.get("band")
        if band:
            lo, hi = px(band["low"]), px(band["high"])
            words = "Industry figure (%s %s, %s): %s%s" % (band["source"].split(",")[0], band["year"], band["sample"], say(band["value"]),
                                                          "" if band["low"] == band["high"] else " (range %s to %s)" % (say(band["low"]), say(band["high"])))
            if hi - lo >= 3:
                inner += '<rect class="band" x="%.1f" y="%.1f" width="%.1f" height="16" rx="4"%s/>' % (lo, y - 8, hi - lo, tip(words))
            inner += '<line class="band-tick" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f"%s/>' % (px(band["value"]), y - 11, px(band["value"]), y + 11, tip(words))
            inner += '<text class="ind" x="%.1f" y="%.1f" text-anchor="middle">industry %s</text>' % (min(max(px(band["value"]), left + 30), width - 36), y - 15, esc(say(band["value"])))
        if r["value"] is None:
            inner += '<text x="%d" y="%.1f">n/a</text>' % (left + 8, y + 4)
        else:
            inner += ('<circle class="pt" style="fill:%s" cx="%.1f" cy="%.1f" r="6" tabindex="0"%s/><text x="%.1f" y="%.1f">%s</text>'
                      % (r["colour"], px(r["value"]), y, tip("%s: %s" % (r["name"], say(r["value"]))), min(px(r["value"]) + 11, width - right + 4), y + 4, esc(say(r["value"]))))
        parts.append('<g data-series="%s">%s</g>' % (esc(r["name"]), inner))
    parts.append('<g class="axis-labels">%s</g>' % "".join(names))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, top, left, height - 38))
    key = '<p class="chart-key">Dot = your value &middot; bar or band = industry figure &middot; dashed line = your median</p>'
    return _figure("".join(parts) + "</svg>", esc(label), chips([(r["name"], r["colour"]) for r in shown]), fit=True, key_html=key)


MIN_BUCKET_ADS = 3  # arbitrary default: a bucket with fewer ads than this is dimmed and marked too few to read


def bars_with_dots(labels: Sequence[str], shares: Sequence[Optional[float]], counts: Sequence[int], dots: Sequence[Optional[float]],
                   dot_fmt: Callable[[float], str], dot_name: str, label: str, caption: str = "", width: int = 880, height: int = 300,
                   dot_tip_fmt: Optional[Callable[[float], str]] = None) -> str:
    """Bars of spend share per bucket with a dot per bucket on a second, right-hand axis, its value written above it.

    The ad count is written above each bar; a bucket with fewer than MIN_BUCKET_ADS ads is dimmed and says it has too few to read.
    Axis labels and counts sit outside the series groups, so switching a series off never hides them.
    """
    count = len(labels)
    if not count or not any(v for v in shares):
        return ""
    say = dot_tip_fmt or dot_fmt
    left, right, top, bottom = 52, 56, 26, 40
    plot_w, plot_h = width - left - right, height - top - bottom
    slot = plot_w / count
    _, phigh, pticks = nice_scale(0, max(v for v in shares if v is not None))
    real = [d for d in dots if d is not None]
    _, dhigh, dticks = nice_scale(0, max(real) if real else 1.0)
    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    for t in pticks:
        parts.append('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, height - bottom - t / phigh * plot_h, width - right, height - bottom - t / phigh * plot_h))
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%s%%</text>' % (left - 6, height - bottom - t / phigh * plot_h + 4, _trim(t)))
    for t in dticks:
        parts.append('<text x="%d" y="%.1f">%s</text>' % (width - right + 6, height - bottom - t / dhigh * plot_h + 4, esc(dot_fmt(t))))
    bar_group, dot_group, outside = [], [], []
    for i in range(count):
        cx = left + i * slot + slot / 2
        thin = 0 < counts[i] < MIN_BUCKET_ADS
        top_y = height - bottom - (max(plot_h * shares[i] / phigh, 1) if shares[i] else 0)
        if shares[i]:
            bar = '<rect class="bar-bg solid" x="%.1f" y="%.1f" width="%.1f" height="%.1f"%s/>' % (
                cx - slot * 0.3, top_y, slot * 0.6, height - bottom - top_y, tip("%s: %.1f%% of spend, %d ads" % (labels[i], shares[i], counts[i])))
            bar_group.append('<g class="thin">%s</g>' % bar if thin else bar)
        words = "%d ad%s" % (counts[i], "" if counts[i] == 1 else "s") + (": too few to read" if thin else "")
        outside.append('<text class="count" x="%.1f" y="%.1f" text-anchor="middle">%s</text>' % (cx, top_y - 5, words))
        outside.append('<text class="tk" x="%.1f" y="%d" text-anchor="middle">%s</text>' % (cx, height - bottom + 16, esc(labels[i])))
        if dots[i] is not None:
            cy = height - bottom - dots[i] / dhigh * plot_h
            mark = ('<circle class="pt" style="fill:var(--series-2)" cx="%.1f" cy="%.1f" r="6" tabindex="0"%s/><text class="dot-label" x="%.1f" y="%.1f" text-anchor="middle">%s</text>'
                    % (cx, cy, tip("%s, %s: %s" % (labels[i], dot_name, say(dots[i]))), cx, cy - 10, esc(say(dots[i]))))
            dot_group.append('<g class="thin">%s</g>' % mark if thin else mark)
    parts.append('<g data-series="Spend share">%s</g><g data-series="%s">%s</g><g class="axis-labels">%s</g>' % ("".join(bar_group), esc(dot_name), "".join(dot_group), "".join(outside)))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">Share of spend (%%)</text>' % (top + plot_h / 2, top + plot_h / 2))
    parts.append('<text transform="rotate(90 %d %.1f)" x="%d" y="%.1f" text-anchor="middle">%s</text>' % (width - 8, top + plot_h / 2, width - 8, top + plot_h / 2, esc(dot_name)))
    return _figure("".join(parts) + "</svg>", esc(caption or label), chips([("Spend share", "var(--series-neutral)"), (dot_name, "var(--series-2)")]))
