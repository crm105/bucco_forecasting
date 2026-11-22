"""Inline SVG charts. Colours come from CSS variables defined by the page, so they follow
light and dark mode. Each function returns an SVG string."""

from __future__ import annotations

from html import escape

import pandas as pd

from bucco.models.base import GAMES, PIRATES_TEAM_ID


def _scale(lo: float, hi: float, a: float, b: float):
    span = (hi - lo) or 1
    return lambda v: a + (v - lo) / span * (b - a)


def range_chart(teams: pd.DataFrame) -> str:
    """One row per team: a dot for expected wins, a bar for the 80% range."""
    width, left, right, row, top = 720, 54, 54, 22, 26
    height = top + row * len(teams) + 24
    lo = float((teams["low"].min() // 5) * 5)
    hi = float(-(-teams["high"].max() // 5) * 5)
    x = _scale(lo, hi, left, width - right)
    parts = [(f'<svg viewBox="0 0 {width} {height}" role="img" class="chart" '
             f'aria-label="Forecast wins and 80% range for each team">')]
    for tick in range(int(lo), int(hi) + 1, 10):
        parts.append(f'<line class="grid" x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="{top - 6}" '
                     f'y2="{height - 22}"/><text class="axis" x="{x(tick):.1f}" y="{height - 6}" '
                     f'text-anchor="middle">{tick}</text>')
    parts.append(f'<line class="ref" x1="{x(GAMES / 2):.1f}" x2="{x(GAMES / 2):.1f}" '
                 f'y1="{top - 6}" y2="{height - 22}"/><text class="axis" x="{x(GAMES / 2):.1f}" '
                 f'y="{top - 10}" text-anchor="middle">81</text>')
    for i, t in enumerate(teams.itertuples()):
        y = top + i * row + row / 2
        mine = t.team_id == PIRATES_TEAM_ID
        cls = "pit" if mine else "other"
        if mine:
            parts.append(f'<rect class="rowhl" x="0" y="{y - row / 2:.1f}" width="{width}" '
                         f'height="{row}"/>')
        parts.append(
            f'<text class="label {cls}" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">'
            f'{escape(t.team_abbr)}</text>'
            f'<line class="bar {cls}" x1="{x(t.low):.1f}" x2="{x(t.high):.1f}" y1="{y:.1f}" '
            f'y2="{y:.1f}"/><circle class="dot {cls}" cx="{x(t.wins):.1f}" cy="{y:.1f}" r="4.5"/>'
            f'<text class="val {cls}" x="{width - right + 8}" y="{y + 4:.1f}">{t.wins:.0f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def timeline_chart(timeline: pd.DataFrame, opening_day: str | None) -> str:
    """Pirates expected wins by as-of date, with the 80% range as a band."""
    width, height, left, right, top, bottom = 720, 220, 44, 24, 16, 36
    days = pd.to_datetime(timeline["as_of_date"])
    t0, t1 = days.min().value, days.max().value
    x = _scale(t0, t1, left, width - right)
    lo = float((timeline["low"].min() // 5) * 5)
    hi = float(-(-timeline["high"].max() // 5) * 5)
    y = _scale(hi, lo, top, height - bottom)  # higher wins sit higher on the page
    xs = [x(d.value) for d in days]
    band_up = [f"{px:.1f},{y(v):.1f}" for px, v in zip(xs, timeline["high"])]
    band_dn = [f"{px:.1f},{y(v):.1f}" for px, v in zip(xs[::-1], timeline["low"][::-1])]
    line = [f"{px:.1f},{y(v):.1f}" for px, v in zip(xs, timeline["wins"])]
    parts = [(f'<svg viewBox="0 0 {width} {height}" role="img" class="chart" '
             f'aria-label="Pirates forecast wins by as-of date">')]
    for tick in range(int(lo), int(hi) + 1, 5):
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{y(tick):.1f}" '
                     f'y2="{y(tick):.1f}"/><text class="axis" x="{left - 8}" y="{y(tick) + 4:.1f}" '
                     f'text-anchor="end">{tick}</text>')
    parts.append(f'<polygon class="band" points="{" ".join(band_up + band_dn)}"/>'
                 f'<polyline class="trend" points="{" ".join(line)}"/>')
    for px, (_, r) in zip(xs, timeline.iterrows()):
        parts.append(f'<circle class="dot pit" cx="{px:.1f}" cy="{y(r.wins):.1f}" r="4.5"/>'
                     f'<text class="axis" x="{px:.1f}" y="{height - 14}" text-anchor="middle">'
                     f'{escape(r.as_of_date[5:])}</text>')
    if opening_day and t0 <= pd.Timestamp(opening_day).value <= t1:
        ox = x(pd.Timestamp(opening_day).value)
        parts.append(f'<line class="ref" x1="{ox:.1f}" x2="{ox:.1f}" y1="{top}" '
                     f'y2="{height - bottom}"/><text class="axis" x="{ox:.1f}" y="{top + 10}" '
                     f'text-anchor="middle">Opening Day</text>')
    parts.append("</svg>")
    return "".join(parts)


def error_chart(past: pd.DataFrame) -> str:
    """Pirates prediction error by season: bars up mean the model was too high."""
    width, height, left, right, top, bottom = 720, 220, 44, 12, 14, 30
    limit = max(10.0, float(-(-past["error"].abs().max() // 5) * 5))
    y = _scale(limit, -limit, top, height - bottom)
    step = (width - left - right) / len(past)
    parts = [(f'<svg viewBox="0 0 {width} {height}" role="img" class="chart" '
             f'aria-label="Pirates forecast error by season">')]
    for tick in (-limit, -limit / 2, 0, limit / 2, limit):
        parts.append(f'<line class="{"ref" if tick == 0 else "grid"}" x1="{left}" '
                     f'x2="{width - right}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>'
                     f'<text class="axis" x="{left - 8}" y="{y(tick) + 4:.1f}" '
                     f'text-anchor="end">{tick:+.0f}</text>')
    for i, r in enumerate(past.itertuples()):
        bx = left + i * step + step * 0.15
        y0, y1 = sorted((y(0), y(r.error)))
        parts.append(f'<rect class="errbar {"over" if r.error > 0 else "under"}" x="{bx:.1f}" '
                     f'y="{y0:.1f}" width="{step * 0.7:.1f}" height="{max(y1 - y0, 0.5):.1f}"/>')
        if i % 3 == 0 or i == len(past) - 1:
            parts.append(f'<text class="axis" x="{bx + step * 0.35:.1f}" y="{height - 10}" '
                         f'text-anchor="middle">{r.season}</text>')
    parts.append("</svg>")
    return "".join(parts)
