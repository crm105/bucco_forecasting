"""Rung 5a of the model ladder: ZiPS player projections turned into a team through a depth chart.

Each team's batters and pitchers are run through the depth chart (see depth_chart.py and
docs/R&D/depth_chart.md), which shares a team's plate appearances and innings among its players
and adds up WAR. The model then turns team WAR into a win percentage:

    mean_win_pct = intercept + slope * (team WAR - that season's league-average team WAR)

Centering on the league average removes the drift in ZiPS's overall WAR level between seasons
(about 20 per team in 2011-2013, 43 now), which would otherwise swamp the slope. The slope and
intercept are an ordinary least-squares line over earlier seasons only; with fewer than
MIN_TRAIN_SEASONS earlier seasons of projections the model uses a slope of one win per WAR.

The model never reads files or the database. It is handed a `PlayerData` object (built from the
database by `bucco.models.player_inputs`) and decides which rows it may see: projections dated
after the forecast's as-of date are ignored.
"""

from __future__ import annotations

import logging
from datetime import date

import numpy as np
import pandas as pd

from bucco.models import depth_chart as dc
from bucco.models.base import GAMES, LUCK_SD, forecast_frame, residual_sd

log = logging.getLogger(__name__)

MIN_TRAIN_SEASONS = 2          # earlier seasons of projections needed to fit the line
THEORY_SLOPE = 1.0 / GAMES     # win percentage per WAR if the line cannot be fit: 1 win per WAR
SHORTENED_GAMES = 150          # a team-season with fewer games is left out of the fit (2020)

BATTER_COLUMNS = ["season", "team_id", "mlbam_id", "player_name", "pa", "war", "def_runs", "bsr"]
PITCHER_COLUMNS = ["season", "team_id", "mlbam_id", "player_name", "ip", "war", "gs"]


class PlayerData:
    """Projected batters, pitchers and prior-season positions, with team WAR cached by season.

    batters: BATTER_COLUMNS (+ optional as_of_date); pitchers: PITCHER_COLUMNS (+ as_of_date);
    positions: season, mlbam_id, position, games, as in the player_position_games mart.
    """

    def __init__(self, batters: pd.DataFrame, pitchers: pd.DataFrame,
                 positions: pd.DataFrame) -> None:
        self.batters = batters.copy()
        self.pitchers = pitchers.copy()
        self.positions = positions
        for frame in (self.batters, self.pitchers):
            if "as_of_date" not in frame:
                frame["as_of_date"] = pd.NaT
            frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
        self.seasons = sorted(set(self.batters["season"]) & set(self.pitchers["season"]))
        self._cache: dict[tuple[int, date | None], pd.Series] = {}

    def team_war(self, season: int, as_of: date | None = None) -> pd.Series:
        """Depth-chart team WAR (batters + pitchers) per team_id for one season."""
        key = (season, as_of)
        if key not in self._cache:
            self._cache[key] = self._compute(season, as_of)
        return self._cache[key]

    def _visible(self, frame: pd.DataFrame, season: int, as_of: date | None) -> pd.DataFrame:
        rows = frame[frame["season"] == season]
        if as_of is not None:
            late = rows["as_of_date"].notna() & (rows["as_of_date"] > pd.Timestamp(as_of))
            if late.any():
                log.warning("ignoring %d %d projection rows dated after %s", int(late.sum()),
                            season, as_of)
            rows = rows[~late]
        return rows

    def _compute(self, season: int, as_of: date | None) -> pd.Series:
        batters = self._visible(self.batters, season, as_of).dropna(subset=["team_id"]).copy()
        pitchers = self._visible(self.pitchers, season, as_of).dropna(subset=["team_id"])
        if batters.empty or pitchers.empty:
            raise ValueError(f"no ZiPS player projections for {season}")
        batters["bsr_pct"] = dc.bsr_percentiles(batters)
        pool = dc.build_batter_pool(batters, self.positions[self.positions["season"] == season])
        bat = dc.depth_chart_by_team(pool, group="team_id").groupby("team_id")["scaled_war"].sum()
        pit = pd.concat([dc.build_pitcher_depth_chart(g) for _, g in pitchers.groupby("team_id")]
                        ).groupby("team_id")["scaled_war"].sum()
        return bat.add(pit, fill_value=0.0)


class DepthChartModel:
    """Rung 5a: ZiPS depth-chart team WAR to win percentage, centered on the league average."""

    name = "depth_chart"

    def __init__(self, data: PlayerData) -> None:
        self.data = data
        self.seasons = set(data.seasons)   # seasons this model can predict
        self.intercept = 0.5
        self.slope = THEORY_SLOPE
        self.sd = LUCK_SD
        self.n_train = 0

    def fit(self, history: pd.DataFrame) -> None:
        """`history` is team_seasons for earlier seasons; only full seasons with projections count."""
        full = history[history["games_played"] >= SHORTENED_GAMES] if "games_played" in history \
            else history
        rows = []
        for season in sorted(set(full["season"]) & self.seasons):
            war = self.data.team_war(int(season))
            part = full[full["season"] == season][["team_id", "win_pct"]].copy()
            part["w"] = part["team_id"].map(war - war.mean())
            rows.append(part.dropna())
        train = pd.concat(rows) if rows else pd.DataFrame(columns=["team_id", "win_pct", "w"])
        self.n_train = len(rows)
        if len(rows) >= MIN_TRAIN_SEASONS:
            slope, intercept = np.polyfit(train["w"], train["win_pct"], 1)
            if slope > 0:
                self.slope, self.intercept = float(slope), float(intercept)
                self.sd = residual_sd(train["win_pct"] - (intercept + slope * train["w"]))
                log.info("depth_chart: %.2f wins per WAR over %d seasons", slope * GAMES, len(rows))
                return
        self.intercept = float(train["win_pct"].mean()) if len(train) else 0.5
        self.slope = THEORY_SLOPE
        self.sd = residual_sd(train["win_pct"] - (self.intercept + self.slope * train["w"])
                              if len(train) else pd.Series(dtype=float))

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        if season not in self.seasons:
            raise ValueError(f"depth_chart: no ZiPS player projections for {season}")
        war = self.data.team_war(season, as_of)
        centered = war - war.mean()
        mean = features["team_id"].map(self.intercept + self.slope * centered)
        return forecast_frame(features, mean.fillna(self.intercept), self.sd)
