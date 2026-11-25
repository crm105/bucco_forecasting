"""Checks for the MLB player stats (batting, pitching, people) extract."""

import pandas as pd
import pytest

from bucco.extract.mlb_player_stats import (
    BATTING_COLUMNS,
    PITCHING_COLUMNS,
    parse_people,
    parse_player_stats,
    validate_player_stats,
)


def _split(player_id, team_id, stat, teams=1, name="A Player"):
    return {"player": {"id": player_id, "fullName": name}, "team": {"id": team_id},
            "numTeams": teams, "stat": stat}


def test_parse_splits_the_two_groups_and_keeps_counts_only():
    payload = {"stats": [
        {"group": {"displayName": "hitting"}, "splits": [
            _split(1, 134, {"plateAppearances": 600, "homeRuns": 25, "avg": ".280"}, teams=2)]},
        {"group": {"displayName": "pitching"}, "splits": [
            _split(2, 147, {"outs": 540, "battersFaced": 750, "era": "3.10"}),
            _split(1, 134, {"outs": 3, "battersFaced": 4})]},     # a two-way line
    ]}
    batting, pitching = parse_player_stats(payload, 2025, "now")
    assert len(batting) == 1 and len(pitching) == 2
    bat = batting[0]
    assert bat["pa"] == 600 and bat["hr"] == 25 and bat["so"] == 0   # missing counts are 0
    assert bat["last_team_id"] == 134 and bat["num_teams"] == 2 and bat["season"] == 2025
    assert "avg" not in bat and set(bat) == set(BATTING_COLUMNS)
    assert pitching[0]["outs"] == 540 and set(pitching[0]) == set(PITCHING_COLUMNS)


def test_parse_handles_an_empty_response():
    assert parse_player_stats({"stats": []}, 2025, "now") == ([], [])
    assert parse_player_stats({}, 2025, "now") == ([], [])


def _season(pa_per_player=700, bf_per_player=700, teams=30, per_team=10):
    bat, pit = [], []
    for t in range(1, teams + 1):
        for i in range(per_team):
            pid = t * 100 + i
            bat.append({c: 0 for c in BATTING_COLUMNS} | {
                "season": 2025, "mlbam_id": pid, "player_name": "x", "last_team_id": t,
                "num_teams": 1, "pa": pa_per_player, "fetched_at": "now"})
            pit.append({c: 0 for c in PITCHING_COLUMNS} | {
                "season": 2025, "mlbam_id": pid, "player_name": "x", "last_team_id": t,
                "num_teams": 1, "bf": bf_per_player, "fetched_at": "now"})
    return pd.DataFrame(bat), pd.DataFrame(pit)


def test_a_complete_season_passes():
    validate_player_stats(*_season(), 2025)


def test_plate_appearances_must_match_batters_faced():
    with pytest.raises(ValueError, match="disagree"):
        validate_player_stats(*_season(pa_per_player=700, bf_per_player=730), 2025)


def test_a_thin_or_partial_season_is_refused():
    with pytest.raises(ValueError, match="plate appearances in the season"):
        validate_player_stats(*_season(pa_per_player=100, bf_per_player=100), 2025)
    with pytest.raises(ValueError, match="expected 30 teams"):
        validate_player_stats(*_season(teams=29), 2025)


def test_a_player_listed_twice_is_refused():
    bat, pit = _season()
    bat = pd.concat([bat, bat.iloc[[0]]], ignore_index=True)
    pit = pd.concat([pit, pit.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="appears twice"):
        validate_player_stats(bat, pit, 2025)


def test_parse_people_reads_codes_and_tolerates_missing_fields():
    payload = {"people": [
        {"id": 668804, "fullName": "Bryan Reynolds", "birthDate": "1995-01-27",
         "batSide": {"code": "S"}, "pitchHand": {"code": "R"},
         "primaryPosition": {"abbreviation": "LF"}, "mlbDebutDate": "2019-04-20"},
        {"id": 1, "fullName": "No Details"},
    ]}
    rows = parse_people(payload, "now")
    assert rows[0]["bats"] == "S" and rows[0]["primary_position"] == "LF"
    assert rows[0]["birth_date"] == "1995-01-27"
    assert rows[1]["birth_date"] is None and rows[1]["bats"] is None
