"""Load the player-level inputs the rung-5a models need from the database.

This is the one place that reads `bucco.duckdb` for those models; each model is handed the
resulting `PlayerData`. Each source's data is loaded once per process.
"""

from __future__ import annotations

from functools import lru_cache

import duckdb
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.models import availability as avail
from bucco.models import innings as inn
from bucco.models import marcel
from bucco.models.depth_chart_model import DepthChartModel, PlayerData

# source in player_projections -> (name for messages, how playing time is decided)
SOURCES = {"zips": ("ZiPS", "depth_chart"), "steamer": ("Steamer", "as_given")}


@lru_cache(maxsize=4)
def load_player_data(source: str = "zips", path=DUCKDB_PATH,
                     playing_time: str | None = None) -> PlayerData:
    """One source's player projections; `playing_time` overrides the source's default."""
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    label, default = SOURCES[source]
    playing_time = playing_time or default
    with duckdb.connect(str(path), read_only=True) as con:
        proj = con.execute("select * from marts.player_projections where source = ? "
                           "and team_id is not null and mlbam_id is not null", [source]).df()
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
        matchups = con.sql("select season, team_id, opponent_id, games "
                           "from marts.team_matchups").df()
    batters = proj[proj["player_type"] == "batter"].rename(
        columns={"plate_appearances": "pa", "bsr_runs": "bsr"})
    pitchers = proj[proj["player_type"] == "pitcher"].rename(
        columns={"innings_pitched": "ip", "games_started": "gs"})
    return PlayerData(batters, pitchers, positions, source=label, playing_time=playing_time,
                      matchups=matchups)


FIELDING_SOURCES = ("steamer", "zips")    # whose projected Def Marcel borrows (`fielding`)


def external_def_rates(sources: tuple[str, ...] = FIELDING_SOURCES,
                       path=DUCKDB_PATH) -> pd.DataFrame:
    """season, mlbam_id, def_rate: the mean over `sources` of each batter's projected Def per
    PA, over the sources that project him (any team or none). The files are made before
    Opening Day, so the target season's may be used."""
    with duckdb.connect(str(path), read_only=True) as con:
        rows = con.execute(
            "select source, season, mlbam_id, def_runs / plate_appearances as def_rate "
            "from marts.player_projections where player_type = 'batter' "
            "and mlbam_id is not null and plate_appearances > 0 and def_runs is not null "
            "and source in (select unnest(?)) "
            "qualify row_number() over (partition by source, season, mlbam_id "
            "order by plate_appearances desc) = 1", [list(sources)]).df()
    return rows.groupby(["season", "mlbam_id"], as_index=False)["def_rate"].mean()


@lru_cache(maxsize=4)
def marcel_projections(aging: bool = False, prior: str = "league", park: bool = False,
                       fielding: bool = False, innings: str = "marcel",
                       availability: str = "none",
                       path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Marcel projections (bucco.models.marcel) for every player with MLB history in the three
    seasons before each target season, on any team or none: (batters, pitchers). `aging`
    applies age curves fitted, for each target season, on earlier seasons only. `prior` is what
    rates are shrunk toward (marcel.PRIORS; "fitted" depends on how much history a player has).
    `park` projects from park-neutral history (and fits the age curves on it). `fielding`
    replaces batters' positional-only Def with the mean of Steamer's and ZiPS's projected Def
    per PA (marcel.apply_external_def). `innings`: "marcel" (Marcel's playing-time formula)
    or "baseline" (bucco.models.innings, fitted on earlier seasons' rostered pitchers), which
    also adds each season's start_penalty for the staff optimizer. `availability`: "none", or
    scale the playing time of players on a preseason roster by their Opening Day 40-man status
    (bucco.models.availability), "relative" to active 40-man players or "absolute"."""
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        league = con.sql("select * from marts.league_seasons").df()
        bat_frame = con.sql("select * from marts.batter_projection_frame").df()
        pit_frame = con.sql("select * from marts.pitcher_projection_frame").df()
        bat_history = con.sql("select season, mlbam_id, age, off_runs, off_runs_neutral, pa "
                              "from marts.player_batting_seasons where not is_pitcher").df()
        pit_history = con.sql("select season, mlbam_id, age, games, gs, outs, pitching_runs, "
                              "pitching_runs_neutral, bf from marts.player_pitching_seasons").df()
    off_col = "off_runs_neutral" if park else "off_runs"
    runs_col = "pitching_runs_neutral" if park else "pitching_runs"
    bat_curves = pit_curves = None
    if aging:
        bat_curves = marcel.age_curves(bat_history, off_col, "pa", bat_frame["season"])
        pit_curves = marcel.age_curves(pit_history, runs_col, "bf", pit_frame["season"])
    batters = marcel.project_batters(bat_frame, league, curves=bat_curves, prior=prior,
                                     park=park)
    if fielding:
        batters = marcel.apply_external_def(batters, external_def_rates(path=path), league)
    pit_frame = pit_frame.reset_index(drop=True)
    pitchers = marcel.project_pitchers(pit_frame, league, curves=pit_curves, prior=prior,
                                       park=park)
    if innings == "baseline":
        roster = marcel_rosters(path=path)
        keys = set(zip(roster.loc[roster["player_type"] == "pitcher", "season"],
                       roster.loc[roster["player_type"] == "pitcher", "mlbam_id"], strict=True))
        rostered = pd.Series([k in keys for k in zip(pit_frame["season"], pit_frame["mlbam_id"],
                                                      strict=True)])
        pitchers = marcel.rescale_innings(pitchers, inn.baseline_ip(pit_frame, rostered).to_numpy())
        penalty = inn.start_penalties(pit_history, runs_col, pitchers["season"])
        pitchers["start_penalty"] = pitchers["season"].map(penalty)
    elif innings != "marcel":
        raise ValueError(f"innings must be 'marcel' or 'baseline', not {innings!r}")
    if availability != "none":
        if availability not in ("relative", "absolute"):
            raise ValueError(f"availability must be 'none', 'relative' or 'absolute', "
                             f"not {availability!r}")
        with duckdb.connect(str(path), read_only=True) as con:
            status = con.sql("select season, mlbam_id, il_group "
                             "from marts.player_preseason_status").df()
        roster = marcel_rosters(path=path)
        relative = availability == "relative"
        # what was delivered: 0 for a completed season he did not play, unknown for the upcoming
        bat_real = bat_frame.assign(actual=bat_frame["target_pa"].fillna(0.0).where(
            ~bat_frame["is_upcoming_season"].astype(bool)))
        pit_real = pit_frame.assign(actual=(pit_frame["target_outs"] / 3.0).fillna(0.0).where(
            ~pit_frame["is_upcoming_season"].astype(bool)))
        f = _availability_factor(batters, "pa", bat_real, roster, "batter", status, relative)
        for col in ("pa", "off_runs", "def_runs", "fld_runs", "bsr", "war"):
            batters[col] = batters[col] * f
        batters["availability"] = f
        f = _availability_factor(pitchers, "ip", pit_real, roster, "pitcher", status, relative)
        pitchers = marcel.rescale_innings(pitchers, pitchers["ip"] * f)
        pitchers["availability"] = f
    return batters, pitchers


def _availability_factor(proj: pd.DataFrame, volume: str, frame: pd.DataFrame,
                         roster: pd.DataFrame, player_type: str, status: pd.DataFrame,
                         relative: bool) -> pd.Series:
    """Availability factor per projection row: fitted and applied only for players on a
    preseason roster (others, such as unsigned free agents, get 1)."""
    keys = roster.loc[roster["player_type"] == player_type, ["season", "mlbam_id"]]
    rows = proj[["season", "mlbam_id", volume]].reset_index().merge(
        keys.drop_duplicates(), on=["season", "mlbam_id"]).merge(
        frame[["season", "mlbam_id", "actual"]].drop_duplicates(["season", "mlbam_id"]),
        on=["season", "mlbam_id"], how="left").set_index("index")
    groups = avail.status_groups(rows, status)
    f = avail.availability(groups, rows[volume], rows["actual"], rows["season"], relative)
    return pd.Series(1.0, index=proj.index).add(f - 1.0, fill_value=0.0)


@lru_cache(maxsize=1)
def park_fit_inputs(path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(batter profiles, team parks, league constants) for the park fit. Team parks for season
    S are the side factors through S - 1 at the ballpark the team plays in during S (from the
    schedule, so known before Opening Day); a team in a new ballpark gets none (neutral)."""
    with duckdb.connect(str(path), read_only=True) as con:
        league = con.sql("select * from marts.league_seasons").df()
        frame = con.sql("select f.*, p.bats from marts.batter_projection_frame f "
                        "left join staging.stg_mlb__people p using (mlbam_id)").df()
        parks = con.sql(
            "select hp.season, hp.team_id, pf.* exclude (season, team_id, venue_id, venue_name, "
            "seasons_pooled) from intermediate.int__team_home_parks hp "
            "join marts.park_factors_by_side pf on pf.team_id = hp.team_id "
            "and pf.season = hp.season - 1 and pf.venue_id = hp.venue_id").df()
    return marcel.batter_profiles(frame, league), parks, league


def with_park_fit(batters: pd.DataFrame, team_means: pd.Series | None = None,
                  path=DUCKDB_PATH) -> pd.DataFrame:
    """Batters on teams (season, mlbam_id, team_id, pa, off_runs, war) with each one's fit to
    his team's park added (marcel.apply_park_fit), centered on `team_means` (default: these
    rows' own team averages)."""
    profiles, parks, league = park_fit_inputs(path)
    runs = marcel.park_runs_per_pa(batters, profiles, parks, league)
    return marcel.apply_park_fit(batters, runs, league, team_means)


def park_fit_team_means(batters: pd.DataFrame, path=DUCKDB_PATH) -> pd.Series:
    """Each team's PA-weighted park runs per PA over its rostered batters (for centering a
    player added to the team, such as a free agent)."""
    profiles, parks, league = park_fit_inputs(path)
    runs = marcel.park_runs_per_pa(batters, profiles, parks, league)
    keys = [batters["season"], batters["team_id"]]
    return (runs * batters["pa"]).groupby(keys).sum() / batters["pa"].groupby(keys).sum()


def marcel_rosters(roster_source: str = "steamer", path=DUCKDB_PATH) -> pd.DataFrame:
    """Preseason rosters: season, player_type, mlbam_id, team_id, as_of_date, from the team
    assignments in `roster_source`'s player files."""
    with duckdb.connect(str(path), read_only=True) as con:
        roster = con.execute("select distinct season, player_type, mlbam_id, team_id, as_of_date "
                             "from marts.player_projections where source = ? "
                             "and team_id is not null and mlbam_id is not null",
                             [roster_source]).df()
    return roster.drop_duplicates(["season", "player_type", "mlbam_id"])


def on_rosters(projections: pd.DataFrame, roster: pd.DataFrame, player_type: str) -> pd.DataFrame:
    """Projections of the players on a preseason roster, with their team."""
    rows = roster[roster["player_type"] == player_type].drop(columns="player_type")
    return projections.merge(rows, on=["season", "mlbam_id"])


@lru_cache(maxsize=4)
def load_marcel_data(playing_time: str = "depth_chart", roster_source: str = "steamer",
                     aging: bool = False, prior: str = "league", park: bool = False,
                     park_fit: bool = False, fielding: bool = False,
                     innings: str = "marcel", pitcher_playing_time: str = "depth_chart",
                     availability: str = "none", path=DUCKDB_PATH) -> PlayerData:
    """Our own Marcel projections on each team's preseason roster.

    Rosters are the team assignments in `roster_source`'s player files (players listed for
    each team before Opening Day); only who is on which team is taken from them. Players on a
    roster with no MLB history in the three prior seasons get no projection. Pitchers always go
    through the depth chart: Marcel lists every pitcher with his own innings. `park_fit` adds
    each batter's fit to his 2027 (target-season) park, centered on his team. `fielding`: see
    `marcel_projections`, as is `availability`. `innings` ("marcel" or "baseline") and
    `pitcher_playing_time`
    ("depth_chart" or "optimized": bucco.models.staff_optimizer) set how pitchers' innings are
    projected and shared out."""
    batters, pitchers = marcel_projections(aging, prior, park, fielding, innings,
                                           availability, path=path)
    roster = marcel_rosters(roster_source, path)
    with duckdb.connect(str(path), read_only=True) as con:
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
        matchups = con.sql("select season, team_id, opponent_id, games "
                           "from marts.team_matchups").df()
    batters = on_rosters(batters, roster, "batter")
    if park_fit:
        batters = with_park_fit(batters, path=path)
    return PlayerData(batters, on_rosters(pitchers, roster, "pitcher"),
                      positions, source="Marcel", playing_time=playing_time,
                      matchups=matchups, pitcher_playing_time=pitcher_playing_time)


def make_marcel_model() -> DepthChartModel:
    """Factory for the registry: our Marcel projections through the depth chart."""
    return DepthChartModel(load_marcel_data(), name="marcel")


def make_marcel_optimized_model() -> DepthChartModel:
    """Factory for the registry: Marcel batters through the lineup optimizer, pitchers through
    the depth chart."""
    return DepthChartModel(load_marcel_data("optimized"), name="marcel_optimized")


def make_marcel_aging_model() -> DepthChartModel:
    """Factory for the registry: Marcel with age curves, through the depth chart."""
    return DepthChartModel(load_marcel_data(aging=True), name="marcel_aging")


def make_marcel_aging_optimized_model() -> DepthChartModel:
    """Factory for the registry: Marcel with age curves, batters through the lineup optimizer."""
    return DepthChartModel(load_marcel_data("optimized", aging=True),
                           name="marcel_aging_optimized")


def make_marcel_shrunk_model() -> DepthChartModel:
    """Factory for the registry: Marcel with aging, each player shrunk toward what players with
    as much history went on to do (not the league average), through the depth chart."""
    return DepthChartModel(load_marcel_data(aging=True, prior="fitted"), name="marcel_shrunk")


def make_marcel_shrunk_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_shrunk` with batters through the lineup optimizer."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted"),
                           name="marcel_shrunk_optimized")


def make_marcel_park_model() -> DepthChartModel:
    """Factory for the registry: `marcel_shrunk` on park-neutral history."""
    return DepthChartModel(load_marcel_data(aging=True, prior="fitted", park=True),
                           name="marcel_park")


def make_marcel_park_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_park` with batters through the lineup optimizer and
    fielding borrowed from Steamer's and ZiPS's projected Def."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted", park=True,
                                            fielding=True), name="marcel_park_optimized")


def make_marcel_staff_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_park_optimized` with baseline innings
    (bucco.models.innings) shared out by the staff optimizer (bucco.models.staff_optimizer), and
    playing time scaled by Opening Day 40-man status (bucco.models.availability)."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted", park=True,
                                            fielding=True, innings="baseline",
                                            pitcher_playing_time="optimized",
                                            availability="absolute"),
                           name="marcel_staff_optimized")


def make_marcel_parkfit_model() -> DepthChartModel:
    """Factory for the registry: `marcel_park` plus each batter's fit to his team's park."""
    return DepthChartModel(load_marcel_data(aging=True, prior="fitted", park=True,
                                            park_fit=True), name="marcel_parkfit")


def make_marcel_parkfit_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_parkfit` with batters through the lineup optimizer."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted", park=True,
                                            park_fit=True), name="marcel_parkfit_optimized")


def make_depth_chart_model() -> DepthChartModel:
    """Factory for the registry: ZiPS through the depth chart, over shared, cached data."""
    return DepthChartModel(load_player_data("zips"))


def make_steamer_model() -> DepthChartModel:
    """Factory for the registry: Steamer's own playing time, team WAR summed as given."""
    return DepthChartModel(load_player_data("steamer"), name="steamer")


def make_steamer_optimized_model() -> DepthChartModel:
    """Factory for the registry: Steamer batters through the lineup optimizer, pitchers as given."""
    return DepthChartModel(load_player_data("steamer", playing_time="optimized"),
                           name="steamer_optimized")


def make_zips_optimized_model() -> DepthChartModel:
    """Factory for the registry: ZiPS batters through the lineup optimizer; ZiPS pitchers (a raw
    list of every player) through the depth chart."""
    return DepthChartModel(load_player_data("zips", playing_time="optimized"),
                           name="zips_optimized")
