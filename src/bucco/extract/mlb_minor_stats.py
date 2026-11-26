"""MLB Stats API: minor-league batting and pitching lines, Triple-A to Single-A, by player, level
and season.

One row per player and level a season (a player who moved between teams at one level has one
combined line, listed under his last team and league). With his age, the league (so league
environments such as the Pacific Coast League's can be taken out) and the counts our batting
run values need. The raw material for major-league equivalents (bucco.models.milb).

Levels are MLB's sport ids: 11 Triple-A, 12 Double-A, 13 High-A, 14 Single-A (Low-A). The 2021
reorganization moved whole leagues between High-A and Low-A, so a level is not the same set of
leagues across that year. There was no minor-league season in 2020.

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/minor_batting/season=<year>.parquet
    data/cache/mlb_api/minor_pitching/season=<year>.parquet
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bucco.config import CACHE_DIR
from bucco.extract._io import get_json, record_run, utc_now_iso, write_parquet
from bucco.extract.mlb_api import BASE_URL

log = logging.getLogger(__name__)

SOURCE = "mlb_api"
MINOR_DIR = CACHE_DIR / "mlb_api" / "minor_batting"
LEVELS = {11: "AAA", 12: "AA", 13: "A+", 14: "A"}
FIRST_SEASON = 2006                # three seasons before the first roster season (2009)
NO_SEASON = {2020}                 # minor-league season cancelled
MIN_ROWS_PER_LEVEL = 300

STATS = {"plateAppearances": "pa", "atBats": "ab", "hits": "h", "doubles": "doubles",
         "triples": "triples", "homeRuns": "hr", "baseOnBalls": "bb", "intentionalWalks": "ibb",
         "hitByPitch": "hbp", "strikeOuts": "so", "sacFlies": "sf", "sacBunts": "sh",
         "stolenBases": "sb", "caughtStealing": "cs", "gamesPlayed": "games"}
COLUMNS = ["season", "sport_id", "level", "league_id", "league_name", "team_id", "mlbam_id",
           "player_name", "age", "num_teams", *STATS.values(), "fetched_at"]


def parse_batting(payload: dict, season: int, sport_id: int, fetched_at: str) -> list[dict]:
    """One level's season batting lines as rows."""
    rows = []
    for split in payload["stats"][0]["splits"] if payload.get("stats") else []:
        stat = split.get("stat", {})
        row = {"season": season, "sport_id": sport_id, "level": LEVELS[sport_id],
               "league_id": split.get("league", {}).get("id"),
               "league_name": split.get("league", {}).get("name"),
               "team_id": split.get("team", {}).get("id"),
               "mlbam_id": split["player"]["id"], "player_name": split["player"].get("fullName"),
               "age": stat.get("age"), "num_teams": split.get("numTeams"),
               "fetched_at": fetched_at}
        row.update({ours: int(stat.get(theirs) or 0) for theirs, ours in STATS.items()})
        rows.append(row)
    return rows


def fetch_batting(season: int) -> pd.DataFrame:
    """Every level's batting lines for one season (one request per level)."""
    fetched_at = utc_now_iso()
    rows: list[dict] = []
    for sport_id in LEVELS:
        payload = get_json(f"{BASE_URL}/stats",
                           params={"stats": "season", "group": "hitting", "sportId": sport_id,
                                   "season": season, "playerPool": "ALL", "limit": 10000})
        rows.extend(parse_batting(payload, season, sport_id, fetched_at))
    return pd.DataFrame(rows, columns=COLUMNS)


def validate_batting(df: pd.DataFrame, season: int) -> None:
    """Refuse to save a season that looks incomplete or wrong."""
    problems = []
    counts = df.groupby("level").size()
    missing = [lv for lv in LEVELS.values() if counts.get(lv, 0) < MIN_ROWS_PER_LEVEL]
    if missing:
        problems.append(f"levels with fewer than {MIN_ROWS_PER_LEVEL} players: {missing}")
    if df.duplicated(["level", "mlbam_id"]).any():
        problems.append("a player appears twice at one level")
    if df["league_id"].isna().any():
        problems.append("lines without a league")
    parts = df["ab"] + df["bb"] + df["hbp"] + df["sf"] + df["sh"]
    if (parts > df["pa"]).any():
        problems.append("at-bats, walks, hit by pitch and sacrifices exceed PA")
    if problems:
        raise ValueError(f"Minor-league batting for {season} failed checks: " + "; ".join(problems))


def extract_minor_batting(seasons: list[int] | None = None, refresh: bool = False,
                          today: date | None = None) -> None:
    """Fetch minor-league batting for completed seasons from FIRST_SEASON (4 requests each)."""
    today = today or date.today()
    last = today.year if today.month >= 10 else today.year - 1
    wanted = seasons or [s for s in range(FIRST_SEASON, last + 1) if s not in NO_SEASON]
    for season in wanted:
        out = MINOR_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_batting(season)
        validate_batting(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "minor_batting", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/stats?group=hitting&sportId=11-14")
        log.info("Saved %d minor-league batting lines for %d", len(df), season)


# ---- pitching ----------------------------------------------------------------------------
MINOR_PITCHING_DIR = CACHE_DIR / "mlb_api" / "minor_pitching"
PITCHING_STATS = {"outs": "outs", "battersFaced": "bf", "homeRuns": "hr", "baseOnBalls": "bb",
                  "intentionalWalks": "ibb", "hitBatsmen": "hbp", "strikeOuts": "so",
                  "hits": "h", "gamesStarted": "gs", "gamesPitched": "games"}
PITCHING_COLUMNS = ["season", "sport_id", "level", "league_id", "league_name", "team_id",
                    "mlbam_id", "player_name", "age", "num_teams", *PITCHING_STATS.values(),
                    "fetched_at"]
MIN_PITCHERS_PER_LEVEL = 300


def parse_pitching(payload: dict, season: int, sport_id: int, fetched_at: str) -> list[dict]:
    """One level's season pitching lines as rows (same layout as batting)."""
    rows = []
    for split in payload["stats"][0]["splits"] if payload.get("stats") else []:
        stat = split.get("stat", {})
        row = {"season": season, "sport_id": sport_id, "level": LEVELS[sport_id],
               "league_id": split.get("league", {}).get("id"),
               "league_name": split.get("league", {}).get("name"),
               "team_id": split.get("team", {}).get("id"),
               "mlbam_id": split["player"]["id"], "player_name": split["player"].get("fullName"),
               "age": stat.get("age"), "num_teams": split.get("numTeams"),
               "fetched_at": fetched_at}
        row.update({ours: int(stat.get(theirs) or 0) for theirs, ours in PITCHING_STATS.items()})
        rows.append(row)
    return rows


def fetch_pitching(season: int) -> pd.DataFrame:
    """Every level's pitching lines for one season (one request per level)."""
    fetched_at = utc_now_iso()
    rows: list[dict] = []
    for sport_id in LEVELS:
        payload = get_json(f"{BASE_URL}/stats",
                           params={"stats": "season", "group": "pitching", "sportId": sport_id,
                                   "season": season, "playerPool": "ALL", "limit": 10000})
        rows.extend(parse_pitching(payload, season, sport_id, fetched_at))
    return pd.DataFrame(rows, columns=PITCHING_COLUMNS)


def validate_pitching(df: pd.DataFrame, season: int) -> None:
    """Refuse to save a season that looks incomplete or wrong."""
    problems = []
    counts = df.groupby("level").size()
    missing = [lv for lv in LEVELS.values() if counts.get(lv, 0) < MIN_PITCHERS_PER_LEVEL]
    if missing:
        problems.append(f"levels with fewer than {MIN_PITCHERS_PER_LEVEL} pitchers: {missing}")
    if df.duplicated(["level", "mlbam_id"]).any():
        problems.append("a pitcher appears twice at one level")
    if df["league_id"].isna().any():
        problems.append("lines without a league")
    if (df["gs"] > df["games"]).any():
        problems.append("more starts than games")
    if (df["so"] + df["bb"] + df["hbp"] + df["hr"] > df["bf"]).any():
        problems.append("strikeouts, walks, hit batters and home runs exceed batters faced")
    if problems:
        raise ValueError(f"Minor-league pitching for {season} failed checks: "
                         + "; ".join(problems))


def extract_minor_pitching(seasons: list[int] | None = None, refresh: bool = False,
                           today: date | None = None) -> None:
    """Fetch minor-league pitching for completed seasons from FIRST_SEASON (4 requests each)."""
    today = today or date.today()
    last = today.year if today.month >= 10 else today.year - 1
    wanted = seasons or [s for s in range(FIRST_SEASON, last + 1) if s not in NO_SEASON]
    for season in wanted:
        out = MINOR_PITCHING_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_pitching(season)
        validate_pitching(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "minor_pitching", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/stats?group=pitching&sportId=11-14")
        log.info("Saved %d minor-league pitching lines for %d", len(df), season)
