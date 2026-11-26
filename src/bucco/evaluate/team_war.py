"""Intermediate check for player-projection models: projected team WAR against what each team
actually produced (marts.team_war_seasons), before WAR is turned into wins.

Wins add game-to-game luck (about 6.4 wins of the ~9.5 RMSE), run sequencing and the WAR-to-wins
line on top of the projections, so a real improvement in player projections can be invisible in
the wins backtest. Team WAR keeps only what the projections and the playing-time steps decide.
Both sides are centered on each season's league average (projected and actual totals differ in
level, e.g. replacement-level conventions), so the score is about which teams are better and by
how much. Projections are taken as of Opening Day, as in the backtest; 2020 is left out.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.evaluate.backtest import _as_of
from bucco.evaluate.metrics import SHORTENED_SEASONS

PARTS = ("batting", "pitching", "total")


def load_actual(path=DUCKDB_PATH) -> pd.DataFrame:
    """season, team_id, batting, pitching, total: actual team WAR."""
    with duckdb.connect(str(path), read_only=True) as con:
        return con.sql("select season, team_id, batting_war as batting, "
                       "pitching_war as pitching, war as total "
                       "from marts.team_war_seasons").df()


def projected(model, features: pd.DataFrame, seasons) -> pd.DataFrame:
    """season, team_id, batting, pitching, total: a player-projection model's team WAR (its
    `data.team_war_parts`) as of each season's Opening Day."""
    rows = []
    for season in seasons:
        as_of = _as_of(features[features["season"] == season])
        parts = model.data.team_war_parts(int(season), as_of)
        rows.append(parts.assign(total=parts["batting"] + parts["pitching"], season=season)
                    .rename_axis("team_id").reset_index())
    return pd.concat(rows, ignore_index=True)[["season", "team_id", *PARTS]]


def errors(proj: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Projected minus actual team WAR per season and team, each centered on its season's
    league mean (2020 left out)."""
    x = proj.merge(actual, on=["season", "team_id"], suffixes=("_p", "_a"))
    x = x[~x["season"].isin(SHORTENED_SEASONS)]
    out = x[["season", "team_id"]].copy()
    for part in PARTS:
        p, a = x[f"{part}_p"], x[f"{part}_a"]
        out[part] = (p - p.groupby(x["season"]).transform("mean")) \
            - (a - a.groupby(x["season"]).transform("mean"))
    return out


def score(err: pd.DataFrame) -> pd.Series:
    """RMSE in WAR of batting, pitching and total team WAR, and the number of team-seasons."""
    out = {f"{part}_rmse": float(np.sqrt((err[part] ** 2).mean())) for part in PARTS}
    out["n"] = len(err)
    return pd.Series(out)


def save(err: pd.DataFrame, model: str, path=DUCKDB_PATH) -> None:
    """Store a model's errors in evaluate.team_war_results, replacing its earlier rows."""
    with duckdb.connect(str(path)) as con:
        con.execute("create schema if not exists evaluate")
        con.register("new_rows", err.assign(model=model))
        con.execute("create table if not exists evaluate.team_war_results as "
                    "select * from new_rows limit 0")
        con.execute("delete from evaluate.team_war_results where model = ?", [model])
        con.execute("insert into evaluate.team_war_results by name select * from new_rows")
