"""Learned pitcher innings and rates (gradient-boosted trees), on top of Marcel.

Two models, each fitted walk-forward (a target season's model sees only earlier seasons) and
tuned for each target season on the two seasons before it (`GRID`: 18 settings of leaves, rows
per leaf and trees; the first is the most complex):

* innings: next season's innings for pitchers on an Opening Day 40-man roster (0 if none), with
  our pipeline's innings (baseline innings x availability) as an input;
* rate: next season's park-neutral FIP-based runs above average per 9 innings, for every pitcher
  Marcel projects, fitted on pitchers who threw 30+ innings (weighted by innings), with Marcel's
  rate as an input.

Inputs, from the three seasons before (`history`): MLB and minor-league lines combined as one
season (batters faced, innings, starts, games, start share, the four FIP run parts per 700
batters faced, against each league), the share of batters faced in the minors and the average
minor-league level, ground-out share against the league, injured-list days, stints and 60-day
stints; plus age, the season, Marcel's start share, rate and WAR per 180 innings, and Opening Day
injured-list status this season and last. Training rows are weighted toward recent seasons
(x DECAY per year back). Unknown values (injured list before 2009, minor leagues before 2006) are
left missing; the trees handle them.

Fitting takes about an hour, so `fit_and_save` (`bucco fit-ml-pitchers`) saves every season's
predictions to PREDICTIONS; `apply` swaps them into Marcel's pitcher projections. Innings are
learned from 2012 (the first season with two earlier roster seasons to tune on); earlier seasons
keep the pipeline's. See docs/R&D/ml_playing_time.md.
"""

from __future__ import annotations

import itertools
import logging

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from bucco.config import CACHE_DIR, DUCKDB_PATH

log = logging.getLogger(__name__)

PREDICTIONS = CACHE_DIR / "derived" / "ml_pitchers.parquet"
GRID = [{"max_leaf_nodes": a, "min_samples_leaf": b, "max_iter": c}
        for a, b, c in itertools.product((15, 7, 4), (40, 100, 200), (300, 150))]
DECAY = 0.9
LEARNING_RATE = 0.05
L2 = 1.0
FIRST_PREDICTED = 2012          # first season with learned values
FIRST_TRAIN = {"innings": 2009, "rate": 2004}
MIN_RATE_IP = 30.0
LEVEL = {"AAA": 1, "AA": 2, "A+": 3, "A": 4}
PARTS = ["k_runs", "bb_runs", "hr_runs", "other_runs"]
LAGS = ["bf", "ip", "gs", "games", "gs_share", "milb_share", "milb_level", "k700", "bb700",
        "hr700", "other700", "go", "il_days", "il_stints", "on_60_day"]
OPENING_DAY = ["od_il_60", "od_il_short", "prev_il_60", "prev_il_short", "prev_on_40"]
SHORTENED = {2020}


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
    g.loc[g["season"] < 2006, ["milb_share", "milb_level"]] = np.nan
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
    g = g.merge(il, on=["season", "mlbam_id"], how="left")
    known = g["season"] >= 2009
    for c in ("il_days", "il_stints", "on_60_day"):
        g[c] = g[c].where(~known, g[c].fillna(0))
    return g[["season", "mlbam_id", *LAGS]]


def lagged(rows: pd.DataFrame, hist: pd.DataFrame) -> pd.DataFrame:
    """`rows` (season, mlbam_id, ...) with the three seasons before as y1_*, y2_*, y3_*."""
    out = rows.copy()
    for k in (1, 2, 3):
        x = hist.assign(season=hist["season"] + k)
        out = out.merge(x.rename(columns={c: f"y{k}_{c}" for c in LAGS}),
                        on=["season", "mlbam_id"], how="left")
        for c in ("bf", "ip", "gs", "games"):
            out[f"y{k}_{c}"] = out[f"y{k}_{c}"].fillna(0)
    return out


def opening_day(rows: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    """Opening Day injured-list flags this season and last (status: season, mlbam_id,
    il_group); last season's are unknown for the first roster season."""
    st = status.rename(columns={"il_group": "od"})
    prev = st.assign(season=st["season"] + 1).rename(columns={"od": "od_prev"})
    rows = rows.merge(st, on=["season", "mlbam_id"], how="left") \
        .merge(prev, on=["season", "mlbam_id"], how="left")
    for g in ("il_60", "il_short"):
        rows[f"od_{g}"] = (rows["od"] == g).astype(float)
        rows[f"prev_{g}"] = (rows["od_prev"] == g).astype(float)
    rows["prev_on_40"] = rows["od_prev"].notna().astype(float)
    first = status["season"].min()
    rows.loc[rows["season"] <= first, ["prev_il_60", "prev_il_short", "prev_on_40"]] = np.nan
    return rows.drop(columns=["od", "od_prev"])


class _Fitted:
    """A model fitted on the inputs that vary in its training rows."""

    def __init__(self, model, cols):
        self.model, self.cols = model, cols

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return self.model.predict(x[self.cols])


def _fit(train: pd.DataFrame, feats: list[str], params: dict, target: int) -> _Fitted:
    weight = train["vol"] * DECAY ** (target - 1 - train["season"])
    cols = [c for c in feats if train[c].nunique(dropna=True) >= 2]
    model = HistGradientBoostingRegressor(learning_rate=LEARNING_RATE, l2_regularization=L2,
                                          random_state=0, **params)
    return _Fitted(model.fit(train[cols], train["y"], sample_weight=weight), cols)


def _rmse(pred: np.ndarray, rows: pd.DataFrame, centered: bool) -> float:
    p, y = pd.Series(pred, rows.index), rows["y"]
    w = rows["vol"]
    if centered:
        def center(s):
            return s - (s * w).groupby(rows["season"]).transform("sum") \
                / w.groupby(rows["season"]).transform("sum")
        p, y = center(p), center(y)
    return float(np.sqrt(np.average((p - y) ** 2, weights=w)))


def walk_forward(train_rows: pd.DataFrame, predict_rows: pd.DataFrame, feats: list[str],
                 targets, centered: bool) -> pd.DataFrame:
    """For each target season: choose GRID settings on the two seasons before it (fitted on the
    seasons before those), refit on every season before it and predict `predict_rows` of that
    season. train_rows need season, y, vol and the features."""
    usable = train_rows[~train_rows["season"].isin(SHORTENED)]
    out = []
    for t in targets:
        prior = sorted(s for s in usable["season"].unique() if s < t)
        val_seasons = prior[-2:]
        fit_rows = usable[usable["season"] < min(val_seasons)]
        val = usable[usable["season"].isin(val_seasons)]
        scores = [_rmse(_fit(fit_rows, feats, p, min(val_seasons)).predict(val), val, centered)
                  for p in GRID]
        best = GRID[int(np.argmin(scores))]
        model = _fit(usable[usable["season"] < t], feats, best, t)
        rows = predict_rows[predict_rows["season"] == t]
        out.append(rows[["season", "mlbam_id"]].assign(pred=model.predict(rows)))
        log.info("%d: %s", t, best)
    return pd.concat(out, ignore_index=True)


def frames(pitchers: pd.DataFrame, roster: pd.DataFrame,
           path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(rate rows: every Marcel pitcher projection; innings rows: those on a preseason roster),
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
    p = lagged(p.drop(columns=["runs_per_ip", "war"]), hist)
    p = p.merge(actual, on=["season", "mlbam_id"], how="left")
    last = int(actual["season"].max())
    rate = p.copy()
    rate["y"] = rate["act_runs"] / rate["act_ip"].where(rate["act_ip"] > 0) * 9
    rate["vol"] = rate["act_ip"]
    on = on_rosters(pitchers[["season", "mlbam_id", "ip"]], roster, "pitcher")
    inn = opening_day(on[["season", "mlbam_id", "ip"]].rename(columns={"ip": "pipe"})
                      .drop_duplicates(["season", "mlbam_id"])
                      .merge(p.drop(columns="ip"), on=["season", "mlbam_id"]), status)
    inn["y"] = inn["act_ip"].fillna(0.0).where(inn["season"] <= last)
    inn["vol"] = 1.0
    return rate, inn


RATE_FEATURES = ["age", "season", "start_share"] + [f"y{k}_{c}" for k in (1, 2, 3) for c in LAGS]
INNINGS_FEATURES = ["age", "season", "start_share", "marcel_fip9", "marcel_war180",
                    *OPENING_DAY] + [f"y{k}_{c}" for k in (1, 2, 3) for c in LAGS]


def fit_and_save(path=DUCKDB_PATH, out=PREDICTIONS) -> pd.DataFrame:
    """Fit both models walk-forward for every season from FIRST_PREDICTED to the upcoming one
    and save season, mlbam_id, ml_ip (rostered pitchers) and ml_runs9 to `out`."""
    from bucco.models.player_inputs import (
        marcel_projections,
        marcel_rosters,
        staff_projection_settings,
    )

    _, pitchers = marcel_projections(*staff_projection_settings(), path=path)
    rate, inn = frames(pitchers, marcel_rosters("mlb", path), path)
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
    out.parent.mkdir(parents=True, exist_ok=True)
    preds.to_parquet(out)
    return preds


def load_predictions(path=PREDICTIONS) -> pd.DataFrame:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco fit-ml-pitchers` first.")
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
