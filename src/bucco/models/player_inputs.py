"""Load the player-level inputs the rung-5a models need from the database.

This is the one place that reads `bucco.duckdb` for those models; each model is handed the
resulting `PlayerData`. Each source's data is loaded once per process.
"""

from __future__ import annotations

from functools import lru_cache

import duckdb

from bucco.config import DUCKDB_PATH
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
