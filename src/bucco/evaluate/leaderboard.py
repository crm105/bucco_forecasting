"""Printable leaderboard and Pirates-only view of the backtest results."""

from __future__ import annotations

import pandas as pd

from bucco.evaluate import metrics
from bucco.models.base import GAMES, PIRATES_TEAM_ID


def leaderboard(results: pd.DataFrame, first_season: int | None = None,
                include_shortened: bool = False) -> str:
    table = metrics.by_model(results, first_season, include_shortened)
    table = table.rename(columns={
        "n": "team_seasons", "mae": "MAE", "rmse": "RMSE", "bias": "bias",
        "sd_wins": "avg_sd", "cover_80": "80%_cover"})
    return table.to_string(float_format=lambda x: f"{x:.2f}")


def pirates_view(results: pd.DataFrame) -> str:
    """Pirates predictions and errors by season. For interest only, never for choosing models."""
    pirates = results[results["team_id"] == PIRATES_TEAM_ID].copy()
    pirates["wins_pred"] = pirates["pred_win_pct"] * GAMES
    pirates["wins_actual"] = pirates["actual_win_pct"] * GAMES
    pirates["error"] = pirates["wins_pred"] - pirates["wins_actual"]
    wide = pirates.pivot(index="season", columns="model", values="error")
    wide.insert(0, "actual_wins", pirates.drop_duplicates("season").set_index("season")
                ["wins_actual"])
    return wide.to_string(float_format=lambda x: f"{x:.1f}")
