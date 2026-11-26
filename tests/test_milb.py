"""Major-league equivalents of minor-league batting."""

import numpy as np
import pandas as pd
import pytest

from bucco.models import marcel, milb


def _lines(seasons=(2015, 2016, 2017, 2018), n=150):
    """Players at two adjacent levels in a season; each level up costs 0.02 runs per PA."""
    rate = {"A": 0.06, "A+": 0.04, "AA": 0.02, "AAA": 0.0, "MLB": -0.02}
    rows = []
    for s in seasons:
        for i in range(n):
            for lo, hi in zip(milb.CHAIN[:-1], milb.CHAIN[1:], strict=True):
                pid = hash((lo, i)) % 10**7
                rows += [{"season": s, "mlbam_id": pid, "level": lo, "pa": 200.0,
                          "off_runs": 200.0 * rate[lo]},
                         {"season": s, "mlbam_id": pid, "level": hi, "pa": 200.0,
                          "off_runs": 200.0 * rate[hi]}]
    return pd.DataFrame(rows)


def test_drops_chain_up_the_levels():
    drops = milb.fit_drops(_lines(), before=2019)
    assert drops == pytest.approx({"AAA": -0.02, "AA": -0.04, "A+": -0.06, "A": -0.08})


def test_drops_never_see_the_target_season_and_need_enough_pairs():
    lines = _lines()
    changed = lines.copy()
    changed.loc[changed["season"] == 2018, "off_runs"] = 99.0
    assert milb.fit_drops(lines, 2018) == milb.fit_drops(changed, 2018)
    assert np.isnan(milb.fit_drops(_lines(n=10), 2019)["A"])


def test_history_translates_recent_minor_league_seasons():
    lines = _lines()
    minor = pd.DataFrame({"season": [2018, 2017], "mlbam_id": [7, 7], "player_name": ["P", "P"],
                          "age": [22, 21], "level": ["AA", "AAA"], "pa": [300.0, 100.0],
                          "off_runs": [6.0, 0.0]})
    mlb = lines[lines["level"] == "MLB"]
    other = lines[lines["level"] != "MLB"].assign(player_name="x", age=25)
    h = milb.milb_history(pd.concat([other, minor]), mlb, [2019])
    row = h[h["mlbam_id"] == 7].iloc[0]
    assert row["y1_milb_pa"] == 300.0 and row["y2_milb_pa"] == 100.0
    assert row["y1_milb_runs"] == pytest.approx(6.0 - 0.04 * milb.DROP_SCALE * 300.0)
    assert row["y2_milb_runs"] == pytest.approx(0.0 - 0.02 * milb.DROP_SCALE * 100.0)
    assert row["milb_age"] == 23                                       # 22 + 1 = 21 + 2


def test_rookie_rows_only_for_players_missing_from_the_frame():
    frame = pd.DataFrame({"season": [2019], "mlbam_id": [1], "y1_pa": [300.0],
                          "y1_team_games": [162.0], "y1_off_runs": [3.0]})
    history = pd.DataFrame({"season": [2019, 2019, 2019], "mlbam_id": [1, 2, 3],
                            "y1_milb_pa": [200.0, 400.0, 50.0], "y2_milb_pa": 0.0,
                            "y3_milb_pa": 0.0, "milb_age": [24, 22, 21],
                            "milb_name": ["a", "b", "c"]})
    targets = pd.DataFrame({"season": [2019], "mlbam_id": [2], "target_pa": [120.0],
                            "target_off_runs": [1.0], "target_off_runs_neutral": [1.0]})
    rows = milb.rookie_rows(frame, history, targets, upcoming=set())
    assert list(rows["mlbam_id"]) == [2]                   # 1 has MLB history, 3 too few PA
    assert rows.iloc[0]["y1_pa"] == 0.0 and rows.iloc[0]["target_pa"] == 120.0


def test_minor_league_history_joins_marcels_weighted_rate():
    league = pd.DataFrame({"season": [2018], "runs_per_win": [10.0],
                           "batting_replacement_runs_per_pa": [0.03],
                           "pitching_replacement_runs_per_ip": [0.1],
                           "sp_replacement_runs_per_ip": [0.12],
                           "rp_replacement_runs_per_ip": [0.05], "runs_per_pa": [0.12],
                           "era": [4.0]})
    row = {"season": 2019, "mlbam_id": 1, "player_name": "A", "age": 25, "last_team_id": 1,
           "is_pitcher": False}
    for k in (1, 2, 3):
        row |= {f"y{k}_team_games": 162.0, f"y{k}_pa": 0.0, f"y{k}_off_runs": None,
                f"y{k}_baserunning_runs": None, f"y{k}_positional_runs": None,
                f"y{k}_milb_pa": 0.0, f"y{k}_milb_runs": 0.0}
    row |= {"y1_milb_pa": 400.0, "y1_milb_runs": 8.0}
    f = pd.DataFrame([row])
    out = marcel.project_batters(f, league, milb_weight=0.5).iloc[0]
    rate = 5 * 0.5 * 8.0 / (5 * 0.5 * 400.0 + marcel.REG_PA)
    assert out["off_runs"] == pytest.approx(rate * out["pa"])
    assert not out["has_position"]
    assert marcel.project_batters(f, league).iloc[0]["off_runs"] == 0.0     # weight 0: ignored


# ---- pitchers ----------------------------------------------------------------------------
def test_pitcher_history_carries_extra_counts_and_uses_its_own_drop_scale():
    lines = _lines().rename(columns={"pa": "bf", "off_runs": "pitching_runs"})
    mlb = lines[lines["level"] == "MLB"]
    other = lines[lines["level"] != "MLB"].assign(player_name="x", age=25, outs=0, gs=0, games=0)
    me = pd.DataFrame({"season": [2018], "mlbam_id": [7], "player_name": ["P"], "age": [22],
                       "level": ["AAA"], "bf": [400.0], "pitching_runs": [4.0], "outs": [300],
                       "gs": [18], "games": [20]})
    h = milb.milb_history(pd.concat([other, me]), mlb, [2019], volume="bf",
                          runs="pitching_runs", extra=("outs", "gs", "games"), drop_scale=0.25)
    row = h[h["mlbam_id"] == 7].iloc[0]
    assert (row["y1_milb_bf"], row["y1_milb_outs"], row["y1_milb_gs"]) == (400.0, 300.0, 18.0)
    assert row["y1_milb_runs"] == pytest.approx(4.0 - 0.02 * 0.25 * 400.0)


def test_pitcher_rookie_rows_zero_their_mlb_counts_and_are_marked():
    frame = pd.DataFrame({"season": [2019], "mlbam_id": [1], "y1_outs": [300.0], "y1_bf": [400.0],
                          "y1_role": ["SP"], "y1_team_games": [162.0]})
    history = pd.DataFrame({"season": [2019], "mlbam_id": [2], "y1_milb_bf": [500.0],
                            "y2_milb_bf": 0.0, "y3_milb_bf": 0.0, "milb_age": [23],
                            "milb_name": ["b"]})
    targets = pd.DataFrame({"season": [2019], "mlbam_id": [2], "target_outs": [90.0]})
    rows = milb.rookie_rows(frame, history, targets, upcoming=set(), volume="bf",
                            min_volume=100.0, pitchers=True)
    r = rows.iloc[0]
    assert (r["y1_outs"], r["y1_bf"], r["target_outs"]) == (0.0, 0.0, 90.0)
    assert pd.isna(r["y1_role"]) and r["milb_rookie"] and "is_pitcher" not in rows


def test_minor_league_history_joins_a_pitchers_rate_and_role():
    league = pd.DataFrame({"season": [2018], "runs_per_win": [10.0],
                           "batting_replacement_runs_per_pa": [0.03],
                           "pitching_replacement_runs_per_ip": [0.1],
                           "sp_replacement_runs_per_ip": [0.12],
                           "rp_replacement_runs_per_ip": [0.05], "runs_per_pa": [0.12],
                           "era": [4.0]})
    row = {"season": 2019, "mlbam_id": 1, "player_name": "A", "age": 24, "last_team_id": 1}
    for k in (1, 2, 3):
        row |= {f"y{k}_team_games": 162.0, f"y{k}_bf": 0.0, f"y{k}_outs": 0.0, f"y{k}_gs": 0.0,
                f"y{k}_games": 0.0, f"y{k}_pitching_runs": None, f"y{k}_milb_bf": 0.0,
                f"y{k}_milb_runs": 0.0, f"y{k}_milb_outs": 0.0, f"y{k}_milb_gs": 0.0,
                f"y{k}_milb_games": 0.0}
    row |= {"y1_milb_bf": 600.0, "y1_milb_runs": 6.0, "y1_milb_outs": 420.0, "y1_milb_gs": 25.0,
            "y1_milb_games": 26.0}
    out = marcel.project_pitchers(pd.DataFrame([row]), league, milb_weight=0.5).iloc[0]
    rate = 3 * 0.5 * 6.0 / (3 * 0.5 * 600.0 + marcel.REG_BF)
    assert out["runs"] / out["bf"] == pytest.approx(rate)
    assert out["runs_per_ip"] == pytest.approx(rate * 600.0 / 140.0)     # his BF per inning
    assert out["role"] == "SP" and out["start_share"] == pytest.approx(25 / 26)
