"""A weighted average of two season forecasters, with the weight tuned without look-ahead.

`blend_optimized` averages `steamer_optimized` and `zips_optimized`. Their errors are highly
correlated (0.94), but averaging still removes some noise.

The weight is chosen inside `fit`, from the seasons it is given (all before the target season):
for each of those seasons t, both components are fitted on the seasons before t and predict t,
which gives honest out-of-sample predictions; the weight that minimizes their squared error
(least squares, clipped to [0, 1]) is used for the target season. With fewer than
MIN_WEIGHT_SEASONS such seasons the weight is PRIOR_WEIGHT (an even split). The 80% range uses
the spread of the blended out-of-sample errors.

When only one component has projections for a season (no ZiPS file for 2027 yet), the blend is
that component's forecast. Both components are schedule-adjusted, and a weighted average of two
forecasts whose wins add up to the games played does too.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

import numpy as np
import pandas as pd

from bucco.models.base import forecast_frame, residual_sd

log = logging.getLogger(__name__)

MIN_WEIGHT_SEASONS = 3     # out-of-sample seasons needed before the weight is fitted
PRIOR_WEIGHT = 0.5         # weight on the second component until then
SHORTENED_GAMES = 150      # a shortened season (2020) is left out of the weight fit


class BlendModel:
    """(1 - w) * first + w * second, w fitted on earlier seasons' out-of-sample forecasts."""

    def __init__(self, first: Callable[[], object], second: Callable[[], object],
                 name: str = "blend", min_weight_seasons: int = MIN_WEIGHT_SEASONS,
                 prior_weight: float = PRIOR_WEIGHT) -> None:
        self.name = name
        self.makers = (first, second)
        self.min_weight_seasons = min_weight_seasons
        self.prior_weight = prior_weight
        self.component_seasons = tuple(set(getattr(m(), "seasons", set())) for m in self.makers)
        self.seasons = self.component_seasons[0] | self.component_seasons[1]
        self.weight = prior_weight
        self.sd: float | None = None
        self.n_weight_seasons = 0
        self.fitted: tuple = ()

    # -- out-of-sample predictions for earlier seasons --
    def _out_of_sample(self, history: pd.DataFrame) -> pd.DataFrame:
        """Both components' forecasts for each earlier full season, each fitted only on the
        seasons before it."""
        full = history
        if "games_played" in history:
            full = history[history["games_played"] >= SHORTENED_GAMES]
        both = self.component_seasons[0] & self.component_seasons[1]
        rows = []
        for t in sorted(set(full["season"]) & both):
            actual = full[full["season"] == t][["team_id", "win_pct"]]
            earlier = history[history["season"] < t]
            preds = []
            for make in self.makers:
                m = make()
                m.fit(earlier)
                preds.append(m.predict(int(t), None, actual).set_index("team_id")["mean_win_pct"])
            part = actual.set_index("team_id").assign(first=preds[0], second=preds[1], season=t)
            rows.append(part.reset_index())
        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
            columns=["team_id", "win_pct", "first", "second", "season"])

    def fit(self, history: pd.DataFrame) -> None:
        """`history` is team_seasons for seasons before the target season only."""
        self.fitted = tuple(self._fit_one(make, history) for make in self.makers)
        oos = self._out_of_sample(history)
        self.n_weight_seasons = int(oos["season"].nunique()) if len(oos) else 0
        if self.n_weight_seasons >= self.min_weight_seasons:
            gap = oos["second"] - oos["first"]
            target = oos["win_pct"] - oos["first"]
            denom = float((gap ** 2).sum())
            w = float((target * gap).sum() / denom) if denom > 0 else self.prior_weight
            self.weight = float(np.clip(w, 0.0, 1.0))
        else:
            self.weight = self.prior_weight
        if len(oos):
            blend = (1 - self.weight) * oos["first"] + self.weight * oos["second"]
            self.sd = residual_sd(oos["win_pct"] - blend)
        log.info("%s: weight %.2f on the second component from %d earlier seasons",
                 self.name, self.weight, self.n_weight_seasons)

    @staticmethod
    def _fit_one(make: Callable[[], object], history: pd.DataFrame):
        model = make()
        model.fit(history)
        return model

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        have = [season in s for s in self.component_seasons]
        if not any(have):
            raise ValueError(f"{self.name}: no component has projections for {season}")
        if not all(have):
            only = self.fitted[have.index(True)]
            return only.predict(season, as_of, features)
        a, b = (m.predict(season, as_of, features) for m in self.fitted)
        mean = (1 - self.weight) * a["mean_win_pct"].to_numpy() \
            + self.weight * b["mean_win_pct"].to_numpy()
        sd = self.sd if self.sd is not None else float(
            (1 - self.weight) * a["sd_win_pct"].iloc[0] + self.weight * b["sd_win_pct"].iloc[0])
        return forecast_frame(features, mean, sd)


def make_blend_optimized_model() -> BlendModel:
    """Factory for the registry: steamer_optimized and zips_optimized, weight tuned walk-forward."""
    from bucco.models.player_inputs import (
        make_steamer_optimized_model,
        make_zips_optimized_model,
    )

    return BlendModel(make_steamer_optimized_model, make_zips_optimized_model,
                      name="blend_optimized")
