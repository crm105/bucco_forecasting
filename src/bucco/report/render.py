"""Turn the report dictionary into one self-contained HTML file."""

from __future__ import annotations

from html import escape
from pathlib import Path

from bucco.config import REPORTS_DIR
from bucco.report import charts
from bucco.report.text import fill, load_text

BADGE_CLASSES = {"record": "record", "preliminary": "prelim", "late": "late"}

CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b19;--muted:#6b675f;--line:#e3dfd6;--card:#fff;--accent:#c79a00;
--accent-ink:#5c4600;--other:#4a6277;--hl:#fff6d6;--over:#b5523b;--under:#3d7a5f}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#15140f;--fg:#efece4;
--muted:#a39e92;--line:#33302a;--card:#1d1c17;--accent:#f1c232;--accent-ink:#f1c232;
--other:#8fb0c9;--hl:#2d2814;--over:#e08a73;--under:#6fbf9a}}
:root[data-theme="dark"]{--bg:#15140f;--fg:#efece4;--muted:#a39e92;--line:#33302a;--card:#1d1c17;
--accent:#f1c232;--accent-ink:#f1c232;--other:#8fb0c9;--hl:#2d2814;--over:#e08a73;--under:#6fbf9a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:1.7rem;margin:0 0 4px}h2{font-size:1.2rem;margin:40px 0 8px}
.muted{color:var(--muted)}.badge{display:inline-block;padding:2px 10px;border-radius:99px;
font-size:.8rem;border:1px solid var(--line)}.badge.record{background:var(--accent);
color:#1c1b19;border-color:var(--accent)}.badge.late{color:var(--over);border-color:var(--over)}
.hero{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;
margin:20px 0}.big{font-size:2.6rem;font-weight:700;line-height:1.1}
.big small{font-size:1rem;font-weight:400;color:var(--muted)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;
margin-top:16px}.fact{border-top:1px solid var(--line);padding-top:8px}
.fact b{font-size:1.4rem;display:block}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:600}
.chart{width:100%;height:auto;display:block}
.grid{stroke:var(--line);stroke-width:1}.ref{stroke:var(--muted);stroke-width:1;
stroke-dasharray:4 3}.axis{fill:var(--muted);font-size:11px}
.label,.val{font-size:12px;fill:var(--fg)}.label.pit,.val.pit{font-weight:700}
.bar{stroke-width:3;stroke-linecap:round}.bar.other{stroke:var(--other);opacity:.55}
.bar.pit{stroke:var(--accent)}.dot.other{fill:var(--other)}.dot.pit{fill:var(--accent)}
.rowhl{fill:var(--hl)}.band{fill:var(--accent);opacity:.2}
.trend{fill:none;stroke:var(--accent);stroke-width:2}
.errbar.over{fill:var(--over)}.errbar.under{fill:var(--under)}
ul{padding-left:20px}footer{margin-top:48px;padding-top:16px;border-top:1px solid var(--line);
font-size:.85rem;color:var(--muted)}
"""


def _wins(value: float) -> str:
    return f"{value:.0f}"


def what_changed(data: dict, text: dict | None = None) -> str:
    """Plain-text note on how this forecast differs from the previous saved one."""
    text = text or load_text()
    prev, now = data["previous"], data["pirates"]["wins"]
    if prev is None:
        return text["what_changed_first"].format(season=data["season"])
    delta = now - prev["wins"]
    note = text["what_changed_moved"].format(
        before=f"{prev['wins']:.1f}", now=f"{now:.1f}", delta=f"{delta:+.1f}",
        before_date=prev["as_of_date"])
    if prev["model"] != data["model"]:
        note += " " + text["what_changed_model"].format(before_model=prev["model"])
    elif abs(delta) < 0.05:
        note += " " + text["what_changed_unchanged"]
    return note


def render_html(data: dict, text: dict | None = None) -> str:
    text = text or load_text()
    p, season = data["pirates"], data["season"]
    badge_class = BADGE_CLASSES[data["badge"]]
    model_label = text["model_labels"].get(data["model"], data["model"])
    board = data["leaderboard"]
    as_of = data["as_of"]
    board_rows = "".join(
        f"<tr><td>{escape(str(name))}{' (shown)' if name == data['model'] else ''}</td>"
        f"<td>{int(r.first_season)}</td><td>{r.mae:.1f}</td><td>{r.rmse:.1f}</td>"
        f"<td>{r.rmse_shared:.2f}</td><td>{r.cover_80 * 100:.0f}%</td></tr>"
        for name, r in board.iterrows())

    timeline = ""
    if len(data["timeline"]) >= 2:
        timeline = (f"<h2>{fill(text['timeline_heading'])}</h2>"
                    f"<p class='muted'>{fill(text['timeline_intro'])}</p>"
                    + charts.timeline_chart(data["timeline"], data["opening_day"]))

    opening_note = f"Opening Day is {data['opening_day']}." if data["opening_day"] else ""
    commit_note = f"Code version {data['commit']}." if data["commit"] else ""
    unknowns = "".join(f"<li>{fill(item, as_of=as_of)}</li>" for item in text["unknowns"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pirates {season} forecast</title><style>{CSS}</style></head><body><main>
<p class="muted" style="margin:0">{fill(text['kicker'])}</p>
<h1>{fill(text['title'], season=season)}</h1>
<span class="badge {badge_class}">{fill(text['badges'][data['badge']])}</span>
<span class="muted"> {fill(text['date_line'], as_of=as_of, opening_day_note=opening_note)}</span>

<div class="hero">
<div class="big">{_wins(p['wins'])} wins
<small>80% range: {_wins(p['low'])} to {_wins(p['high'])}</small></div>
<p>{fill(text['hero_explanation'], low=_wins(p['low']), high=_wins(p['high']))}</p>
<div class="facts">
<div class="fact"><b>{p['p_above_500'] * 100:.0f}%</b>{fill(text['fact_above_500'])}</div>
<div class="fact"><b>{p['p_beat_last'] * 100:.0f}%</b>{fill(
        text['fact_beat_last'], last_wins=f"{p['last_wins']:.0f}", last_season=p['last_season'])}
</div>
</div></div>

<h2>{fill(text['what_changed_heading'])}</h2><p>{escape(what_changed(data, text))}</p>
{timeline}
<h2>{fill(text['league_heading'])}</h2>
<p class="muted">{fill(text['league_intro'])}</p>
{charts.range_chart(data['teams'])}

<h2>{fill(text['trust_heading'])}</h2>
<p>{fill(text['trust_intro'], model_label=model_label,
         first_season=data['first_scored_season'], last_season=data['last_scored_season'])}</p>
<table><tr><th>Model</th><th>Scored from</th><th>Typical miss (wins)</th><th>RMSE (wins)</th>
<th>RMSE, {data['shared_first']}–{data['shared_last']}</th>
<th>Results inside the 80% range</th></tr>{board_rows}</table>
<p class="muted">{fill(text['table_note'])}</p>

<h3>{fill(text['past_heading'])}</h3>
<p class="muted">{fill(text['past_intro'])}</p>
{charts.error_chart(data['pirates_past'])}

<h3>{fill(text['unknowns_heading'])}</h3>
<ul>{unknowns}</ul>

<footer>{fill(text['footer'], today=data['today'], commit_note=commit_note)}</footer>
</main></body></html>"""


def report_path(data: dict, root: Path = REPORTS_DIR) -> Path:
    return root / str(data["season"]) / f"{data['model']}_{data['as_of']}.html"


def write_report(data: dict, root: Path = REPORTS_DIR) -> Path:
    path = report_path(data, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(data).rstrip("\n") + "\n", encoding="utf-8")
    return path
