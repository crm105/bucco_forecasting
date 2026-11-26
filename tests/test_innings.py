"""Baseline innings and the staff optimizer."""

import numpy as np
import pandas as pd
import pytest

from bucco.models import innings
from bucco.models import staff_optimizer as so


def _frame(n_per_season=300, seasons=(2015, 2016, 2017), seed=0, target=None):
    """Pitcher frame rows whose next-season innings are 20 + 0.6 x last season's."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for i in range(n_per_season):
            ip1 = float(rng.uniform(0, 200))
            row = {"season": s, "mlbam_id": i, "age": float(rng.integers(22, 36)),
                   "target_outs": 3 * (20 + 0.6 * ip1) if target is None else target}
            for k in (1, 2, 3):
                row |= {f"y{k}_team_games": 162.0, f"y{k}_outs": 3 * ip1 if k == 1 else 0.0,
                        f"y{k}_gs": 30.0 if ip1 > 100 else 0.0, f"y{k}_games": 30.0}
            rows.append(row)
    return pd.DataFrame(rows)


def test_baseline_recovers_a_known_line_and_has_no_fit_for_the_first_season():
    f = _frame()
    base = innings.baseline_ip(f, pd.Series(True, index=f.index))
    assert base[f["season"] == 2015].isna().all()          # nothing earlier to learn from
    later = f["season"] == 2017
    expected = 20 + 0.6 * f.loc[later, "y1_outs"] / 3
    assert base[later].to_numpy() == pytest.approx(expected.to_numpy(), abs=1e-6)


def test_baseline_never_sees_the_target_season():
    f = _frame()
    changed = f.copy()
    changed.loc[changed["season"] == 2017, "target_outs"] = 0.0
    keep = pd.Series(True, index=f.index)
    a, b = innings.baseline_ip(f, keep), innings.baseline_ip(changed, keep)
    assert a[f["season"] == 2017].to_numpy() == pytest.approx(b[f["season"] == 2017].to_numpy())


def _staff(over=None):
    rows = [{"mlbam_id": i, "player_name": f"P{i}", "rate": 0.05, "base_ip": 150.0, "age": 27.0,
             "starter": True} for i in range(5)]
    rows += [{"mlbam_id": 10 + i, "player_name": f"R{i}", "rate": 0.05, "base_ip": 60.0,
              "age": 27.0, "starter": False} for i in range(8)]
    p = pd.DataFrame(rows)
    for (i, col), v in (over or {}).items():
        p.loc[p["mlbam_id"] == i, col] = v
    return p


def test_pools_are_filled_exactly_and_relievers_never_start():
    alloc = so.optimize_staff(_staff(), rep_sp=0.13, rep_rp=0.05, runs_per_win=10.0)
    assert alloc.loc[alloc["pool"] == "SP", "ip"].sum() == pytest.approx(so.ROTATION_IP)
    assert alloc.loc[alloc["pool"] == "RP", "ip"].sum() == pytest.approx(so.BULLPEN_IP)
    starters = alloc[(alloc["pool"] == "SP") & (alloc["mlbam_id"] >= 0)]
    assert (starters["mlbam_id"] < 10).all()


def test_younger_arms_are_pushed_further_past_their_baseline():
    p = _staff({(0, "age"): 23.0, (1, "age"): 34.0})
    alloc = so.optimize_staff(p, rep_sp=0.13, rep_rp=0.05, runs_per_win=10.0)
    ip = alloc[alloc["mlbam_id"] >= 0].groupby("mlbam_id")["ip"].sum()
    assert ip[0] > ip[1] >= 150.0 - so.SEGMENT_IP


def test_proportional_fatigue_keeps_an_ace_off_the_innings_cap():
    p = _staff({(0, "rate"): 0.25})                       # an ace among average starters
    kw = {"rep_sp": 0.13, "rep_rp": 0.05, "runs_per_win": 10.0}
    flat = so.optimize_staff(p, proportional=False, **kw)
    prop = so.optimize_staff(p, proportional=True, **kw)
    def ace(a):
        return a.loc[a["mlbam_id"] == 0, "ip"].sum()
    assert ace(flat) == pytest.approx(so.MAX_SP_IP)
    assert 150.0 < ace(prop) < so.MAX_SP_IP


def test_war_is_runs_above_replacement_at_the_fatigued_rate():
    alloc = so.optimize_staff(_staff(), rep_sp=0.13, rep_rp=0.05, runs_per_win=10.0)
    row = alloc[(alloc["mlbam_id"] == 0)].iloc[0]
    rate = so.pitching_rate(0.05, 150.0, row["ip"], float(so.fatigue_c(27.0))
                            * (0.05 + 0.13) / so.REFERENCE_VALUE)
    assert row["war"] == pytest.approx(row["ip"] * (rate + 0.13) / 10.0)


def test_a_swingman_can_start_but_a_pure_reliever_cannot():
    p = _staff().assign(team_id=1, sp_rep_per_ip=0.13, rp_rep_per_ip=0.05, runs_per_win=10.0)
    p["start_share"] = np.where(p["mlbam_id"] < 10, 1.0, 0.0)
    p.loc[p["mlbam_id"] == 10, ["start_share", "rate"]] = [0.3, 0.2]    # a good swingman
    p.loc[p["mlbam_id"] == 11, "rate"] = 0.3                            # a better pure reliever
    alloc = so.optimize_staffs(p)
    rotation = alloc[(alloc["pool"] == "SP") & (alloc["mlbam_id"] >= 0)]
    assert 10 in set(rotation["mlbam_id"]) and 11 not in set(rotation["mlbam_id"])
    only_starters = so.optimize_staffs(p, min_start_share=0.5)
    assert 10 not in set(only_starters.loc[only_starters["pool"] == "SP", "mlbam_id"])


def test_a_reliever_pays_the_start_penalty_and_a_starter_gains_it_in_relief():
    p = _staff().assign(start_share=lambda d: np.where(d["mlbam_id"] < 10, 1.0, 0.0))
    kw = {"rep_sp": 0.13, "rep_rp": 0.05, "runs_per_win": 10.0}
    plain = so.optimize_staff(p, start_penalty=0.0, **kw)
    pen = so.optimize_staff(p, start_penalty=0.03, **kw)
    # every rotation inning here is thrown by a pure starter: no change in the rotation
    assert pen.loc[pen["pool"] == "SP", "war"].sum() == \
        pytest.approx(plain.loc[plain["pool"] == "SP", "war"].sum())
    swing = p.assign(start_share=lambda d: np.where(d["mlbam_id"] == 0, 0.0, d["start_share"]))
    a = so.optimize_staff(swing, start_penalty=0.03, **kw)
    b = so.optimize_staff(swing, start_penalty=0.0, **kw)
    mine = a[a["mlbam_id"] == 0]
    row = mine[mine["pool"] == "SP"].iloc[0]
    c = float(so.fatigue_c(27.0)) * (0.05 + 0.13) / so.REFERENCE_VALUE
    rate = so.pitching_rate(0.05, 150.0, mine["ip"].sum(), c)
    assert row["war"] == pytest.approx(row["ip"] * (rate + 0.13 - 0.03) / 10.0)   # full penalty
    assert row["ip"] < b.loc[(b["mlbam_id"] == 0) & (b["pool"] == "SP"), "ip"].sum()


def test_start_penalty_recovers_a_known_effect():
    rng = np.random.default_rng(1)
    rows = []
    for pid in range(400):
        skill = rng.normal(0, 0.01)
        for s in (2015, 2016, 2017):
            share = float(rng.uniform(0, 1))
            rows.append({"season": s, "mlbam_id": pid, "age": 27, "games": 30,
                         "gs": share * 30, "bf": 430.0, "outs": 300.0,
                         "runs": (skill - 0.007 * share) * 430.0})
    h = pd.DataFrame(rows)
    assert innings.fit_start_penalty(h, "runs", 2018) == pytest.approx(0.007 * 4.3, rel=1e-6)
    assert innings.fit_start_penalty(h, "runs", 2016) == 0.0      # no pairs before 2016


def test_rookies_get_their_own_innings_line():
    f = _frame()
    f["milb_rookie"] = False
    rook = f.copy()
    rook["mlbam_id"] += 10_000
    rook["milb_rookie"] = True
    rook["y1_outs"] = 0.0
    rook["m1_aaa_sp"] = np.tile(np.linspace(0, 150, 300), 3)
    rook["target_outs"] = 3 * (2 + 0.2 * rook["m1_aaa_sp"])   # 2 IP + 0.2 per Triple-A start IP
    both = pd.concat([f, rook], ignore_index=True)
    base = innings.baseline_ip(both, pd.Series(True, index=both.index))
    later = (both["season"] == 2017) & both["milb_rookie"]
    expected = 2 + 0.2 * both.loc[later, "m1_aaa_sp"]
    assert base[later].to_numpy() == pytest.approx(expected.to_numpy(), abs=1e-6)
    est = (both["season"] == 2017) & ~both["milb_rookie"]           # established line unchanged
    assert base[est].to_numpy() == pytest.approx(
        innings.baseline_ip(f, pd.Series(True, index=f.index))[f["season"] == 2017].to_numpy())


def test_pitcher_rate_is_kept_at_zero_innings():
    from bucco.models.depth_chart_model import pitcher_rate
    p = pd.DataFrame({"ip": [0.0, 100.0], "runs": [0.0, 5.0], "runs_per_ip": [0.08, 0.05]})
    assert list(pitcher_rate(p)) == [0.08, 0.05]
    assert list(pitcher_rate(p.drop(columns="runs_per_ip"))) == [0.0, 0.05]


def test_relief_innings_follow_the_role():
    p = _staff({(0, "rate"): -0.05, (0, "base_ip"): 200.0})      # a weak starter with a big workload
    p["start_share"] = np.where(p["starter"], 1.0, 0.0)
    alloc = so.optimize_staff(p, rep_sp=0.13, rep_rp=0.05, runs_per_win=10.0)
    relief = alloc[(alloc["pool"] == "RP") & (alloc["mlbam_id"] >= 0)].groupby("mlbam_id")["ip"].sum()
    starters = relief[relief.index < 10]
    assert (starters <= so.RELIEF_FLOOR_IP + 1e-6).all()            # pure starters: long relief only
    assert (relief <= so.MAX_RP_IP + so.RELIEF_FLOOR_IP + 1e-6).all()
