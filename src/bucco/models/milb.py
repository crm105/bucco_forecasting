"""Major-league equivalents (MLEs) of minor-league batting, for Marcel.

Each minor-league line is valued against its own league (marts.minor_batting_seasons: batting
plus stolen-base runs above the league average, with MLB run values). It is translated to MLB
by adding the level's drop in runs per PA:

    MLE runs = runs above league average + drop(level) x PA

The drops are chained level by level from players who played at two adjacent levels in the same
season (100+ PA at the lower one, 50+ at the higher): Single-A to High-A, High-A to Double-A,
Double-A to Triple-A and Triple-A to MLB (park-neutral Off), each the PA-weighted mean
difference in runs per PA (harmonic-mean weights). A level's drop is the sum of the steps above
it. On 2009-2026, per 600 PA: Triple-A -27, Double-A -45, High-A -64, Single-A -83; each step is
the same in both eras and with 50 or 100 PA. The steps are refitted for each target season on
earlier seasons only. Players promoted in mid-season were often promoted because they were hot,
so those drops are too harsh: projections built on them came out 11 to 17 runs per 600 PA low
for rookies. They are scaled by DROP_SCALE (0.5), chosen with Marcel's weight for minor-league
PA (MILB_WEIGHT) on next-season Off of players with little MLB history. The translation keeps
the player's whole margin over his league (slope 1): Marcel's own regression does the
shrinking.

See docs/R&D/milb.md.
"""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pandas as pd

CHAIN = ("A", "A+", "AA", "AAA", "MLB")
MIN_LOW_PA = 100.0           # PA at the lower level for a pair (keeps out rehab stints)
MIN_HIGH_PA = 50.0
MIN_PAIRS = 100              # pairs a step needs before it is used
ROOKIE_MIN_PA = 100.0        # minor-league PA over three seasons to project a player with no MLB
DROP_SCALE = 0.5             # share of the fitted drops used (see the module notes)
MILB_WEIGHT = 0.5            # Marcel's weight for a minor-league PA (an MLB PA is 1)
ROOKIE_MIN_BF = 100.0        # minor-league batters faced over three seasons, for pitchers
PITCHER_DROP_SCALE = 0.5     # as DROP_SCALE, for pitchers (chosen at player level, see milb.md)
PITCHER_MILB_WEIGHT = 0.5    # Marcel's weight for a minor-league batter faced


def fit_drops(lines: pd.DataFrame, before: int) -> dict[str, float]:
    """Drop in runs per PA from each level to MLB, from seasons before `before`. lines: season,
    mlbam_id, level (CHAIN, MLB included), pa, off_runs. A step with too few pairs makes the
    levels below it unusable (NaN)."""
    h = lines[lines["season"] < before]
    steps = {}
    for lo, hi in pairwise(CHAIN):
        p = h[h["level"] == lo].merge(h[h["level"] == hi], on=["season", "mlbam_id"],
                                      suffixes=("_lo", "_hi"))
        p = p[(p["pa_lo"] >= MIN_LOW_PA) & (p["pa_hi"] >= MIN_HIGH_PA)]
        if len(p) < MIN_PAIRS:
            steps[lo] = np.nan
            continue
        w = 2.0 / (1.0 / p["pa_lo"] + 1.0 / p["pa_hi"])
        d = p["off_runs_hi"] / p["pa_hi"] - p["off_runs_lo"] / p["pa_lo"]
        steps[lo] = float(np.average(d, weights=w))
    drops, total = {}, 0.0
    for lo in reversed(CHAIN[:-1]):
        total += steps[lo]
        drops[lo] = total
    return drops


def milb_history(minor: pd.DataFrame, mlb: pd.DataFrame, targets, volume: str = "pa",
                 runs: str = "off_runs", extra: tuple[str, ...] = (),
                 drop_scale: float | None = None) -> pd.DataFrame:
    """Translated minor-league history for each target season: season (the target), mlbam_id,
    y1-y3_milb_<volume> and y1-y3_milb_runs (MLE runs, seasons t-1 to t-3), the same for each of
    `extra` (summed as they are, e.g. outs, starts), milb_age (his age in the target season, from
    the minor-league lines) and milb_name.

    Batters: minor = marts.minor_batting_seasons (pa, off_runs), mlb = MLB batting (pa, off_runs:
    park-neutral Off). Pitchers: volume "bf", runs "pitching_runs" (FIP-based runs above the
    league), extra ("outs", "gs", "games"). The drops are fitted on runs per unit of volume."""
    scale = DROP_SCALE if drop_scale is None else drop_scale
    lines = pd.concat([minor[["season", "mlbam_id", "level", volume, runs]],
                       mlb[["season", "mlbam_id", volume, runs]].assign(level="MLB")])
    lines = lines.rename(columns={volume: "pa", runs: "off_runs"})
    out = []
    for t in sorted({int(s) for s in targets}):
        drops = fit_drops(lines, t)
        recent = minor[minor["season"].between(t - 3, t - 1)].copy()
        recent["drop"] = recent["level"].map(drops).astype(float) * scale
        recent = recent[recent["drop"].notna()]
        if recent.empty:
            continue
        recent["k"] = t - recent["season"]
        recent["mle_runs"] = recent[runs] + recent["drop"] * recent[volume]
        values = [volume, "mle_runs", *extra]
        wide = recent.pivot_table(index="mlbam_id", columns="k", values=values,
                                  aggfunc="sum").fillna(0.0)
        frame = pd.DataFrame(index=wide.index)
        for k in (1, 2, 3):
            for v in values:
                name = "runs" if v == "mle_runs" else v
                frame[f"y{k}_milb_{name}"] = wide[v].get(k, 0.0)
        ages = (recent["age"] + recent["k"]).groupby(recent["mlbam_id"]).max()
        names = recent.sort_values("season").groupby("mlbam_id")["player_name"].last()
        frame["milb_age"], frame["milb_name"] = ages, names
        out.append(frame.reset_index().assign(season=t))
    cols = ["season", "mlbam_id",
            *[f"y{k}_milb_{c}" for k in (1, 2, 3) for c in (volume, "runs", *extra)],
            "milb_age", "milb_name"]
    return pd.concat(out, ignore_index=True)[cols] if out else pd.DataFrame(columns=cols)


def rookie_rows(frame: pd.DataFrame, history: pd.DataFrame, mlb_targets: pd.DataFrame,
                upcoming: set[int], volume: str = "pa", min_volume: float = ROOKIE_MIN_PA,
                pitchers: bool = False) -> pd.DataFrame:
    """Projection-frame-like rows for players with minor-league history (`min_volume` or more
    of `volume` over three seasons) but no row in the frame (no MLB history in three seasons):
    no MLB seasons, age and name from the minor-league lines, and their target-season MLB
    columns from `mlb_targets` (every column but season and mlbam_id; 0 if they did not play,
    unknown for an upcoming season). Batter frames get is_pitcher false; pitcher frames
    (`pitchers`) get every MLB season count set to 0."""
    known = set(zip(frame["season"], frame["mlbam_id"], strict=True))
    h = history[[(s, m) not in known for s, m in zip(history["season"], history["mlbam_id"],
                                                    strict=True)]]
    h = h[h[[f"y{k}_milb_{volume}" for k in (1, 2, 3)]].sum(axis=1) >= min_volume]
    rows = pd.DataFrame({"season": h["season"].to_numpy(), "mlbam_id": h["mlbam_id"].to_numpy(),
                         "player_name": h["milb_name"].to_numpy(), "age": h["milb_age"].to_numpy(),
                         "last_team_id": np.nan})
    if not pitchers:
        rows["is_pitcher"] = False
    for col in frame.columns:
        if col.startswith("y") and col[1] in "123" and col not in rows and "_milb_" not in col:
            numeric = pd.api.types.is_numeric_dtype(frame[col])
            count = col.endswith(("_pa", "_team_games")) or (pitchers and numeric)
            rows[col] = 0.0 if count else np.nan
    for k in (1, 2, 3):
        rows[f"y{k}_team_games"] = 162.0
    t = rows[["season", "mlbam_id"]].merge(mlb_targets, on=["season", "mlbam_id"], how="left")
    done = ~rows["season"].isin(upcoming)
    for col in [c for c in mlb_targets.columns if c not in ("season", "mlbam_id")]:
        rows[col] = t[col].where(~done, t[col].fillna(0.0)).to_numpy()
    rows["is_upcoming_season"] = ~done
    rows["milb_rookie"] = True
    return rows
