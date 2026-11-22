"""MLB Stats API: the season calendar and final regular-season standings.

Standings cover every team, so one source gives the full backtest history (wins, losses,
runs scored and allowed, playoff status). Team ids stay the same through moves and
renames, so `team_id` is the franchise key everywhere in this project.

Saved files (all rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/seasons.parquet
    data/cache/mlb_api/standings/season=<year>.parquet
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from bucco.config import CACHE_DIR, setting
from bucco.extract._io import get_json, record_run, utc_now_iso, write_parquet

log = logging.getLogger(__name__)

SOURCE = "mlb_api"
BASE_URL = "https://statsapi.mlb.com/api/v1"
LEAGUE_IDS = "103,104"  # American League, National League

SEASONS_PATH = CACHE_DIR / "mlb_api" / "seasons.parquet"
STANDINGS_DIR = CACHE_DIR / "mlb_api" / "standings"

EXPECTED_TEAMS = 30


def fetch_seasons() -> pd.DataFrame:
    """Season calendar: one row per season with the key dates."""
    payload = get_json(f"{BASE_URL}/seasons/all", params={"sportId": 1})
    fetched_at = utc_now_iso()
    rows = [
        {
            "season_id": s["seasonId"],
            "regular_season_start_date": s.get("regularSeasonStartDate"),
            "regular_season_end_date": s.get("regularSeasonEndDate"),
            "post_season_start_date": s.get("postSeasonStartDate"),
            "post_season_end_date": s.get("postSeasonEndDate"),
            "has_wildcard": s.get("hasWildcard"),
            "fetched_at": fetched_at,
        }
        for s in payload["seasons"]
    ]
    return pd.DataFrame(rows)


def extract_seasons() -> None:
    """Fetch the season calendar and save it. Always refreshed (it is small and changes)."""
    df = fetch_seasons()
    write_parquet(df, SEASONS_PATH)
    record_run(SOURCE, "seasons", SEASONS_PATH, rows=len(df), url=f"{BASE_URL}/seasons/all")
    log.info("Saved %d seasons to %s", len(df), SEASONS_PATH)


def fetch_standings(season: int) -> pd.DataFrame:
    """Final regular-season standings for one season: one row per team."""
    params = {"leagueId": LEAGUE_IDS, "season": season, "standingsTypes": "regularSeason"}
    payload = get_json(f"{BASE_URL}/standings", params=params)
    fetched_at = utc_now_iso()

    rows = []
    for record in payload["records"]:  # one record per division
        for t in record["teamRecords"]:
            rows.append(
                {
                    "season": season,
                    "team_id": t["team"]["id"],
                    "team_name": t["team"]["name"],
                    "league_id": record["league"]["id"],
                    "division_id": record["division"]["id"],
                    "games_played": t["gamesPlayed"],
                    "wins": t["wins"],
                    "losses": t["losses"],
                    "runs_scored": t["runsScored"],
                    "runs_allowed": t["runsAllowed"],
                    "division_rank": t.get("divisionRank"),
                    # x, y, z, w when the team made the playoffs, empty otherwise
                    "clinch_indicator": t.get("clinchIndicator"),
                    "fetched_at": fetched_at,
                }
            )
    return pd.DataFrame(rows)


def validate_standings(df: pd.DataFrame, season: int) -> None:
    """Refuse to save a season that looks incomplete or wrong."""
    problems = []
    if len(df) != EXPECTED_TEAMS or df["team_id"].nunique() != EXPECTED_TEAMS:
        problems.append(f"expected {EXPECTED_TEAMS} distinct teams, got {len(df)} rows")
    if df["wins"].sum() != df["losses"].sum():
        problems.append(f"league wins ({df['wins'].sum()}) do not equal losses ({df['losses'].sum()})")
    if df[["wins", "losses", "runs_scored", "runs_allowed"]].isna().any().any():
        problems.append("missing wins, losses or runs")
    if problems:
        raise ValueError(f"Standings for {season} failed checks: " + "; ".join(problems))


def completed_seasons(calendar: pd.DataFrame, today: date | None = None) -> list[int]:
    """Seasons from the history start that finished at least `completed_buffer_days` ago."""
    today = today or date.today()
    buffer = timedelta(days=setting("completed_buffer_days"))
    first = setting("history_start_season")

    ends = pd.to_datetime(calendar["regular_season_end_date"], errors="coerce")
    seasons = pd.to_numeric(calendar["season_id"], errors="coerce")
    done = ends.notna() & ((ends + buffer) <= pd.Timestamp(today)) & (seasons >= first)
    return sorted(int(s) for s in seasons[done])


def extract_standings(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Fetch final standings for completed seasons and save one file per season.

    Seasons already saved are skipped unless `refresh` is set. A season that has not
    finished yet is never saved, so a half-played season cannot be mistaken for a result.
    """
    if not SEASONS_PATH.exists():
        extract_seasons()
    calendar = pd.read_parquet(SEASONS_PATH)
    available = completed_seasons(calendar)

    targets = seasons if seasons else available
    for season in targets:
        if season not in available:
            log.warning("Skipping %d: not a completed season in the calendar", season)
            continue
        out = STANDINGS_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue

        df = fetch_standings(season)
        validate_standings(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "standings", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/standings")
        log.info("Saved %d standings rows for %d", len(df), season)
