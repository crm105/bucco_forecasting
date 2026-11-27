"""Learned player models: swapping predictions into projections, walk-forward fitting."""

import numpy as np
import pandas as pd
import pytest

from bucco.models.ml import core
from bucco.models.ml import hitters as mlh
from bucco.models.ml import pitchers as mlp


def _pitchers():
    return pd.DataFrame({"season": [2024, 2024], "mlbam_id": [1, 2], "ip": [100.0, 50.0],
                         "gs": [20.0, 0.0], "runs_per_ip": [0.1, 0.0], "runs": [10.0, 0.0],
                         "start_share": [1.0, 0.0], "sp_rep_per_ip": [0.14, 0.14],
                         "rp_rep_per_ip": [0.04, 0.04], "runs_per_win": [10.0, 10.0],
                         "war": [2.4, 0.2], "fip": [3.5, 4.2]})


def test_apply_swaps_innings_and_rate_and_keeps_the_rest():
    preds = pd.DataFrame({"season": [2024], "mlbam_id": [1], "ml_ip": [150.0], "ml_runs9": [1.8]})
    out = mlp.apply(_pitchers(), preds).set_index("mlbam_id")
    assert out.loc[1, "ip"] == 150.0 and out.loc[1, "gs"] == pytest.approx(30.0)
    assert out.loc[1, "runs_per_ip"] == pytest.approx(0.2)
    assert out.loc[1, "war"] == pytest.approx((0.2 * 150 + 0.14 * 150) / 10)
    assert out.loc[1, "fip"] == pytest.approx(3.5 - 0.9)
    assert out.loc[2, "ip"] == 50.0 and out.loc[2, "war"] == pytest.approx(0.2)   # no prediction


def test_walk_forward_never_sees_the_target_season():
    rng = np.random.default_rng(0)
    rows = []
    for season in range(2010, 2020):
        x = rng.normal(size=300)
        y = 2 * x + (100 if season == 2019 else 0)          # the target season is different
        rows.append(pd.DataFrame({"season": season, "mlbam_id": range(300), "x": x, "y": y,
                                  "vol": 1.0}))
    df = pd.concat(rows, ignore_index=True)
    out = core.walk_forward(df, df, ["x"], [2019], centered=False)
    assert out["pred"].abs().mean() < 10         # learned 2 * x, not the 2019 shift


def test_opening_day_flags_minor_leaguers_off_the_40_man():
    status = pd.DataFrame({"season": [2023, 2024, 2024], "mlbam_id": [1, 1, 2],
                           "il_group": ["active", "il_60", "active"]})
    rows = pd.DataFrame({"season": [2024, 2024, 2024], "mlbam_id": [1, 2, 3]})
    out = core.opening_day(rows, status).set_index("mlbam_id")
    assert out["on_40"].tolist() == [1.0, 1.0, 0.0]          # 3: organization depth only
    assert out.loc[1, "od_il_60"] == 1.0 and out.loc[1, "prev_on_40"] == 1.0
    assert out.loc[3, ["od_il_60", "od_il_short", "prev_on_40"]].tolist() == [0.0, 0.0, 0.0]


def test_predictions_are_kept_per_roster_source():
    assert mlp.PREDICTIONS["mlb"] != mlp.PREDICTIONS["mlb_org"]
    with pytest.raises(ValueError):
        mlp.fit_and_save(roster_source="steamer")


def test_hitter_pa_scales_offense_defense_and_war_and_keeps_unpredicted_rows():
    b = pd.DataFrame({"season": [2024, 2024], "mlbam_id": [1, 2], "pa": [600.0, 300.0],
                      "off_runs": [12.0, -3.0], "def_runs": [3.0, 1.0], "bsr": [1.0, 0.0],
                      "war": [3.0, 0.5]})
    preds = pd.DataFrame({"season": [2024], "mlbam_id": [1], "ml_pa": [450.0]})
    out = mlh.apply(b, preds).set_index("mlbam_id")
    assert out.loc[1, "pa"] == 450.0
    assert out.loc[1, ["off_runs", "def_runs", "bsr", "war"]].tolist() == \
        pytest.approx([9.0, 2.25, 0.75, 2.25])                 # rates unchanged
    assert out.loc[2, ["pa", "off_runs", "def_runs", "bsr", "war"]].tolist() == [300.0, -3.0, 1.0, 0.0, 0.5]


def test_score_compares_model_and_baseline_on_completed_seasons():
    rows = pd.DataFrame({"season": [2024, 2024, 2025, 2020], "mlbam_id": [1, 2, 1, 1],
                         "y": [100.0, 0.0, np.nan, 50.0], "vol": 1.0,
                         "base": [80.0, 20.0, 90.0, 0.0]})
    pred = rows[["season", "mlbam_id"]].assign(pred=[100.0, 0.0, 500.0, 0.0])
    s = core.score(pred, rows, centered=False, baseline="base")
    assert list(s.index) == ["all", 2024]                       # 2025 unknown, 2020 left out
    assert s.loc["all", "model"] == 0.0 and s.loc["all", "baseline"] == pytest.approx(20.0)


def test_hitter_roster_context_ranks_teammates_at_his_position():
    rows = pd.DataFrame({"season": 2024, "team_id": [1, 1, 1, 1], "mlbam_id": [1, 2, 3, 4],
                         "pipe": [600.0, 300.0, 400.0, 100.0],
                         "marcel_war600": [4.0, 1.0, 2.0, 0.5]})
    positions = pd.DataFrame({"season": 2024, "mlbam_id": [1, 2, 3, 3],
                              "position": ["SS", "SS", "C", "1B"], "games": [150, 40, 90, 20]})
    out = mlh.roster_context(rows, positions).set_index("mlbam_id")
    assert out["ctx_rank_team"].tolist() == [1.0, 3.0, 2.0, 4.0]
    assert out.loc[1, "ctx_rank_pos"] == 1.0 and out.loc[2, "ctx_rank_pos"] == 2.0
    assert out.loc[1, "ctx_gap_pos"] == pytest.approx(3.0)       # 4.0 against the next SS
    assert out.loc[2, "ctx_gap_pos"] == pytest.approx(-3.0)
    assert np.isnan(out.loc[3, "ctx_gap_pos"]) and out.loc[3, "ctx_is_c"] == 1.0   # sole catcher
    assert out.loc[4, "ctx_no_pos"] == 1.0 and np.isnan(out.loc[4, "ctx_rank_pos"])
    assert out["ctx_pipe_share"].sum() == pytest.approx(1.0)


def test_pitcher_roster_context_ranks_the_rotation_and_the_fifth_starter_gap():
    war = [5.0, 4.0, 3.0, 2.0, 1.0, 0.5, 2.5]
    rows = pd.DataFrame({"season": 2024, "team_id": 1, "mlbam_id": range(7),
                         "pipe": [180.0, 170, 160, 150, 140, 100, 60],
                         "start_share": [1.0] * 6 + [0.0], "marcel_war180": war})
    out = mlp.roster_context(rows).set_index("mlbam_id")
    assert out.loc[0, "ctx_rot_rank"] == 1.0 and out.loc[5, "ctx_rot_rank"] == 6.0
    assert out.loc[0, "ctx_gap5"] == pytest.approx(4.0)        # fifth starter: 1.0
    assert out.loc[5, "ctx_gap5"] == pytest.approx(-0.5)
    assert out.loc[6, "ctx_rp_rank"] == 1.0 and np.isnan(out.loc[6, "ctx_rot_rank"])
    assert out.loc[0, "ctx_n_sp"] == 6 and out.loc[0, "ctx_rot_ip"] == pytest.approx(900.0)


def test_learned_offense_replaces_marcels_rate_and_moves_war():
    b = pd.DataFrame({"season": [2024, 2024], "mlbam_id": [1, 2], "pa": [600.0, 300.0],
                      "off_runs": [12.0, -3.0], "def_runs": [3.0, 1.0], "war": [3.0, 0.5]})
    preds = pd.DataFrame({"season": [2024], "mlbam_id": [1], "ml_pa": [450.0],
                          "ml_off600": [20.0]})
    out = mlh.apply(b, preds, runs_per_win=pd.Series({2024: 10.0})).set_index("mlbam_id")
    assert out.loc[1, "off_runs"] == pytest.approx(15.0)        # 20 per 600 at 450 PA
    assert out.loc[1, "war"] == pytest.approx(2.25 + (15.0 - 9.0) / 10.0)
    assert out.loc[2, ["off_runs", "war"]].tolist() == [-3.0, 0.5]
