"""Turn the outlook dictionary (outlook_data.py) into one self-contained HTML page.

Wording lives in config/outlook_text.yml; this module fills it in and draws the charts as inline
SVG (colours from the page's CSS variables, so they follow light and dark mode).
"""

from __future__ import annotations

import math
import re
from html import escape
from pathlib import Path
from string import Formatter

import yaml

from bucco.config import REPO_ROOT, REPORTS_DIR
from bucco.report.outlook_data import STRONG_RANK, WEAK_RANK, ordinal
from bucco.report.render import CSS as BASE_CSS

TEXT_PATH = REPO_ROOT / "config" / "outlook_text.yml"

# Placeholders each entry may use. An entry missing here may not use any.
ALLOWED: dict[str, set[str]] = {
    "title": {"team_name", "season"},
    "date_line": {"as_of", "source_label"},
    "intro": {"team_short", "pitching_rank", "batting_rank", "wins", "win_rank"},
    "hero_range": {"low", "high"},
    "hero_avg": {"avg"},
    "strength_item": {"spot", "rank", "war", "avg", "who"},
    "weakness_item": {"spot", "rank", "war", "avg", "who"},
    "run_scoring_item": {"rank", "runs", "wins"},
    "defense_item": {"rank"},
    "scatter_intro": {"team"},
    "division_heading": {"division"},
    "division_behind": {"team_short", "place", "leader", "gap"},
    "division_ahead": {"team_short", "gap"},
    "move_lineup_below": {"gap", "gaps"},
    "move_lineup_above": {"gap"},
    "move_rotation": {"names", "share", "total"},
    "fa_off_position": {"names"},
    "fa_pair": {"first", "second", "gain", "separate"},
    "fa_pitching_intro": {"weakest", "war", "ip"},
    "footer": {"model", "rmse", "first", "last", "rmse_recent", "recent_first", "today"},
}
REQUIRED = [
    "kicker", "title", "date_line", "intro", "hero_wins", "hero_range", "hero_team_war",
    "hero_pitching", "hero_batting", "hero_avg", "strengths_heading", "weaknesses_heading",
    "strength_item", "weakness_item", "no_strengths", "no_weaknesses", "run_scoring_item",
    "defense_item", "positions_heading", "positions_intro", "positions_chart_note",
    "positions_caption", "scatter_heading", "scatter_intro", "runs_heading", "runs_intro",
    "leaders_heading", "leaders_note", "division_heading", "division_note", "division_behind",
    "division_ahead", "move_heading", "move_lineup_below", "move_lineup_above", "move_rotation",
    "fa_heading", "fa_intro", "fa_off_position", "fa_pair", "fa_pitching_intro", "fa_caveat",
    "footer",
]
HEADLINES = ["pitching_led", "batting_led", "both_strong", "both_weak", "balanced"]

EXTRA_CSS = """
main{max-width:800px}
.hero{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px}
.hero>div{min-width:0}.eyebrow{font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted)}.big{font-size:2.2rem}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}
.cols>div{min-width:0}.cols h3{margin:0 0 6px;font-size:1rem}.cols li{margin:0 0 6px}
.scroll{overflow-x:auto}td,th{white-space:nowrap}td.wrap{white-space:normal}
tr.mine td{background:var(--hl);font-weight:600}figcaption{font-size:.85rem;color:var(--muted)}
.above{fill:var(--under)}.below{fill:var(--over)}.zero{stroke:var(--muted)}
.dot.other{fill:var(--other);opacity:.6}.dot.mine{fill:var(--accent)}
.lbl{font-size:12px;fill:var(--fg)}.lbl.mine{font-weight:700}
"""


class OutlookTextError(ValueError):
    """The outlook text file is missing an entry or uses a placeholder it should not."""


def _check(key: str, template: object) -> None:
    if not isinstance(template, str) or not template.strip():
        raise OutlookTextError(f"{key}: must be non-empty text")
    used = {name for _, name, _, _ in Formatter().parse(template) if name}
    unknown = used - ALLOWED.get(key, set())
    if unknown:
        allowed = sorted(ALLOWED.get(key, set())) or "none"
        raise OutlookTextError(f"{key}: unknown placeholder(s) {sorted(unknown)}; "
                               f"allowed: {allowed}")


def load_text(path=TEXT_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        text = yaml.safe_load(f) or {}
    for key in REQUIRED:
        if key not in text:
            raise OutlookTextError(f"{key}: missing from {Path(path).name}")
        _check(key, text[key])
    for key in HEADLINES:
        _check(f"headlines.{key}", (text.get("headlines") or {}).get(key))
    for group in ("spot_labels", "source_labels"):
        if not isinstance(text.get(group), dict):
            raise OutlookTextError(f"{group}: must be a mapping")
    return text


def fill(template: str, **values) -> str:
    filled = template.format(**{k: str(v) for k, v in values.items()})
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(filled))


def short_name(team_name: str) -> str:
    """'Pittsburgh Pirates' -> 'Pirates', 'Boston Red Sox' -> 'Red Sox'."""
    words = team_name.split()
    return " ".join(words[-2:]) if words[-1] in {"Sox", "Jays"} else words[-1]


def headline_key(pitching_rank: int, batting_rank: int) -> str:
    pit_strong, pit_weak = pitching_rank <= STRONG_RANK, pitching_rank >= WEAK_RANK
    bat_strong, bat_weak = batting_rank <= STRONG_RANK, batting_rank >= WEAK_RANK
    if pit_strong and bat_strong:
        return "both_strong"
    if pit_weak and bat_weak:
        return "both_weak"
    if pit_strong and not bat_strong:
        return "pitching_led" if bat_weak or batting_rank > pitching_rank + 10 else "balanced"
    if bat_strong and not pit_strong:
        return "batting_led" if pit_weak or pitching_rank > batting_rank + 10 else "balanced"
    return "balanced"


def _who(spot: dict) -> str:
    parts = []
    for w in spot["who"]:
        if "pa" in w:
            name = "replacement level" if w["replacement"] else w["name"]
            parts.append(f"{name} {w['pa']:.0f}")
        else:
            parts.append(f"{w['name']} {w['war']:.1f}")
    return ", ".join(parts)


def _signed(v: float, digits: int = 1) -> str:
    return f"{v:+.{digits}f}".replace("-", "−")


SUFFIXES = {"jr.", "jr", "sr.", "sr", "ii", "iii", "iv"}


def surname(name: str) -> str:
    """Last name, keeping a suffix with it ("Rafael Flores Jr." -> "Flores Jr.")."""
    parts = name.split()
    if len(parts) > 2 and parts[-1].lower() in SUFFIXES:
        return " ".join(parts[-2:])
    return parts[-1] if parts else name


def losers_text(losers: list) -> str:
    """("Jake Mangum", 135.0), ... -> "Mangum 135, Simon 125"; replacement level by name."""
    return ", ".join(f"{'replacement' if n == 'replacement level' else surname(n)} {pa:.0f}"
                     for n, pa in losers) or "—"


def and_join(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def wins_text(gap: float) -> str:
    n = round(gap)
    return f"{n} win" if n == 1 else f"{n} wins"


def _num(v, fmt: str = ".0f") -> str:
    """A number, or blank when it is missing (None or NaN)."""
    return "" if v is None or math.isnan(v) else format(v, fmt)


# ---- charts ------------------------------------------------------------------------------
def spot_chart(spots: list[dict], labels: dict) -> str:
    """Diverging bars: the team's WAR at each spot minus the league average."""
    width, left, right, row, top = 720, 150, 60, 30, 8
    height = top + row * len(spots) + 28
    diffs = [s["war"] - s["avg"] for s in spots]
    lo = min(-1.0, float(int(min(diffs)) - 1))
    hi = max(1.0, float(int(max(diffs)) + 1))

    def x(v):
        return left + (v - lo) / (hi - lo) * (width - left - right)

    parts = [(f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
              f'aria-label="WAR minus league average by position">')]
    for t in range(int(lo), int(hi) + 1):
        parts.append(f'<line class="{"zero" if t == 0 else "grid"}" x1="{x(t):.1f}" '
                     f'x2="{x(t):.1f}" y1="{top}" y2="{height - 22}"/>'
                     f'<text class="axis" x="{x(t):.1f}" y="{height - 6}" text-anchor="middle">'
                     f'{"+" if t > 0 else ""}{t}</text>')
    for i, (s, d) in enumerate(zip(spots, diffs, strict=True)):
        y = top + i * row
        x0, x1 = x(0), x(d)
        label = escape(labels.get(s["spot"], s["spot"]))
        tip = escape(f"{labels.get(s['spot'], s['spot'])}: {s['war']:.1f} WAR, league average "
                     f"{s['avg']:.1f}, {ordinal(s['rank'])} of 30")
        parts.append(
            f'<g><title>{tip}</title>'
            f'<text class="lbl" x="0" y="{y + row / 2 + 4:.1f}">{label}</text>'
            f'<rect class="{"above" if d >= 0 else "below"}" x="{min(x0, x1):.1f}" '
            f'y="{y + 7:.1f}" width="{max(abs(x1 - x0), 2):.1f}" height="{row - 14}" rx="3"/>'
            f'<text class="lbl" x="{(x1 + 6) if d >= 0 else (x1 - 6):.1f}" y="{y + row / 2 + 4:.1f}" '
            f'text-anchor="{"start" if d >= 0 else "end"}">{escape(_signed(d))}</text>'
            f'<text class="axis" x="{width - 2}" y="{y + row / 2 + 4:.1f}" text-anchor="end">'
            f'{ordinal(s["rank"])}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def scatter_chart(points: list[dict], team: str, label_teams: set[str]) -> str:
    width, height = 720, 440
    m = {"l": 48, "r": 16, "t": 14, "b": 42}
    xs = [p["batting"] for p in points]
    ys = [p["pitching"] for p in points]
    xlo, xhi = 2 * int(min(xs) / 2) - 2, 2 * int(max(xs) / 2) + 2
    ylo, yhi = 2 * int(min(ys) / 2) - 2, 2 * int(max(ys) / 2) + 2

    def x(v):
        return m["l"] + (v - xlo) / (xhi - xlo) * (width - m["l"] - m["r"])

    def y(v):
        return height - m["b"] - (v - ylo) / (yhi - ylo) * (height - m["t"] - m["b"])

    parts = [(f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
              f'aria-label="Batting WAR against pitching WAR for all teams">')]
    for t in range(xlo, xhi + 1, 4):
        parts.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{m["t"]}" '
                     f'y2="{height - m["b"]}"/><text class="axis" x="{x(t):.1f}" '
                     f'y="{height - m["b"] + 16}" text-anchor="middle">{t}</text>')
    for t in range(ylo, yhi + 1, 4):
        parts.append(f'<line class="grid" x1="{m["l"]}" x2="{width - m["r"]}" y1="{y(t):.1f}" '
                     f'y2="{y(t):.1f}"/><text class="axis" x="{m["l"] - 6}" y="{y(t) + 4:.1f}" '
                     f'text-anchor="end">{t}</text>')
    ax, ay = sum(xs) / len(xs), sum(ys) / len(ys)
    parts.append(f'<line class="ref" x1="{x(ax):.1f}" x2="{x(ax):.1f}" y1="{m["t"]}" '
                 f'y2="{height - m["b"]}"/><line class="ref" x1="{m["l"]}" x2="{width - m["r"]}" '
                 f'y1="{y(ay):.1f}" y2="{y(ay):.1f}"/>')
    parts.append(f'<text class="axis" x="{(m["l"] + width - m["r"]) / 2:.0f}" y="{height - 6}" '
                 f'text-anchor="middle">Batting WAR</text><text class="axis" x="12" '
                 f'y="{(m["t"] + height - m["b"]) / 2:.0f}" text-anchor="middle" '
                 f'transform="rotate(-90 12 {(m["t"] + height - m["b"]) / 2:.0f})">'
                 f'Pitching WAR</text>')
    for p in sorted(points, key=lambda p: p["team"] == team):
        mine = p["team"] == team
        cls = "mine" if mine else "other"
        parts.append(f'<g><title>{escape(p["team"])}: batting {p["batting"]:.1f}, pitching '
                     f'{p["pitching"]:.1f}</title><circle class="dot {cls}" cx="{x(p["batting"]):.1f}" '
                     f'cy="{y(p["pitching"]):.1f}" r="{8 if mine else 5}"/>')
        if mine or p["team"] in label_teams:
            parts.append(f'<text class="lbl {cls}" x="{x(p["batting"]) + (11 if mine else 8):.1f}" '
                         f'y="{y(p["pitching"]) + 4:.1f}">{escape(p["team"])}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


# ---- page --------------------------------------------------------------------------------
def _list_items(spots, text, labels, kind):
    rows = []
    for s in spots:
        rank = s["rank"]
        if (kind == "strength" and rank <= STRONG_RANK) or (kind == "weakness" and rank >= WEAK_RANK):
            rows.append(fill(text[f"{kind}_item"], spot=labels.get(s["spot"], s["spot"]),
                             rank=ordinal(rank), war=f"{s['war']:.1f}", avg=f"{s['avg']:.1f}",
                             who=_who(s) + "."))
    return rows


def render_outlook(data: dict, text: dict | None = None) -> str:
    text = text or load_text()
    labels = text["spot_labels"]
    mine_row = ' class="mine"'

    team, short = data["team"], short_name(data["team_name"])
    f, bat, pit, tot = data["forecast"], data["batting"], data["pitching"], data["total"]
    head = text["headlines"][headline_key(pit["rank"], bat["rank"])]
    source_label = text["source_labels"].get(data["source"], data["source"])

    strengths = _list_items(data["spots"], text, labels, "strength") or [fill(text["no_strengths"])]
    weaknesses = _list_items(data["spots"], text, labels, "weakness") or [fill(text["no_weaknesses"])]
    runs = data["runs"]
    run_gap = runs["batting"]["avg"] - runs["batting"]["value"]
    if run_gap > 0:
        weaknesses.append(fill(text["run_scoring_item"], rank=ordinal(runs["batting"]["rank"]),
                               runs=f"{run_gap:.0f}", wins=f"{run_gap / data['runs_per_win']:.0f}"))
    if runs["defense"]["rank"] >= WEAK_RANK:
        weaknesses.append(fill(text["defense_item"], rank=ordinal(runs["defense"]["rank"])))

    fields = [s for s in data["spots"] if s["spot"] not in ("Rotation", "Bullpen")]
    gaps = sorted(fields, key=lambda s: s["war"] - s["avg"])
    lineup_gap = bat["value"] - bat["avg"]
    if lineup_gap < 0:
        worst = [s for s in gaps if s["war"] - s["avg"] <= -0.3][:5] or gaps[:2]
        gap_text = and_join([f"{labels.get(s['spot'], s['spot']).lower()} "
                             f"({_signed(s['war'] - s['avg'])})" for s in worst])
        move = fill(text["move_lineup_below"], gap=f"{-lineup_gap:.1f}", gaps=gap_text)
    else:
        move = fill(text["move_lineup_above"], gap=f"{lineup_gap:.1f}")
    arms = data["leaders"]["pitchers"]
    top3 = sorted(arms, key=lambda a: -a["war"])[:3]
    rotation_note = ""
    if pit["value"] > 0 and sum(a["war"] for a in top3) / pit["value"] >= 0.5:
        rotation_note = fill(text["move_rotation"], names=and_join([a["name"] for a in top3]),
                             share=f"{sum(a['war'] for a in top3):.1f}",
                             total=f"{pit['value']:.1f}")

    spot_rows = "".join(
        f"<tr><td>{escape(labels.get(s['spot'], s['spot']))}</td><td>{s['war']:.1f}</td>"
        f"<td>{s['avg']:.1f}</td><td>{escape(_signed(s['war'] - s['avg']))}</td>"
        f"<td>{ordinal(s['rank'])}</td><td>{s['best']:.1f} ({escape(s['best_team'])})</td>"
        f"<td class='wrap' style='text-align:left'>{escape(_who(s))}</td></tr>"
        for s in data["spots"])
    run_names = {"batting": "Batting", "defense": "Defense (fielding + position)",
                 "baserunning": "Baserunning"}
    run_rows = "".join(
        f"<tr><td>{run_names[k]}</td><td>{escape(_signed(v['value']))}</td>"
        f"<td>{escape(_signed(v['avg']))}</td><td>{ordinal(v['rank'])}</td></tr>"
        for k, v in runs.items())
    bat_rows = "".join(
        f"<tr><td>{escape(b['name'])}</td><td>{escape(b['position'])}</td><td>{b['pa']:.0f}</td>"
        f"<td>{_num(b['wrc_plus'])}</td>"
        f"<td>{b['war']:.1f}</td></tr>" for b in data["leaders"]["batters"])
    arm_rows = "".join(
        f"<tr><td>{escape(a['name'])}</td><td>{a['role']}</td><td>{a['ip']:.0f}</td>"
        f"<td>{_num(a['fip'], '.2f')}</td><td>{a['war']:.1f}</td></tr>"
        for a in data["leaders"]["pitchers"])

    div = data["division"]
    div_rows = "".join(
        f"<tr{mine_row if r['team'] == team else ''}><td>{escape(r['name'])}</td>"
        f"<td>{r['wins']:.1f}</td><td>{r['batting']:.1f}</td><td>{r['pitching']:.1f}</td></tr>"
        for r in div["rows"])
    place = [r["team"] for r in div["rows"]].index(team)
    if place == 0:
        div_text = fill(text["division_ahead"], team_short=short,
                        gap=wins_text(div['rows'][0]['wins'] - div['rows'][1]['wins']))
    else:
        leader = div["rows"][0]
        div_text = fill(text["division_behind"], team_short=short, place=ordinal(place + 1),
                        leader=short_name(leader["name"]),
                        gap=wins_text(leader['wins'] - div['rows'][place]['wins']))

    fa = data["free_agents"]
    fa_rows = "".join(
        f"<tr{mine_row if r.get('last_team') == team else ''}>"
        f"<td>{escape(r['name'])}{' *' if r['off_position'] else ''}</td>"
        f"<td>{escape(str(r.get('last_team') or '—'))}</td>"
        f"<td>{escape('/'.join(r['natives']) or '—')}</td>"
        f"<td>{escape(', '.join(f'{q} {p:.0f}' for q, p in r['where']))}</td>"
        f"<td>{_num(r['wrc_plus'])}</td>"
        f"<td>{r['proj_war']:.1f}</td><td>{r['proj_pa']:.0f}</td>"
        f"<td>{escape(_signed(r['gain']))}</td>"
        f"<td>{escape(losers_text(r.get('losers') or []))}</td></tr>" for r in fa["batters"])
    off = [r["name"] for r in fa["batters"] if r["off_position"]]
    fa_notes = []
    if off:
        fa_notes.append(fill(text["fa_off_position"], names=and_join(off)))
    if fa["pair"]:
        fa_notes.append(fill(text["fa_pair"], first=fa["pair"]["names"][0],
                             second=fa["pair"]["names"][1], gain=f"{fa['pair']['gain']:.1f}",
                             separate=f"{fa['pair']['separate']:.1f}"))
    pit_rows = "".join(
        f"<tr><td>{escape(r['name'])}</td><td>{r['role']}</td><td>{r['ip']:.0f}</td>"
        f"<td>{_num(r['fip'], '.2f')}</td><td>{r['war']:.1f}</td>"
        f"<td>{escape(_signed(r['gain']))}</td></tr>" for r in fa["pitchers"])
    pit_intro = ""
    if fa["pitching_base"]:
        b = fa["pitching_base"]
        pit_intro = fill(text["fa_pitching_intro"], weakest=b["weakest_sp"],
                         war=f"{b['weakest_sp_war']:.1f}", ip=f"{b['weakest_sp_ip']:.0f}")
    fa_section = ""
    if fa["batters"] or fa["pitchers"]:
        fa_section = f"""<h2>{fill(text['fa_heading'])}</h2><p>{fill(text['fa_intro'])}</p>
<div class="scroll"><table><tr><th>Free agent</th><th>Last team</th><th>Played</th>
<th style="text-align:left">Where he would play (PA)</th><th>wRC+</th><th>Projected WAR</th>
<th>Projected PA</th><th>Gain (WAR)</th>
<th style="text-align:left">Loses time (PA)</th></tr>
{fa_rows}</table></div>
{''.join(f'<p class="muted">{n}</p>' for n in fa_notes)}
<h3>Pitching</h3><p class="muted">{pit_intro}</p>
<div class="scroll"><table><tr><th>Free agent</th><th>Role</th><th>IP</th><th>FIP</th>
<th>WAR</th><th>Gain (WAR)</th></tr>{pit_rows}</table></div>
<p class="muted">{fill(text['fa_caveat'])}</p>"""

    division_teams = {r["team"] for r in div["rows"]}
    ranked = sorted(data["scatter"], key=lambda p: p["batting"] + p["pitching"])
    label_teams = division_teams | {ranked[0]["team"], ranked[-1]["team"]}
    scores = data["scores"]
    footer = fill(text["footer"], model=data["model"], rmse=f"{scores.get('rmse', float('nan')):.2f}",
                  first=scores.get("first", ""), last=scores.get("last", ""),
                  rmse_recent=f"{scores.get('rmse_recent', float('nan')):.2f}",
                  recent_first=scores.get("recent_first", ""), today=data["today"])

    def hero(label, value, rank, avg):
        return (f'<div><div class="eyebrow">{fill(label)}</div><div class="big">{value:.1f} '
                f'<small>{ordinal(rank)}</small></div><div class="muted">'
                f'{fill(text["hero_avg"], avg=f"{avg:.1f}")}</div></div>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(short)} {data['season']} outlook</title><style>{BASE_CSS}{EXTRA_CSS}</style></head>
<body><main>
<p class="muted" style="margin:0">{fill(text['kicker'])}</p>
<h1>{fill(text['title'], team_name=data['team_name'], season=data['season'])}: {escape(head)}</h1>
<p class="muted">{fill(text['date_line'], as_of=data['as_of'], source_label=source_label)}</p>
<p>{fill(text['intro'], team_short=short, pitching_rank=ordinal(pit['rank']),
         batting_rank=ordinal(bat['rank']), wins=f"{f['wins']:.1f}", win_rank=ordinal(f['rank']))}</p>

<div class="hero">
<div><div class="eyebrow">{fill(text['hero_wins'])}</div><div class="big">{f['wins']:.1f}
<small>{ordinal(f['rank'])}</small></div><div class="muted">{fill(text['hero_range'],
    low=f"{f['low']:.1f}", high=f"{f['high']:.1f}")}</div></div>
{hero(text['hero_team_war'], tot['value'], tot['rank'], tot['avg'])}
{hero(text['hero_pitching'], pit['value'], pit['rank'], pit['avg'])}
{hero(text['hero_batting'], bat['value'], bat['rank'], bat['avg'])}
</div>

<div class="cols">
<div><h3>{fill(text['strengths_heading'])}</h3><ul>{''.join(f'<li>{s}</li>' for s in strengths)}</ul></div>
<div><h3>{fill(text['weaknesses_heading'])}</h3><ul>{''.join(f'<li>{w}</li>' for w in weaknesses)}</ul></div>
</div>

<h2>{fill(text['positions_heading'])}</h2>
<p>{fill(text['positions_intro'])}</p>
<p class="muted">{fill(text['positions_chart_note'])}</p>
<figure style="margin:0">{spot_chart(data['spots'], labels)}
<figcaption>{fill(text['positions_caption'])}</figcaption></figure>
<div class="scroll"><table><tr><th>Spot</th><th>WAR</th><th>League avg</th><th>Difference</th>
<th>Rank</th><th>Best team</th><th style="text-align:left">Who plays (PA; pitchers: WAR)</th></tr>
{spot_rows}</table></div>

<h2>{fill(text['scatter_heading'])}</h2>
<p>{fill(text['scatter_intro'], team=team)}</p>
{scatter_chart(data['scatter'], team, label_teams)}

<h2>{fill(text['runs_heading'])}</h2>
<p>{fill(text['runs_intro'])}</p>
<div class="scroll"><table><tr><th>Component</th><th>{escape(short)}</th><th>League avg</th>
<th>Rank</th></tr>{run_rows}</table></div>

<h2>{fill(text['leaders_heading'])}</h2>
<p class="muted">{fill(text['leaders_note'])}</p>
<div class="cols">
<div class="scroll"><table><tr><th>Batter</th><th>Pos</th><th>PA</th><th>wRC+</th><th>WAR</th></tr>
{bat_rows}</table></div>
<div class="scroll"><table><tr><th>Pitcher</th><th>Role</th><th>IP</th><th>FIP</th><th>WAR</th></tr>
{arm_rows}</table></div>
</div>

<h2>{fill(text['division_heading'], division=div['name'])}</h2>
<div class="scroll"><table><tr><th>Team</th><th>Projected wins</th><th>Batting WAR</th>
<th>Pitching WAR</th></tr>{div_rows}</table></div>
<p class="muted">{fill(text['division_note'])}</p>
<p>{div_text}</p>

<h2>{fill(text['move_heading'])}</h2>
<p>{move}</p>
{f'<p>{rotation_note}</p>' if rotation_note else ''}

{fa_section}

<footer>{footer}</footer>
</main></body></html>"""


def outlook_path(data: dict, root: Path = REPORTS_DIR) -> Path:
    return (root / str(data["season"])
            / f"{data['model']}_{data['team'].lower()}_outlook_{data['as_of']}.html")


def write_outlook(data: dict, root: Path = REPORTS_DIR) -> Path:
    path = outlook_path(data, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_outlook(data).rstrip("\n") + "\n", encoding="utf-8")
    return path
