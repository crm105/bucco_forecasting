"""Learned hitter plate appearances, on top of Marcel.

One model, fitted walk-forward and tuned per target season (bucco.models.ml.core): next season's
MLB plate appearances for every hitter on an Opening Day 40-man roster (0 if none), with our
pipeline's PA (Marcel's playing time scaled by Opening Day status) as an input. Scored and tuned
on plain (unweighted) RMSE, one row per rostered hitter.

Inputs, from the three seasons before (`history`): MLB and minor-league lines combined as one
season (plate appearances, games, offense runs per 600 PA, strikeout, walk, home-run and stolen-
base rates, ISO and BABIP, each against that season's MLB average), the share of PA in the minors
and the average minor-league level, injured-list days, stints and 60-day stints; plus age, the
season, Marcel's offense, defense and WAR per 600 PA, Opening Day status this season and last,
and roster context (`roster_context`: where he stands among his team's hitters and at his main
position last season). Unknown values (injured list before 2009, minor leagues before 2006) are left missing.

The model's PA are used as given (`apply`: offense, defense and WAR scale with the PA; no lineup
optimizer), in `marcel_ml_hitter_pa`. `fit_and_save` (`bucco fit-ml --targets hitters`) saves
every season's predictions from FIRST_PREDICTED to the upcoming one to PREDICTIONS. Learned hitter
rates were tried and tie Marcel's, so they are not modeled. See docs/R&D/ml_playing_time.md.
"""

from __future__ import annotations

import logging

import duckdb
import numpy as np
import pandas as pd

from bucco.config import CACHE_DIR, DUCKDB_PATH
from bucco.models.ml.core import (
    FIRST_MILB_SEASON,
    LEVEL,
    OPENING_DAY,
    lagged,
    opening_day,
    score,
    walk_forward,
    with_il,
)

log = logging.getLogger(__name__)

PREDICTIONS = CACHE_DIR / "derived" / "ml_hitters.parquet"
FIRST_PREDICTED = 2012          # the first season with two earlier roster seasons to tune on
FIRST_TRAIN = 2009              # the first Opening Day roster season
COUNTS = ["pa", "ab", "h", "doubles", "triples", "hr", "bb", "so", "sb", "sf"]
RATES = ["k", "bbr", "hrr", "sbr", "iso", "babip"]
LAGS = ["pa", "games", "milb_share", "milb_level", "off600", *RATES, "il_days", "il_stints",
        "on_60_day"]
VOLUMES = ("pa", "games")
CONTEXT = ["ctx_rank_team", "ctx_team_n", "ctx_pipe_share", "ctx_team_pipe", "ctx_rank_pos",
           "ctx_n_pos", "ctx_pos_pipe", "ctx_gap_pos", "ctx_is_c", "ctx_no_pos"]
PA_FEATURES = ["age", "season", "marcel_off600", "marcel_def600", "marcel_war600", "pipe",
               *OPENING_DAY, *CONTEXT] + [f"y{k}_{c}" for k in (1, 2, 3) for c in LAGS]


def _rates(x: pd.DataFrame) -> pd.DataFrame:
    pa = x["pa"].replace(0, np.nan)
    return pd.DataFrame({
        "k": x["so"] / pa, "bbr": x["bb"] / pa, "hrr": x["hr"] / pa, "sbr": x["sb"] / pa,
        "iso": (x["doubles"] + 2 * x["triples"] + 3 * x["hr"]) / x["ab"].replace(0, np.nan),
        "babip": (x["h"] - x["hr"]) / (x["ab"] - x["so"] - x["hr"] + x["sf"]).replace(0, np.nan),
    }, index=x.index)


def history(path=DUCKDB_PATH) -> pd.DataFrame:
    """One row per hitter and season: MLB and minor-league lines combined (see module notes)."""
    with duckdb.connect(str(path), read_only=True) as con:
        lg = con.sql("select season, team_games from marts.league_seasons").df()
        mlb = con.sql(f"select season, mlbam_id, games, off_runs_neutral as runs, "
                      f"{', '.join(COUNTS)} from marts.player_batting_seasons "
                      "where not is_pitcher").df()
        minor = con.sql("select s.season, s.mlbam_id, s.level, "
                        + ", ".join(f"s.{c}" for c in COUNTS)
                        + ", m.off_runs as runs from staging.stg_mlb__minor_batting s "
                        "join marts.minor_batting_seasons m using (season, mlbam_id, level)").df()
        il = con.sql("select season, mlbam_id, il_days, il_stints, on_60_day "
                     "from marts.player_il_seasons").df()
    scale = mlb["season"].map(dict(zip(lg["season"], 162.0 / lg["team_games"].clip(lower=1),
                                       strict=True)))
    for c in [*COUNTS, "games", "runs"]:
        mlb[c] = mlb[c] * scale
    minor["lvl"] = minor["level"].map(LEVEL) * minor["pa"]
    minor = minor.groupby(["season", "mlbam_id"])[[*COUNTS, "runs", "lvl"]].sum().reset_index()
    minor["milb_level"] = minor["lvl"] / minor["pa"].replace(0, np.nan)
    h = mlb.merge(minor.drop(columns="lvl"), on=["season", "mlbam_id"], how="outer",
                  suffixes=("", "_m"))
    h[[*COUNTS, "runs", "games"]] = h[[*COUNTS, "runs", "games"]].fillna(0)
    for c in [*COUNTS, "runs"]:
        h[c] = h[c] + h[f"{c}_m"].fillna(0)
    h["milb_share"] = h["pa_m"].fillna(0) / h["pa"].replace(0, np.nan)
    h.loc[h["season"] < FIRST_MILB_SEASON, ["milb_share", "milb_level"]] = np.nan
    h["off600"] = h["runs"] / h["pa"].replace(0, np.nan) * 600
    h[RATES] = _rates(h)
    league = _rates(mlb).assign(season=mlb["season"], w=mlb["pa"])
    for c in RATES:                     # against that season's MLB average (PA-weighted)
        ok = league.dropna(subset=[c])
        avg = (ok[c] * ok["w"]).groupby(ok["season"]).sum() / ok["w"].groupby(ok["season"]).sum()
        h[c] = h[c] - h["season"].map(avg)
    return with_il(h, il)[["season", "mlbam_id", *LAGS]]


def _gap_to_best_other(s: pd.Series) -> pd.Series:
    """Each value minus the best other value in its group (NaN alone)."""
    v = s.to_numpy()
    if len(v) < 2:
        return pd.Series(np.nan, s.index)
    top, second = np.sort(v)[::-1][:2]
    return pd.Series(v - np.where(v == top, second, top), s.index)


def roster_context(rows: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """Where each rostered hitter stands on his team (rows: season, team_id, mlbam_id, pipe,
    marcel_war600; positions: season, mlbam_id, position, games, last season's games as in
    marts.player_position_games): his rank by Marcel's WAR per 600 among the team's hitters and
    among those whose main position last season was his, how many share it, the gap to the best
    of them, and his share of the team's and the position's pipeline PA."""
    main = positions.sort_values("games", ascending=False) \
        .drop_duplicates(["season", "mlbam_id"])[["season", "mlbam_id", "position"]]
    rows = rows.merge(main, on=["season", "mlbam_id"], how="left")
    known = rows["position"].notna()
    q = rows["marcel_war600"].fillna(-5.0)
    team = [rows["season"], rows["team_id"]]
    at = [rows["season"], rows["team_id"], rows["position"].fillna("none")]
    rows["ctx_rank_team"] = q.groupby(team).rank(ascending=False)
    rows["ctx_team_n"] = q.groupby(team).transform("count")
    rows["ctx_team_pipe"] = rows["pipe"].groupby(team).transform("sum")
    rows["ctx_pipe_share"] = rows["pipe"] / rows["ctx_team_pipe"]
    rows["ctx_rank_pos"] = q.groupby(at).rank(ascending=False).where(known)
    rows["ctx_n_pos"] = q.groupby(at).transform("count").where(known)
    rows["ctx_pos_pipe"] = rows["pipe"].groupby(at).transform("sum").where(known)
    rows["ctx_gap_pos"] = q.groupby(at, group_keys=False).apply(_gap_to_best_other).where(known)
    rows["ctx_is_c"] = (rows["position"] == "C").astype(float)
    rows["ctx_no_pos"] = (~known).astype(float)
    return rows.drop(columns="position")


def frames(batters: pd.DataFrame, roster: pd.DataFrame, path=DUCKDB_PATH) -> pd.DataFrame:
    """PA rows: every Marcel hitter projection on an Opening Day roster, with inputs, target y
    (actual PA, 0 if none; unknown for the upcoming season) and weight vol (1)."""
    from bucco.models.player_inputs import on_rosters

    with duckdb.connect(str(path), read_only=True) as con:
        status = con.sql("select season, mlbam_id, il_group "
                         "from marts.player_preseason_status").df()
        actual = con.sql("select season, mlbam_id, pa as act_pa from marts.player_batting_seasons "
                         "where not is_pitcher").df()
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
    b = batters[["season", "mlbam_id", "age", "pa", "off_runs", "def_runs", "war"]].copy()
    pa = b["pa"].where(b["pa"] > 0)
    b["marcel_off600"] = b["off_runs"] / pa * 600
    b["marcel_def600"] = b["def_runs"] / pa * 600
    b["marcel_war600"] = b["war"] / pa * 600
    b = lagged(b.drop(columns=["pa", "off_runs", "def_runs", "war"]), history(path), LAGS,
               VOLUMES)
    on = on_rosters(batters[["season", "mlbam_id", "pa"]], roster, "batter")
    rows = on[["season", "mlbam_id", "team_id", "pa"]].rename(columns={"pa": "pipe"}) \
        .drop_duplicates(["season", "mlbam_id"]).merge(b, on=["season", "mlbam_id"])
    rows = roster_context(rows, positions)
    rows = opening_day(rows, status).merge(actual, on=["season", "mlbam_id"], how="left")
    last = int(actual["season"].max())
    rows["y"] = rows["act_pa"].fillna(0.0).where(rows["season"] <= last)
    rows["vol"] = 1.0
    return rows.drop(columns="act_pa")


def fit_and_save(path=DUCKDB_PATH, out=PREDICTIONS, features=None) -> pd.DataFrame:
    """Fit the PA model walk-forward for every season from FIRST_PREDICTED to the upcoming one and
    save season, mlbam_id, ml_pa to `out` (None: don't save). Holdout scores (model against the
    pipeline's PA) are in .attrs["scores"]."""
    from bucco.models.player_inputs import (
        marcel_projections,
        marcel_rosters,
        staff_projection_settings,
    )

    batters, _ = marcel_projections(*staff_projection_settings(), path=path)
    rows = frames(batters, marcel_rosters("mlb", path), path)
    upcoming = int(batters["season"].max())
    targets = [t for t in range(FIRST_PREDICTED, upcoming + 1) if t != 2020]
    train = rows[(rows["season"] >= FIRST_TRAIN) & rows["y"].notna()]
    log.info("Fitting hitter PA")
    pred = walk_forward(train, rows, features or PA_FEATURES, targets, centered=False)
    pred["pred"] = pred["pred"].clip(lower=0.0)
    scores = score(pred, rows, centered=False, baseline="pipe")
    preds = pred.rename(columns={"pred": "ml_pa"})
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        preds.to_parquet(out)
    preds.attrs["scores"] = scores
    return preds


def load_predictions(path=PREDICTIONS) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco fit-ml --targets hitters` first.")
    return pd.read_parquet(path)


def apply(batters: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    """Marcel hitter projections with the learned PA (ml_pa) where there are any: offense,
    defense, fielding, baserunning and WAR scale with the PA, so rates are Marcel's."""
    b = batters.merge(preds[["season", "mlbam_id", "ml_pa"]]
                      .drop_duplicates(["season", "mlbam_id"]),
                      on=["season", "mlbam_id"], how="left")
    new = b["ml_pa"].fillna(b["pa"])
    f = (new / b["pa"].where(b["pa"] > 0)).fillna(0.0)
    for c in ("off_runs", "def_runs", "fld_runs", "bsr", "war"):
        if c in b:
            b[c] = b[c] * f
    b["pa"] = new
    return b.drop(columns="ml_pa")
