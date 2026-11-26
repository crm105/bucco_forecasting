"""Gather everything a report shows into one plain dictionary. No HTML in this module."""

from __future__ import annotations

import subprocess
from datetime import date
from math import erf, sqrt

import duckdb
import pandas as pd

from bucco.config import DUCKDB_PATH, REPO_ROOT
from bucco.evaluate import metrics
from bucco.evaluate.backtest import load_results
from bucco.evaluate.metrics import Z_80
from bucco.models import REGISTRY
from bucco.models.base import GAMES, PIRATES_TEAM_ID


def prob_above(threshold: float, mean_wins: float, sd_wins: float) -> float:
    """Chance of winning MORE than `threshold` games, for a normal forecast of whole wins.

    Wins are whole numbers, so "more than 81" means 82 or more, which is the area above 81.5.
    """
    cutoff = int(threshold // 1) + 0.5
    return 0.5 * (1 - erf((cutoff - mean_wins) / (sd_wins * sqrt(2))))


def _query(path, sql: str, params: list | None = None) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        return con.execute(sql, params or []).df()


def load_forecasts(season: int, path=DUCKDB_PATH) -> pd.DataFrame:
    try:
        return _query(path, "select * from forecasts.season_forecasts where season = ?", [season])
    except duckdb.CatalogException as error:
        raise RuntimeError("No saved forecasts. Run `bucco forecast --model <name>` first.") \
            from error


def shared_seasons(results: pd.DataFrame) -> list[int]:
    """Full seasons every model in `results` was scored on."""
    full = results[~results["season"].isin(metrics.SHORTENED_SEASONS)]
    per_model = [set(g["season"]) for _, g in full.groupby("model")]
    return sorted(set.intersection(*per_model)) if per_model else []


def board(results: pd.DataFrame) -> pd.DataFrame:
    """The leaderboard with each model's first scored season and its RMSE on the seasons every
    model shares (`rmse_shared`), best first by that: models cover different seasons, and early
    seasons are easier or harder, so only the shared ones compare like with like."""
    table = metrics.by_model(results)
    full = results[~results["season"].isin(metrics.SHORTENED_SEASONS)]
    table["first_season"] = full.groupby("model")["season"].min()
    shared = full[full["season"].isin(shared_seasons(results))]
    table["rmse_shared"] = metrics.by_model(shared)["rmse"]
    return table.sort_values("rmse_shared")


def best_model(results: pd.DataFrame) -> str:
    """Lowest RMSE on the seasons every model shares (2020 excluded)."""
    return str(board(results).index[0])


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _wins(frame: pd.DataFrame) -> pd.DataFrame:
    """Add expected wins and the 80% range, in wins."""
    frame = frame.copy()
    frame["wins"] = frame["pred_win_pct"] * GAMES
    half = Z_80 * frame["sd_win_pct"] * GAMES
    frame["low"] = (frame["wins"] - half).clip(lower=0)
    frame["high"] = (frame["wins"] + half).clip(upper=GAMES)
    return frame


def _badge(as_of: str, opening_day: date | None, all_as_of: list[str], today: date) -> str:
    """Whether this report is the forecast of record, a preliminary one, or too late."""
    if opening_day is None:
        return "preliminary"
    opening = opening_day.isoformat()
    if as_of > opening:
        return "late"
    on_time = [d for d in all_as_of if d <= opening]
    if today > opening_day and as_of == max(on_time):
        return "record"
    return "preliminary"


def build_report_data(model: str | None = None, season: int | None = None,
                      as_of: str | None = None, path=DUCKDB_PATH,
                      today: date | None = None) -> dict:
    """Collect forecast, history, scores and the notes for one report."""
    today = today or date.today()
    results = load_results(path, models=REGISTRY)
    model = model or best_model(results)
    if model not in set(results["model"]):
        raise RuntimeError(f"{model} has no backtest results. Run `bucco backtest` first.")

    team_seasons = _query(path, "select * from marts.team_seasons")
    features = _query(path, "select season, team_id, opening_day, prior_win_pct, "
                            "prior_wins, prior_season from marts.team_season_features")
    season = season or int(team_seasons["season"].max()) + 1

    forecasts = load_forecasts(season, path)
    mine = forecasts[forecasts["model"] == model]
    if mine.empty:
        raise RuntimeError(f"No saved {season} forecast for {model}. "
                           f"Run `bucco forecast --model {model}` first.")
    dates = sorted(mine["as_of_date"].unique())
    as_of = as_of or dates[-1]
    if as_of not in dates:
        raise RuntimeError(f"No saved forecast as of {as_of}. Saved dates: {dates}")

    teams = _wins(mine[mine["as_of_date"] == as_of]).sort_values("wins", ascending=False)
    pirates = teams[teams["team_id"] == PIRATES_TEAM_ID].iloc[0]
    sd_wins = float(pirates["sd_win_pct"] * GAMES)

    target_features = features[(features["season"] == season)
                               & (features["team_id"] == PIRATES_TEAM_ID)].iloc[0]
    opening = pd.Timestamp(target_features["opening_day"]).date() \
        if pd.notna(target_features["opening_day"]) else None
    last_wins = float(target_features["prior_win_pct"] * GAMES)

    # Earlier versions of this forecast, for the timeline and the "what changed" note.
    timeline = _wins(mine[mine["team_id"] == PIRATES_TEAM_ID]).sort_values("as_of_date")
    earlier = forecasts[forecasts["as_of_date"] < as_of]
    previous = None
    if not earlier.empty:
        prev_date = earlier["as_of_date"].max()
        rows = earlier[earlier["as_of_date"] == prev_date]
        prev_model = model if model in set(rows["model"]) else str(rows["model"].iloc[0])
        prev = _wins(rows[(rows["model"] == prev_model) & (rows["team_id"] == PIRATES_TEAM_ID)]
                     ).iloc[0]
        previous = {"as_of_date": prev_date, "model": prev_model, "wins": float(prev["wins"])}

    pirates_past = results[(results["model"] == model)
                           & (results["team_id"] == PIRATES_TEAM_ID)].sort_values("season")
    pirates_past = pirates_past.assign(
        predicted=pirates_past["pred_win_pct"] * GAMES,
        actual=pirates_past["actual_win_pct"] * GAMES)
    pirates_past["error"] = pirates_past["predicted"] - pirates_past["actual"]

    table = board(results)
    shared = shared_seasons(results)
    return {
        "season": season, "model": model, "as_of": as_of, "today": today.isoformat(),
        "opening_day": opening.isoformat() if opening else None,
        "badge": _badge(as_of, opening, dates, today),
        "teams": teams, "pirates": {
            "wins": float(pirates["wins"]), "low": float(pirates["low"]),
            "high": float(pirates["high"]), "sd_wins": sd_wins,
            "p_above_500": prob_above(GAMES / 2, float(pirates["wins"]), sd_wins),
            "last_wins": last_wins,
            "last_season": int(target_features["prior_season"]),
            "p_beat_last": prob_above(last_wins, float(pirates["wins"]), sd_wins),
        },
        "timeline": timeline, "previous": previous,
        "leaderboard": table, "shared_first": shared[0], "shared_last": shared[-1],
        "first_scored_season": int(
            results.loc[~results["season"].isin(metrics.SHORTENED_SEASONS), "season"].min()),
        "last_scored_season": int(results["season"].max()),
        "pirates_past": pirates_past[["season", "predicted", "actual", "error"]],
        "commit": git_commit(),
    }
