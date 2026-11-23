"""Preseason win projections and betting win totals, collected by hand into CSV files.

No reliable free historical archive has been confirmed, so this module does not scrape
anything. It reads the CSV files in data/manual/projections/, checks them hard, and
saves one combined file. The file format is described in data/manual/projections/README.md.

Checks exist because bad projection data is the easiest way to fool the backtest:
a missing team, a duplicate row, or a projection dated after Opening Day would all
make a model look better than it is.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

import pandas as pd

from bucco.config import CACHE_DIR, MANUAL_DIR, SNAPSHOT_DIR, TEAMS_SEED
from bucco.extract._io import record_run, write_parquet

log = logging.getLogger(__name__)

SOURCE = "manual_projections"
INPUT_DIR = MANUAL_DIR / "projections"
OUTPUT_PATH = SNAPSHOT_DIR / "preseason_projections.parquet"
SEASONS_PATH = CACHE_DIR / "mlb_api" / "seasons.parquet"

REQUIRED_COLUMNS = ["season", "source", "kind", "as_of_date", "projected_wins"]
VALID_KINDS = {"projection", "market"}
WIN_RANGE = (40, 125)
SUM_RANGE = (2300, 2550)  # 30 teams x 81 wins is 2,430; betting totals run a bit high
EXPECTED_TEAMS = 30

# Player-level files, e.g. zips_batters_individual_2024.csv. They have their own reader
# (extract/player_projections.py) and are skipped here.
PLAYER_FILE_PATTERN = re.compile(
    r"^(?P<source>[a-z0-9]+)_(?P<kind>batters|pitchers)_individual_(?P<season>\d{4})\.csv$")

OUTPUT_COLUMNS = ["season", "source", "kind", "as_of_date", "team_id",
                  "projected_wins", "source_url", "notes", "source_file"]


class ProjectionValidationError(ValueError):
    """Raised when the input files fail checks. The message lists every problem found."""


def load_team_lookup(seed: Path = TEAMS_SEED) -> tuple[dict[str, int], set[int]]:
    """Map every accepted team abbreviation (current and old) to an MLB team id."""
    teams = pd.read_csv(seed, dtype=str, keep_default_na=False)
    lookup: dict[str, int] = {}
    for row in teams.itertuples():
        names = [row.team_abbr] + [a for a in row.aliases.split("|") if a]
        for name in names:
            lookup[name.strip().upper()] = int(row.team_id)
    return lookup, {int(t) for t in teams["team_id"]}


def read_input_files(directory: Path = INPUT_DIR) -> pd.DataFrame:
    """Read every team-level CSV in the folder (files starting with _ and player files are
    ignored)."""
    files = sorted(p for p in directory.glob("*.csv")
                   if not p.name.startswith("_") and not PLAYER_FILE_PATTERN.match(p.name))
    frames = []
    for path in files:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        frame.columns = [c.strip().lower() for c in frame.columns]
        frame["source_file"] = path.name
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def validate(
    raw: pd.DataFrame,
    lookup: dict[str, int],
    valid_team_ids: set[int],
    opening_days: dict[int, date] | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Clean and check the combined input. Returns (clean frame, errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        return raw, [f"missing required columns: {missing}"], warnings
    if "team_id" not in raw.columns and "team_abbr" not in raw.columns:
        return raw, ["needs a team_id or team_abbr column"], warnings

    df = raw.copy()
    for column in ("source_url", "notes"):
        if column not in df.columns:
            df[column] = ""

    # Teams: accept an MLB team id or an abbreviation (current or old).
    if "team_id" in df.columns:
        df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    else:
        df["team_id"] = df["team_abbr"].str.strip().str.upper().map(lookup)
    bad_teams = df.loc[~df["team_id"].isin(valid_team_ids), "team_abbr" if "team_abbr" in df.columns else "team_id"]
    if len(bad_teams):
        errors.append(f"unrecognised teams: {sorted(set(bad_teams.astype(str)))}")

    # Types and ranges.
    df["season"] = pd.to_numeric(df["season"], errors="coerce")
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["projected_wins"] = pd.to_numeric(df["projected_wins"], errors="coerce")
    df["source"] = df["source"].str.strip().str.lower()
    df["kind"] = df["kind"].str.strip().str.lower()

    for column in ("season", "as_of_date", "projected_wins"):
        n_bad = int(df[column].isna().sum())
        if n_bad:
            errors.append(f"{n_bad} rows have a missing or unreadable {column}")
    if (df["source"] == "").any():
        errors.append("some rows have an empty source")
    bad_kinds = set(df["kind"]) - VALID_KINDS
    if bad_kinds:
        errors.append(f"kind must be one of {sorted(VALID_KINDS)}, found {sorted(bad_kinds)}")
    out_of_range = df[(df["projected_wins"] < WIN_RANGE[0]) | (df["projected_wins"] > WIN_RANGE[1])]
    if len(out_of_range):
        errors.append(f"{len(out_of_range)} rows have projected_wins outside {WIN_RANGE}")

    keys = ["season", "source", "as_of_date", "team_id"]
    duplicates = df[df.duplicated(keys, keep=False)]
    if len(duplicates):
        errors.append(f"{len(duplicates)} rows repeat the same season/source/as_of_date/team")

    # Each set must cover all 30 teams, or a model could be scored on a partial league.
    set_keys = ["season", "source", "as_of_date"]
    for key, group in df.dropna(subset=set_keys).groupby(set_keys):
        n_teams = group["team_id"].nunique()
        if n_teams != EXPECTED_TEAMS:
            errors.append(f"{key[1]} {int(key[0])} ({key[2].date()}) has {n_teams} teams, "
                          f"expected {EXPECTED_TEAMS}")
        total = group["projected_wins"].sum()
        if n_teams == EXPECTED_TEAMS and not SUM_RANGE[0] <= total <= SUM_RANGE[1]:
            warnings.append(f"{key[1]} {int(key[0])}: team wins add up to {total:.0f}, "
                            f"usually {SUM_RANGE[0]}-{SUM_RANGE[1]}")

    # No peeking: a projection has to be dated on or before Opening Day.
    if opening_days:
        late = df[df.apply(
            lambda r: pd.notna(r["season"]) and pd.notna(r["as_of_date"])
            and int(r["season"]) in opening_days
            and r["as_of_date"].date() > opening_days[int(r["season"])], axis=1)]
        if len(late):
            errors.append(f"{len(late)} rows are dated after Opening Day")
    else:
        warnings.append("season calendar not found, so as_of_date was not checked against "
                        "Opening Day (run `bucco extract mlb-seasons`)")

    clean = df.copy()
    clean["as_of_date"] = clean["as_of_date"].dt.strftime("%Y-%m-%d")
    clean["season"] = clean["season"].astype("Int64")
    clean["team_id"] = clean["team_id"].astype("Int64")
    return clean[OUTPUT_COLUMNS], errors, warnings


def _empty_frame() -> pd.DataFrame:
    """Right columns and types, no rows. Lets dbt build before any data is collected."""
    types = {"season": "Int64", "source": "string", "kind": "string", "as_of_date": "string",
             "team_id": "Int64", "projected_wins": "float64", "source_url": "string",
             "notes": "string", "source_file": "string"}
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in types.items()})


def _opening_days() -> dict[int, date] | None:
    if not SEASONS_PATH.exists():
        return None
    calendar = pd.read_parquet(SEASONS_PATH)
    starts = pd.to_datetime(calendar["regular_season_start_date"], errors="coerce")
    seasons = pd.to_numeric(calendar["season_id"], errors="coerce")
    return {int(s): d.date() for s, d in zip(seasons, starts) if pd.notna(s) and pd.notna(d)}


def extract_projections() -> None:
    """Read, check and save the hand-collected projection files."""
    raw = read_input_files()
    if raw.empty:
        log.warning("No projection CSVs found in %s. Saving an empty table so dbt can still "
                    "build. See the README in that folder for the file format.", INPUT_DIR)
        clean = _empty_frame()
    else:
        lookup, valid_ids = load_team_lookup()
        clean, errors, warnings = validate(raw, lookup, valid_ids, _opening_days())
        for message in warnings:
            log.warning(message)
        if errors:
            raise ProjectionValidationError(
                "Projection files failed checks:\n  - " + "\n  - ".join(errors))

    write_parquet(clean, OUTPUT_PATH)
    record_run(SOURCE, "preseason_projections", OUTPUT_PATH, rows=len(clean))
    log.info("Saved %d projection rows to %s", len(clean), OUTPUT_PATH)
