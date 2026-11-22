"""Walk-forward backtest: forecast every team for every past season using only earlier data.

This is the only module that sees a target season's actual results, and it only uses them
after the model has made its predictions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

import duckdb
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.models.base import SeasonForecaster

log = logging.getLogger(__name__)

RESULT_COLUMNS = ["model", "season", "team_id", "as_of_date", "pred_win_pct",
                  "sd_win_pct", "actual_win_pct"]


def run_backtest(
    make_model: Callable[[], SeasonForecaster],
    team_seasons: pd.DataFrame,
    features: pd.DataFrame,
    seasons: list[int] | None = None,
) -> pd.DataFrame:
    """Fit on seasons before each target season, predict it, and score against the result.

    A fresh model is built for every target season, so nothing carries over between them.
    `team_seasons` holds results; `features` holds prior-season inputs per target season.
    """
    first_season = int(team_seasons["season"].min()) + 1  # needs one earlier season
    targets = seasons or sorted(int(s) for s in team_seasons["season"].unique()
                                if s >= first_season)
    frames = []
    for season in targets:
        history = team_seasons[team_seasons["season"] < season].copy()
        target_features = features[features["season"] == season].copy()
        if history.empty or target_features.empty:
            raise ValueError(f"No history or features to forecast {season}")

        model = make_model()
        model.fit(history)
        as_of = _as_of(target_features)
        predictions = model.predict(season, as_of, target_features)

        actual = team_seasons.loc[team_seasons["season"] == season, ["team_id", "win_pct"]]
        scored = predictions.merge(actual.rename(columns={"win_pct": "actual_win_pct"}),
                                   on="team_id", how="outer", validate="one_to_one")
        if scored[["mean_win_pct", "sd_win_pct", "actual_win_pct"]].isna().any().any():
            raise ValueError(f"{model.name}: predictions for {season} do not match the "
                             "teams that played")
        scored = scored.rename(columns={"mean_win_pct": "pred_win_pct"})
        scored["model"] = model.name
        scored["season"] = season
        scored["as_of_date"] = as_of.isoformat() if as_of else None
        frames.append(scored[RESULT_COLUMNS])
    return pd.concat(frames, ignore_index=True)


def _as_of(target_features: pd.DataFrame) -> date | None:
    """The forecast date: Opening Day of the target season."""
    opening = target_features["opening_day"].dropna()
    return pd.Timestamp(opening.min()).date() if len(opening) else None


def load_inputs(path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read team_seasons and team_season_features, as built by `bucco build`."""
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        team_seasons = con.sql("select * from marts.team_seasons order by season, team_id").df()
        features = con.sql(
            "select * from marts.team_season_features order by season, team_id").df()
    return team_seasons, features


def save_results(results: pd.DataFrame, path=DUCKDB_PATH) -> None:
    """Store results in evaluate.backtest_results, replacing earlier rows for the same models."""
    with duckdb.connect(str(path)) as con:
        con.execute("create schema if not exists evaluate")
        con.register("new_results", results)
        con.execute("create table if not exists evaluate.backtest_results as "
                    "select *, current_timestamp as run_at from new_results where false")
        con.execute("delete from evaluate.backtest_results where model in "
                    "(select distinct model from new_results)")
        con.execute("insert into evaluate.backtest_results "
                    "select *, current_timestamp from new_results")


def load_results(path=DUCKDB_PATH) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco backtest` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        try:
            return con.sql("select * from evaluate.backtest_results").df()
        except duckdb.CatalogException as error:
            raise RuntimeError("No backtest results yet. Run `bucco backtest` first.") from error
