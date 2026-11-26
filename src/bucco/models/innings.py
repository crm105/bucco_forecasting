"""Baseline innings: how many innings a pitcher is expected to throw, from his past innings,
role and age.

A least-squares line, refitted for every target season on the pitchers on earlier seasons'
preseason rosters (2020 targets left out), of next-season innings on

    the last three seasons' innings (each scaled to 162 games), his weighted share of games
    started (3/2/1), that share times last season's innings, and age, age squared, age times
    last season's innings, age squared times last season's innings and age times whether he is
    a starter.

Pitchers who threw no MLB innings the next season count as 0, so the baseline is an
expectation that includes injuries and lost jobs. On 2013-2026 it scores 37.2 IP RMSE against
43.5 (and a +20 IP bias) for Marcel's 0.5 x last + 0.1 x before + 60 (starter) or 25.
See docs/R&D/pitcher_innings.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FULL_SEASON_GAMES = 162.0
SHARE_WEIGHTS = (3.0, 2.0, 1.0)
PEAK_AGE = 27.0             # ages are centered here
MIN_TRAIN_ROWS = 500        # earlier rostered pitcher-seasons needed to fit the line
FEATURES = ("1", "ip1", "ip2", "ip3", "share", "share_ip1", "a", "a2", "a_ip1", "a2_ip1", "a_sp")
# Rookies (no MLB history; rows marked milb_rookie) get their own line, on last season's
# minor-league innings by level and role (columns m1_<level>_<role>, from the loader) and age:
# a Triple-A starter is far likelier to reach MLB than a Single-A reliever. Opening Day 40-man
# status is the strongest signal (on_40, il_40: on the 40-man roster, active or injured), also
# on its own for upper-level starters (on_40_sp); so rookies' availability is in this line.
ROOKIE_FEATURES = ("1", "m1_aaa_sp", "m1_aaa_rp", "m1_aa_sp", "m1_aa_rp", "m1_low", "a", "a2",
                   "on_40", "il_40", "on_40_sp")


def ip_features(frame: pd.DataFrame) -> pd.DataFrame:
    """season, mlbam_id, age, ip1-ip3 (scaled to 162 games), start share and the model's
    features, from pitcher_projection_frame rows."""
    f = frame.reset_index(drop=True)
    out = pd.DataFrame({"season": f["season"], "mlbam_id": f["mlbam_id"],
                        "age": f["age"].astype(float)})
    gs = games = 0.0
    for k, w in zip((1, 2, 3), SHARE_WEIGHTS, strict=True):
        scale = FULL_SEASON_GAMES / f[f"y{k}_team_games"].fillna(FULL_SEASON_GAMES).clip(lower=1)
        out[f"ip{k}"] = f[f"y{k}_outs"].fillna(0.0) / 3.0 * scale
        gs = gs + w * f[f"y{k}_gs"].fillna(0.0) * scale
        games = games + w * f[f"y{k}_games"].fillna(0.0) * scale
    out["share"] = (gs / games.where(games > 0)).fillna(0.0).clip(0.0, 1.0)
    a = (out["age"] - PEAK_AGE).fillna(0.0)
    sp = (out["share"] >= 0.5).astype(float)
    out["1"] = 1.0
    out["share_ip1"] = out["share"] * out["ip1"]
    out["a"], out["a2"] = a, a ** 2
    out["a_ip1"], out["a2_ip1"] = a * out["ip1"], a ** 2 * out["ip1"]
    out["a_sp"] = a * sp
    for col in ROOKIE_FEATURES:
        if col.startswith(("m1_", "on_40", "il_40")) and col != "on_40_sp":
            out[col] = f[col].fillna(0.0).astype(float) if col in f else 0.0
    out["on_40_sp"] = out["on_40"] * (out["m1_aaa_sp"] + out["m1_aa_sp"])
    out["rookie"] = f["milb_rookie"].fillna(False).astype(bool) if "milb_rookie" in f else False
    if "target_outs" in f:
        out["target_ip"] = f["target_outs"] / 3.0
    return out


def baseline_ip(frame: pd.DataFrame, rostered: pd.Series,
                shortened: set[int] | frozenset[int] = frozenset({2020})) -> pd.Series:
    """Baseline innings for every row of pitcher_projection_frame, each target season's from a
    line fitted only on earlier seasons' rostered pitchers (`rostered`: a boolean per row).
    Rookies (`milb_rookie` rows) get a separate line on ROOKIE_FEATURES, fitted on earlier
    rostered rookies. Seasons with fewer than MIN_TRAIN_ROWS earlier rows get NaN (callers
    fall back)."""
    x = ip_features(frame)
    usable = (rostered.to_numpy() & x["target_ip"].notna().to_numpy()
              & ~x["season"].isin(shortened).to_numpy())
    rookie = x["rookie"].to_numpy()
    out = np.full(len(x), np.nan)
    for group, cols in ((~rookie, list(FEATURES)), (rookie, list(ROOKIE_FEATURES))):
        coef = None
        for season in sorted(x["season"].unique()):
            train = usable & group & (x["season"] < season).to_numpy()
            if train.sum() >= MIN_TRAIN_ROWS:
                coef, *_ = np.linalg.lstsq(x.loc[train, cols].to_numpy(),
                                           x.loc[train, "target_ip"].to_numpy(), rcond=None)
            if coef is not None:
                rows = group & (x["season"] == season).to_numpy()
                out[rows] = x.loc[rows, cols].to_numpy() @ coef
    return pd.Series(np.clip(out, 0.0, None), index=frame.index)



def fit_start_penalty(history: pd.DataFrame, runs: str, before: int) -> float:
    """Runs per inning a pitcher loses by starting rather than relieving, from seasons before
    `before` (player_pitching_seasons: season, mlbam_id, age, games, gs, bf, outs, `runs`).

    Delta method, as for the age curves: for each pitcher with seasons s - 1 and s, the change
    in `runs` per batter faced against the change in his share of games started, with age and
    age squared as controls, weighted by the harmonic mean of the two seasons' batters faced.
    The slope (per unit of start share) is turned into runs per inning with the league's batters
    faced per inning. On 2012-2026 it is about 0.03 (0.27 runs per 9): fewer strikeouts and
    more home runs as a starter. Relievers moved to the rotation are usually the ones who were
    pitching well, so this is likely a little low. Fewer than 100 pairs: 0."""
    h = history[(history["season"] < before) & (history["bf"] > 0) & (history["games"] > 0)]
    h = h.assign(share=h["gs"] / h["games"], rate=h[runs] / h["bf"])
    cols = ["mlbam_id", "season", "age", "share", "rate", "bf"]
    pairs = h[cols].merge(h[cols].assign(season=h["season"] + 1), on=["mlbam_id", "season"],
                          suffixes=("", "_prev"))
    pairs = pairs[pairs["age"].between(20, 40)]
    if len(pairs) < 100:
        return 0.0
    a = pairs["age"].astype(float) - PEAK_AGE
    x = np.c_[np.ones(len(pairs)), pairs["share"] - pairs["share_prev"], a, a ** 2]
    y = (pairs["rate"] - pairs["rate_prev"]).to_numpy()
    w = np.sqrt(2.0 / (1.0 / pairs["bf"] + 1.0 / pairs["bf_prev"])).to_numpy()
    coef, *_ = np.linalg.lstsq(x * w[:, None], y * w, rcond=None)
    bf_per_ip = float(h["bf"].sum() / (h["outs"].sum() / 3.0))
    return max(0.0, -float(coef[1]) * bf_per_ip)


def start_penalties(history: pd.DataFrame, runs: str, seasons) -> dict[int, float]:
    """One starting penalty per target season, each fitted only on seasons before it."""
    return {int(t): fit_start_penalty(history, runs, int(t)) for t in sorted(set(seasons))}
