"""Opening Day 40-man rosters: snapshot dates, parsing, duplicates and checks."""

from datetime import date

import pandas as pd
import pytest

from bucco.extract import mlb_rosters as mr


def _schedule(tmp_path, season=2025):
    games = pd.DataFrame({"game_date": ["2025-03-18", "2025-03-27", "2025-03-28", "2025-04-01"],
                          "home_team_id": [119, 134, 119, 147], "away_team_id": [121, 147, 121, 134]})
    games.to_parquet(tmp_path / f"season={season}.parquet")
    return tmp_path


def test_each_team_is_taken_on_its_own_first_game(tmp_path):
    dates = mr.snapshot_dates(2025, today=date(2025, 6, 1), schedule_dir=_schedule(tmp_path))
    assert dates == {119: date(2025, 3, 18), 121: date(2025, 3, 18),     # Tokyo opener
                     134: date(2025, 3, 27), 147: date(2025, 3, 27)}


def test_a_season_not_started_is_taken_today(tmp_path):
    dates = mr.snapshot_dates(2025, today=date(2024, 11, 25), schedule_dir=_schedule(tmp_path))
    assert set(dates.values()) == {date(2024, 11, 25)}


def test_parse_reads_status():
    payload = {"roster": [{"person": {"id": 1, "fullName": "A"}, "position": {"abbreviation": "P"},
                           "status": {"code": "D60", "description": "Injured 60-Day"}}]}
    rows = mr.parse_roster(payload, 2025, 134, date(2025, 3, 27), "now")
    assert rows[0]["status_code"] == "D60" and rows[0]["snapshot_date"] == "2025-03-27"
    assert mr.parse_roster({}, 2025, 134, date(2025, 3, 27), "now") == []


def test_a_player_listed_twice_keeps_the_injured_list_row():
    df = pd.DataFrame({"team_id": [110, 110, 110], "mlbam_id": [5, 5, 6],
                       "status_code": ["RM", "D15", "A"]})
    out = mr.one_row_per_player(df)
    assert len(out) == 2 and out.loc[out["mlbam_id"] == 5, "status_code"].item() == "D15"


def _season(n_teams=30, per_team=40):
    return pd.DataFrame([{"team_id": t, "mlbam_id": t * 100 + i, "status_code": "A"}
                         for t in range(n_teams) for i in range(per_team)])


def test_checks_reject_missing_teams_thin_rosters_and_missing_status():
    mr.validate_rosters(_season(), 2025)
    with pytest.raises(ValueError, match="expected 30 teams"):
        mr.validate_rosters(_season(n_teams=29), 2025)
    with pytest.raises(ValueError, match="fewer than"):
        mr.validate_rosters(_season(per_team=10), 2025)
    bad = _season()
    bad.loc[0, "status_code"] = None
    with pytest.raises(ValueError, match="without a status"):
        mr.validate_rosters(bad, 2025)
