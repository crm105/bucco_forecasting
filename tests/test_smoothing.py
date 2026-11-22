"""Checks for the damped-trend smoothing model (rung 2)."""

import numpy as np
import pandas as pd
import pytest

from bucco.evaluate import metrics
from bucco.evaluate.backtest import run_backtest
from bucco.models.base import LUCK_SD
from bucco.models.naive import ConstantModel, PersistenceModel
from bucco.models.smoothing import FALLBACK_PARAMS, HoltModel, fit_pooled_params

TEAMS = list(range(1, 31))


def _history(seasons=12, noise=0.04, seed=0):
    """Teams with fixed true talent plus yearly luck: smoothing should beat last year."""
    rng = np.random.default_rng(seed)
    talent = dict(zip(TEAMS, np.linspace(0.38, 0.62, 30)))
    rows = [{"season": 2000 + i, "team_id": t, "win_pct": talent[t] + rng.normal(0, noise)}
            for i in range(seasons) for t in TEAMS]
    return pd.DataFrame(rows)


def _features(team_seasons):
    prior = team_seasons.assign(season=team_seasons["season"] + 1)
    features = prior.rename(columns={"win_pct": "prior_win_pct"})[["season", "team_id",
                                                                   "prior_win_pct"]]
    features["opening_day"] = pd.to_datetime(features["season"].astype(str) + "-04-01")
    return features


def test_fallback_params_repeat_last_season():
    series = np.array([0.40, 0.55, 0.47])
    from bucco.models.smoothing import _smooth
    assert _smooth(series, FALLBACK_PARAMS).forecast(1)[0] == pytest.approx(0.47)


def test_params_stay_in_bounds():
    series = [h["win_pct"].to_numpy() for _, h in _history().groupby("team_id")]
    assert all(0.0 <= p <= 1.0 for p in fit_pooled_params(series))


def test_noisy_stable_teams_get_smoothing_not_persistence():
    history = _history()
    model = HoltModel()
    model.fit(history)
    alpha, _, phi = model.params
    assert alpha < 0.6  # true talent never changes, so last year should not get most weight
    assert phi < 0.5  # and there is no momentum to carry forward


def test_beats_last_year_when_talent_is_stable():
    team_seasons = _history()
    features = _features(team_seasons)
    results = pd.concat([run_backtest(m, team_seasons, features)
                         for m in (ConstantModel, PersistenceModel, HoltModel)])
    assert metrics.by_model(results).index[0] == "holt"


@pytest.mark.parametrize("target", [2001, 2002])
def test_short_history_matches_last_year(target):
    team_seasons = _history(seasons=3)
    features = _features(team_seasons)
    holt = run_backtest(HoltModel, team_seasons, features, seasons=[target])
    last = run_backtest(PersistenceModel, team_seasons, features, seasons=[target])
    assert holt["pred_win_pct"].to_numpy() == pytest.approx(last["pred_win_pct"].to_numpy())
    assert holt["sd_win_pct"].to_numpy() == pytest.approx(last["sd_win_pct"].to_numpy())
    if target == 2001:
        assert holt["sd_win_pct"].eq(LUCK_SD).all()  # one prior season: no errors to measure


def test_unknown_team_gets_fallback():
    model = HoltModel()
    model.fit(_history(seasons=6))
    out = model.predict(2006, None, pd.DataFrame({"team_id": [1, 999]}))
    assert out["mean_win_pct"].iloc[1] == 0.5


def test_gap_in_seasons_is_rejected():
    history = _history(seasons=6)
    history = history[~((history["team_id"] == 3) & (history["season"] == 2002))]
    with pytest.raises(ValueError, match="gap"):
        HoltModel().fit(history)
