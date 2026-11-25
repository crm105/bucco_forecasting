"""Checks for the players' home/road and batter-side splits extract."""

import pandas as pd
import pytest

from bucco.extract.mlb_player_splits import (
    COLUMNS,
    parse_player_splits,
    validate_player_splits,
)


def test_parse_maps_split_codes_and_uses_batters_faced_for_pitchers():
    payload = {"stats": [{"splits": [
        {"player": {"id": 1}, "team": {"id": 134}, "numTeams": 1, "split": {"code": "vl"},
         "stat": {"battersFaced": 394, "homeRuns": 7}},
        {"player": {"id": 1}, "team": {"id": 134}, "numTeams": 1, "split": {"code": "vr"},
         "stat": {"battersFaced": 339, "homeRuns": 4}},
        {"player": {"id": 1}, "split": {"code": "xx"}, "stat": {}},          # unknown: skipped
    ]}]}
    rows = parse_player_splits(payload, 2025, "pitching", "now")
    assert [(r["split"], r["pa"], r["hr"]) for r in rows] == [("vs_left", 394, 7),
                                                             ("vs_right", 339, 4)]
    assert set(rows[0]) == set(COLUMNS)


def _season(home=90_000, road=93_000, left=80_000, right=103_000, vs_left=80_000,
            vs_right=103_000):
    rows = []
    for i, (group, split, pa) in enumerate([("batting", "home", home), ("batting", "road", road),
                                            ("batting", "bat_left", left),
                                            ("batting", "bat_right", right),
                                            ("pitching", "vs_left", vs_left),
                                            ("pitching", "vs_right", vs_right)]):
        rows.append({c: 0 for c in COLUMNS} | {"season": 2025, "mlbam_id": i, "group": group,
                                                "split": split, "pa": pa})
    return pd.DataFrame(rows)


def test_a_season_whose_splits_add_up_passes():
    validate_player_splits(_season(), 2025)


def test_splits_that_do_not_add_up_are_refused():
    with pytest.raises(ValueError, match="pitchers vs left/right"):
        validate_player_splits(_season(vs_right=90_000), 2025)
