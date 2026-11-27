"""Shared machinery for the learned player models: walk-forward fitting with per-season tuning,
lagged history, Opening Day status, and player-level scores.

Every model is a gradient-boosted tree regressor (scikit-learn's HistGradientBoostingRegressor)
fitted walk-forward: a target season's model sees only earlier seasons. Its settings are chosen
for each target season on the two seasons before it, from `GRID` (18 settings of leaves, rows per
leaf and trees; the first is the most complex), fitted on the seasons before those. Training rows
are weighted toward recent seasons (x DECAY per year back) and by each row's `vol`.
"""

from __future__ import annotations

import itertools
import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

log = logging.getLogger(__name__)

GRID = [{"max_leaf_nodes": a, "min_samples_leaf": b, "max_iter": c}
        for a, b, c in itertools.product((15, 7, 4), (40, 100, 200), (300, 150))]
DECAY = 0.9
LEARNING_RATE = 0.05
L2 = 1.0
SHORTENED = {2020}
LEVEL = {"AAA": 1, "AA": 2, "A+": 3, "A": 4}     # minor-league levels, highest first
IL_COLUMNS = ("il_days", "il_stints", "on_60_day")
FIRST_IL_SEASON = 2009                            # injured-list history is known from here
FIRST_MILB_SEASON = 2006                          # minor-league lines are known from here
OPENING_DAY = ["on_40", "od_il_60", "od_il_short", "prev_il_60", "prev_il_short", "prev_on_40"]


def lagged(rows: pd.DataFrame, hist: pd.DataFrame, cols: list[str],
           volumes: tuple[str, ...] = ()) -> pd.DataFrame:
    """`rows` (season, mlbam_id, ...) with `hist`'s `cols` for the three seasons before, as
    y1_*, y2_*, y3_*. `volumes` (playing-time columns) are 0, not unknown, for a season with no
    line."""
    out = rows.copy()
    for k in (1, 2, 3):
        x = hist[["season", "mlbam_id", *cols]].assign(season=hist["season"] + k)
        out = out.merge(x.rename(columns={c: f"y{k}_{c}" for c in cols}),
                        on=["season", "mlbam_id"], how="left")
        for c in volumes:
            out[f"y{k}_{c}"] = out[f"y{k}_{c}"].fillna(0)
    return out


def with_il(g: pd.DataFrame, il: pd.DataFrame) -> pd.DataFrame:
    """History rows with injured-list days, stints and 60-day stints: 0 if none from
    FIRST_IL_SEASON, unknown before."""
    g = g.merge(il, on=["season", "mlbam_id"], how="left")
    known = g["season"] >= FIRST_IL_SEASON
    for c in IL_COLUMNS:
        g[c] = g[c].where(~known, g[c].fillna(0))
    return g


def opening_day(rows: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    """Opening Day flags this season and last (status: season, mlbam_id, il_group, one row per
    40-man player): on the 40-man, on the 60-day or a short injured list. Last season's are
    unknown for the first roster season. on_40 is constant (so unused) for 40-man rows."""
    st = status.rename(columns={"il_group": "od"})
    prev = st.assign(season=st["season"] + 1).rename(columns={"od": "od_prev"})
    rows = rows.merge(st, on=["season", "mlbam_id"], how="left") \
        .merge(prev, on=["season", "mlbam_id"], how="left")
    for g in ("il_60", "il_short"):
        rows[f"od_{g}"] = (rows["od"] == g).astype(float)
        rows[f"prev_{g}"] = (rows["od_prev"] == g).astype(float)
    rows["on_40"] = rows["od"].notna().astype(float)
    rows["prev_on_40"] = rows["od_prev"].notna().astype(float)
    first = status["season"].min()
    rows.loc[rows["season"] <= first, ["prev_il_60", "prev_il_short", "prev_on_40"]] = np.nan
    return rows.drop(columns=["od", "od_prev"])


class Fitted:
    """A model fitted on the inputs that vary in its training rows."""

    def __init__(self, model, cols):
        self.model, self.cols = model, cols

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return self.model.predict(x[self.cols])


def fit(train: pd.DataFrame, feats: list[str], params: dict, target: int) -> Fitted:
    weight = train["vol"] * DECAY ** (target - 1 - train["season"])
    cols = [c for c in feats if train[c].nunique(dropna=True) >= 2]
    model = HistGradientBoostingRegressor(learning_rate=LEARNING_RATE, l2_regularization=L2,
                                          random_state=0, **params)
    return Fitted(model.fit(train[cols], train["y"], sample_weight=weight), cols)


def rmse(pred, rows: pd.DataFrame, centered: bool) -> float:
    """RMSE weighted by `vol`; `centered` removes each season's (vol-weighted) mean from both."""
    p, y = pd.Series(np.asarray(pred), rows.index), rows["y"]
    w = rows["vol"]
    if centered:
        def center(s):
            return s - (s * w).groupby(rows["season"]).transform("sum") \
                / w.groupby(rows["season"]).transform("sum")
        p, y = center(p), center(y)
    return float(np.sqrt(np.average((p - y) ** 2, weights=w)))


def walk_forward(train_rows: pd.DataFrame, predict_rows: pd.DataFrame, feats: list[str],
                 targets, centered: bool, grid: list[dict] | None = None) -> pd.DataFrame:
    """For each target season: choose `grid` settings (default GRID) on the two seasons before it
    (fitted on the seasons before those), refit on every season before it and predict
    `predict_rows` of that season. train_rows need season, y, vol and the features. Returns
    season, mlbam_id, pred."""
    grid = grid or GRID
    usable = train_rows[~train_rows["season"].isin(SHORTENED)]
    out = []
    for t in targets:
        prior = sorted(s for s in usable["season"].unique() if s < t)
        val_seasons = prior[-2:]
        fit_rows = usable[usable["season"] < min(val_seasons)]
        val = usable[usable["season"].isin(val_seasons)]
        scores = [rmse(fit(fit_rows, feats, p, min(val_seasons)).predict(val), val, centered)
                  for p in grid]
        best = grid[int(np.argmin(scores))]
        model = fit(usable[usable["season"] < t], feats, best, t)
        rows = predict_rows[predict_rows["season"] == t]
        out.append(rows[["season", "mlbam_id"]].assign(pred=model.predict(rows)))
        log.info("%d: %s", t, best)
    return pd.concat(out, ignore_index=True)


def score(pred: pd.DataFrame, rows: pd.DataFrame, centered: bool,
          baseline: str | None = None) -> pd.DataFrame:
    """Holdout RMSE of walk-forward predictions (season, mlbam_id, pred) against `rows` (season,
    mlbam_id, y, vol and `baseline`, the input being improved on), overall and by season, for
    completed seasons other than SHORTENED."""
    x = rows.merge(pred, on=["season", "mlbam_id"])
    x = x[x["y"].notna() & ~x["season"].isin(SHORTENED)]
    cols = {"model": "pred"} | ({"baseline": baseline} if baseline else {})
    out = {"all": {k: rmse(x[c], x, centered) for k, c in cols.items()}}
    for s, g in x.groupby("season"):
        out[int(s)] = {k: rmse(g[c], g, centered) for k, c in cols.items()}
    return pd.DataFrame(out).T
