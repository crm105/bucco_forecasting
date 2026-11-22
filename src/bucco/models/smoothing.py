"""Rung 2 of the model ladder: damped-trend exponential smoothing (Holt's method).

Each team's win percentage is a yearly series. The model keeps two running estimates per
team: a level (current talent) and a slope (how fast talent is changing). The forecast is
level + phi * slope. Three parameters control it, and one set is shared by all 30 teams
(pooled), chosen to minimize one-year-ahead errors over every team's history:

    smoothing_level   (alpha)  how fast the level follows the latest season; 1 = last year
    smoothing_trend   (beta)   how fast the slope follows the latest change in level
    damping_trend     (phi)    how much of the slope carries into the forecast; 0 = no trend

(alpha=1, beta=0, phi=0) is exactly the last-year model, so this model can only match or
improve on rung 1 in-sample.

There is no seasonal term: one number per team per year has no seasonal cycle.
"""

from __future__ import annotations

import logging
import warnings
from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from statsmodels.tsa.holtwinters import Holt

from bucco.models.base import forecast_frame, residual_sd

log = logging.getLogger(__name__)

# Fewer seasons than this and the parameters can't be estimated sensibly, so the model
# falls back to repeating last season (the same as rung 1).
MIN_SEASONS = 4
FALLBACK_PARAMS = (1.0, 0.0, 0.0)  # alpha, beta, phi

# Starting points for the search: a coarse grid, then a local search from the best one.
_GRID = [(a, b, p) for a in (0.2, 0.5, 0.8) for b in (0.0, 0.2, 0.6) for p in (0.0, 0.5, 0.9)]


def _smooth(series: np.ndarray, params: tuple[float, float, float]):
    """Run the smoother over one team's series, starting from its first season."""
    alpha, beta, phi = params
    model = Holt(series, damped_trend=True, initialization_method="known",
                 initial_level=series[0], initial_trend=0.0)
    with warnings.catch_warnings():
        # statsmodels takes log(sse) for its AIC/BIC, which we don't use; sse can be 0
        # when a parameter set repeats the series exactly (as in a flat test series).
        warnings.simplefilter("ignore", RuntimeWarning)
        return model.fit(smoothing_level=alpha, smoothing_trend=beta, damping_trend=phi,
                         optimized=False)


def _forecast_next(fit) -> float:
    """The forecast for the season after the series ends (same warning handling as _smooth)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return float(fit.forecast(1)[0])


def _one_step_errors(series_by_team: list[np.ndarray], params) -> np.ndarray:
    """Actual minus forecast for every season after each team's first, all teams together."""
    errors = []
    for series in series_by_team:
        fitted = _smooth(series, params).fittedvalues
        errors.append(series[1:] - fitted[1:])
    return np.concatenate(errors)


def fit_pooled_params(series_by_team: list[np.ndarray]) -> tuple[float, float, float]:
    """The (alpha, beta, phi) that minimize squared one-year-ahead error over all teams."""
    def loss(params):
        return float(np.mean(_one_step_errors(series_by_team, tuple(params)) ** 2))

    start = min(_GRID, key=loss)
    result = minimize(loss, start, method="Nelder-Mead", bounds=[(0.0, 1.0)] * 3,
                      options={"xatol": 1e-3, "fatol": 1e-9})
    best = result.x if result.fun <= loss(start) else np.asarray(start)
    return tuple(float(np.clip(v, 0.0, 1.0)) for v in best)


class HoltModel:
    """Rung 2: damped-trend smoothing of each team's win percentage, pooled parameters."""

    name = "holt"

    def __init__(self, fallback: float = 0.5) -> None:
        self.fallback = fallback
        self.params = FALLBACK_PARAMS
        self.sd = None
        self.next_win_pct: dict[int, float] = {}

    def fit(self, history: pd.DataFrame) -> None:
        series_by_team = {}
        for team_id, rows in history.sort_values("season").groupby("team_id"):
            seasons = rows["season"].to_numpy()
            if len(seasons) > 1 and np.diff(seasons).max() > 1:
                raise ValueError(f"team {team_id} has a gap in its seasons; smoothing needs "
                                 "consecutive years")
            series_by_team[int(team_id)] = rows["win_pct"].to_numpy(dtype=float)

        usable = [s for s in series_by_team.values() if len(s) >= MIN_SEASONS]
        self.params = fit_pooled_params(usable) if usable else FALLBACK_PARAMS
        if usable:
            log.info("holt: alpha=%.3f beta=%.3f phi=%.3f", *self.params)

        errors = []
        self.next_win_pct = {}
        for team_id, series in series_by_team.items():
            if len(series) < 2:
                self.next_win_pct[team_id] = float(series[-1])
                continue
            fit = _smooth(series, self.params)
            errors.append(series[1:] - fit.fittedvalues[1:])
            self.next_win_pct[team_id] = _forecast_next(fit)
        self.sd = residual_sd(pd.Series(np.concatenate(errors) if errors else []))

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        mean = features["team_id"].map(self.next_win_pct).fillna(self.fallback)
        return forecast_frame(features, mean, self.sd)
