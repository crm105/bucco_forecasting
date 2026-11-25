"""Checks for the home/road team splits extract (park factor input)."""

import pandas as pd
import pytest

from bucco.extract.mlb_park_splits import COLUMNS, parse_splits, validate_splits


def test_parse_reads_both_sides_and_uses_batters_faced_for_pitching():
    payload = {"stats": [
        {"group": {"displayName": "hitting"}, "splits": [
            {"team": {"id": 115}, "stat": {"plateAppearances": 3022, "homeRuns": 86,
                                           "runs": 369, "baseOnBalls": 218}}]},
        {"group": {"displayName": "pitching"}, "splits": [
            {"team": {"id": 115}, "stat": {"battersFaced": 3371, "homeRuns": 131}}]},
        {"group": {"displayName": "fielding"}, "splits": []},
    ]}
    rows = parse_splits(payload, 2025, "h", "now")
    assert [(r["side"], r["site"], r["pa"]) for r in rows] == [("batting", "home", 3022),
                                                               ("pitching", "home", 3371)]
    assert rows[0]["hr"] == 86 and rows[0]["so"] == 0 and set(rows[0]) == set(COLUMNS)


def _season(home_pa=3000, road_pa=3000, teams=30):
    rows = []
    for t in range(1, teams + 1):
        for site, side, pa in (("home", "batting", home_pa), ("home", "pitching", road_pa),
                               ("road", "batting", road_pa), ("road", "pitching", home_pa)):
            rows.append({c: 0 for c in COLUMNS} | {"season": 2025, "team_id": t, "site": site,
                                                    "side": side, "pa": pa})
    return pd.DataFrame(rows)


def test_a_complete_season_passes():
    validate_splits(_season(), 2025)


def test_home_and_road_games_must_add_up():
    df = _season()
    df.loc[(df["site"] == "road") & (df["side"] == "pitching"), "pa"] = 3500
    with pytest.raises(ValueError, match="disagree"):
        validate_splits(df, 2025)


def test_missing_teams_are_refused():
    with pytest.raises(ValueError, match="30 teams"):
        validate_splits(_season(teams=29), 2025)
