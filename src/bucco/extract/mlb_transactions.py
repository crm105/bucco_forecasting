"""MLB Stats API: injured-list transactions by season (placements, transfers, activations).

The raw material for how long each player spent on the injured list (the disabled list before
2019) in past seasons: marts.player_il_seasons. One request per calendar year; only rows about the
injured list are kept, parsed into an event, the list's length and any retroactive start date
("placed ... on the 15-day injured list retroactive to March 25, 2024."). The API's log is nearly
empty before 2009.

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/mlb_api/il_transactions/season=<year>.parquet
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

import pandas as pd

from bucco.config import CACHE_DIR
from bucco.extract._io import get_json, record_run, utc_now_iso, write_parquet
from bucco.extract.mlb_api import BASE_URL

log = logging.getLogger(__name__)

SOURCE = "mlb_api"
IL_DIR = CACHE_DIR / "mlb_api" / "il_transactions"
FIRST_SEASON = 2009                # the first year with a full transaction log
MIN_IL_ROWS = 500                  # a season has 800 to 1,700

COLUMNS = ["season", "transaction_id", "date", "effective_date", "mlbam_id", "player_name",
           "team_id", "event", "list_days", "retro_date", "description", "fetched_at"]

_IL = re.compile(r"(injured|disabled) list", re.IGNORECASE)
_EVENTS = (("transferred", "transferred"), ("placed", "placed"), ("activated", "activated"),
           ("reinstated", "activated"))
_DAYS = re.compile(r"(\d+)[- ]day (?:injured|disabled) list", re.IGNORECASE)
_RETRO = re.compile(r"retroactive to ([A-Z][a-z]+\.? \d{1,2}, \d{4})")


def _retro_date(text: str) -> str | None:
    m = _RETRO.search(text)
    if not m:
        return None
    raw = m.group(1).replace(".", "")
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_transactions(payload: dict, season: int, fetched_at: str) -> list[dict]:
    """The injured-list rows of one year's transactions. `event` is placed, transferred (to a
    longer list), activated (or reinstated) or other; `list_days` is the list named first."""
    rows = []
    for t in payload.get("transactions", []):
        text = t.get("description") or ""
        person = t.get("person") or {}
        if not _IL.search(text) or not person.get("id"):
            continue
        lower = text.lower()
        event = next((name for word, name in _EVENTS if f" {word} " in f" {lower}"), "other")
        days = _DAYS.search(text)
        team = t.get("toTeam") or t.get("fromTeam") or {}
        rows.append({
            "season": season, "transaction_id": t.get("id"), "date": t.get("date"),
            "effective_date": t.get("effectiveDate") or t.get("date"),
            "mlbam_id": person["id"], "player_name": person.get("fullName"),
            "team_id": team.get("id"), "event": event,
            "list_days": int(days.group(1)) if days else None,
            "retro_date": _retro_date(text), "description": text, "fetched_at": fetched_at})
    return rows


def fetch_transactions(season: int) -> pd.DataFrame:
    """One calendar year's injured-list transactions, major-league teams (one request)."""
    payload = get_json(f"{BASE_URL}/transactions",
                       params={"sportId": 1, "startDate": f"{season}-01-01",
                               "endDate": f"{season}-12-31"}, timeout=120)
    return pd.DataFrame(parse_transactions(payload, season, utc_now_iso()), columns=COLUMNS)


def validate_transactions(df: pd.DataFrame, season: int) -> None:
    """Refuse a year that looks incomplete or unparsed."""
    problems = []
    if len(df) < MIN_IL_ROWS:
        problems.append(f"only {len(df)} injured-list rows")
    if df["transaction_id"].duplicated().any():
        problems.append("a transaction listed twice")
    placed = df[df["event"] == "placed"]
    if len(placed) and placed["list_days"].isna().mean() > 0.05:
        problems.append("placements without a list length")
    if (df["event"] == "other").mean() > 0.25:
        problems.append("more than a quarter of rows not understood")
    if problems:
        raise ValueError(f"Injured-list transactions for {season} failed checks: "
                         + "; ".join(problems))


def extract_il_transactions(seasons: list[int] | None = None, refresh: bool = False,
                            today: date | None = None) -> None:
    """Fetch injured-list transactions for completed seasons from FIRST_SEASON."""
    today = today or date.today()
    last = today.year if today.month >= 11 else today.year - 1
    wanted = seasons or list(range(FIRST_SEASON, last + 1))
    for season in wanted:
        out = IL_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_transactions(season)
        validate_transactions(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "il_transactions", out, rows=len(df), season=season,
                   url=f"{BASE_URL}/transactions?sportId=1")
        log.info("Saved %d injured-list transactions for %d (%d placements)", len(df), season,
                 int((df["event"] == "placed").sum()))
