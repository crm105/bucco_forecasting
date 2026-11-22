"""Forecast the upcoming season with one model and save the result.

The model is fit on every completed season, then predicts the next one from team_season_features.
Each run is stored with its as-of date, so earlier versions of a forecast (before a trade,
say) are kept and the version on Opening Day can be told apart.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

import duckdb
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.evaluate.metrics import Z_80
from bucco.models.base import GAMES, PIRATES_TEAM_ID, SeasonForecaster

log = logging.getLogger(__name__)

FORECAST_COLUMNS = ["model", "season", "team_id", "team_abbr", "as_of_date",
                    "pred_win_pct", "sd_win_pct"]


def upcoming_season(team_seasons: pd.DataFrame) -> int:
    """The season after the latest completed one."""
    return int(team_seasons["season"].max()) + 1


def make_forecast(
    make_model: Callable[[], SeasonForecaster],
    team_seasons: pd.DataFrame,
    features: pd.DataFrame,
    season: int | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Fit on all completed seasons and predict `season` (default: the upcoming one)."""
    season = season or upcoming_season(team_seasons)
    if season in set(team_seasons["season"]):
        raise ValueError(f"{season} is already complete. Use `bucco backtest` to score "
                         "models on past seasons.")
    target = features[features["season"] == season].copy()
    if target.empty:
        raise ValueError(f"No features for {season}. Re-run `bucco extract all` and "
                         "`bucco build`.")
    as_of = as_of or date.today()
    opening = target["opening_day"].dropna()
    if len(opening) and as_of > pd.Timestamp(opening.min()).date():
        log.warning("as-of date %s is after Opening Day %s; the forecast of record is the "
                    "one made on or before Opening Day.", as_of, pd.Timestamp(opening.min()).date())

    history = team_seasons[team_seasons["season"] < season]
    model = make_model()
    model.fit(history)
    predictions = model.predict(season, as_of, target)
    if set(predictions["team_id"]) != set(target["team_id"]):
        raise ValueError(f"{model.name}: predictions do not cover the same teams as the features")

    out = predictions.merge(target[["team_id", "team_abbr"]], on="team_id", validate="one_to_one")
    out = out.rename(columns={"mean_win_pct": "pred_win_pct"})
    out["model"] = model.name
    out["season"] = season
    out["as_of_date"] = as_of.isoformat()
    return out[FORECAST_COLUMNS]


def save_forecast(forecast: pd.DataFrame, path=DUCKDB_PATH) -> None:
    """Store in forecasts.season_forecasts. Same model, season and as-of date is replaced;
    other as-of dates are kept."""
    with duckdb.connect(str(path)) as con:
        con.execute("create schema if not exists forecasts")
        con.register("new_forecast", forecast)
        con.execute("create table if not exists forecasts.season_forecasts as "
                    "select *, current_timestamp as run_at from new_forecast where false")
        con.execute("delete from forecasts.season_forecasts where (model, season, as_of_date) in "
                    "(select distinct model, season, as_of_date from new_forecast)")
        con.execute("insert into forecasts.season_forecasts "
                    "select *, current_timestamp from new_forecast")


def format_forecast(forecast: pd.DataFrame) -> str:
    """Wins and an 80% range for each team, best first. The Pirates are marked with *."""
    wins = forecast["pred_win_pct"] * GAMES
    half = Z_80 * forecast["sd_win_pct"] * GAMES
    table = pd.DataFrame({
        "team": forecast["team_abbr"] + forecast["team_id"].eq(PIRATES_TEAM_ID).map(
            {True: " *", False: ""}),
        "wins": wins,
        "low_80": (wins - half).clip(lower=0),
        "high_80": (wins + half).clip(upper=GAMES),
    }).sort_values("wins", ascending=False).reset_index(drop=True)
    table.index += 1
    first = forecast.iloc[0]
    header = f"{first['model']} forecast for {first['season']} (as of {first['as_of_date']})"
    return header + "\n" + table.to_string(float_format=lambda x: f"{x:.1f}")
