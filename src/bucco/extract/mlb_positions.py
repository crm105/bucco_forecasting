"""MLB Stats API: who played which position, by player, team and season.

One row per player, team and position, with games, games started and innings. Pitchers show
up as position `P` (games started tells starters from relievers) and designated hitters as
`DH`. This is the raw material for the player_positions panel, which lists each player's
position as of the PRIOR season (see transform/models/marts/player_positions.sql).

The endpoint is queried one team at a time, so a player traded mid-season has one row per team
instead of being folded into a single total.

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/fielding/season=<year>.parquet
"""

from __future__ import annotations

import logging

import pandas as pd

from bucco.config import CACHE_DIR, TEAMS_SEED
from bucco.extract._io import get_json, record_run, utc_now_iso, write_parquet
from bucco.extract.mlb_api import (
    BASE_URL,
    EXPECTED_TEAMS,
    SEASONS_PATH,
    completed_seasons,
    extract_seasons,
)

log = logging.getLogger(__name__)

SOURCE = "mlb_api"
FIELDING_DIR = CACHE_DIR / "mlb_api" / "fielding"
POSITIONS = {"P", "C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
MIN_ROWS_PER_TEAM = 20  # a real team uses at least this many player-position combinations

COLUMNS = ["season", "team_id", "mlbam_id", "player_name", "position", "games",
           "games_started", "innings", "fetched_at"]


def innings_to_float(text: str | None) -> float:
    """MLB writes innings as `69.2` meaning 69 and two thirds. Returns 69.667."""
    if not text:
        return 0.0
    whole, _, thirds = str(text).partition(".")
    return int(whole or 0) + int(thirds or 0) / 3


def parse_fielding(payload: dict, season: int, team_id: int, fetched_at: str) -> list[dict]:
    """One team's fielding splits as rows. Splits without a recognisable position are skipped."""
    rows = []
    for split in payload["stats"][0]["splits"] if payload.get("stats") else []:
        position = split.get("position", {}).get("abbreviation")
        if position not in POSITIONS:
            continue
        stat = split["stat"]
        rows.append({
            "season": season,
            "team_id": team_id,
            "mlbam_id": split["player"]["id"],
            "player_name": split["player"].get("fullName"),
            "position": position,
            "games": stat.get("gamesPlayed", stat.get("games", 0)) or 0,
            "games_started": stat.get("gamesStarted", 0) or 0,
            "innings": innings_to_float(stat.get("innings")),
            "fetched_at": fetched_at,
        })
    return rows


def team_ids(seed=TEAMS_SEED) -> list[int]:
    return [int(t) for t in pd.read_csv(seed, dtype=str)["team_id"]]


def fetch_fielding(season: int) -> pd.DataFrame:
    """Every team's fielding splits for one season."""
    fetched_at = utc_now_iso()
    rows: list[dict] = []
    for team in team_ids():
        params = {"stats": "season", "group": "fielding", "season": season, "sportId": 1,
                  "playerPool": "ALL", "teamId": team, "limit": 500, "gameType": "R"}
        payload = get_json(f"{BASE_URL}/stats", params=params)
        rows.extend(parse_fielding(payload, season, team, fetched_at))
    return pd.DataFrame(rows, columns=COLUMNS)


def validate_fielding(df: pd.DataFrame, season: int) -> None:
    """Refuse to save a season that looks incomplete or wrong."""
    problems = []
    if df["team_id"].nunique() != EXPECTED_TEAMS:
        problems.append(f"expected {EXPECTED_TEAMS} teams, got {df['team_id'].nunique()}")
    thin = df.groupby("team_id").size()
    thin = thin[thin < MIN_ROWS_PER_TEAM]
    if len(thin):
        problems.append(f"teams with fewer than {MIN_ROWS_PER_TEAM} rows: {sorted(thin.index)}")
    if df.duplicated(["team_id", "mlbam_id", "position"]).any():
        problems.append("a player appears twice at the same position for one team")
    if (df[["games", "games_started", "innings"]] < 0).any().any():
        problems.append("negative games or innings")
    missing = {"C", "SS", "CF", "P", "DH"} - set(df["position"])
    if missing:
        problems.append(f"no rows for positions {sorted(missing)}")
    if problems:
        raise ValueError(f"Fielding data for {season} failed checks: " + "; ".join(problems))


def extract_positions(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Fetch fielding splits for completed seasons, one file per season (30 requests each)."""
    if not SEASONS_PATH.exists():
        extract_seasons()
    available = completed_seasons(pd.read_parquet(SEASONS_PATH))
    for season in seasons if seasons else available:
        if season not in available:
            log.warning("Skipping %d: not a completed season in the calendar", season)
            continue
        out = FIELDING_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_fielding(season)
        validate_fielding(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "fielding", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/stats?group=fielding")
        log.info("Saved %d fielding rows for %d", len(df), season)
