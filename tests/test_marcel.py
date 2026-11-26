"""Marcel projections: weighting, regression, playing time and value, from prior seasons only."""

import pandas as pd
import pytest

from bucco.models import marcel

LEAGUE = pd.DataFrame({
    "season": [2022, 2023, 2024],
    "runs_per_win": [9.5, 10.0, 99.0],              # 2024 must never be used for a 2024 target
    "batting_replacement_runs_per_pa": [0.03, 0.02, 9.0],
    "pitching_replacement_runs_per_ip": [0.10, 0.12, 9.0],
    "sp_replacement_runs_per_ip": [0.14, 0.16, 9.0],
    "rp_replacement_runs_per_ip": [0.04, 0.05, 9.0],
    "runs_per_pa": [0.12, 0.12, 9.0],
    "era": [4.0, 4.2, 99.0],
})


def _batter(**over):
    row = {"season": 2024, "mlbam_id": 1, "player_name": "A", "age": 28, "last_team_id": 134,
           "is_pitcher": False}
    for k in (1, 2, 3):
        row |= {f"y{k}_team_games": 162.0, f"y{k}_pa": 0, f"y{k}_off_runs": None,
                f"y{k}_baserunning_runs": None, f"y{k}_positional_runs": None}
    row |= over
    return pd.DataFrame([row])


def test_one_season_batter_is_regressed_and_valued_with_last_seasons_constants():
    out = marcel.project_batters(_batter(y1_pa=600, y1_off_runs=30.0, y1_baserunning_runs=3.0,
                                         y1_positional_runs=-6.0), LEAGUE).iloc[0]
    rate = 5 * 30.0 / (5 * 600 + marcel.REG_PA)
    pa = 0.5 * 600 + marcel.PA_BASE
    assert out["pa"] == pytest.approx(pa)
    assert out["off_runs"] == pytest.approx(rate * pa)
    assert out["def_runs"] == pytest.approx(-6.0 / 600 * pa)      # positional: not regressed
    assert out["war"] == pytest.approx((rate * pa - 6.0 / 600 * pa + 0.02 * pa) / 10.0)
    bsr_rate = 5 * 3.0 / (5 * 600 + marcel.REG_PA)
    assert out["wrc_plus"] == pytest.approx(100 * (1 + (rate - bsr_rate) / 0.12))


def test_recent_seasons_weigh_more():
    hot_last = marcel.project_batters(_batter(y1_pa=500, y1_off_runs=20.0, y3_pa=500,
                                              y3_off_runs=-20.0), LEAGUE).iloc[0]
    hot_first = marcel.project_batters(_batter(y1_pa=500, y1_off_runs=-20.0, y3_pa=500,
                                               y3_off_runs=20.0), LEAGUE).iloc[0]
    assert hot_last["off_runs"] > 0 > hot_first["off_runs"]


def test_shortened_season_playing_time_is_scaled_to_162_games():
    out = marcel.project_batters(_batter(y1_pa=200, y1_off_runs=0.0, y1_team_games=60.0),
                                 LEAGUE).iloc[0]
    assert out["pa"] == pytest.approx(0.5 * 200 * 162 / 60 + marcel.PA_BASE)


def test_pitchers_batting_is_dropped():
    assert marcel.project_batters(_batter(is_pitcher=True, y1_pa=50), LEAGUE).empty


def _pitcher(**over):
    row = {"season": 2024, "mlbam_id": 2, "player_name": "P", "age": 30, "last_team_id": 134}
    for k in (1, 2, 3):
        row |= {f"y{k}_team_games": 162.0, f"y{k}_bf": 0, f"y{k}_outs": 0, f"y{k}_gs": 0,
                f"y{k}_games": 0, f"y{k}_pitching_runs": None}
    row |= over
    return pd.DataFrame([row])


def test_starter_and_reliever_playing_time_and_value():
    sp = marcel.project_pitchers(_pitcher(y1_bf=800, y1_outs=570, y1_gs=32, y1_games=32,
                                          y1_pitching_runs=15.0), LEAGUE).iloc[0]
    assert sp["ip"] == pytest.approx(0.5 * 190 + marcel.SP_IP_BASE)
    assert sp["gs"] == pytest.approx(32 / 190 * sp["ip"])
    runs_per_bf = 3 * 15.0 / (3 * 800 + marcel.REG_BF)
    assert sp["runs"] == pytest.approx(runs_per_bf * 800 / 190 * sp["ip"])
    assert sp["war"] == pytest.approx((sp["runs"] + 0.16 * sp["ip"]) / 10.0)   # starter level
    assert sp["role"] == "SP" and sp["fip"] == pytest.approx(4.2 - 9 * sp["runs"] / sp["ip"])
    rp = marcel.project_pitchers(_pitcher(y1_bf=260, y1_outs=180, y1_gs=0, y1_games=60,
                                          y1_pitching_runs=0.0), LEAGUE).iloc[0]
    assert rp["ip"] == pytest.approx(0.5 * 60 + marcel.RP_IP_BASE) and rp["gs"] == 0
    assert rp["war"] == pytest.approx((rp["runs"] + 0.05 * rp["ip"]) / 10.0)   # reliever level


def _by_part(**parts):
    """A one-season starter whose 15 pitching runs are split by part."""
    row = {"y1_bf": 800, "y1_outs": 570, "y1_gs": 32, "y1_games": 32, "y1_pitching_runs": 15.0}
    for part in marcel.COMPONENTS:
        for k in (1, 2, 3):
            row[f"y{k}_{part}_runs"] = parts.get(part, 0.0) if k == 1 else None
    return _pitcher(**row)


def test_parts_at_one_weight_equal_the_one_number_projection():
    frame = _by_part(k=12.0, bb=-2.0, hr=4.0, other=1.0)
    one = marcel.project_pitchers(frame, LEAGUE).iloc[0]
    parts = marcel.project_pitchers(frame, LEAGUE, components=dict.fromkeys(
        marcel.COMPONENTS, marcel.REG_BF)).iloc[0]
    assert parts["runs"] == pytest.approx(one["runs"])


def test_each_part_is_regressed_by_its_own_weight():
    k_only = marcel.project_pitchers(_by_part(k=15.0), LEAGUE, components=dict(
        marcel.COMPONENT_REG_BF)).iloc[0]
    hr_only = marcel.project_pitchers(_by_part(hr=15.0), LEAGUE, components=dict(
        marcel.COMPONENT_REG_BF)).iloc[0]
    per_ip = 800 / 190 * 3 * 15.0
    assert k_only["runs_per_ip"] == pytest.approx(per_ip / (3 * 800 + marcel.COMPONENT_REG_BF["k"]))
    assert hr_only["runs_per_ip"] == pytest.approx(
        per_ip / (3 * 800 + marcel.COMPONENT_REG_BF["hr"]))
    assert k_only["runs"] > hr_only["runs"]          # strikeouts are believed sooner


def test_parts_refuse_the_replacement_prior():
    with pytest.raises(ValueError, match="components"):
        marcel.project_pitchers(_by_part(k=1.0), LEAGUE, prior="replacement",
                                components=dict(marcel.COMPONENT_REG_BF))


def _aging_history(change_per_year, seasons=range(2000, 2012), players=400, seed=1):
    """Players whose true rate changes by change_per_year(age) each season, plus noise."""
    import numpy as np
    rng = np.random.default_rng(seed)
    rows = []
    for pid in range(players):
        start_age = int(rng.integers(21, 34))
        rate = rng.normal(0, 0.02)
        for i, season in enumerate(seasons):
            age = start_age + i
            if i:
                rate += change_per_year(age)
            rows.append({"mlbam_id": pid, "season": season, "age": age, "pa": 500,
                         "off_runs": (rate + rng.normal(0, 0.005)) * 500})
    return pd.DataFrame(rows)


def test_age_curve_recovers_a_known_peak():
    history = _aging_history(lambda age: 0.004 if age <= 27 else -0.004)
    curve = marcel.fit_age_curve(history, "off_runs", "pa", before=2012)
    peak = int(curve.loc[20:40].idxmax())
    assert 25 <= peak <= 29
    assert curve[34] - curve[30] == pytest.approx(-0.016, abs=0.006)


def test_age_curve_never_sees_the_target_season_or_later():
    history = _aging_history(lambda age: 0.0)
    wild = history.copy()
    wild.loc[wild["season"] >= 2008, "off_runs"] *= 50       # garbage from 2008 on
    assert marcel.fit_age_curve(history, "off_runs", "pa", before=2008).equals(
        marcel.fit_age_curve(wild, "off_runs", "pa", before=2008))


def test_aging_moves_each_past_season_to_the_target_age():
    curve = pd.Series([0.001 * (30 - a) if a > 30 else 0.0 for a in marcel.CURVE_AGES],
                      index=list(marcel.CURVE_AGES))      # -0.001 per year after 30
    row = _batter(age=34, y1_pa=600, y1_off_runs=0.0, y3_pa=600, y3_off_runs=0.0)
    aged = marcel.project_batters(row, LEAGUE, curves={2024: curve}).iloc[0]
    flat = marcel.project_batters(row, LEAGUE).iloc[0]
    # y1 at 33 -> 34: -0.001; y3 at 31 -> 34: -0.003
    expected = (5 * 600 * -0.001 + 3 * 600 * -0.003) / (5 * 600 + 3 * 600 + marcel.REG_PA)
    assert flat["off_runs"] == 0.0
    assert aged["off_runs"] / aged["pa"] == pytest.approx(expected)


def _shrink_frame(seed=4):
    """Batters over 2001-2012: players with little history are truly worse (-0.03 runs/PA),
    regulars average. Last season's line is the truth plus noise."""
    import numpy as np
    rng = np.random.default_rng(seed)
    rows = []
    for season in range(2001, 2013):
        for i in range(300):
            regular = i % 2 == 0
            truth = 0.0 if regular else -0.03
            pa1 = 600 if regular else 60
            row = _batter(season=season, mlbam_id=season * 1000 + i, y1_pa=pa1,
                          y1_off_runs=(truth + rng.normal(0, 0.02)) * pa1).iloc[0].to_dict()
            row |= {"target_pa": 400, "target_off_runs": (truth + rng.normal(0, 0.01)) * 400}
            rows.append(row)
    return pd.DataFrame(rows)


SHRINK_LEAGUE = pd.DataFrame({
    "season": range(2000, 2013), "runs_per_win": 10.0, "batting_replacement_runs_per_pa": 0.03,
    "pitching_replacement_runs_per_ip": 0.1, "sp_replacement_runs_per_ip": 0.13,
    "rp_replacement_runs_per_ip": 0.03, "runs_per_pa": 0.12, "era": 4.0,
    "is_shortened_season": False})


def test_fitted_prior_shrinks_thin_histories_toward_what_such_players_did():
    frame = _shrink_frame()
    rate = {p: marcel.project_batters(frame, SHRINK_LEAGUE, prior=p)
            .assign(thin=frame["y1_pa"] < 100).query("season == 2012")
            .groupby("thin").apply(lambda d: (d["off_runs"] / d["pa"]).mean())
            for p in ("league", "fitted", "replacement")}
    assert rate["league"][True] > -0.01                     # league prior flatters them
    assert rate["fitted"][True] == pytest.approx(-0.03, abs=0.006)
    assert rate["fitted"][False] == pytest.approx(0.0, abs=0.006)
    assert rate["replacement"][False] < rate["fitted"][False] - 0.004   # pulls regulars down too


def test_fitted_prior_never_sees_the_target_season():
    frame = _shrink_frame()
    wild = frame.copy()
    wild.loc[wild["season"] == 2012, "target_off_runs"] = 1e6
    a = marcel.project_batters(frame, SHRINK_LEAGUE, prior="fitted").query("season == 2012")
    b = marcel.project_batters(wild, SHRINK_LEAGUE, prior="fitted").query("season == 2012")
    assert list(a["off_runs"]) == pytest.approx(list(b["off_runs"]))


def test_unknown_prior_is_refused():
    with pytest.raises(ValueError, match="prior"):
        marcel.project_batters(_batter(y1_pa=100, y1_off_runs=0.0), LEAGUE, prior="vibes")


def _fit_setup():
    league = pd.DataFrame({"season": [2026], "woba_scale": [1.2], "runs_per_win": [10.0],
                           "w_single": [0.9], "w_double": [1.25], "w_triple": [1.6],
                           "w_hr": [2.0], "w_ubb": [0.7], "w_hbp": [0.72]})
    profiles = pd.DataFrame({
        "season": 2027, "mlbam_id": [1, 2], "left_share": [0.0, 0.0],
        "rate_singles": [0.12, 0.17], "rate_doubles": [0.04, 0.06], "rate_triples": [0.0, 0.01],
        "rate_hr": [0.06, 0.01], "rate_ubb": [0.1, 0.07], "rate_hbp": [0.01, 0.01]})
    parks = pd.DataFrame({"season": 2027, "team_id": 147, "side": ["L", "R"],
                          "pf_singles": 1.0, "pf_doubles": 1.0, "pf_triples": 1.0,
                          "pf_hr": 1.2, "pf_ubb": 1.0, "pf_hbp": 1.0})
    rows = pd.DataFrame({"season": 2027, "mlbam_id": [1, 2], "team_id": 147, "pa": [600.0, 600.0],
                         "off_runs": [10.0, 0.0], "war": [3.0, 2.0]})
    return rows, profiles, parks, league


def test_a_power_hitter_gains_in_a_home_run_park_and_the_team_total_is_unchanged():
    rows, profiles, parks, league = _fit_setup()
    runs = marcel.park_runs_per_pa(rows, profiles, parks, league)
    assert runs.iloc[0] == pytest.approx(0.06 * 0.1 * 2.0 / 1.2)     # half the 20%, run value
    out = marcel.apply_park_fit(rows, runs, league)
    assert out["park_fit"].iloc[0] > 0 > out["park_fit"].iloc[1]
    assert out["off_runs"].sum() == pytest.approx(rows["off_runs"].sum())
    assert out["war"].iloc[0] - 3.0 == pytest.approx((out["off_runs"].iloc[0] - 10.0) / 10.0)


def test_a_team_without_park_factors_is_neutral():
    rows, profiles, parks, league = _fit_setup()
    runs = marcel.park_runs_per_pa(rows.assign(team_id=999), profiles, parks, league)
    assert list(runs) == [0.0, 0.0]


def _projected(**over):
    row = {"season": 2024, "mlbam_id": 1, "pa": 600.0, "def_runs": -6.0, "fld_runs": 0.0,
           "war": 2.0}
    return pd.DataFrame([row | over])


def test_external_def_replaces_the_positional_rate_and_counts_the_rest_as_fielding():
    rates = pd.DataFrame({"season": [2024], "mlbam_id": [1], "def_rate": [4.0 / 600]})
    out = marcel.apply_external_def(_projected(), rates, LEAGUE).iloc[0]
    assert out["def_runs"] == pytest.approx(4.0)
    assert out["fld_runs"] == pytest.approx(10.0)
    assert out["war"] == pytest.approx(2.0 + 10.0 / 10.0)    # runs per win of the season before


def test_a_batter_without_an_external_def_keeps_his_own():
    rates = pd.DataFrame({"season": [2023], "mlbam_id": [1], "def_rate": [0.05]})  # wrong season
    out = marcel.apply_external_def(_projected(), rates, LEAGUE).iloc[0]
    assert (out["def_runs"], out["fld_runs"], out["war"]) == (-6.0, 0.0, 2.0)
