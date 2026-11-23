"""Fit how a fielder's defense changes when he moves position, from Statcast Outs Above Average.

    uv run python scripts/fit_position_switch.py <folder of Savant OAA CSVs>

Input: Baseball Savant OAA leaderboard CSVs, one per season and position, named
oaa_<season>_<pos>.csv with pos the scorer's number (3 = 1B ... 9 = RF), downloaded from
https://baseballsavant.mlb.com/leaderboard/outs_above_average?type=Fielder&startYear=<season>
&endYear=<season>&split=no&team=&range=year&min=1&pos=<pos>&roles=&viz=hide&csv=true
Innings by position come from staging.stg_mlb__fielding in bucco.duckdb.

OAA is centered on each position's average for the season first (it is not centered as
published: outfielders are all judged on the same plays).

Method (the "delta method" used to build positional adjustments):
1. Same-season pairs. A player-season with a main position p (most innings, >= MIN_MAIN innings)
   and some time at q (>= MIN_OTHER innings). delta = runs per FULL_SEASON innings at q minus at
   p, both relative to the average fielder at that position. Weight: harmonic mean of innings.
2. Additive fit. delta(p -> q) ~ h[p] - h[q], h = how hard a position is (1B fixed at 0),
   by weighted least squares over all pairs. This gives every move an estimate, including rare
   ones.
3. Each move's own average is shrunk toward the additive fit by its weight: the move's weight
   W and a prior weight SHRINK (both in innings), estimate = (W * own + SHRINK * additive) /
   (W + SHRINK).
4. First-time cost. Players who play a position next season that they did not play this season,
   compared with players who stayed put (same change in fielding, allowing for regression to the
   mean), after removing the fitted delta. One number for all moves.

Prints the fitted matrix and writes it to data/derived/position_switch.csv, which the lineup
optimizer reads (`bucco.models.lineup_optimizer.load_switch_matrix`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bucco.config import DATA_DIR, DUCKDB_PATH

POS_CODE = {3: "1B", 4: "2B", 5: "3B", 6: "SS", 7: "LF", 8: "CF", 9: "RF"}
ORDER = ["1B", "2B", "3B", "SS", "LF", "CF", "RF"]
FULL_SEASON = 1350.0     # innings in a full season at one position (about 700 PA)
MIN_MAIN = 300.0         # innings at the main position for a same-season pair
MIN_OTHER = 30.0         # innings at the other position
MIN_STAY = 500.0         # innings at a position in both seasons for the stay-put baseline
MIN_NEW = 150.0          # innings at the new position in the first-time comparison
SHRINK = 2000.0          # prior weight, in innings, pulling each move toward the additive fit
OUTPUT = DATA_DIR / "derived" / "position_switch.csv"


def load(folder: Path) -> pd.DataFrame:
    """Fielding runs per full season, by player, season and position, with innings."""
    frames = []
    for path in sorted(folder.glob("oaa_*_*.csv")):
        _, season, code = path.stem.split("_")
        raw = pd.read_csv(path, encoding="utf-8-sig")
        frames.append(pd.DataFrame({
            "season": int(season), "position": POS_CODE[int(code)],
            "mlbam_id": raw["player_id"].astype("int64"),
            "runs": pd.to_numeric(raw["fielding_runs_prevented"], errors="coerce")}))
    oaa = pd.concat(frames).dropna()
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
        innings = con.sql("select season, mlbam_id, position, sum(innings) as innings "
                          "from staging.stg_mlb__fielding group by 1, 2, 3").df()
    df = oaa.merge(innings, on=["season", "mlbam_id", "position"], how="inner")
    df = df[df["innings"] > 0].copy()
    # OAA is not centered at each position (outfielders are all judged on the same plays, so the
    # average center fielder is about +5 runs a season and the average left fielder about -3).
    # Center it on each position's innings-weighted average for the season, so a rate means runs
    # relative to the average fielder at that position, like FanGraphs' fielding runs.
    totals = df.groupby(["season", "position"])[["runs", "innings"]].transform("sum")
    df["rate"] = (df["runs"] - df["innings"] * totals["runs"] / totals["innings"]) \
        / df["innings"] * FULL_SEASON
    return df


def same_season_pairs(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (_, _), g in df.groupby(["season", "mlbam_id"]):
        if len(g) < 2:
            continue
        main = g.loc[g["innings"].idxmax()]
        if main["innings"] < MIN_MAIN:
            continue
        for r in g.itertuples():
            if r.position == main["position"] or r.innings < MIN_OTHER:
                continue
            w = 2 * main["innings"] * r.innings / (main["innings"] + r.innings)
            rows.append({"from": main["position"], "to": r.position,
                         "delta": r.rate - main["rate"], "weight": w})
    return pd.DataFrame(rows)


def additive_fit(pairs: pd.DataFrame) -> dict[str, float]:
    """h[p] - h[q] ~ delta(p -> q), h['1B'] = 0, weighted least squares."""
    free = ORDER[1:]
    x = np.zeros((len(pairs), len(free)))
    for k, (p, q) in enumerate(zip(pairs["from"], pairs["to"], strict=True)):
        if p in free:
            x[k, free.index(p)] += 1.0
        if q in free:
            x[k, free.index(q)] -= 1.0
    sw = np.sqrt(pairs["weight"].to_numpy())
    coef, *_ = np.linalg.lstsq(x * sw[:, None], pairs["delta"].to_numpy() * sw, rcond=None)
    return {"1B": 0.0, **dict(zip(free, coef, strict=True))}


def matrix(pairs: pd.DataFrame, h: dict[str, float]) -> pd.DataFrame:
    cells = pairs.groupby(["from", "to"]).apply(
        lambda g: pd.Series({"own": np.average(g["delta"], weights=g["weight"]),
                             "weight": g["weight"].sum(), "n": len(g)}), include_groups=False)
    rows = []
    for p in ORDER:
        for q in ORDER:
            if p == q:
                continue
            additive = h[p] - h[q]
            if (p, q) in cells.index:
                own, w, n = cells.loc[(p, q), ["own", "weight", "n"]]
            else:
                own, w, n = np.nan, 0.0, 0
            fit = additive if w == 0 else (w * own + SHRINK * additive) / (w + SHRINK)
            rows.append({"from": p, "to": q, "delta": fit, "additive": additive,
                         "own": own, "n": int(n), "weight": w,
                         "difficulty_from": h[p], "difficulty_to": h[q]})
    return pd.DataFrame(rows)


def first_time_cost(df: pd.DataFrame, fit: pd.DataFrame) -> tuple[float, int]:
    """Extra change in fielding the first season at a new position, beyond the fitted delta and
    beyond what players who stayed put show (with regression to the mean allowed for)."""
    by = df.set_index(["season", "mlbam_id", "position"])
    main = df.loc[df.groupby(["season", "mlbam_id"])["innings"].idxmax()]
    stay, moved = [], []
    delta = fit.set_index(["from", "to"])["delta"]
    for r in main.itertuples():
        if r.innings < MIN_STAY:
            continue
        nxt = df[(df["season"] == r.season + 1) & (df["mlbam_id"] == r.mlbam_id)]
        if nxt.empty:
            continue
        same = nxt[nxt["position"] == r.position]
        if len(same) and same["innings"].iloc[0] >= MIN_STAY:
            stay.append((r.rate, same["rate"].iloc[0]))
        for s in nxt.itertuples():
            if s.position == r.position or s.innings < MIN_NEW:
                continue
            if (r.season, r.mlbam_id, s.position) in by.index:   # played it already this season
                continue
            moved.append((r.rate, s.rate, delta[(r.position, s.position)], s.innings))
    stay = np.array(stay)
    b, a = np.polyfit(stay[:, 0], stay[:, 1], 1)       # next = a + b * this (regression to mean)
    moved = np.array(moved)
    expected = a + b * moved[:, 0] + moved[:, 2]
    extra = np.average(moved[:, 1] - expected, weights=moved[:, 3])
    return float(extra), len(moved)


def main(argv: list[str]) -> None:
    folder = Path(argv[0])
    df = load(folder)
    pairs = same_season_pairs(df)
    h = additive_fit(pairs)
    fit = matrix(pairs, h)
    extra, n_moved = first_time_cost(df, fit)
    print(f"{len(df)} player-season-positions, {len(pairs)} same-season pairs, "
          f"{df['season'].min()}-{df['season'].max()}")
    print("difficulty h (runs per full season, 1B = 0):",
          {k: round(v, 1) for k, v in h.items()})
    print(f"first-time cost: {extra:+.1f} runs per full season ({n_moved} first-time moves)")
    table = fit.pivot(index="from", columns="to", values="delta").reindex(index=ORDER,
                                                                          columns=ORDER)
    print("\nfitted change in fielding runs per full season, relative to the average at each "
          "position (rows: from, columns: to)")
    print(table.round(1).to_string())
    print("\npairs per move")
    print(fit.pivot(index="from", columns="to", values="n").reindex(index=ORDER, columns=ORDER)
          .fillna(0).astype(int).to_string())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fit.assign(first_time_cost=extra).to_csv(OUTPUT, index=False)
    print(f"\nwrote {OUTPUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
