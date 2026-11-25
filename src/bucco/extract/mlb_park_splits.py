"""MLB Stats API: each team's batting and pitching lines at home and on the road, by season.

The raw material for park factors (see transform/models/marts/park_factors.sql): a team's home
games, with both teams batting, against its road games. Team batting at home plus team pitching
at home is everything that happened in its home games.

Two requests per season (home, road), each returning hitting and pitching for all 30 teams.

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/park_splits/season=<year>.parquet
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
SPLITS_DIR = CACHE_DIR / "mlb_api" / "park_splits"
SITES = {"h": "home", "a": "road"}
GROUPS = {"hitting": "batting", "pitching": "pitching"}
# API field -> our column. Batting rows have pa, pitching rows bf; both are "pa" here (the
# plate appearances in those games while the team batted, or while it pitched).
STATS = {"gamesPlayed": "games", "runs": "runs", "hits": "h", "doubles": "doubles",
         "triples": "triples", "homeRuns": "hr", "baseOnBalls": "bb", "intentionalWalks": "ibb",
         "hitByPitch": "hbp", "strikeOuts": "so", "sacFlies": "sf", "atBats": "ab"}
COLUMNS = ["season", "team_id", "site", "side", "pa", *STATS.values(), "fetched_at"]
SITE_PA_TOLERANCE = 0.01    # a team's home + road PA must match its season PA within 1%


def parse_splits(payload: dict, season: int, site: str, fetched_at: str) -> list[dict]:
    rows = []
    for block in payload.get("stats") or []:
        side = GROUPS.get(block.get("group", {}).get("displayName"))
        if side is None:
            continue
        for split in block.get("splits") or []:
            stat = split["stat"]
            pa = stat.get("plateAppearances") if side == "batting" else stat.get("battersFaced")
            row = {"season": season, "team_id": split["team"]["id"], "site": SITES[site],
                   "side": side, "pa": int(pa or 0)}
            row.update({ours: int(stat.get(api) or 0) for api, ours in STATS.items()})
            row["fetched_at"] = fetched_at
            rows.append(row)
    return rows


def fetch_splits(season: int) -> pd.DataFrame:
    fetched_at = utc_now_iso()
    rows: list[dict] = []
    for site in SITES:
        params = {"stats": "statSplits", "sitCodes": site, "group": "hitting,pitching",
                  "season": season, "sportId": 1, "gameType": "R"}
        rows += parse_splits(get_json(f"{BASE_URL}/teams/stats", params=params), season, site,
                             fetched_at)
    return pd.DataFrame(rows, columns=COLUMNS)


def validate_splits(df: pd.DataFrame, season: int) -> None:
    """Refuse a season without 30 teams at each site and side, or whose home and road games
    do not add up."""
    problems = []
    counts = df.groupby(["site", "side"])["team_id"].nunique()
    if len(counts) != 4 or (counts != EXPECTED_TEAMS).any():
        problems.append(f"expected {EXPECTED_TEAMS} teams for each site and side: {counts.to_dict()}")
    if df.duplicated(["team_id", "site", "side"]).any():
        problems.append("a team appears twice for one site and side")
    # Every game is someone's home game: league batting at home = league pitching on the road.
    by = df.groupby(["site", "side"])["pa"].sum()
    if len(by) == 4:
        for a, b in ((("home", "batting"), ("road", "pitching")),
                     (("road", "batting"), ("home", "pitching"))):
            if abs(by[a] - by[b]) > SITE_PA_TOLERANCE * by[a]:
                problems.append(f"{a} PA {by[a]:,} and {b} PA {by[b]:,} disagree")
    if problems:
        raise ValueError(f"Park splits for {season} failed checks: " + "; ".join(problems))


def extract_park_splits(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Home and road team lines for completed seasons, one file per season."""
    if not SEASONS_PATH.exists():
        extract_seasons()
    available = completed_seasons(pd.read_parquet(SEASONS_PATH))
    for season in seasons if seasons else available:
        if season not in available:
            log.warning("Skipping %d: not a completed season in the calendar", season)
            continue
        out = SPLITS_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_splits(season)
        validate_splits(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "park_splits", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/teams/stats?stats=statSplits")
        log.info("Saved %d park split rows for %d", len(df), season)
