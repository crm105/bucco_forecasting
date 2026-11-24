"""Fit extra switch penalties from how often teams actually make each move.

    uv run python scripts/fit_rarity_penalty.py [penalty ...]

Real teams move players about 2.5 times as often as the lineup optimizer (injuries, rest and
slumps force moves a full-season plan never needs), so absolute rates cannot calibrate the
penalties. Instead, for each group of moves we compare the optimizer's count with the real count
(2016-2025, 2020 left out) and look for groups the optimizer over-uses relative to its usual
share. Rarity is read one way only: a move the optimizer makes less often than teams do is not
made cheaper (players often stay put because they are worth more where they are).

A player's main position is where he plays most (at least 300 innings, or the PA equivalent);
a move is at least 100 innings (52 PA) at another position. Innings to PA: 1350 per 700.

For each candidate penalty on outfield -> first base (added to the selection penalty, so only at
positions a player did not play last season), the script prints the optimizer's ratio to real
moves by group. Pick the smallest penalty that brings the group's ratio down to the median of
the others, then backtest it.
"""

from __future__ import annotations

import sys

import duckdb
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.models import lineup_optimizer as lo

FIELD = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
GROUP = {"C": "C", "1B": "1B", "2B": "IF", "3B": "IF", "SS": "IF",
         "LF": "OF", "CF": "OF", "RF": "OF"}
SEASONS = [s for s in range(2016, 2026) if s != 2020]
INN_PER_PA = 1350 / 700
MAIN_INN, MOVE_INN = 300.0, 100.0
TARGET = [("OF", "1B")]


def move_counts(df: pd.DataFrame, vol: str, main_min: float, move_min: float) -> pd.Series:
    """Number of moves by group (e.g. 'OF->1B', 'within IF')."""
    df = df[df["position"].isin(FIELD)]
    main = df.sort_values(vol).groupby(["season", "mlbam_id"]).tail(1)
    main = main.loc[main[vol] >= main_min, ["season", "mlbam_id", "position"]]
    m = df.merge(main.rename(columns={"position": "p"}), on=["season", "mlbam_id"])
    m = m[(m["position"] != m["p"]) & (m[vol] >= move_min)]
    gp, gq = m["p"].map(GROUP), m["position"].map(GROUP)
    label = (gp + "->" + gq).where(gp != gq, "within " + gp)
    return label.value_counts()


def real_counts(con) -> pd.Series:
    real = con.sql(f"""select season, mlbam_id, position, sum(innings) as inn
                       from staging.stg_mlb__fielding
                       where season in ({",".join(map(str, SEASONS))}) group by 1, 2, 3""").df()
    return move_counts(real, "inn", MAIN_INN, MOVE_INN)


def optimizer_counts(con, switch: lo.SwitchMatrix) -> pd.Series:
    allocs = []
    for s in SEASONS:
        proj = con.sql("select * from marts.player_projections where source = 'steamer' and "
                       f"season = {s} and team_id is not null and mlbam_id is not null and "
                       "player_type = 'batter'").df()
        pos = con.sql("select mlbam_id, position, games from marts.player_position_games "
                      f"where season = {s}").df()
        a, _ = lo.optimize_league(proj, pos, switch=switch)
        a = a[a["mlbam_id"] >= 0].groupby(["mlbam_id", "position"])["pa"].sum().reset_index()
        a["season"] = s
        allocs.append(a)
    return move_counts(pd.concat(allocs), "pa", MAIN_INN / INN_PER_PA, MOVE_INN / INN_PER_PA)


def main(penalties: list[float]) -> None:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    real = real_counts(con)
    table = {"real": real}
    for x in penalties:
        rarity = {(p, "1B"): x for p in ("LF", "CF", "RF")} if x else {}
        table[f"pen {x:g}"] = optimizer_counts(con, lo.load_switch_matrix(rarity=rarity))
    counts = pd.DataFrame(table).fillna(0)
    counts = counts[counts["real"] >= 5]
    ratios = counts.drop(columns="real").div(counts["real"], axis=0).round(2)
    print(counts.astype(int).join(ratios.add_suffix(" ratio")).to_string())
    others = ratios.drop(index=[f"{a}->{b}" for a, b in TARGET], errors="ignore")
    print("\nmedian ratio of the other groups:", others.median().round(2).to_dict())


if __name__ == "__main__":
    main([float(a) for a in sys.argv[1:]] or [0.0, 3.0, 6.0, 10.0])
