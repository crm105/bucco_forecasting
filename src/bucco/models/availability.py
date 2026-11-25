"""Availability: how much of his projected playing time a player delivers, from his status on
his team's Opening Day 40-man roster (marts.player_preseason_status).

Groups: `il_60` (60-day injured list), `il_short` (7-, 10- or 15-day), `active` (on the 40-man
roster and not on the injured list, including optioned players) and `off_40` (on a team's
preseason list but not its 40-man roster: non-roster invitees and minor leaguers).

For each target season, and separately for batters and pitchers, a group's factor is the playing
time its players delivered over what was projected, on earlier seasons only (2020 targets left
out). With `relative`, factors are divided by the active group's, so an active 40-man player's
projection is unchanged and only the others are scaled. On 2012-2026: 60-day injured list about
0.2, short injured list 0.6-0.7, off the 40-man 0.1 (batters) to 0.4 (pitchers). See
docs/R&D/availability.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

GROUPS = ("il_60", "il_short", "active", "off_40")
MIN_GROUP_ROWS = 30         # earlier player-seasons a group needs to get its own factor


def status_groups(rows: pd.DataFrame, status: pd.DataFrame) -> pd.Series:
    """The availability group of each row (season, mlbam_id), from player_preseason_status
    (season, mlbam_id, il_group). A player missing from the 40-man snapshot is `off_40`."""
    g = rows[["season", "mlbam_id"]].merge(status[["season", "mlbam_id", "il_group"]],
                                           on=["season", "mlbam_id"], how="left")["il_group"]
    g = g.map({"il_60": "il_60", "il_short": "il_short", "none": "active"}).fillna("off_40")
    return pd.Series(g.to_numpy(), index=rows.index)


def fit_factors(groups: pd.Series, projected: pd.Series, actual: pd.Series,
                seasons: pd.Series, before: int, relative: bool = True,
                shortened: frozenset[int] = frozenset({2020})) -> dict[str, float]:
    """Delivered over projected playing time by group, on target seasons before `before`. A
    group with fewer than MIN_GROUP_ROWS rows gets 1 (or the active group's, if relative)."""
    use = (seasons < before) & ~seasons.isin(shortened) & actual.notna() & (projected > 0)
    out = {}
    for g in GROUPS:
        m = use & (groups == g)
        out[g] = float(actual[m].sum() / projected[m].sum()) if m.sum() >= MIN_GROUP_ROWS else np.nan
    base = out["active"] if relative and not np.isnan(out["active"]) else 1.0
    return {g: (1.0 if np.isnan(v) else v / base) for g, v in out.items()}


def availability(groups: pd.Series, projected: pd.Series, actual: pd.Series,
                 seasons: pd.Series, relative: bool = True) -> pd.Series:
    """Each row's factor, from the factors fitted on seasons before its own."""
    out = pd.Series(1.0, index=groups.index)
    for season in sorted(seasons.unique()):
        f = fit_factors(groups, projected, actual, seasons, int(season), relative)
        rows = seasons == season
        out[rows] = groups[rows].map(f).fillna(1.0)
    return out
