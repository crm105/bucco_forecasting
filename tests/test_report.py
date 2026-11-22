"""Checks for report numbers, text, charts and the end-to-end build from a small database."""

import xml.etree.ElementTree as ET
from datetime import date

import duckdb
import numpy as np
import pandas as pd
import pytest

from bucco.report import charts, render
from bucco.report.data import _badge, build_report_data, prob_above


def test_prob_above_uses_continuity_correction():
    # mean 81.5, so the chance of 82 or more wins (above 81.5) is exactly half
    assert prob_above(81, 81.5, 6.4) == pytest.approx(0.5)
    # far above the mean is near zero, far below is near one
    assert prob_above(120, 80, 6.4) < 0.001
    assert prob_above(40, 80, 6.4) > 0.999


def test_badge():
    opening = date(2027, 3, 25)
    assert _badge("2027-02-01", opening, ["2027-02-01"], date(2027, 2, 2)) == "preliminary"
    assert _badge("2027-03-20", opening, ["2027-03-01", "2027-03-20"], date(2027, 4, 1)) == "record"
    assert _badge("2027-03-01", opening, ["2027-03-01", "2027-03-20"], date(2027, 4, 1)) \
        == "preliminary"
    assert _badge("2027-04-01", opening, ["2027-04-01"], date(2027, 4, 2)) == "late"


def _teams(n=30):
    wins = np.linspace(65, 98, n)
    return pd.DataFrame({
        "team_id": [134] + list(range(1, n)), "team_abbr": ["PIT"] + [f"T{i}" for i in range(1, n)],
        "wins": wins, "low": wins - 12, "high": wins + 12})


def test_charts_are_valid_svg():
    ET.fromstring(charts.range_chart(_teams()))
    timeline = pd.DataFrame({"as_of_date": ["2027-01-01", "2027-03-01"], "wins": [78.0, 80.0],
                             "low": [66.0, 68.0], "high": [90.0, 92.0]})
    ET.fromstring(charts.timeline_chart(timeline, "2027-03-25"))
    past = pd.DataFrame({"season": range(2001, 2010), "error": np.linspace(-9, 12, 9)})
    ET.fromstring(charts.error_chart(past))


def test_what_changed_text():
    base = {"season": 2027, "model": "last_year", "pirates": {"wins": 80.0}}
    assert "first saved forecast" in render.what_changed({**base, "previous": None})
    same = {"as_of_date": "2027-01-01", "model": "last_year", "wins": 78.0}
    text = render.what_changed({**base, "previous": same})
    assert "78.0 to 80.0" in text and "+2.0" in text
    other = render.what_changed({**base, "previous": {**same, "model": "constant"}})
    assert "constant" in other


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test.duckdb"
    rng = np.random.default_rng(1)
    ids = list(range(1, 30)) + [134]
    seasons = pd.DataFrame([{"season": s, "team_id": t, "win_pct": 0.5 + rng.normal(0, 0.06)}
                            for s in (2024, 2025, 2026) for t in ids])
    features = pd.DataFrame({
        "season": 2027, "team_id": ids, "opening_day": pd.Timestamp("2027-03-25"),
        "prior_win_pct": 0.5, "prior_wins": 81, "prior_season": 2026})
    results = pd.DataFrame([
        {"model": m, "season": s, "team_id": t, "as_of_date": f"{s}-04-01", "pred_win_pct": 0.5,
         "sd_win_pct": 0.07, "actual_win_pct": 0.5 + rng.normal(0, 0.07)}
        for m in ("constant", "last_year") for s in (2024, 2025, 2026) for t in ids])
    with duckdb.connect(str(path)) as con:
        for schema in ("marts", "evaluate", "forecasts"):
            con.execute(f"create schema {schema}")
        con.register("a", seasons)
        con.register("b", features)
        con.register("c", results)
        con.execute("create table marts.team_seasons as select * from a")
        con.execute("create table marts.team_season_features as select * from b")
        con.execute("create table evaluate.backtest_results as select * from c")
    return path


def _save(path, model, as_of, mean):
    rows = pd.DataFrame({"model": model, "season": 2027, "team_id": list(range(1, 30)) + [134],
                         "team_abbr": [f"T{i}" for i in range(1, 30)] + ["PIT"],
                         "as_of_date": as_of, "pred_win_pct": mean, "sd_win_pct": 0.07})
    from bucco.forecast import save_forecast
    save_forecast(rows, path)


def test_build_and_render_report(db, tmp_path):
    _save(db, "last_year", "2027-01-10", 0.48)
    _save(db, "last_year", "2027-02-10", 0.50)
    data = build_report_data(model="last_year", path=db, today=date(2027, 2, 11))
    assert data["as_of"] == "2027-02-10" and data["badge"] == "preliminary"
    assert data["previous"]["as_of_date"] == "2027-01-10"
    assert len(data["timeline"]) == 2
    path = render.write_report(data, root=tmp_path / "reports")
    assert path == tmp_path / "reports" / "2027" / "last_year_2027-02-10.html"
    html = path.read_text()
    assert "Pirates 2027 forecast" in html and "How the Pirates forecast has moved" in html
    assert "https://" not in html.replace("statsapi.mlb.com", "")  # nothing external loaded


def test_report_without_forecast_explains_what_to_run(db):
    with pytest.raises(RuntimeError, match="bucco forecast"):
        build_report_data(model="last_year", path=db)


def test_text_file_is_valid_and_fills_placeholders():
    from bucco.report.text import fill, load_text
    text = load_text()
    assert "<b>x</b>" in fill("**x**")
    assert "<script>" not in fill("<script>")
    assert "67" in fill(text["hero_explanation"], low=67, high=97)


def test_text_rejects_unknown_placeholder_and_missing_entry(tmp_path):
    from bucco.report.text import TEXT_PATH, ReportTextError, load_text
    good = TEXT_PATH.read_text()
    bad = tmp_path / "bad.yml"
    bad.write_text(good.replace("{low}", "{lowest}"))
    with pytest.raises(ReportTextError, match="hero_explanation"):
        load_text(bad)
    bad.write_text(good.replace("league_heading:", "other_heading:"))
    with pytest.raises(ReportTextError, match="league_heading"):
        load_text(bad)


def test_edited_text_appears_in_report(db, tmp_path):
    from bucco.report.text import TEXT_PATH, load_text
    _save(db, "last_year", "2027-02-10", 0.50)
    edited = tmp_path / "t.yml"
    edited.write_text(TEXT_PATH.read_text().replace("The whole league", "Around the league"))
    html = render.render_html(build_report_data(model="last_year", path=db), load_text(edited))
    assert "Around the league" in html and "The whole league" not in html
