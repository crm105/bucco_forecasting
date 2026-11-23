"""Load the player-level inputs the depth-chart model needs from the database.

This is the one place that reads `bucco.duckdb` for that model; the model itself is handed the
resulting `PlayerData`. The data is loaded once per process.
"""

from __future__ import annotations

from functools import lru_cache

import duckdb

from bucco.config import DUCKDB_PATH
from bucco.models.depth_chart_model import DepthChartModel, PlayerData

SOURCE = "zips"


@lru_cache(maxsize=1)
def load_player_data(path=DUCKDB_PATH) -> PlayerData:
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        proj = con.sql(f"select * from marts.player_projections where source = '{SOURCE}' "
                       "and team_id is not null and mlbam_id is not null").df()
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
    batters = proj[proj["player_type"] == "batter"].rename(
        columns={"plate_appearances": "pa", "bsr_runs": "bsr"})
    pitchers = proj[proj["player_type"] == "pitcher"].rename(
        columns={"innings_pitched": "ip", "games_started": "gs"})
    return PlayerData(batters, pitchers, positions)


def make_depth_chart_model() -> DepthChartModel:
    """Factory for the registry: a fresh model over the shared, cached player data."""
    return DepthChartModel(load_player_data())
