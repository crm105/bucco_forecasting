"""Checks for the Baseball Savant leaderboard extract."""

import pandas as pd
import pytest

from bucco.extract.savant import (
    COLUMNS,
    STATS,
    parse_custom,
    parse_speeds,
    validate_players,
)

CSV = ('"last_name, first_name",player_id,year,pa,k_percent,whiff_percent,sprint_speed\n'
       '"Judge, Aaron",592450,2024,704,28.3,30.1,26.9\n'
       '"Cruz, Oneil",665833,2024,595,30.0,32.0,29.5\n')


def test_parse_custom_keeps_raw_rates_and_blanks_what_the_csv_lacks():
    out = parse_custom(CSV, 2024, "batter", "now")
    assert list(out["mlbam_id"]) == [592450, 665833]
    assert out.loc[0, "k_percent"] == 28.3 and out.loc[1, "sprint_speed"] == 29.5
    assert out["xwoba"].isna().all()                         # not selected here
    pit = parse_custom(CSV, 2024, "pitcher", "now")
    assert pit["sprint_speed"].isna().all()                  # batters only


def test_an_exact_repeat_is_dropped():
    lines = CSV.splitlines()
    out = parse_custom("\n".join([*lines, lines[1]]) + "\n", 2024, "batter", "now")
    assert list(out["mlbam_id"]) == [592450, 665833]


def test_parse_speeds_takes_the_fastball_columns():
    text = '"last_name, first_name",pitcher,ff_avg_speed,si_avg_speed\nx,1,95.1,\ny,2,,93.0\n'
    out = parse_speeds(text).set_index("mlbam_id")
    assert out.loc[1, "ff_speed"] == 95.1 and pd.isna(out.loc[1, "si_speed"])
    assert out.loc[2, "si_speed"] == 93.0 and out["sl_speed"].isna().all()


def _season(n=450, pa=150, speed=95.0):
    rows = []
    for kind in ("batter", "pitcher"):
        for i in range(n):
            speeds = {c: None for c in ("ff_speed", "si_speed", "fc_speed", "sl_speed")}
            rows.append({c: 0.0 for c in COLUMNS} | speeds | {
                "season": 2024, "mlbam_id": i, "player_type": kind, "pa": pa,
                "ff_speed": speed if kind == "pitcher" else None})
    return pd.DataFrame(rows)


def test_a_full_season_passes():
    validate_players(_season(), 2024)


@pytest.mark.parametrize("season, message", [
    (_season(n=300), "only 300 batters"),
    (_season(pa=100), "batter PA"),
    (_season(speed=None), "pitch speed"),
])
def test_thin_or_incomplete_seasons_are_refused(season, message):
    with pytest.raises(ValueError, match=message):
        validate_players(season, 2024)


def test_every_selected_stat_is_a_column():
    assert set(STATS) <= set(COLUMNS)
