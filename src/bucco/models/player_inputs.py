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
def load_player_data(source: str = "zips", path=DUCKDB_PATH) -> PlayerData:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    label, playing_time = SOURCES[source]
    with duckdb.connect(str(path), read_only=True) as con:
        proj = con.execute("select * from marts.player_projections where source = ? "
                           "and team_id is not null and mlbam_id is not null", [source]).df()
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
    batters = proj[proj["player_type"] == "batter"].rename(
        columns={"plate_appearances": "pa", "bsr_runs": "bsr"})
    pitchers = proj[proj["player_type"] == "pitcher"].rename(
        columns={"innings_pitched": "ip", "games_started": "gs"})
    return PlayerData(batters, pitchers, positions, source=label, playing_time=playing_time)


def make_depth_chart_model() -> DepthChartModel:
    """Factory for the registry: ZiPS through the depth chart, over shared, cached data."""
    return DepthChartModel(load_player_data("zips"))


def make_steamer_model() -> DepthChartModel:
    """Factory for the registry: Steamer's own playing time, team WAR summed as given."""
    return DepthChartModel(load_player_data("steamer"), name="steamer")
