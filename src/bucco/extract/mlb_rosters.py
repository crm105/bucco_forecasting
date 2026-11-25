"""MLB Stats API: each team's 40-man roster on its Opening Day, with each player's status.

The status says whether a player starts the season on the injured list (`D60`, `D15`, `D10`,
`D7`), active (`A`), in the minors (`RM` and others). That is what a forecaster knows about
injuries on Opening Day, and it is what Steamer's own files (made just before Opening Day) know.

The snapshot for a completed or started season is taken on each team's first regular-season game
(from the schedule cache), so teams that open abroad (Tokyo, Seoul) are taken on their own date.
For a season that has not started, it is taken today and refreshed on every run: the injured list
is cleared after the World Series, so a November snapshot shows only the few players teams kept on
the 60-day list.

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/rosters/season=<year>.parquet
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from bucco.config import CACHE_DIR
from bucco.extract._io import get_json, record_run, utc_now_iso, write_parquet
from bucco.extract.mlb_api import BASE_URL, EXPECTED_TEAMS
from bucco.extract.mlb_positions import team_ids

log = logging.getLogger(__name__)

SOURCE = "mlb_api"
ROSTER_DIR = CACHE_DIR / "mlb_api" / "rosters"
SCHEDULE_DIR = CACHE_DIR / "mlb_api" / "schedules"
FIRST_SEASON = 2012               # the first season with Steamer projections
MIN_PLAYERS_PER_TEAM = 30         # a 40-man roster on Opening Day has close to 40

COLUMNS = ["season", "team_id", "snapshot_date", "mlbam_id", "player_name", "position",
           "status_code", "status_description", "fetched_at"]


def first_game_dates(season: int, schedule_dir=SCHEDULE_DIR) -> dict[int, date]:
    """Each team's first regular-season game date, from the schedule cache."""
    path = schedule_dir / f"season={season}.parquet"
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract mlb-schedules` first.")
    games = pd.read_parquet(path)
    long = pd.concat([games[["game_date", "home_team_id"]].rename(columns={"home_team_id": "team_id"}),
                      games[["game_date", "away_team_id"]].rename(columns={"away_team_id": "team_id"})])
    first = pd.to_datetime(long["game_date"]).groupby(long["team_id"]).min()
    return {int(t): d.date() for t, d in first.items()}


def snapshot_dates(season: int, today: date | None = None,
                   schedule_dir=SCHEDULE_DIR) -> dict[int, date]:
    """The date each team's roster is taken: its first game, or today if that is still ahead."""
    today = today or date.today()
    return {t: min(d, today) for t, d in first_game_dates(season, schedule_dir).items()}


def parse_roster(payload: dict, season: int, team_id: int, snapshot: date,
                 fetched_at: str) -> list[dict]:
    """One team's roster as rows."""
    rows = []
    for p in payload.get("roster", []):
        status = p.get("status", {})
        rows.append({
            "season": season, "team_id": team_id, "snapshot_date": snapshot.isoformat(),
            "mlbam_id": p["person"]["id"], "player_name": p["person"].get("fullName"),
            "position": p.get("position", {}).get("abbreviation"),
            "status_code": status.get("code"), "status_description": status.get("description"),
            "fetched_at": fetched_at,
        })
    return rows


def fetch_rosters(season: int, today: date | None = None) -> pd.DataFrame:
    """Every team's 40-man roster on its snapshot date."""
    fetched_at = utc_now_iso()
    dates = snapshot_dates(season, today)
    rows: list[dict] = []
    for team in team_ids():
        snapshot = dates.get(team)
        if snapshot is None:
            continue
        payload = get_json(f"{BASE_URL}/teams/{team}/roster",
                           params={"rosterType": "40Man", "date": snapshot.isoformat()})
        rows.extend(parse_roster(payload, season, team, snapshot, fetched_at))
    return one_row_per_player(pd.DataFrame(rows, columns=COLUMNS))


def one_row_per_player(df: pd.DataFrame) -> pd.DataFrame:
    """The API sometimes lists a player twice on one team (2012: Zack Britton, both reassigned
    to the minors and on the 15-day injured list). Keep the injured-list row, since that is
    what this snapshot is for; otherwise the first."""
    on_il = df["status_code"].fillna("").str.startswith("D")
    order = df.assign(_il=~on_il).sort_values(["team_id", "mlbam_id", "_il"], kind="stable")
    out = order.drop_duplicates(["team_id", "mlbam_id"]).drop(columns="_il")
    if len(out) < len(df):
        log.info("Dropped %d duplicate roster rows (kept the injured-list status)",
                 len(df) - len(out))
    return out.sort_index().reset_index(drop=True)


def validate_rosters(df: pd.DataFrame, season: int) -> None:
    """Refuse to save a season that looks incomplete or wrong."""
    problems = []
    if df["team_id"].nunique() != EXPECTED_TEAMS:
        problems.append(f"expected {EXPECTED_TEAMS} teams, got {df['team_id'].nunique()}")
    thin = df.groupby("team_id").size()
    thin = thin[thin < MIN_PLAYERS_PER_TEAM]
    if len(thin):
        problems.append(f"teams with fewer than {MIN_PLAYERS_PER_TEAM} players: {sorted(thin.index)}")
    if df.duplicated(["team_id", "mlbam_id"]).any():
        problems.append("a player appears twice on one team")
    if df["status_code"].isna().any():
        problems.append("players without a status")
    if problems:
        raise ValueError(f"Roster data for {season} failed checks: " + "; ".join(problems))


def extract_rosters(seasons: list[int] | None = None, refresh: bool = False,
                    today: date | None = None) -> None:
    """Fetch Opening Day 40-man rosters (30 requests a season). Seasons that have not started
    are always fetched again, since their snapshot is today's."""
    today = today or date.today()
    available = sorted(int(p.stem.split("=")[1]) for p in SCHEDULE_DIR.glob("season=*.parquet"))
    for season in seasons if seasons else [s for s in available if s >= FIRST_SEASON]:
        if season not in available:
            log.warning("Skipping %d: no schedule saved (run `bucco extract mlb-schedules`)", season)
            continue
        out = ROSTER_DIR / f"season={season}.parquet"
        upcoming = min(first_game_dates(season).values()) > today
        if out.exists() and not refresh and not upcoming:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_rosters(season, today)
        validate_rosters(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "rosters", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/teams/<team>/roster?rosterType=40Man")
        on_il = int(df["status_code"].str.startswith("D").sum())
        log.info("Saved %d roster rows for %d (%d on the injured list)", len(df), season, on_il)
