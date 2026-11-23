"""Turn player projections into a team: share a team's playing-time budget among its players.

The ZiPS player files give each player's WAR for his own projected playing time, estimated
without regard to the rest of the roster, so a team's players add up to about four times a
real team's plate appearances. This module applies a team budget (for example 6,240 PA)
using the "regulars first" rule described in docs/R&D/proportional_fill.md:

1. Rank the team's players, by WAR per unit of playing time (the default) or by projected playing
   time. The top `n_regulars` are the regulars. With the rate ranking, players projected for
   less than `min_volume` rank below everyone who clears it, so a few lucky plate appearances
   can't make a regular.
2. Regulars get a share of the budget, `1 - bench_share`, handed out in proportion to their
   own projected playing time (never more than they were projected for, or `cap`).
3. The set-aside `bench_share` goes to the next players in the ranking, with each player getting
   `decay` times the share of the one before him (an exponential decay), and no player getting
   more than his own projection. Anything a capped player can't take moves to the players
   below him.
4. WAR is scaled by the same fraction of projected playing time each player receives.

Nothing here reads files or the database. It does not know positions yet (see the TODO in the
planning doc), so the catcher cap and DH rule are not applied.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PA_BUDGET = 6240.0        # 640 (catcher slot) + 7 x 700 (other slots incl. DH); see the R&D note
IP_BUDGET = 1500.0        # FanGraphs: "about 1,500 innings of pitching"
N_REGULARS = 12           # about nine starters plus platoon partners and regular backups
PA_CAP = 700.0            # FanGraphs' cap for a non-catcher
DEFAULT_BENCH_SHARE = 0.15
DEFAULT_DECAY = 0.8
DEFAULT_RANK_BY = "rate"
DEFAULT_MIN_PA = 200.0    # results barely change for floors of 0-250; see docs/R&D/proportional_fill.md
RANK_OPTIONS = ("rate", "volume")


def _spread_bench(pool: float, capacity: np.ndarray, decay: float) -> np.ndarray:
    """Split `pool` over players in rank order with geometric weights, respecting capacities.

    Weights are decay**0, decay**1, ... A player who would get more than his capacity gets
    exactly his capacity, and the excess is re-split over the rest by the same weights.
    """
    n = len(capacity)
    out = np.zeros(n)
    if n == 0 or pool <= 0:
        return out
    weights = decay ** np.arange(n)
    open_ = capacity > 0
    remaining = pool
    for _ in range(n + 1):
        if remaining <= 1e-9 or not open_.any():
            break
        w = np.where(open_, weights, 0.0)
        want = remaining * w / w.sum()
        room = capacity - out
        give = np.minimum(want, room)
        out += give
        remaining -= give.sum()
        open_ &= out < capacity - 1e-9
    return out


def _rank(volume: np.ndarray, war: np.ndarray, rank_by: str, min_volume: float) -> np.ndarray:
    """Row positions from best to worst. Ties fall back to larger volume, then row order."""
    position = np.arange(len(volume))
    if rank_by == "volume":
        return np.lexsort((position, -war, -volume))
    rate = np.divide(war, volume, out=np.zeros(len(volume)), where=volume > 0)
    below_floor = volume < max(min_volume, 1e-12)  # zero-volume players are never eligible
    # lexsort sorts by the LAST key first: eligibility, then the score, then tie-breaks.
    score = np.where(below_floor, -volume, -rate)
    return np.lexsort((position, -volume, score, below_floor))


def allocate_playing_time(
    players: pd.DataFrame,
    volume: str,
    budget: float,
    war: str = "war",
    n_regulars: int = N_REGULARS,
    bench_share: float = DEFAULT_BENCH_SHARE,
    decay: float = DEFAULT_DECAY,
    cap: float | None = None,
    rank_by: str = DEFAULT_RANK_BY,
    min_volume: float = DEFAULT_MIN_PA,
) -> pd.DataFrame:
    """Allocate one team's playing-time budget among its players ("regulars first").

    `players` is one team's rows. `volume` is the projected playing-time column (PA for
    batters, IP for pitchers). Returns a copy with `role`, `allocated`, `fraction` (allocated /
    projected) and `scaled_war`, in the original row order.

    bench_share: fraction of the budget set aside for players outside the top `n_regulars`.
        If the regulars cannot use all of their share (their projections run short), the
        unused part also goes to the bench, so the bench gets at least this much.
    decay: each bench player gets this fraction of the previous bench player's share
        (before caps), so 0.8 means 100, 80, 64, 51, ... Must be between 0 and 1.
    cap: most playing time any one player can receive. None means his own projection only.
    rank_by: "rate" ranks by `war` per unit of projected volume (WAR/PA or WAR/IP), highest
        first; "volume" ranks by projected volume. Ties go to the larger volume.
    min_volume: with rank_by="rate", players projected for less than this rank below all players
        who reach it (among themselves, by volume), so tiny samples can't win the ranking.
    """
    if not 0.0 <= bench_share <= 1.0:
        raise ValueError("bench_share must be between 0 and 1")
    if not 0.0 < decay <= 1.0:
        raise ValueError("decay must be in (0, 1]")
    if n_regulars < 0 or budget < 0:
        raise ValueError("n_regulars and budget must not be negative")
    if rank_by not in RANK_OPTIONS:
        raise ValueError(f"rank_by must be one of {RANK_OPTIONS}")

    out = players.copy()
    projected = out[volume].astype(float).clip(lower=0).to_numpy()
    order = _rank(projected, out[war].to_numpy(dtype=float), rank_by, min_volume)
    ceiling = projected if cap is None else np.minimum(projected, cap)

    allocated = np.zeros(len(out))
    role = np.full(len(out), "unused", dtype=object)

    regulars = order[:n_regulars]
    regular_budget = (1.0 - bench_share) * budget
    regular_total = ceiling[regulars].sum()
    scale = min(1.0, regular_budget / regular_total) if regular_total > 0 else 0.0
    allocated[regulars] = ceiling[regulars] * scale
    role[regulars] = "regular"

    bench = order[n_regulars:]
    pool = budget - allocated.sum()
    given = _spread_bench(pool, ceiling[bench], decay)
    allocated[bench] = given
    role[bench[given > 0]] = "bench"

    out["role"] = role
    out["allocated"] = allocated
    out["fraction"] = np.divide(allocated, projected, out=np.zeros(len(out)), where=projected > 0)
    out["scaled_war"] = out[war].astype(float) * out["fraction"]
    return out


def allocate_by_team(
    players: pd.DataFrame,
    volume: str,
    budget: float,
    group: str | list[str] = "team_id",
    **kwargs,
) -> pd.DataFrame:
    """Apply `allocate_playing_time` to every team (and season, etc.) in `group`."""
    parts = [allocate_playing_time(rows, volume, budget, **kwargs)
             for _, rows in players.groupby(group, sort=False)]
    return pd.concat(parts).loc[players.index] if parts else players.assign(
        role=[], allocated=[], fraction=[], scaled_war=[])


def team_war(allocated: pd.DataFrame, group: str | list[str] = "team_id") -> pd.Series:
    """Sum of scaled WAR per team from `allocate_by_team` output."""
    return allocated.groupby(group)["scaled_war"].sum()
