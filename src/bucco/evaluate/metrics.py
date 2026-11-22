"""Scores for a table of backtest results. Everything is reported in wins per 162 games."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bucco.models.base import GAMES

# Seasons too short to compare with a normal 162-game year (2020 had 60 games). They stay in
# the saved backtest results but are left out of the scores unless asked for.
SHORTENED_SEASONS = (2020,)

Z_80 = 1.2816  # a normal interval of +/- 1.2816 sd holds 80% of outcomes


def score(results: pd.DataFrame) -> dict[str, float]:
    """Accuracy and interval quality for one group of rows."""
    error = (results["pred_win_pct"] - results["actual_win_pct"]) * GAMES
    inside = error.abs() <= Z_80 * results["sd_win_pct"] * GAMES
    return {
        "n": len(results),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt((error ** 2).mean())),
        "bias": float(error.mean()),
        "sd_wins": float((results["sd_win_pct"] * GAMES).mean()),
        "cover_80": float(inside.mean()),
    }


def by_model(results: pd.DataFrame, first_season: int | None = None,
             include_shortened: bool = False) -> pd.DataFrame:
    """One row per model, best (lowest RMSE) first. Shortened seasons are skipped by default."""
    if not include_shortened:
        results = results[~results["season"].isin(SHORTENED_SEASONS)]
    if first_season is not None:
        results = results[results["season"] >= first_season]
    rows = {model: score(group) for model, group in results.groupby("model")}
    return pd.DataFrame(rows).T.astype({"n": int}).sort_values("rmse")


def by_season(results: pd.DataFrame) -> pd.DataFrame:
    """RMSE in wins for each model (columns) and season (rows)."""
    return results.groupby(["season", "model"]).apply(
        lambda g: score(g)["rmse"], include_groups=False).unstack("model")
