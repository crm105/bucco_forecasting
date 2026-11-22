"""The interface every season forecaster implements.

Models take DataFrames in and return DataFrames out. They never read files or the database,
so the backtest decides exactly what a model is allowed to see.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd

GAMES = 162
PIRATES_TEAM_ID = 134

# Standard deviation of win percentage from game-to-game luck alone: sqrt(.25 / 162), about
# 6.4 wins. No forecast can have a smaller spread than this, so it is also the fallback
# when a model has too little history to measure its own residuals.
LUCK_SD = float(np.sqrt(0.25 / GAMES))
MIN_RESIDUALS = 30  # one season of teams


class SeasonForecaster(Protocol):
    name: str

    def fit(self, history: pd.DataFrame) -> None:
        """`history` is team_seasons for seasons BEFORE the target season only."""

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        """One row per team in `features`: team_id, mean_win_pct, sd_win_pct."""


def residual_sd(residuals: pd.Series) -> float:
    """Spread of past forecast errors, or the luck floor if there are too few to trust."""
    residuals = residuals.dropna()
    if len(residuals) < MIN_RESIDUALS:
        return LUCK_SD
    return float(max(residuals.std(ddof=1), LUCK_SD))


def forecast_frame(features: pd.DataFrame, mean: pd.Series | float, sd: float) -> pd.DataFrame:
    return pd.DataFrame({
        "team_id": features["team_id"].to_numpy(),
        "mean_win_pct": np.asarray(mean, dtype=float) * np.ones(len(features)),
        "sd_win_pct": sd,
    })
