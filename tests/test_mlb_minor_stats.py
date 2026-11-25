"""Minor-league batting extract: parsing and checks."""

import pandas as pd
import pytest

from bucco.extract import mlb_minor_stats as ms


def test_parse_reads_level_league_age_and_counts():
    payload = {"stats": [{"splits": [{
        "player": {"id": 9, "fullName": "A"}, "team": {"id": 561}, "numTeams": 1,
        "league": {"id": 112, "name": "PCL"},
        "stat": {"age": 23, "plateAppearances": 400, "atBats": 350, "hits": 100, "doubles": 20,
                 "homeRuns": 15, "baseOnBalls": 40, "stolenBases": 5}}]}]}
    row = ms.parse_batting(payload, 2025, 11, "now")[0]
    assert (row["level"], row["league_name"], row["age"], row["pa"], row["triples"]) == \
        ("AAA", "PCL", 23, 400, 0)


def _season(per_level=400):
    rows = [{"level": lv, "mlbam_id": i, "league_id": 1, "pa": 100, "ab": 80, "bb": 10,
             "hbp": 2, "sf": 2, "sh": 1} for lv in ms.LEVELS.values() for i in range(per_level)]
    return pd.DataFrame(rows)


def test_checks_reject_thin_levels_duplicates_and_bad_arithmetic():
    ms.validate_batting(_season(), 2025)
    with pytest.raises(ValueError, match="fewer than"):
        ms.validate_batting(_season(per_level=10), 2025)
    dup = pd.concat([_season(), _season().iloc[:1]])
    with pytest.raises(ValueError, match="twice"):
        ms.validate_batting(dup, 2025)
    bad = _season()
    bad.loc[0, "ab"] = 200
    with pytest.raises(ValueError, match="exceed PA"):
        ms.validate_batting(bad, 2025)
