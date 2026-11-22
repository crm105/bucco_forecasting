"""Checks for the baseline models, the backtest and the no-peeking rule."""

from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from bucco.evaluate import metrics
from bucco.evaluate.backtest import run_backtest
from bucco.models.base import LUCK_SD, forecast_frame
from bucco.models.naive import ConstantModel, PersistenceModel

TEAMS = list(range(1, 31))


@pytest.fixture
def data():
    """Ten fake seasons. Each team's win pct is a fixed value, so persistence is exact."""
    rng = np.random.default_rng(0)
    base = dict(zip(TEAMS, np.linspace(0.35, 0.65, 30)))
    rows = [{"season": s, "team_id": t, "win_pct": base[t] + rng.normal(0, 0.01)}
            for s in range(2000, 2010) for t in TEAMS]
    team_seasons = pd.DataFrame(rows)
    prior = team_seasons.assign(season=team_seasons["season"] + 1)
    features = prior.rename(columns={"win_pct": "prior_win_pct"})[["season", "team_id",
                                                                   "prior_win_pct"]]
    features["opening_day"] = pd.to_datetime(features["season"].astype(str) + "-04-01")
    return team_seasons, features


def test_constant_predicts_half(data):
    team_seasons, features = data
    results = run_backtest(ConstantModel, team_seasons, features)
    assert (results["pred_win_pct"] == 0.5).all()
    assert set(results["season"]) == set(range(2001, 2010))
    assert results.groupby("season")["team_id"].nunique().eq(30).all()


def test_persistence_beats_constant_when_teams_are_stable(data):
    team_seasons, features = data
    both = pd.concat([run_backtest(m, team_seasons, features)
                      for m in (ConstantModel, PersistenceModel)])
    table = metrics.by_model(both)
    assert table.index[0] == "last_year"


def test_sd_falls_back_to_luck_with_no_history(data):
    team_seasons, features = data
    results = run_backtest(PersistenceModel, team_seasons, features, seasons=[2001])
    assert results["sd_win_pct"].eq(LUCK_SD).all()  # only one prior season: no residuals yet


def test_missing_prior_uses_fallback():
    model = PersistenceModel()
    model.sd = 0.05
    features = pd.DataFrame({"team_id": [1, 2], "prior_win_pct": [0.6, np.nan]})
    out = model.predict(2001, None, features)
    assert out["mean_win_pct"].tolist() == [0.6, 0.5]


class SpyModel:
    """Records what the backtest hands it, so the tests can check nothing leaks."""

    name = "spy"
    calls: ClassVar[list] = []

    def fit(self, history):
        self.history_seasons = set(history["season"])

    def predict(self, season, as_of, features):
        SpyModel.calls.append((season, self.history_seasons, set(features["season"]),
                               set(features.columns)))
        return forecast_frame(features, 0.5, LUCK_SD)


def test_model_never_sees_target_season_or_later(data):
    team_seasons, features = data
    SpyModel.calls = []
    run_backtest(SpyModel, team_seasons, features)
    assert SpyModel.calls
    for season, history_seasons, feature_seasons, columns in SpyModel.calls:
        assert max(history_seasons) < season       # history is strictly earlier
        assert feature_seasons == {season}          # features are only for the target
        assert "win_pct" not in columns             # no result columns in features


def test_model_with_wrong_teams_is_rejected(data):
    team_seasons, features = data

    class Short(SpyModel):
        def predict(self, season, as_of, features):
            return forecast_frame(features.head(10), 0.5, LUCK_SD)

    with pytest.raises(ValueError):
        run_backtest(Short, team_seasons, features)


def test_score_in_wins():
    results = pd.DataFrame({"pred_win_pct": [0.5, 0.5], "actual_win_pct": [0.6, 0.4],
                            "sd_win_pct": [0.04, 0.04]})
    s = metrics.score(results)
    assert s["mae"] == pytest.approx(0.1 * 162)
    assert s["bias"] == pytest.approx(0)
    assert s["cover_80"] == 0.0  # 16.2 wins off, interval is +/- 8.3


def test_shortened_season_excluded_by_default():
    results = pd.DataFrame({
        "model": "m", "season": [2019, 2020], "team_id": 1,
        "pred_win_pct": 0.5, "sd_win_pct": 0.04, "actual_win_pct": [0.5, 0.9]})
    assert metrics.by_model(results).loc["m", "n"] == 1
    assert metrics.by_model(results).loc["m", "rmse"] == 0
    assert metrics.by_model(results, include_shortened=True).loc["m", "n"] == 2


def test_forecast_uses_only_completed_seasons_and_targets_next(data):
    from bucco import forecast
    team_seasons, features = data
    SpyModel.calls = []
    out = forecast.make_forecast(SpyModel, team_seasons, features.assign(team_abbr="X"))
    season, history_seasons, feature_seasons, _ = SpyModel.calls[0]
    assert season == 2010 and max(history_seasons) == 2009 and feature_seasons == {2010}
    assert len(out) == 30 and (out["season"] == 2010).all()


def test_forecast_refuses_completed_season(data):
    from bucco import forecast
    team_seasons, features = data
    with pytest.raises(ValueError):
        forecast.make_forecast(ConstantModel, team_seasons, features, season=2005)
