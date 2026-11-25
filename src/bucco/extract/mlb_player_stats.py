"""MLB Stats API: what each player did, by player, team and season (batting and pitching).

This is the history our own player projections (rung 5b) are built from. One league-wide
request per season returns both groups: one row per player with his full-season totals, the
team he finished with and how many teams he played for. A two-way player appears in both files.

Why league-wide and not one request per team (as the fielding extract does): the per-team query
leaves out players who left the team during the season. In 2025 the Pirates' per-team rows were
654 plate appearances short of the team total, while the league-wide rows match league batters
faced exactly.

Only counting stats are kept. Rates (AVG, ERA, ...) are recomputed downstream from the counts so
that combining a traded player's teams, or several seasons, is a plain sum.

Player details (birth date for age, bats/throws, primary position) come from /people, fetched
only for ids not yet saved.

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/batting/season=<year>.parquet
    data/cache/mlb_api/pitching/season=<year>.parquet
    data/cache/mlb_api/people.parquet
"""

from __future__ import annotations

import logging

import pandas as pd

from bucco.config import CACHE_DIR
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
STATS_LIMIT = 5000          # rows per request; a season has ~800 batters and ~900 pitchers
BATTING_DIR = CACHE_DIR / "mlb_api" / "batting"
PITCHING_DIR = CACHE_DIR / "mlb_api" / "pitching"
PEOPLE_PATH = CACHE_DIR / "mlb_api" / "people.parquet"
PEOPLE_BATCH = 150          # ids per /people request
FULL_SEASON_PA = 150_000    # a full season has ~183,000 PA; 2020 (60 games) has ~68,000
MIN_SEASON_PA = 60_000
BF_PA_TOLERANCE = 0.005     # league batters faced must match league PA within 0.5%

# API field -> our column. Every one is a count.
BATTING_STATS = {
    "gamesPlayed": "games", "plateAppearances": "pa", "atBats": "ab", "hits": "h",
    "doubles": "doubles", "triples": "triples", "homeRuns": "hr", "baseOnBalls": "bb",
    "intentionalWalks": "ibb", "hitByPitch": "hbp", "strikeOuts": "so", "sacFlies": "sf",
    "sacBunts": "sh", "catchersInterference": "ci", "stolenBases": "sb",
    "caughtStealing": "cs", "groundIntoDoublePlay": "gidp", "groundOuts": "ground_outs",
    "airOuts": "air_outs", "runs": "runs", "rbi": "rbi",
}
PITCHING_STATS = {
    "gamesPitched": "games", "gamesStarted": "gs", "gamesFinished": "games_finished",
    "completeGames": "complete_games", "saves": "saves", "holds": "holds", "wins": "wins",
    "losses": "losses", "outs": "outs", "battersFaced": "bf", "hits": "h",
    "doubles": "doubles", "triples": "triples", "homeRuns": "hr", "baseOnBalls": "bb",
    "intentionalWalks": "ibb", "hitByPitch": "hbp", "strikeOuts": "so", "sacFlies": "sf",
    "sacBunts": "sh", "runs": "runs", "earnedRuns": "er", "wildPitches": "wp",
    "balks": "balks", "groundOuts": "ground_outs", "airOuts": "air_outs",
}
KEYS = ["season", "mlbam_id", "player_name", "last_team_id", "num_teams"]
BATTING_COLUMNS = KEYS + list(BATTING_STATS.values()) + ["fetched_at"]
PITCHING_COLUMNS = KEYS + list(PITCHING_STATS.values()) + ["fetched_at"]
PEOPLE_FIELDS = ("people,id,fullName,birthDate,batSide,pitchHand,primaryPosition,"
                 "abbreviation,code,mlbDebutDate,lastPlayedDate")
PEOPLE_COLUMNS = ["mlbam_id", "player_name", "birth_date", "bats", "throws",
                  "primary_position", "mlb_debut_date", "last_played_date", "fetched_at"]


def _rows(splits: list[dict], fields: dict, season: int, fetched_at: str) -> list[dict]:
    rows = []
    for split in splits:
        stat = split["stat"]
        row = {"season": season, "mlbam_id": split["player"]["id"],
               "player_name": split["player"].get("fullName"),
               "last_team_id": split.get("team", {}).get("id"),
               "num_teams": int(split.get("numTeams") or 1)}
        row.update({ours: int(stat.get(api) or 0) for api, ours in fields.items()})
        row["fetched_at"] = fetched_at
        rows.append(row)
    return rows


def parse_player_stats(payload: dict, season: int,
                       fetched_at: str) -> tuple[list[dict], list[dict]]:
    """Batting and pitching rows from a league-wide `group=hitting,pitching` response."""
    batting: list[dict] = []
    pitching: list[dict] = []
    for block in payload.get("stats") or []:
        group = block.get("group", {}).get("displayName")
        splits = block.get("splits") or []
        if group == "hitting":
            batting += _rows(splits, BATTING_STATS, season, fetched_at)
        elif group == "pitching":
            pitching += _rows(splits, PITCHING_STATS, season, fetched_at)
    return batting, pitching


def fetch_player_stats(season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Every player's batting and pitching line for one season (one request)."""
    params = {"stats": "season", "group": "hitting,pitching", "season": season, "sportId": 1,
              "playerPool": "ALL", "limit": STATS_LIMIT, "gameType": "R"}
    batting, pitching = parse_player_stats(get_json(f"{BASE_URL}/stats", params=params),
                                           season, utc_now_iso())
    return (pd.DataFrame(batting, columns=BATTING_COLUMNS),
            pd.DataFrame(pitching, columns=PITCHING_COLUMNS))


def validate_player_stats(batting: pd.DataFrame, pitching: pd.DataFrame, season: int) -> None:
    """Refuse to save a season that looks incomplete or wrong."""
    problems = []
    for name, df in (("batting", batting), ("pitching", pitching)):
        if df["last_team_id"].nunique() != EXPECTED_TEAMS:
            problems.append(f"{name}: expected {EXPECTED_TEAMS} teams, "
                            f"got {df['last_team_id'].nunique()}")
        if df["mlbam_id"].duplicated().any():
            problems.append(f"{name}: a player appears twice")
        if len(df) >= STATS_LIMIT:
            problems.append(f"{name}: {len(df)} rows hits the request limit; some are missing")
        counts = df.drop(columns=["season", "mlbam_id", "player_name", "last_team_id",
                                  "fetched_at"])
        if (counts < 0).any().any():
            problems.append(f"{name}: negative counts")
    pa, bf = batting["pa"].sum(), pitching["bf"].sum()
    if pa < MIN_SEASON_PA:
        problems.append(f"only {pa:,} plate appearances in the season")
    if pa and abs(bf - pa) / pa > BF_PA_TOLERANCE:
        problems.append(f"batters faced ({bf:,}) and plate appearances ({pa:,}) disagree")
    if problems:
        raise ValueError(f"Player stats for {season} failed checks: " + "; ".join(problems))


def parse_people(payload: dict, fetched_at: str) -> list[dict]:
    return [{
        "mlbam_id": p["id"],
        "player_name": p.get("fullName"),
        "birth_date": p.get("birthDate"),
        "bats": p.get("batSide", {}).get("code"),
        "throws": p.get("pitchHand", {}).get("code"),
        "primary_position": p.get("primaryPosition", {}).get("abbreviation"),
        "mlb_debut_date": p.get("mlbDebutDate"),
        "last_played_date": p.get("lastPlayedDate"),
        "fetched_at": fetched_at,
    } for p in payload.get("people") or []]


def extract_people(refresh: bool = False) -> None:
    """Details for every player in the saved batting and pitching files. Only ids not yet
    saved are fetched, unless `refresh`."""
    ids: set[int] = set()
    for folder in (BATTING_DIR, PITCHING_DIR):
        for path in folder.glob("season=*.parquet"):
            ids |= set(pd.read_parquet(path, columns=["mlbam_id"])["mlbam_id"].astype(int))
    saved = pd.read_parquet(PEOPLE_PATH) if PEOPLE_PATH.exists() and not refresh else None
    todo = sorted(ids - set(saved["mlbam_id"])) if saved is not None else sorted(ids)
    if not todo:
        log.info("People: nothing new to fetch")
        return
    fetched_at = utc_now_iso()
    rows: list[dict] = []
    for i in range(0, len(todo), PEOPLE_BATCH):
        batch = ",".join(str(x) for x in todo[i:i + PEOPLE_BATCH])
        payload = get_json(f"{BASE_URL}/people",
                           params={"personIds": batch, "fields": PEOPLE_FIELDS})
        rows += parse_people(payload, fetched_at)
    new = pd.DataFrame(rows, columns=PEOPLE_COLUMNS)
    missing = set(todo) - set(new["mlbam_id"])
    if missing:
        log.warning("People: no record returned for %d ids, e.g. %s", len(missing),
                    sorted(missing)[:5])
    people = new if saved is None else pd.concat([saved, new], ignore_index=True)
    people = people.drop_duplicates("mlbam_id", keep="last").sort_values("mlbam_id")
    write_parquet(people, PEOPLE_PATH)
    record_run(SOURCE, "people", PEOPLE_PATH, rows=len(people), url=f"{BASE_URL}/people")
    log.info("Saved %d people (%d new)", len(people), len(new))


def extract_player_stats(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Batting and pitching lines for completed seasons, one file per season and group, then
    the people they mention."""
    if not SEASONS_PATH.exists():
        extract_seasons()
    available = completed_seasons(pd.read_parquet(SEASONS_PATH))
    for season in seasons if seasons else available:
        if season not in available:
            log.warning("Skipping %d: not a completed season in the calendar", season)
            continue
        bat_out = BATTING_DIR / f"season={season}.parquet"
        pit_out = PITCHING_DIR / f"season={season}.parquet"
        if bat_out.exists() and pit_out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        batting, pitching = fetch_player_stats(season)
        validate_player_stats(batting, pitching, season)
        for df, out, dataset in ((batting, bat_out, "batting"), (pitching, pit_out, "pitching")):
            write_parquet(df, out)
            record_run(SOURCE, dataset, out, rows=len(df), season=season,
                       url=f"{BASE_URL}/stats?group=hitting,pitching")
        log.info("Saved %d batting and %d pitching rows for %d", len(batting), len(pitching),
                 season)
    extract_people(refresh=refresh)
