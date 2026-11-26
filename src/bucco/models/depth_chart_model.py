"""Rung 5a of the model ladder: player projections turned into team WAR, then into wins.

Three ways to get team WAR from one projection system's player files:

* `depth_chart` (used for ZiPS): each team's batters and pitchers are run through the depth
  chart (see depth_chart.py and docs/R&D/depth_chart.md), which shares a team's plate
  appearances and innings among its players and adds up WAR. ZiPS projects every player on his
  own, so its playing time adds up to several teams' worth and must be shared out.
* `optimized` (used for Steamer, `steamer_optimized`): batters' plate appearances are shared
  out by the lineup optimizer (lineup_optimizer.py: the same PA at every position for every team,
  fatigue, fitted position-switch costs); pitchers are taken as given, as in `as_given`.
* `as_given` (used for Steamer): each team's projected WAR is summed as it is. Steamer's
  playing time is already shared out within each team (about 5,800 PA and 1,500 IP per team), and
  it beat the depth chart on both PA and wins error. A file that is a raw list of every player
  instead (Steamer 2013: about 15,800 PA per team) is detected by its team totals and run
  through the depth chart.

The model then turns team WAR into a win percentage:

    mean_win_pct = intercept + slope * (team WAR - that season's league-average team WAR)

Then, when the season's schedule is known (`matchups`), each team's win percentage is adjusted
for strength of schedule: its expected record against the opponents it actually plays (log5;
see schedule.py). League wins still add up to the number of games.

Centering on the league average removes the drift in a system's overall WAR level between
seasons (for ZiPS, about 20 per team in 2011-2013, 43 now), which would otherwise swamp the slope. The slope and
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
from bucco.models.schedule import schedule_adjusted

log = logging.getLogger(__name__)

MIN_TRAIN_SEASONS = 2          # earlier seasons of projections needed to fit the line
THEORY_SLOPE = 1.0 / GAMES     # win percentage per WAR if the line cannot be fit: 1 win per WAR
SHORTENED_GAMES = 150          # a team-season with fewer games is left out of the fit (2020)
PLAYING_TIME = ("depth_chart", "as_given", "optimized")
# Median team totals above these mean a file lists every player with his own playing time
# rather than sharing a team's out (real teams: about 6,200 PA and 1,450 IP). Such a file is
# run through the depth chart even in `as_given` mode.
RAW_LIST_PA = 10_000.0
RAW_LIST_IP = 2_500.0

BATTER_COLUMNS = ["season", "team_id", "mlbam_id", "player_name", "pa", "war", "def_runs", "bsr"]
PITCHER_COLUMNS = ["season", "team_id", "mlbam_id", "player_name", "ip", "war", "gs"]


def pitcher_rate(pitchers: pd.DataFrame) -> pd.Series:
    """Runs above average per inning: the projection's own rate (Marcel's `runs_per_ip`) where
    it has one, which stays known for a pitcher projected for 0 innings; else runs / ip."""
    ip = pitchers["ip"].astype(float)
    derived = (pitchers["runs"] / ip.where(ip > 0)).fillna(0.0)
    if "runs_per_ip" in pitchers:
        return pitchers["runs_per_ip"].fillna(derived)
    return derived


class PlayerData:
    """Projected batters, pitchers and prior-season positions, with team WAR cached by season.

    batters: BATTER_COLUMNS (+ optional as_of_date); pitchers: PITCHER_COLUMNS (+ as_of_date);
    positions: season, mlbam_id, position, games, as in the player_position_games mart.
    source: the projection system's name, for messages. playing_time: one of PLAYING_TIME.
    matchups: season, team_id, opponent_id, games, as in the team_matchups mart (optional; the
    schedule is fixed before the season, so the forecast season's may be used).
    optimizer_options: keyword arguments for `lineup_optimizer.optimize_league` in `optimized`
    mode (e.g. anchor_pa).
    pitcher_playing_time: "depth_chart" always shares pitchers' innings out with the depth chart
    (for a source that lists every pitcher with his own innings); "optimized" with the staff
    optimizer (bucco.models.staff_optimizer; needs Marcel's pitcher columns); default: as for
    batters. staff_options: keyword arguments for `staff_optimizer.optimize_staffs`.
    injury_sims: with both playing times "optimized", team WAR is the mean over this many
    injury draws (bucco.models.injury_sim), from `injury_samples` (season -> group -> draws).
    """

    def __init__(self, batters: pd.DataFrame, pitchers: pd.DataFrame,
                 positions: pd.DataFrame, source: str = "ZiPS",
                 playing_time: str = "depth_chart",
                 matchups: pd.DataFrame | None = None,
                 optimizer_options: dict | None = None,
                 pitcher_playing_time: str | None = None,
                 staff_options: dict | None = None,
                 injury_sims: int = 0,
                 injury_samples: dict | None = None) -> None:
        if playing_time not in PLAYING_TIME:
            raise ValueError(f"playing_time must be one of {PLAYING_TIME}, not {playing_time!r}")
        self.source = source
        self.playing_time = playing_time
        self.pitcher_playing_time = pitcher_playing_time
        self.batters = batters.copy()
        self.pitchers = pitchers.copy()
        self.positions = positions
        self.optimizer_options = dict(optimizer_options or {})
        self.staff_options = dict(staff_options or {})
        self.injury_sims = injury_sims
        self.injury_samples = injury_samples or {}
        self.sim_sd: dict[int, pd.Series] = {}     # team WAR sd over injury draws, by season
        self.matchups = (matchups if matchups is not None
                         else pd.DataFrame(columns=["season", "team_id", "opponent_id", "games"]))
        for frame in (self.batters, self.pitchers):
            if "as_of_date" not in frame:
                frame["as_of_date"] = pd.NaT
            frame["as_of_date"] = pd.to_datetime(frame["as_of_date"])
        self.seasons = sorted(set(self.batters["season"]) & set(self.pitchers["season"]))
        self._cache: dict[tuple[int, date | None], pd.Series] = {}
        self._parts: dict[tuple[int, date | None], pd.DataFrame] = {}
        self._players: dict[tuple[int, date | None], dict[str, pd.DataFrame]] = {}

    def team_war(self, season: int, as_of: date | None = None) -> pd.Series:
        """Depth-chart team WAR (batters + pitchers) per team_id for one season."""
        key = (season, as_of)
        if key not in self._cache:
            self._cache[key] = self._compute(season, as_of)
        return self._cache[key]

    def player_allocations(self, season: int, as_of: date | None = None) -> dict | None:
        """The playing time and WAR team_war gave each player: {"batting": team_id, mlbam_id,
        pa, war; "pitching": team_id, mlbam_id, ip, war}; None with injury draws."""
        self.team_war(season, as_of)
        return self._players.get((season, as_of))

    def team_war_parts(self, season: int, as_of: date | None = None) -> pd.DataFrame:
        """Team WAR split into batting and pitching per team_id (columns batting, pitching), as
        team_war computes it; with injury draws the split is not kept (both NaN)."""
        self.team_war(season, as_of)
        parts = self._parts.get((season, as_of))
        if parts is None:
            idx = self._cache[(season, as_of)].index
            return pd.DataFrame({"batting": np.nan, "pitching": np.nan}, index=idx)
        return parts

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
            raise ValueError(f"no {self.source} player projections for {season}")
        if self.injury_sims and self.playing_time == "optimized" \
                and self.pitcher_playing_time == "optimized":
            return self._simulated(batters, pitchers, season)
        if self.playing_time == "optimized":
            bat_players = self._optimized_batting(batters, season)
        elif self._as_given(batters, "pa", RAW_LIST_PA, season):
            bat_players = batters[["team_id", "mlbam_id", "pa", "war"]]
        else:
            batters["bsr_pct"] = dc.bsr_percentiles(batters)
            pool = dc.build_batter_pool(batters, self.positions[self.positions["season"] == season])
            chart = dc.depth_chart_by_team(pool, group="team_id")
            bat_players = chart[["team_id", "mlbam_id", "allocated", "scaled_war"]].rename(
                columns={"allocated": "pa", "scaled_war": "war"})
        if self.pitcher_playing_time == "optimized":
            pit_players = self._optimized_pitching(pitchers)
        elif self.pitcher_playing_time != "depth_chart" and \
                self._as_given(pitchers, "ip", RAW_LIST_IP, season):
            pit_players = pitchers[["team_id", "mlbam_id", "ip", "war"]]
        else:
            chart = pd.concat([dc.build_pitcher_depth_chart(g)
                               for _, g in pitchers.groupby("team_id")])
            pit_players = chart[["team_id", "mlbam_id", "allocated", "scaled_war"]].rename(
                columns={"allocated": "ip", "scaled_war": "war"})
        bat_players = (bat_players.groupby(["team_id", "mlbam_id"], as_index=False)[["pa", "war"]]
                       .sum())
        pit_players = (pit_players.groupby(["team_id", "mlbam_id"], as_index=False)[["ip", "war"]]
                       .sum())
        self._players[(season, as_of)] = {"batting": bat_players, "pitching": pit_players}
        bat = bat_players.groupby("team_id")["war"].sum()
        pit = pit_players.groupby("team_id")["war"].sum()
        self._parts[(season, as_of)] = pd.DataFrame({"batting": bat, "pitching": pit}).fillna(0.0)
        return bat.add(pit, fill_value=0.0)

    def _optimized_batting(self, batters: pd.DataFrame, season: int) -> pd.DataFrame:
        """Each batter's PA and WAR (by team and position) with plate appearances shared out by
        the lineup optimizer (needs off_runs, def_runs and fld_runs in the batter rows)."""
        from bucco.models.lineup_optimizer import optimize_league

        rows = batters.rename(columns={"pa": "plate_appearances"})
        if "fld_runs" not in rows:
            rows["fld_runs"] = np.nan
        allocations, _ = optimize_league(rows, self.positions[self.positions["season"] == season],
                                         **self.optimizer_options)
        return allocations

    def _simulated(self, batters: pd.DataFrame, pitchers: pd.DataFrame, season: int) -> pd.Series:
        """Team WAR as the mean over injury draws, with lineups and staffs re-optimized in each
        (bucco.models.injury_sim). Keeps each team's sd in `sim_sd`."""
        from bucco.models import injury_sim
        from bucco.models import lineup_optimizer as lo
        from bucco.models.staff_optimizer import ROTATION_MIN_SHARE

        rows = batters.rename(columns={"pa": "plate_appearances"})
        if "fld_runs" not in rows:
            rows["fld_runs"] = np.nan
        rpw, rep = lo.war_scale(rows)
        bat = lo.player_inputs(rows, self.positions[self.positions["season"] == season])
        bat = bat.merge(rows[["mlbam_id", "team_id", "age"]].drop_duplicates(["mlbam_id", "team_id"]),
                        on=["mlbam_id", "team_id"], how="left")
        ip = pitchers["ip"].astype(float)
        pit = pitchers.assign(rate=pitcher_rate(pitchers), base_ip=ip,
                              starter=pitchers["start_share"] >= ROTATION_MIN_SHARE)
        res = injury_sim.simulate_season(bat, pit, self.injury_samples.get(season, {}), rep, rpw,
                                         options=self.optimizer_options,
                                         n_sims=self.injury_sims, seed=season).set_index("team_id")
        self.sim_sd[season] = res["sd"]
        return res["bat"] + res["pit"]

    def _optimized_pitching(self, pitchers: pd.DataFrame) -> pd.DataFrame:
        """Each pitcher's innings and WAR (by team and pool) as shared out by the staff optimizer
        (needs runs, ip, age, start_share and the league constants of bucco.models.marcel's
        pitchers)."""
        from bucco.models.staff_optimizer import optimize_staffs

        ip = pitchers["ip"].astype(float)
        rows = pitchers.assign(rate=pitcher_rate(pitchers),
                               base_ip=ip)
        return optimize_staffs(rows, **self.staff_options)

    def _as_given(self, rows: pd.DataFrame, volume: str, raw_list: float, season: int) -> bool:
        """Use the projected playing time as it is, unless the file looks like a raw list.
        Pitchers in `optimized` mode are taken as given too."""
        if self.playing_time not in ("as_given", "optimized"):
            return False
        per_team = float(rows.groupby("team_id")[volume].sum().median())
        if per_team > raw_list:
            log.info("%s %d: median team %s of %.0f looks like a raw list of every player, so "
                     "it is run through the depth chart", self.source, season, volume, per_team)
            return False
        return True


class DepthChartModel:
    """Rung 5a: projected team WAR to win percentage, centered on the league average."""

    name = "depth_chart"

    def __init__(self, data: PlayerData, name: str | None = None, schedule: bool = True) -> None:
        if name is not None:
            self.name = name
        self.data = data
        self.schedule = schedule           # adjust for strength of schedule when it is known
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
                log.info("%s: %.2f wins per WAR over %d seasons", self.name, slope * GAMES, len(rows))
                return
        self.intercept = float(train["win_pct"].mean()) if len(train) else 0.5
        self.slope = THEORY_SLOPE
        self.sd = residual_sd(train["win_pct"] - (self.intercept + self.slope * train["w"])
                              if len(train) else pd.Series(dtype=float))

    def predict(self, season: int, as_of: date, features: pd.DataFrame) -> pd.DataFrame:
        if season not in self.seasons:
            raise ValueError(f"{self.name}: no {self.data.source} player projections for {season}")
        war = self.data.team_war(season, as_of)
        centered = war - war.mean()
        neutral = self.intercept + self.slope * centered
        if self.schedule:
            games = self.data.matchups[self.data.matchups["season"] == season]
            if games.empty:
                log.info("%s: no %d schedule, so no strength-of-schedule adjustment",
                         self.name, season)
            else:
                neutral = schedule_adjusted(neutral, games)
        mean = features["team_id"].map(neutral)
        return forecast_frame(features, mean.fillna(self.intercept), self.sd)
