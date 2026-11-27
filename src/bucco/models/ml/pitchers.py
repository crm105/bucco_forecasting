"""Learned pitcher innings and rates, on top of Marcel.

Two models, fitted walk-forward and tuned per target season (bucco.models.ml.core):

* innings: next season's innings for pitchers on a preseason roster (0 if none), with our
  pipeline's innings (baseline innings x availability) as an input. The roster is the Opening Day
  40-man ("mlb", marcel_ml_pitchers) or that plus each organization's minor-league depth
  ("mlb_org": minor leaguers Marcel projects too, most of whom throw no MLB innings; tried, not
  adopted, see docs/R&D/ml_playing_time.md);
* rate: next season's park-neutral FIP-based runs above average per 9 innings, for every pitcher
  Marcel projects, fitted on pitchers who threw 30+ innings (weighted by innings), with Marcel's
  rate as an input.

Inputs, from the three seasons before (`history`): MLB and minor-league lines combined as one
season (batters faced, innings, starts, games, start share, the four FIP run parts per 700
batters faced, against each league), the share of batters faced in the minors and the average
minor-league level, ground-out share against the league, injured-list days, stints and 60-day
stints; plus age, the season, Marcel's start share, rate and WAR per 180 innings, and Opening Day
status this season and last (on the 40-man, on the injured list); the innings model also gets
roster context (`roster_context`: rank in his team's rotation or bullpen). Unknown values (injured list
before 2009, minor leagues before 2006) are left missing; the trees handle them.

Fitting takes about half an hour (longer with organization depth), so `fit_and_save` (`bucco
fit-ml --targets pitchers [--roster mlb_org]`) saves every season's predictions to
PREDICTIONS[roster]; `apply` swaps them into Marcel's pitcher projections. Innings are learned
from 2012 (the first season with two earlier roster seasons to tune on); earlier seasons
keep the pipeline's. See docs/R&D/ml_playing_time.md.
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
    SHORTENED,
    lagged,
    opening_day,
    score,
    walk_forward,
    with_il,
)

log = logging.getLogger(__name__)

PREDICTIONS = {"mlb": CACHE_DIR / "derived" / "ml_pitchers.parquet",
               "mlb_org": CACHE_DIR / "derived" / "ml_pitchers_org.parquet"}
FIRST_PREDICTED = 2012          # first season with learned values
FIRST_TRAIN = {"innings": 2009, "rate": 2004}
MIN_RATE_IP = 30.0
PARTS = ["k_runs", "bb_runs", "hr_runs", "other_runs"]
LAGS = ["bf", "ip", "gs", "games", "gs_share", "milb_share", "milb_level", "k700", "bb700",
        "hr700", "other700", "go", "il_days", "il_stints", "on_60_day"]
VOLUMES = ("bf", "ip", "gs", "games")


def history(path=DUCKDB_PATH) -> pd.DataFrame:
    """One row per pitcher and season: MLB and minor-league lines combined (see module notes)."""
    with duckdb.connect(str(path), read_only=True) as con:
        lg = con.sql("select season, team_games from marts.league_seasons").df()
        mlb = con.sql("select season, mlbam_id, bf, outs, gs, games, ground_outs, air_outs, "
                + ", ".join(f"{p}_neutral as {p}" for p in PARTS)
                + " from marts.player_pitching_seasons").df()
        minor = con.sql("select season, mlbam_id, level, bf, outs, gs, games, " + ", ".join(PARTS)
                  + " from marts.minor_pitching_seasons").df()
        il = con.sql("select season, mlbam_id, il_days, il_stints, on_60_day "
               "from marts.player_il_seasons").df()
    scale = mlb["season"].map(dict(zip(lg["season"], 162.0 / lg["team_games"].clip(lower=1),
                                       strict=True)))
    for c in ["bf", "outs", "gs", "games", *PARTS]:
        mlb[c] = mlb[c] * scale
    minor["lvl"] = minor["level"].map(LEVEL) * minor["bf"]
    minor = minor.groupby(["season", "mlbam_id"])[["bf", "outs", "gs", "games", "lvl", *PARTS]] \
        .sum().reset_index()
    minor["milb_level"] = minor["lvl"] / minor["bf"].replace(0, np.nan)
    g = mlb.merge(minor.drop(columns="lvl"), on=["season", "mlbam_id"], how="outer",
                  suffixes=("", "_m"))
    for c in ["bf", "outs", "gs", "games", *PARTS]:
        g[c] = g[c].fillna(0) + g[f"{c}_m"].fillna(0)
    g["milb_share"] = g["bf_m"].fillna(0) / g["bf"].replace(0, np.nan)
    g.loc[g["season"] < FIRST_MILB_SEASON, ["milb_share", "milb_level"]] = np.nan
    bf = g["bf"].replace(0, np.nan)
    for p in PARTS:
        g[p.replace("_runs", "700")] = g[p] / bf * 700
    g["ip"] = g["outs"] / 3
    g["gs_share"] = g["gs"] / g["games"].replace(0, np.nan)
    go = mlb["ground_outs"] / (mlb["ground_outs"] + mlb["air_outs"]).replace(0, np.nan)
    lg_go = mlb.assign(go=go).dropna(subset=["go"]).groupby("season").apply(
        lambda x: np.average(x["go"], weights=x["bf"]) if x["bf"].sum() > 0 else np.nan,
        include_groups=False)
    g["go"] = g["ground_outs"] / (g["ground_outs"] + g["air_outs"]).replace(0, np.nan) \
        - g["season"].map(lg_go)
    g = with_il(g, il)
    return g[["season", "mlbam_id", *LAGS]]


def roster_context(rows: pd.DataFrame) -> pd.DataFrame:
    """Where each rostered pitcher stands on his team (rows: season, team_id, mlbam_id, pipe,
    start_share, marcel_war180): his rank by Marcel's WAR per 180 innings on the staff and among
    its starters (start share 0.5 or more) or relievers, how many of each there are, a starter's
    gap to the team's fifth-best starter, his share of the team's pipeline innings and the
    starters' pipeline innings."""
    q = rows["marcel_war180"].fillna(-5.0)
    team = [rows["season"], rows["team_id"]]
    sp = rows["start_share"] >= 0.5
    rows = rows.assign(ctx_sp=sp.astype(float))
    rows["ctx_rank_team"] = q.groupby(team).rank(ascending=False)
    rows["ctx_rot_rank"] = q.where(sp).groupby(team).rank(ascending=False)
    rows["ctx_rp_rank"] = q.where(~sp).groupby(team).rank(ascending=False)
    rows["ctx_n_sp"] = sp.groupby(team).transform("sum")
    rows["ctx_n_rp"] = (~sp).groupby(team).transform("sum")
    rows["ctx_team_pipe"] = rows["pipe"].groupby(team).transform("sum")
    rows["ctx_pipe_share"] = rows["pipe"] / rows["ctx_team_pipe"]
    fifth = q.where(sp).groupby(team).transform(
        lambda s: s.nlargest(5).min() if s.notna().sum() >= 5 else np.nan)
    rows["ctx_gap5"] = (q - fifth).where(sp)
    rows["ctx_rot_ip"] = rows["pipe"].where(sp).groupby(team).transform("sum")
    return rows


def frames(pitchers: pd.DataFrame, roster: pd.DataFrame,
           path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(rate rows: every Marcel pitcher projection; innings rows: those on `roster`),
    with inputs, target y (NaN for the upcoming season) and weight vol."""
    from bucco.models.player_inputs import on_rosters

    with duckdb.connect(str(path), read_only=True) as con:
        status = con.sql("select season, mlbam_id, il_group "
                         "from marts.player_preseason_status").df()
        actual = con.sql("select season, mlbam_id, outs / 3.0 as act_ip, "
                         "pitching_runs_neutral as act_runs "
                         "from marts.player_pitching_seasons").df()
    hist = history(path)
    p = pitchers[["season", "mlbam_id", "age", "ip", "runs_per_ip", "war", "start_share"]].copy()
    p["marcel_fip9"] = p["runs_per_ip"] * 9
    p["marcel_war180"] = p["war"] / p["ip"].where(p["ip"] > 0) * 180
    p = lagged(p.drop(columns=["runs_per_ip", "war"]), hist, LAGS, VOLUMES)
    p = p.merge(actual, on=["season", "mlbam_id"], how="left")
    last = int(actual["season"].max())
    rate = p.copy()
    rate["y"] = rate["act_runs"] / rate["act_ip"].where(rate["act_ip"] > 0) * 9
    rate["vol"] = rate["act_ip"]
    on = on_rosters(pitchers[["season", "mlbam_id", "ip"]], roster, "pitcher")
    inn = on[["season", "mlbam_id", "team_id", "ip"]].rename(columns={"ip": "pipe"}) \
        .drop_duplicates(["season", "mlbam_id"]).merge(p.drop(columns="ip"),
                                                       on=["season", "mlbam_id"])
    inn = opening_day(roster_context(inn), status)
    inn["y"] = inn["act_ip"].fillna(0.0).where(inn["season"] <= last)
    inn["vol"] = 1.0
    return rate, inn


RATE_FEATURES = ["age", "season", "start_share"] + [f"y{k}_{c}" for k in (1, 2, 3) for c in LAGS]
CONTEXT = ["ctx_rank_team", "ctx_sp", "ctx_rot_rank", "ctx_n_sp", "ctx_rp_rank", "ctx_n_rp",
           "ctx_pipe_share", "ctx_team_pipe", "ctx_gap5", "ctx_rot_ip"]
INNINGS_FEATURES = ["age", "season", "start_share", "marcel_fip9", "marcel_war180", *CONTEXT,
                    *OPENING_DAY] + [f"y{k}_{c}" for k in (1, 2, 3) for c in LAGS]


def fit_and_save(path=DUCKDB_PATH, out=None, roster_source: str = "mlb",
                 save: bool = True) -> pd.DataFrame:
    """Fit both models walk-forward for every season from FIRST_PREDICTED to the upcoming one
    and save season, mlbam_id, ml_ip (pitchers on `roster_source`'s rosters) and ml_runs9 to
    `out` (default PREDICTIONS[roster_source]; not saved without `save`). Holdout scores (each
    model against Marcel's or the pipeline's value) are in .attrs["scores"]."""
    if roster_source not in PREDICTIONS:
        raise ValueError(f"roster_source must be one of {sorted(PREDICTIONS)}")
    out = out or PREDICTIONS[roster_source]
    from bucco.models.player_inputs import (
        marcel_projections,
        marcel_rosters,
        staff_projection_settings,
    )

    _, pitchers = marcel_projections(*staff_projection_settings(), path=path)
    rate, inn = frames(pitchers, marcel_rosters(roster_source, path), path)
    upcoming = int(pitchers["season"].max())
    targets = range(FIRST_PREDICTED, upcoming + 1)
    targets = [t for t in targets if t not in SHORTENED]
    rate_train = rate[(rate["season"] >= FIRST_TRAIN["rate"]) & (rate["vol"] >= MIN_RATE_IP)]
    log.info("Fitting pitcher rates")
    runs9 = walk_forward(rate_train, rate, RATE_FEATURES + ["marcel_fip9"], targets, True)
    inn_train = inn[(inn["season"] >= FIRST_TRAIN["innings"]) & inn["y"].notna()]
    log.info("Fitting pitcher innings")
    ip = walk_forward(inn_train, inn, INNINGS_FEATURES + ["pipe"], targets, False)
    preds = runs9.rename(columns={"pred": "ml_runs9"}).merge(
        ip.rename(columns={"pred": "ml_ip"}), on=["season", "mlbam_id"], how="outer")
    preds["ml_ip"] = preds["ml_ip"].clip(lower=0.0)
    scored = rate[rate["vol"] >= MIN_RATE_IP]
    scores = {"rate": score(runs9, scored, centered=True, baseline="marcel_fip9"),
              "innings": score(ip.assign(pred=ip["pred"].clip(lower=0.0)), inn, centered=False,
                               baseline="pipe")}
    if save:
        out.parent.mkdir(parents=True, exist_ok=True)
        preds.to_parquet(out)
    preds.attrs["scores"] = scores
    return preds


def load_predictions(roster_source: str = "mlb", path=None) -> pd.DataFrame:
    path = path or PREDICTIONS[roster_source]
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco fit-ml --targets pitchers` first.")
    return pd.read_parquet(path)


def apply(pitchers: pd.DataFrame, preds: pd.DataFrame) -> pd.DataFrame:
    """Marcel pitcher projections with the learned innings (ml_ip) and rates (ml_runs9) where
    there are any: runs, WAR and starts follow; the replacement level stays by start share."""
    p = pitchers.merge(preds[["season", "mlbam_id", "ml_ip", "ml_runs9"]]
                       .drop_duplicates(["season", "mlbam_id"]),
                       on=["season", "mlbam_id"], how="left")
    new_ip = p["ml_ip"].fillna(p["ip"])
    f = (new_ip / p["ip"].where(p["ip"] > 0)).fillna(0.0)
    old_rate = p["runs_per_ip"].copy()
    p["runs_per_ip"] = p["ml_runs9"].div(9).fillna(old_rate)
    p["gs"] = p["gs"] * f
    if "bf" in p:
        p["bf"] = p["bf"] * f
    p["ip"] = new_ip
    p["runs"] = p["runs_per_ip"] * p["ip"]
    rep = p["rp_rep_per_ip"] + (p["sp_rep_per_ip"] - p["rp_rep_per_ip"]) * p["start_share"]
    p["war"] = (p["runs"] + rep * p["ip"]) / p["runs_per_win"]
    if "fip" in p:                       # FIP moves opposite to runs above average
        p["fip"] = p["fip"] - 9 * (p["runs_per_ip"] - old_rate)
    return p.drop(columns=["ml_ip", "ml_runs9"])
