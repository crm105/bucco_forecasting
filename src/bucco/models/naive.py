"""Rungs 0 and 1 of the model ladder: the baselines every other model has to beat."""

from __future__ import annotations

from datetime import date

import pandas as pd

from bucco.models.base import forecast_frame, residual_sd


class ConstantModel:
    """Rung 0: every team wins half its games (81 of 162)."""

    name = "constant"

    def __init__(self, win_pct: float = 0.5) -> None:
        self.win_pct = win_pct
        self.sd = None

    def fit(self, history: pd.DataFrame) -> None:
        self.sd = residual_sd(history["win_pct"] - self.win_pct)

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        return forecast_frame(features, self.win_pct, self.sd)


class PersistenceModel:
    """Rung 1: every team repeats last season's win percentage."""

    name = "last_year"

    def __init__(self, fallback: float = 0.5) -> None:
        self.fallback = fallback
        self.sd = None

    def fit(self, history: pd.DataFrame) -> None:
        """Measure how far a team's next season usually lands from its last one."""
        prior = history[["season", "team_id", "win_pct"]].copy()
        prior["season"] += 1
        pairs = history.merge(prior, on=["season", "team_id"], suffixes=("", "_prior"))
        self.sd = residual_sd(pairs["win_pct"] - pairs["win_pct_prior"])

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        mean = features["prior_win_pct"].fillna(self.fallback)
        return forecast_frame(features, mean, self.sd)
