"""Checks for the Baseball Savant leaderboard extract."""

import pandas as pd
import pytest

from bucco.extract.savant import (
    COLUMNS,
    FIELDING_COLUMNS,
    STATS,
    add_framing,
    parse_custom,
    parse_fielding,
    parse_framing,
    parse_speeds,
    validate_fielding,
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


# ---- fielding --------------------------------------------------------------------------------
FRV = ("name,id,total_runs,inf_of_runs,range_runs,arm_runs,dp_runs,catching_runs,framing_runs,"
       "throwing_runs,blocking_runs,outs_total,outs_2,outs_6\n"
       '"Catcher, A",1,2.0,0.0,,,,2.0,0.0,1.5,0.5,3000,3000,0\n'
       '"Short, B",2,6.0,6.0,5.0,0.5,0.5,,,,,3500,0,3500\n'
       '"Never, C",3,,,,,,,,,,0,0,0\n')


def test_parse_fielding_fills_blank_parts_and_drops_fielders_with_no_outs():
    out = parse_fielding(FRV, 2017, "now").set_index("mlbam_id")
    assert list(out.index) == [1, 2]
    assert out.loc[2, "catching_runs"] == 0.0 and out.loc[1, "range_runs"] == 0.0
    assert out.loc[1, "framing_source"] == "none"
    assert parse_fielding(FRV, 2019, "now")["framing_source"].eq("fielding_run_value").all()


def test_early_framing_is_added_to_framing_catching_and_total():
    framing = parse_framing("last_name,first_name,player_id,runs_extra_strikes\nC,A,1,7.5\n"
                            "League,Average,,0.0\n")
    out = add_framing(parse_fielding(FRV, 2017, "now"), framing).set_index("mlbam_id")
    assert out.loc[1, ["framing_runs", "catching_runs", "total_runs"]].tolist() == [7.5, 9.5, 9.5]
    assert out.loc[1, "framing_source"] == "framing_leaderboard"
    assert out.loc[2, "total_runs"] == 6.0


def _fielders(n=600, outs=3000, broken=False):
    rows = [{c: 0 for c in FIELDING_COLUMNS} | {"season": 2021, "mlbam_id": i, "outs_total": outs,
             "total_runs": 1.0, "inf_of_runs": 1.0} for i in range(n)]
    if broken:
        rows[0]["total_runs"] = 5.0
    return pd.DataFrame(rows)


def test_fielding_checks():
    validate_fielding(_fielders(), 2021)
    with pytest.raises(ValueError, match="only 100 fielders"):
        validate_fielding(_fielders(n=100), 2021)
    with pytest.raises(ValueError, match="differ from their parts"):
        validate_fielding(_fielders(broken=True), 2021)
    no_framing = _fielders().assign(outs_2=2000)
    with pytest.raises(ValueError, match="no framing"):
        validate_fielding(no_framing, 2021)
