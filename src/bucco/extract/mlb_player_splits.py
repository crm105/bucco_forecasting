"""MLB Stats API: players' season lines split by home/road and by batter side.

Four league-wide requests per season:

* batters at home and on the road (`h`, `a`): used to measure how each park treats left- and
  right-side hitters differently (park_factors_by_side), from each team's own hitters;
* batters batting left and batting right (`l`, `r`): each batter's side mix (switch hitters bat
  from both sides);
* batters against left- and right-handed pitchers (`vl`, `vr`, named vs_lhp and vs_rhp): each
  batter's platoon mix and split;
* pitchers against left- and right-side batters (`vl`, `vr`): each pitcher's mix of batters.

One row per player and split, with full-season counts (a traded player's home games at several
parks are combined, so traded players are left out of the park measurement).

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/player_splits/season=<year>.parquet
"""

from __future__ import annotations

import logging

import pandas as pd

from bucco.config import CACHE_DIR
from bucco.extract._io import get_json, record_run, utc_now_iso, write_parquet
from bucco.extract.mlb_api import BASE_URL, SEASONS_PATH, completed_seasons, extract_seasons

log = logging.getLogger(__name__)

SOURCE = "mlb_api"
SPLITS_DIR = CACHE_DIR / "mlb_api" / "player_splits"
STATS_LIMIT = 10_000
# (API group, situation codes) -> our group; split codes -> our names
REQUESTS = [("hitting", "h,a", "batting"), ("hitting", "l,r", "batting"),
            ("hitting", "vl,vr", "batting"), ("pitching", "vl,vr", "pitching")]
SPLITS = {"h": "home", "a": "road", "l": "bat_left", "r": "bat_right",
          "vl": "vs_left", "vr": "vs_right"}
BATTER_VS = {"vl": "vs_lhp", "vr": "vs_rhp"}     # a batter's split against the pitcher's hand
STATS = {"runs": "runs", "hits": "h", "doubles": "doubles", "triples": "triples",
         "homeRuns": "hr", "baseOnBalls": "bb", "intentionalWalks": "ibb", "hitByPitch": "hbp",
         "strikeOuts": "so"}
COLUMNS = ["season", "mlbam_id", "group", "split", "last_team_id", "num_teams", "pa",
           *STATS.values(), "fetched_at"]
PA_TOLERANCE = 0.005     # each pair of splits must add up to league PA within 0.5%


def parse_player_splits(payload: dict, season: int, group: str,
                        fetched_at: str) -> list[dict]:
    rows = []
    for block in payload.get("stats") or []:
        for split in block.get("splits") or []:
            code = (split.get("split") or {}).get("code")
            if code not in SPLITS:
                continue
            stat = split["stat"]
            pa = stat.get("plateAppearances") if group == "batting" else stat.get("battersFaced")
            name = BATTER_VS.get(code, SPLITS[code]) if group == "batting" else SPLITS[code]
            row = {"season": season, "mlbam_id": split["player"]["id"], "group": group,
                   "split": name, "last_team_id": (split.get("team") or {}).get("id"),
                   "num_teams": int(split.get("numTeams") or 1), "pa": int(pa or 0)}
            row.update({ours: int(stat.get(api) or 0) for api, ours in STATS.items()})
            row["fetched_at"] = fetched_at
            rows.append(row)
    return rows


def fetch_player_splits(season: int) -> pd.DataFrame:
    fetched_at = utc_now_iso()
    rows: list[dict] = []
    for api_group, codes, group in REQUESTS:
        params = {"stats": "statSplits", "group": api_group, "sitCodes": codes,
                  "season": season, "sportId": 1, "playerPool": "ALL", "limit": STATS_LIMIT,
                  "gameType": "R"}
        rows += parse_player_splits(get_json(f"{BASE_URL}/stats", params=params), season, group,
                                    fetched_at)
    return pd.DataFrame(rows, columns=COLUMNS)


def validate_player_splits(df: pd.DataFrame, season: int) -> None:
    """Every pair of splits must cover the same plate appearances (home + road = left + right
    = against left- + right-handed pitchers = pitchers' batters faced against left + right), and
    no player may appear twice in a split."""
    problems = []
    if len(df) >= STATS_LIMIT:
        problems.append(f"{len(df)} rows reaches the request limit; some are missing")
    if df.duplicated(["mlbam_id", "group", "split"]).any():
        problems.append("a player appears twice in one split")
    totals = df.groupby("split")["pa"].sum()
    pairs = {"home/road": ("home", "road"), "batting left/right": ("bat_left", "bat_right"),
             "batters vs left/right-handed pitchers": ("vs_lhp", "vs_rhp"),
             "pitchers vs left/right": ("vs_left", "vs_right")}
    sums = {name: int(totals.get(a, 0) + totals.get(b, 0)) for name, (a, b) in pairs.items()}
    reference = sums["home/road"]
    if reference < 60_000:
        problems.append(f"only {reference:,} plate appearances")
    for name, total in sums.items():
        if reference and abs(total - reference) > PA_TOLERANCE * reference:
            problems.append(f"{name} PA {total:,} differ from home/road PA {reference:,}")
    if problems:
        raise ValueError(f"Player splits for {season} failed checks: " + "; ".join(problems))


def extract_player_splits(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Home/road and batter-side splits for completed seasons, one file per season."""
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
        df = fetch_player_splits(season)
        validate_player_splits(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "player_splits", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/stats?stats=statSplits")
        log.info("Saved %d player split rows for %d", len(df), season)
