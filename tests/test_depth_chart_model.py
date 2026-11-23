import logging
from datetime import date

import numpy as np
import pandas as pd
import pytest

from bucco.evaluate import backtest
from bucco.models.base import GAMES, LUCK_SD
from bucco.models.depth_chart_model import (
    THEORY_SLOPE,
    DepthChartModel,
    PlayerData,
)

POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def _players(season, team_id, strength, base_id):
    """A full roster for one team. `strength` scales every player's WAR."""
    bat, pit, games = [], [], []
    for i, pos in enumerate(POSITIONS):
        pid = base_id + i
        bat.append({"season": season, "team_id": team_id, "mlbam_id": pid,
                    "player_name": f"b{pid}", "pa": 650.0, "war": 2.0 * strength,
                    "def_runs": 0.0, "bsr": 0.0})
        if pos != "DH":
            games.append({"season": season, "mlbam_id": pid, "position": pos, "games": 150})
    for i in range(12):
        pid = base_id + 100 + i
        pit.append({"season": season, "team_id": team_id, "mlbam_id": pid,
                    "player_name": f"p{pid}", "ip": 180.0 if i < 5 else 60.0,
                    "war": (2.0 if i < 5 else 0.4) * strength, "gs": 30.0 if i < 5 else 0.0})
    return bat, pit, games


def _data(seasons=(2021, 2022, 2023), strengths=((1.5, 1), (0.5, 1000))):
    bat, pit, games = [], [], []
    for season in seasons:
        for team_id, (strength, base) in enumerate(strengths, start=1):
            b, p, g = _players(season, team_id, strength, base * 10 + season * 10_000)
            bat += b
            pit += p
            games += g
    return PlayerData(pd.DataFrame(bat), pd.DataFrame(pit), pd.DataFrame(games))


def _history(seasons=(2021, 2022), better=0.56, worse=0.44):
    return pd.DataFrame([{"season": s, "team_id": t, "win_pct": w, "games_played": 162}
                         for s in seasons for t, w in ((1, better), (2, worse))])


def _features(season):
    return pd.DataFrame({"season": season, "team_id": [1, 2]})


def test_the_stronger_roster_is_forecast_to_win_more():
    model = DepthChartModel(_data())
    model.fit(_history())
    out = model.predict(2023, date(2023, 3, 30), _features(2023)).set_index("team_id")
    assert out.loc[1, "mean_win_pct"] > 0.5 > out.loc[2, "mean_win_pct"]
    assert model.slope > 0 and model.n_train == 2


def test_forecast_is_centered_on_the_league_average():
    model = DepthChartModel(_data())
    model.fit(_history())
    out = model.predict(2023, date(2023, 3, 30), _features(2023))
    assert out["mean_win_pct"].mean() == pytest.approx(model.intercept)


def test_with_too_little_history_it_uses_one_win_per_war():
    model = DepthChartModel(_data())
    model.fit(_history(seasons=(2022,)))
    assert model.slope == pytest.approx(THEORY_SLOPE)
    assert model.sd == pytest.approx(LUCK_SD)
    empty = pd.DataFrame(columns=["season", "team_id", "win_pct", "games_played"])
    model.fit(empty)
    assert model.intercept == 0.5 and model.slope == pytest.approx(THEORY_SLOPE)


def test_a_shortened_season_is_left_out_of_the_fit():
    history = _history(seasons=(2021, 2022))
    history.loc[history["season"] == 2021, "games_played"] = 60
    model = DepthChartModel(_data())
    model.fit(history)
    assert model.n_train == 1 and model.slope == pytest.approx(THEORY_SLOPE)


def test_predicting_a_season_without_projections_is_an_error():
    model = DepthChartModel(_data(seasons=(2021, 2022)))
    model.fit(_history())
    with pytest.raises(ValueError, match="no ZiPS player projections for 2023"):
        model.predict(2023, date(2023, 3, 30), _features(2023))


def test_projections_dated_after_the_forecast_date_are_ignored(caplog):
    data = _data()
    data.batters["as_of_date"] = pd.Timestamp("2023-06-01")
    data.pitchers["as_of_date"] = pd.Timestamp("2023-06-01")
    data = PlayerData(data.batters, data.pitchers, data.positions)
    model = DepthChartModel(data)
    model.fit(_history())
    with caplog.at_level(logging.WARNING), \
            pytest.raises(ValueError, match="no ZiPS player projections"):
        model.predict(2023, date(2023, 3, 30), _features(2023))
    assert "dated after" in caplog.text


def test_predictions_cover_every_team_in_the_features():
    model = DepthChartModel(_data())
    model.fit(_history())
    feats = pd.DataFrame({"season": 2023, "team_id": [1, 2, 3]})   # team 3 has no roster
    out = model.predict(2023, date(2023, 3, 30), feats)
    assert list(out["team_id"]) == [1, 2, 3]
    assert out["mean_win_pct"].iloc[2] == pytest.approx(model.intercept)
    assert np.isfinite(out["sd_win_pct"]).all()


def test_supported_seasons_follow_the_projection_data():
    team_seasons = pd.DataFrame({"season": list(range(2019, 2025)) * 2, "team_id": [1] * 6 + [2] * 6})
    seasons = backtest.supported_seasons(lambda: DepthChartModel(_data()), team_seasons)
    assert seasons == [2021, 2022, 2023]
    assert backtest.supported_seasons(lambda: type("M", (), {})(), team_seasons) is None


def test_one_win_per_war_constant():
    assert THEORY_SLOPE * GAMES == pytest.approx(1.0)


def test_as_given_sums_projected_war_without_reallocating():
    data = _data()
    given = PlayerData(data.batters, data.pitchers, data.positions, source="Steamer",
                       playing_time="as_given")
    war = given.team_war(2023)
    # strength 1.5: 9 batters x 3.0 + 5 x 3.0 + 7 x 0.6 pitchers; strength 0.5 is a third of that
    assert war.loc[1] == pytest.approx(9 * 3.0 + 5 * 3.0 + 7 * 0.6)
    assert war.loc[2] == pytest.approx(war.loc[1] / 3)


def test_as_given_falls_back_to_the_depth_chart_for_a_raw_list(caplog):
    data = _data()
    raw = data.batters.copy()
    raw["pa"] = 2_000.0    # 9 x 2,000 = 18,000 PA per team: every player's own playing time
    given = PlayerData(raw, data.pitchers, data.positions, source="Steamer",
                       playing_time="as_given")
    chart = PlayerData(raw, data.pitchers, data.positions)
    with caplog.at_level(logging.INFO):
        bat_given = given.team_war(2023) - given.pitchers.groupby("team_id")["war"].sum()
    assert "raw list" in caplog.text
    assert bat_given.loc[1] != pytest.approx(raw.groupby("team_id")["war"].sum().loc[1])
    assert np.isfinite(chart.team_war(2023)).all()


def test_unknown_playing_time_mode_is_an_error():
    data = _data()
    with pytest.raises(ValueError, match="playing_time"):
        PlayerData(data.batters, data.pitchers, data.positions, playing_time="guess")


def test_model_name_and_source_appear_in_the_error():
    data = _data(seasons=(2021, 2022))
    given = PlayerData(data.batters, data.pitchers, data.positions, source="Steamer",
                       playing_time="as_given")
    model = DepthChartModel(given, name="steamer")
    model.fit(_history())
    with pytest.raises(ValueError, match="steamer: no Steamer player projections for 2023"):
        model.predict(2023, date(2023, 3, 30), _features(2023))


def test_optimized_mode_fills_every_position_and_ranks_the_stronger_roster_higher():
    data = _data()
    bat = data.batters.copy()
    bat["off_runs"] = bat["war"] * 10 - 20 * bat["pa"] / 600       # WAR back to batting runs
    bat["def_runs"] = 0.0
    bat["fld_runs"] = np.nan
    # natural positions from last season's games
    games = pd.concat([data.positions, data.positions.assign(season=data.positions["season"] + 1)])
    optimized = PlayerData(bat, data.pitchers, games, source="Steamer", playing_time="optimized")
    war = optimized.team_war(2023)
    assert war.loc[1] > war.loc[2]
    model = DepthChartModel(optimized, name="steamer_optimized")
    model.fit(_history())
    out = model.predict(2023, date(2023, 3, 30), _features(2023)).set_index("team_id")
    assert out.loc[1, "mean_win_pct"] > out.loc[2, "mean_win_pct"]
