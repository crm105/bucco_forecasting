"""Injury simulation: availability draws and simulated team WAR."""

import numpy as np
import pandas as pd
import pytest

from bucco.models import injury_sim as sim
from bucco.models import lineup_optimizer as lo
from bucco.models import staff_optimizer as so


def _rows(seasons=(2015, 2016, 2017), n=150):
    rng = np.random.default_rng(0)
    rows = []
    for s in seasons:
        for g in sim.GROUPS:
            ratio = rng.uniform(0.2, 1.4, n)
            rows += [{"season": s, "group": g, "projected": 100.0, "actual": 100.0 * r}
                     for r in ratio]
    return pd.DataFrame(rows)


def test_availability_is_delivery_over_the_group_median_capped_at_one():
    rows = _rows()
    a = sim.fit_availability(rows, before=2017)
    sp = rows[(rows["season"] < 2017) & (rows["group"] == "sp")]
    ratio = sp["actual"] / sp["projected"]
    assert np.allclose(np.sort(a["sp"]), np.sort(np.minimum(1, ratio / ratio.median())))
    assert (a["sp"] <= 1).all() and (a["sp"] == 1).mean() == pytest.approx(0.5, abs=0.01)


def test_availability_never_sees_the_target_season_and_needs_enough_samples():
    rows = _rows()
    changed = rows.copy()
    changed.loc[changed["season"] == 2017, "actual"] = 0.0
    a, b = sim.fit_availability(rows, 2017), sim.fit_availability(changed, 2017)
    assert all(np.array_equal(a[g], b[g]) for g in a)
    assert sim.fit_availability(_rows(n=20), 2016) == {}


def test_established_players_by_group():
    bat = pd.DataFrame({"season": 2016, "mlbam_id": [1, 2, 3], "age": [25, 35, 25],
                        "pa": [500.0, 600.0, 100.0]})
    pit = pd.DataFrame({"season": 2016, "mlbam_id": [4, 5, 6], "ip": [150.0, 60.0, 60.0],
                        "start_share": [1.0, 0.0, 1.0]})
    act = pd.DataFrame({"season": [2016], "mlbam_id": [1], "actual": [450.0]})
    rows = sim.established_rows(bat, pit, act, act.iloc[0:0])
    assert sorted(rows["group"]) == ["bat_old", "bat_young", "rp", "sp"]   # 3 and 6 too small
    assert rows.loc[rows["group"] == "bat_young", "actual"].item() == 450.0
    assert rows.loc[rows["group"] == "sp", "actual"].item() == 0.0       # did not play


def _team():
    bat = pd.DataFrame([{"mlbam_id": i, "player_name": f"b{i}", "team_id": 1, "age": 27,
                         "proj_pa": 600.0, "o_rate": 0.0,
                         **{f"def_{q}": (0.0 if q == pos else np.nan) for q in lo.POSITIONS}}
                        for i, pos in enumerate(["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF",
                                                 "DH", "2B"])])
    pit = pd.DataFrame([{"mlbam_id": 100 + i, "player_name": f"p{i}", "team_id": 1, "age": 27,
                         "rate": 0.02, "base_ip": 170.0 if i < 5 else 60.0, "starter": i < 5,
                         "start_share": 1.0 if i < 5 else 0.0, "sp_rep_per_ip": 0.13,
                         "rp_rep_per_ip": 0.05, "runs_per_win": 10.0, "start_penalty": 0.03}
                        for i in range(12)])
    return bat, pit


def test_without_draws_the_simulation_is_the_plain_optimizers():
    bat, pit = _team()
    res = sim.simulate_season(bat, pit, {}, rep=0.03, rpw=10.0, n_sims=2, workers=1).iloc[0]
    assert res["bat"] == pytest.approx(lo.optimize_team(bat, 0.03, 10.0)["war"].sum())
    staff = so.optimize_staff(pit, 0.13, 0.05, 10.0, start_penalty=0.03)
    assert res["pit"] == pytest.approx(staff["war"].sum())
    assert res["sd"] == pytest.approx(0.0)


def test_draws_change_a_teams_value_and_are_repeatable():
    bat, pit = _team()
    draws = {g: np.array([0.2, 1.0, 1.0, 1.0]) for g in sim.GROUPS}
    a = sim.simulate_season(bat, pit, draws, rep=0.03, rpw=10.0, n_sims=5, seed=3, workers=1)
    b = sim.simulate_season(bat, pit, draws, rep=0.03, rpw=10.0, n_sims=5, seed=3, workers=1)
    assert a.equals(b) and a.iloc[0]["sd"] > 0
