"""Strength of schedule: a team's expected win percentage against the games it actually plays.

A forecast's win percentage is read as the team's chance of beating an average opponent. Against
its real schedule the team's expected wins are the sum, over its games, of its chance of beating
each opponent, from the log5 formula:

    P(i beats j) = p_i (1 - p_j) / (p_i (1 - p_j) + p_j (1 - p_i))

Because P(i beats j) + P(j beats i) = 1 for every game, the league's expected wins still add up to
exactly the number of games played. Teams in strong divisions lose a little, teams in weak ones
gain. Backtest (2012-2026): RMSE 9.675 -> 9.585 wins for steamer_optimized, almost all of it
before 2023, when teams played 76 division games instead of 52. See docs/R&D/schedule.md.
"""

from __future__ import annotations

import pandas as pd


def log5(p: pd.Series | float, q: pd.Series | float) -> pd.Series | float:
    """Chance that a team with neutral win percentage p beats one with q."""
    return p * (1 - q) / (p * (1 - q) + q * (1 - p))


def schedule_adjusted(win_pct: pd.Series, matchups: pd.DataFrame) -> pd.Series:
    """Expected win percentage against each team's schedule.

    win_pct: neutral win percentage by team_id. matchups: one season's games between each pair,
    from each team's side (team_id, opponent_id, games), as in the team_matchups mart. Teams with
    no scheduled games, or facing a team with no forecast, keep their neutral value.
    """
    m = matchups.assign(p=matchups["team_id"].map(win_pct),
                        q=matchups["opponent_id"].map(win_pct)).dropna(subset=["p", "q"])
    if m.empty:
        return win_pct.copy()
    m = m.assign(wins=m["games"] * log5(m["p"], m["q"]))
    totals = m.groupby("team_id")[["wins", "games"]].sum()
    adjusted = totals["wins"] / totals["games"]
    return adjusted.reindex(win_pct.index).fillna(win_pct)


def neutral_from_adjusted(adjusted: pd.Series, matchups: pd.DataFrame, tol: float = 1e-10,
                          max_iter: int = 100) -> pd.Series:
    """Invert `schedule_adjusted`: the neutral win percentages that give `adjusted` against this
    schedule (for explaining a saved, adjusted forecast). Fixed-point iteration; the adjustment
    is close to the identity, so it converges in a few steps."""
    neutral = adjusted.copy()
    for _ in range(max_iter):
        step = adjusted - schedule_adjusted(neutral, matchups)
        neutral = neutral + step
        if step.abs().max() < tol:
            break
    return neutral
