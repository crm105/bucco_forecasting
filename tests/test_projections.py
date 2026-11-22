"""Checks for the hand-collected projections file validator."""

from datetime import date

import pandas as pd
import pytest

from bucco.extract.projections import load_team_lookup, validate


@pytest.fixture(scope="module")
def teams():
    return load_team_lookup()


def make_set(lookup, season=2019, source="steamer", kind="projection",
             as_of="2019-03-20", wins=81.0):
    """A complete, valid projection set: all 30 teams."""
    team_ids = sorted(set(lookup.values()))
    return pd.DataFrame({
        "season": str(season), "source": source, "kind": kind, "as_of_date": as_of,
        "team_id": [str(t) for t in team_ids], "projected_wins": str(wins),
        "source_file": "test.csv",
    })


def run(df, teams, opening_days=None):
    lookup, ids = teams
    return validate(df, lookup, ids, opening_days)


def test_complete_set_passes(teams):
    clean, errors, _ = run(make_set(teams[0]), teams, {2019: date(2019, 3, 28)})
    assert errors == []
    assert len(clean) == 30


def test_abbreviations_old_and_new_resolve(teams):
    lookup, _ = teams
    assert lookup["ARI"] == lookup["AZ"]
    assert lookup["CWS"] == lookup["CHW"]
    assert lookup["OAK"] == lookup["ATH"]
    assert lookup["WSH"] == lookup["WAS"]


def test_missing_team_is_an_error(teams):
    df = make_set(teams[0]).iloc[:-1]
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert any("29 teams" in e for e in errors)


def test_duplicate_row_is_an_error(teams):
    df = pd.concat([make_set(teams[0]), make_set(teams[0]).iloc[:1]], ignore_index=True)
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert any("repeat" in e for e in errors)


def test_projection_after_opening_day_is_an_error(teams):
    df = make_set(teams[0], as_of="2019-04-02")
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert any("after Opening Day" in e for e in errors)


def test_projection_on_opening_day_is_allowed(teams):
    df = make_set(teams[0], as_of="2019-03-28")
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert errors == []


def test_wins_out_of_range_is_an_error(teams):
    df = make_set(teams[0], wins=200)
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert any("outside" in e for e in errors)


def test_unknown_kind_is_an_error(teams):
    df = make_set(teams[0], kind="guess")
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert any("kind" in e for e in errors)


def test_unknown_team_abbreviation_is_an_error(teams):
    df = make_set(teams[0]).drop(columns="team_id")
    df["team_abbr"] = ["XXX"] + ["PIT"] * 29
    _, errors, _ = run(df, teams, {2019: date(2019, 3, 28)})
    assert any("unrecognised" in e for e in errors)


def test_missing_required_column_is_an_error(teams):
    df = make_set(teams[0]).drop(columns="kind")
    _, errors, _ = run(df, teams)
    assert any("missing required" in e for e in errors)
