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
    depth = pd.DataFrame({  # noqa: F841 (read by duckdb below)
        "season": [2009, 2009, 2009, 2010], "mlbam_id": [4, 5, 1, 6],
        "team_id": [134, 147, 147, 134], "player_type": ["batter", "pitcher", "pitcher", "batter"],
        "last_sport_id": [11, 12, 11, 11]})
    with duckdb.connect(str(path)) as con:
        con.execute("create schema marts")
        con.execute("create table marts.player_preseason_status as select * from status")
        con.execute("create table marts.organization_depth as select * from depth")
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


def test_organization_depth_joins_the_40_man_but_never_overrides_it(db):
    roster = marcel_rosters("mlb_org", db)
    got = set(zip(roster["mlbam_id"], roster["team_id"], roster["player_type"], strict=True))
    assert {(4, 134, "batter"), (5, 147, "pitcher")} <= got
    assert (1, 147, "pitcher") not in got          # on the Pirates' 40-man
    assert 6 not in set(roster["mlbam_id"])         # a season without rosters
    assert roster["as_of_date"].notna().all()
