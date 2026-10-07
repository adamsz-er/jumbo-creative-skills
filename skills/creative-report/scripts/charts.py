"""Inline-SVG charts for the dashboard. Standard library only.

Every chart carries its labels, units and a <title> on each mark, uses the
template's CSS classes for colour (so light, dark and print all work) and is
safe to embed: every string that came from data is escaped.
"""
from __future__ import annotations

import html
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


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


def sparkline(values: Sequence[Optional[float]], label: str, width: int = 120, height: int = 32) -> str:
    """A tiny line with no axes; "" with fewer than two real points. A gap (None) breaks the line."""
    real = [v for v in values if v is not None]
    if len(real) < 2:
        return ""
    low, high = min(real), max(real)
    span = (high - low) or 1.0
    step = (width - 4) / (len(values) - 1)
    path, pen = [], False
    for i, value in enumerate(values):
        if value is None:
            pen = False
            continue
        path.append("%s%.1f %.1f" % ("L" if pen else "M", 2 + i * step, height - 3 - (value - low) / span * (height - 6)))
        pen = True
    return ('<svg class="spark" viewBox="0 0 %d %d" role="img" aria-label="%s"><path d="%s"/></svg>'
            % (width, height, esc(label), " ".join(path)))


def _axis_text(value: float) -> str:
    return "{:,.0f}".format(value) if abs(value) >= 100 else "{:,.2f}".format(value)


def combo_chart(labels: Sequence[str], bars: Optional[Sequence[Optional[float]]], line: Optional[Sequence[Optional[float]]],
                bar_unit: str, line_unit: str, label: str, width: int = 560, height: int = 280) -> str:
    """Bars on the left axis and a line on the right axis over the same x labels; either may be absent.

    A None value is a gap: no bar is drawn and the line breaks, so a missing day never reads as 0.
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
            parts.append('<text x="%d" y="%.1f" text-anchor="end">%s</text>' % (left - 6, y + 4, _axis_text(peak * frac)))
        for i, value in enumerate(bars):
            if value is None:
                continue
            h = max(plot_h * value / peak, 1)
            parts.append('<rect class="bar" x="%.1f" y="%.1f" width="%.1f" height="%.1f"><title>%s: %s %s</title></rect>'
                         % (left + i * slot + slot * 0.15, height - bottom - h, slot * 0.7, h, esc(labels[i]), _axis_text(value), esc(bar_unit)))
        parts.append('<text transform="rotate(-90 12 %.1f)" x="12" y="%.1f" text-anchor="middle">%s</text>'
                     % (top + plot_h / 2, top + plot_h / 2, esc(bar_unit)))
    if line:
        real = [v for v in line if v is not None]
        if real:
            low, high = min(real + [0.0]), max(real)
            span = (high - low) or 1.0
            for frac in (0.0, 0.5, 1.0):
                y = height - bottom - frac * plot_h
                parts.append('<text x="%d" y="%.1f">%s</text>' % (width - right + 6, y + 4, _axis_text(low + span * frac)))
            path, pen, dots = [], False, []
            for i, value in enumerate(line):
                if value is None:
                    pen = False
                    continue
                x, y = left + i * slot + slot / 2, height - bottom - (value - low) / span * plot_h
                path.append("%s%.1f %.1f" % ("L" if pen else "M", x, y))
                pen = True
                dots.append('<circle class="dot line-dot" cx="%.1f" cy="%.1f" r="3"><title>%s: %s %s</title></circle>'
                            % (x, y, esc(labels[i]), _axis_text(value), esc(line_unit)))
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
                 cut: Optional[int], label: str, currency: str, width: int = 600, height: int = 300) -> str:
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
                 x_median: float, y_median: float, quadrants: Sequence[str], width: int = 560, height: int = 380) -> str:
    """Bubbles at (x, y) with area following size, dashed lines at the two medians and the four quadrants named in words.

    points are (x, y, size, name, show_label); quadrants run top-left, top-right, bottom-left, bottom-right.
    """
    if not points:
        return ""
    left, right, top, bottom, rmax = 54, 16, 16, 46, 18.0
    xs = [p[0] for p in points] + [x_median]
    ys = [p[1] for p in points] + [y_median]

    def span(values):
        low, high = min(values), max(values)
        pad = (high - low) * 0.12 or 1.0
        return low - pad, high + pad

    (x0, x1), (y0, y1) = span(xs), span(ys)
    biggest = max(p[2] for p in points) or 1.0

    def px(x):
        return left + (x - x0) / (x1 - x0) * (width - left - right)

    def py(y):
        return height - bottom - (y - y0) / (y1 - y0) * (height - bottom - top)

    parts = ['<figure class="chart wide"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, height - bottom, width - right, height - bottom))
    parts.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d"/>' % (left, top, left, height - bottom))
    for value in _ticks(x0, x1):
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%.1f</text>' % (px(value), height - bottom + 16, value))
    for value in _ticks(y0, y1):
        parts.append('<text x="%d" y="%.1f" text-anchor="end">%.1f</text>' % (left - 8, py(value) + 4, value))
    parts.append('<line class="guide" x1="%.1f" y1="%d" x2="%.1f" y2="%d"/>' % (px(x_median), top, px(x_median), height - bottom))
    parts.append('<line class="guide" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/>' % (left, py(y_median), width - right, py(y_median)))
    corners = ((left + 6, top + 14, "start"), (width - right - 6, top + 14, "end"),
               (left + 6, height - bottom - 8, "start"), (width - right - 6, height - bottom - 8, "end"))
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
        parts.append('<circle class="bub" cx="%.1f" cy="%.1f" r="%.2f"><title>%s: %s %.2f, %s %.2f, spend %s</title></circle>'
                     % (cx, cy, r, esc(name), esc(xlabel), x, esc(ylabel), y, _axis_text(size)))
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
    parts.append("</svg><figcaption>%s. Bubble area is spend; dashed lines are the median of the ads shown.</figcaption></figure>" % esc(label))
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
    parts = ['<figure class="chart wide heat"><svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, esc(label))]
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
