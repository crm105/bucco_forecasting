"""Preseason rosters for our own projections: Steamer's team assignments or the MLB API's."""

import duckdb
import pandas as pd
import pytest

from bucco.models.player_inputs import marcel_rosters


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "bucco.duckdb"
    status = pd.DataFrame({  # noqa: F841 (read by duckdb below)
        "season": [2009, 2009, 2009], "mlbam_id": [1, 2, 3], "team_id": [134, 134, 147],
        "snapshot_date": pd.to_datetime(["2009-04-06", "2009-04-06", "2009-04-07"]),
        "position": ["P", "SS", "TWP"], "status_code": ["A", "D60", "A"],
        "status_description": ["Active", "60-Day IL", "Active"],
        "il_group": ["none", "il_60", "none"]})
    with duckdb.connect(str(path)) as con:
        con.execute("create schema marts")
        con.execute("create table marts.player_preseason_status as select * from status")
    return path


def test_mlb_rosters_split_pitchers_and_batters_by_roster_position(db):
    roster = marcel_rosters("mlb", db).sort_values(["mlbam_id", "player_type"])
    assert list(zip(roster["mlbam_id"], roster["player_type"], strict=True)) == [
        (1, "pitcher"), (2, "batter"), (3, "batter"), (3, "pitcher")]   # two-way: both
    assert set(roster.columns) == {"season", "player_type", "mlbam_id", "team_id", "as_of_date"}
    assert roster.loc[roster["mlbam_id"] == 3, "team_id"].eq(147).all()


def test_unknown_roster_source_is_refused(db):
    with pytest.raises(ValueError, match="roster_source"):
        marcel_rosters("zips", db)
