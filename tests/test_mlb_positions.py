"""Checks for the MLB fielding (positions) extract."""

import pandas as pd
import pytest

from bucco.extract.mlb_positions import (
    COLUMNS,
    innings_to_float,
    parse_fielding,
    validate_fielding,
)


def _split(player_id, position, games, started=0, innings="0.0", name="A Player"):
    return {"player": {"id": player_id, "fullName": name},
            "position": {"abbreviation": position},
            "stat": {"gamesPlayed": games, "gamesStarted": started, "innings": innings}}


def test_innings_are_converted_from_thirds():
    assert innings_to_float("69.2") == pytest.approx(69 + 2 / 3)
    assert innings_to_float("0.0") == 0.0
    assert innings_to_float("") == 0.0 and innings_to_float(None) == 0.0
    assert innings_to_float("150") == 150.0


def test_parse_keeps_real_positions_and_skips_others():
    payload = {"stats": [{"splits": [
        _split(1, "SS", 100, 95, "850.1"),
        _split(2, "P", 30, 30, "180.2"),
        _split(3, "DH", 20),
        _split(4, "PH", 5),        # pinch hitter: not a fielding position
    ]}]}
    rows = parse_fielding(payload, 2025, 134, "now")
    assert [r["position"] for r in rows] == ["SS", "P", "DH"]
    assert rows[1]["games_started"] == 30 and rows[1]["innings"] == pytest.approx(180 + 2 / 3)
    assert rows[0]["team_id"] == 134 and rows[0]["season"] == 2025


def test_parse_handles_an_empty_response():
    assert parse_fielding({"stats": []}, 2025, 134, "now") == []
    assert parse_fielding({"stats": [{"splits": []}]}, 2025, 134, "now") == []


def _season(teams=30, rows_per_team=25, positions=("C", "SS", "CF", "P", "DH", "1B")):
    rows = []
    for t in range(1, teams + 1):
        for i in range(rows_per_team):
            rows.append({"season": 2025, "team_id": t, "mlbam_id": t * 1000 + i,
                         "player_name": "x", "position": positions[i % len(positions)],
                         "games": 10, "games_started": 5, "innings": 50.0, "fetched_at": "n"})
    return pd.DataFrame(rows, columns=COLUMNS)


def test_a_complete_season_passes():
    validate_fielding(_season(), 2025)


def test_missing_team_is_rejected():
    with pytest.raises(ValueError, match="expected 30 teams"):
        validate_fielding(_season(teams=29), 2025)


def test_thin_team_is_rejected():
    df = _season()
    df = df[~((df["team_id"] == 5) & (df["mlbam_id"] % 1000 > 5))]
    with pytest.raises(ValueError, match="fewer than"):
        validate_fielding(df, 2025)


def test_duplicate_rows_and_negative_values_are_rejected():
    dup = pd.concat([_season(), _season().head(1)], ignore_index=True)
    with pytest.raises(ValueError, match="twice"):
        validate_fielding(dup, 2025)
    bad = _season()
    bad.loc[0, "games"] = -1
    with pytest.raises(ValueError, match="negative"):
        validate_fielding(bad, 2025)


def test_missing_main_positions_are_rejected():
    with pytest.raises(ValueError, match="no rows for positions"):
        validate_fielding(_season(positions=("C", "SS", "P")), 2025)
