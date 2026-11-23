"""Player-level preseason projections (for example ZiPS) downloaded by hand from FanGraphs.

Each file is one source, one player type and one season, named like
`zips_batters_individual_2024.csv` or `zips_pitchers_individual_2024.csv`, and lives in
data/manual/projections/ next to the team-level files. FanGraphs does not put the download
date in the file, so it is read from `_player_downloads.csv` in the same folder. Without a
date the rows are still saved, but they cannot be checked against Opening Day (a warning is
logged, and models must refuse rows with no date).

These rows are independent player projections, NOT a roster. Summing them by team counts
every depth and minor-league player with his own playing-time estimate, made without
regard to the rest of the roster, so team totals are far too high.
Turning them into a team forecast needs playing time allocated per team (model rung 5a).
The format is described in data/manual/projections/README.md.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from bucco.config import SNAPSHOT_DIR
from bucco.extract._io import record_run, write_parquet
from bucco.extract.projections import (
    EXPECTED_TEAMS,
    INPUT_DIR,
    PLAYER_FILE_PATTERN,
    ProjectionValidationError,
    _opening_days,
    load_team_lookup,
)

log = logging.getLogger(__name__)

SOURCE = "manual_projections"
OUTPUT_PATH = SNAPSHOT_DIR / "player_projections.parquet"
MANIFEST_NAME = "_player_downloads.csv"
PLAYER_TYPES = {"batters": "batter", "pitchers": "pitcher"}
WAR_RANGE = (-10, 20)
# File-name spellings that mean the same projection system. "streamer" is a common
# misspelling of Steamer; the files keep their names and the rows get the right source.
SOURCE_ALIASES = {"streamer": "steamer"}

# FanGraphs column -> our column, per player type. WAR and the playing-time column are required.
COMMON = {"Name": "player_name", "Team": "team_abbr", "PlayerId": "fangraphs_id",
          "MLBAMID": "mlbam_id", "G": "games", "WAR": "war"}
BATTER_COLUMNS = {**COMMON, "PA": "plate_appearances", "HR": "home_runs", "SB": "stolen_bases",
                  "AVG": "avg", "OBP": "obp", "SLG": "slg", "wOBA": "woba",
                  "wRC+": "wrc_plus", "Off": "off_runs", "Def": "def_runs",
                  "BsR": "bsr_runs", "Fld": "fld_runs"}
PITCHER_COLUMNS = {**COMMON, "GS": "games_started", "IP": "innings_pitched", "ERA": "era",
                   "FIP": "fip", "SO": "strikeouts", "BB": "walks", "HR": "home_runs",
                   "SV": "saves"}
REQUIRED = {"batter": ["Name", "Team", "PlayerId", "MLBAMID", "WAR", "PA"],
            "pitcher": ["Name", "Team", "PlayerId", "MLBAMID", "WAR", "IP"]}

OUTPUT_COLUMNS = [
    "season", "source", "player_type", "as_of_date", "fangraphs_id", "mlbam_id", "player_name",
    "team_abbr", "team_id", "games", "plate_appearances", "games_started", "innings_pitched",
    "war", "home_runs", "stolen_bases", "avg", "obp", "slg", "woba", "wrc_plus", "off_runs",
    "def_runs", "bsr_runs", "fld_runs", "era", "fip", "strikeouts", "walks", "saves",
    "source_url", "notes", "source_file",
]
NUMERIC = [c for c in OUTPUT_COLUMNS if c not in
           {"season", "source", "player_type", "as_of_date", "fangraphs_id", "mlbam_id",
            "player_name", "team_abbr", "team_id", "source_url", "notes", "source_file"}]


def player_files(directory: Path = INPUT_DIR) -> list[Path]:
    return sorted(p for p in directory.glob("*.csv") if PLAYER_FILE_PATTERN.match(p.name))


def read_manifest(directory: Path = INPUT_DIR) -> pd.DataFrame:
    """Download dates per file. Optional: a missing file or blank date means 'unknown'."""
    path = directory / MANIFEST_NAME
    columns = ["file", "as_of_date", "source_url", "notes"]
    if not path.exists():
        return pd.DataFrame(columns=columns)
    manifest = pd.read_csv(path, dtype=str, keep_default_na=False)
    manifest.columns = [c.strip().lower() for c in manifest.columns]
    for column in columns:
        if column not in manifest.columns:
            manifest[column] = ""
    manifest["file"] = manifest["file"].str.strip()
    return manifest[columns]


def read_file(path: Path) -> pd.DataFrame:
    """One FanGraphs export, renamed to our columns. Checks that required columns exist."""
    match = PLAYER_FILE_PATTERN.match(path.name)
    source, kind, season = match["source"], PLAYER_TYPES[match["kind"]], int(match["season"])
    source = SOURCE_ALIASES.get(source, source)
    raw = pd.read_csv(path, encoding="utf-8-sig")  # FanGraphs files start with a BOM
    raw.columns = [c.strip() for c in raw.columns]
    missing = [c for c in REQUIRED[kind] if c not in raw.columns]
    if missing:
        raise ProjectionValidationError(f"{path.name}: missing columns {missing}")
    mapping = BATTER_COLUMNS if kind == "batter" else PITCHER_COLUMNS
    frame = raw[[c for c in mapping if c in raw.columns]].rename(columns=mapping)
    frame["season"], frame["source"], frame["player_type"] = season, source, kind
    frame["source_file"] = path.name
    return frame


def validate(
    raw: pd.DataFrame,
    manifest: pd.DataFrame,
    lookup: dict[str, int],
    opening_days: dict[int, date] | None = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Clean and check the combined player files. Returns (clean frame, errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    df = raw.copy()

    # Rows with no team. A file with no teams at all (FanGraphs left the column empty) cannot
    # be placed on depth charts, so it is skipped. If exactly one team is absent from a file,
    # the blank rows are taken to be that team (FanGraphs left the Marlins blank in 2011 and
    # 2013). Any other blank row is a free agent and is dropped.
    first_abbr: dict[int, str] = {}
    for abbr, team_id in lookup.items():
        first_abbr.setdefault(team_id, abbr)
    no_team = df["team_abbr"].isna() | (df["team_abbr"].astype(str).str.strip() == "")
    for file, group in df.groupby("source_file"):
        blank = no_team.loc[group.index]
        if not blank.any():
            continue
        present = set(group.loc[~blank, "team_abbr"].astype(str).str.strip().str.upper().map(lookup)
                      .dropna().astype(int))
        missing = sorted(set(lookup.values()) - present)
        if not present:
            warnings.append(f"{file} has no team on any row, so it was skipped")
        elif len(missing) == 1:
            df.loc[blank[blank].index, "team_abbr"] = first_abbr[missing[0]]
            no_team.loc[blank[blank].index] = False
            warnings.append(f"{file}: {int(blank.sum())} rows with no team were assigned to "
                            f"{first_abbr[missing[0]]}, the only team missing from the file")
    if no_team.any():
        names = sorted(df.loc[no_team, "player_name"].fillna("(no name)").astype(str))
        shown = names if len(names) <= 10 else names[:10] + [f"... and {len(names) - 10} more"]
        warnings.append(f"dropped {int(no_team.sum())} rows with no team: {shown}")
        df = df.loc[~no_team].copy()

    # Team: FanGraphs abbreviations (KCR, SDP, ...) resolve to MLB team ids through the seed.
    df["team_id"] = df["team_abbr"].astype(str).str.strip().str.upper().map(lookup)
    unknown = sorted(set(df.loc[df["team_id"].isna(), "team_abbr"].astype(str)))
    if unknown:
        errors.append(f"unrecognised teams: {unknown}")

    for column in NUMERIC:
        df[column] = pd.to_numeric(df[column], errors="coerce") if column in df else float("nan")
    for column in ("fangraphs_id", "mlbam_id"):
        df[column] = df[column].astype(str).str.strip()
    # Rows with no MLB id cannot be matched to real playing time or positions, which are
    # keyed on it. FanGraphs exports a few: unnamed ones, and in Steamer the odd minor
    # leaguer projected for a plate appearance or two. Drop them and say so.
    no_id = df["mlbam_id"].fillna("").isin(["", "nan"])
    if no_id.any():
        listing = (df.loc[no_id, ["source_file", "player_name", "team_abbr", "war"]]
                   .round(2).to_dict("records"))
        shown = listing if len(listing) <= 10 else listing[:10] + [f"... {len(listing) - 10} more"]
        warnings.append(f"dropped {int(no_id.sum())} rows with no MLB id: {shown}")
        df = df.loc[~no_id].copy()
    if (df["fangraphs_id"].isin(["", "nan"])).any():
        errors.append("some rows have no PlayerId")
    if df["war"].isna().any():
        errors.append(f"{int(df['war'].isna().sum())} rows have a missing or unreadable WAR")
    bad_war = df[(df["war"] < WAR_RANGE[0]) | (df["war"] > WAR_RANGE[1])]
    if len(bad_war):
        errors.append(f"{len(bad_war)} rows have WAR outside {WAR_RANGE}")

    # Dates from the manifest.
    dates = manifest.drop_duplicates("file").set_index("file")
    df["as_of_date"] = pd.to_datetime(df["source_file"].map(dates["as_of_date"]).replace("", None),
                                      errors="coerce")
    df["source_url"] = df["source_file"].map(dates["source_url"]).replace("", None)
    df["notes"] = df["source_file"].map(dates["notes"]).replace("", None)
    listed = set(manifest["file"])
    undated = sorted(set(df["source_file"]) - set(df.loc[df["as_of_date"].notna(), "source_file"]))
    if undated:
        warnings.append(f"no as_of_date for {len(undated)} files, so they cannot be checked "
                        f"against Opening Day (fill in {MANIFEST_NAME}): {undated}")
    stray = sorted(listed - set(df["source_file"]))
    if stray:
        warnings.append(f"{MANIFEST_NAME} lists files that do not exist: {stray}")

    # One row per player within a file; every file covers the whole league.
    keys = ["season", "source", "player_type", "fangraphs_id"]
    duplicates = df[df.duplicated(keys, keep=False)]
    if len(duplicates):
        errors.append(f"{len(duplicates)} rows repeat a player within a file "
                      f"(e.g. {duplicates['source_file'].iloc[0]})")
    for file, group in df.groupby("source_file"):
        if group["team_id"].nunique() != EXPECTED_TEAMS:
            errors.append(f"{file} has {group['team_id'].nunique()} teams, "
                          f"expected {EXPECTED_TEAMS}")

    # No peeking: the download has to be dated on or before Opening Day.
    if opening_days:
        late = df[df.apply(lambda r: pd.notna(r["as_of_date"]) and r["season"] in opening_days
                           and r["as_of_date"].date() > opening_days[r["season"]], axis=1)]
        if len(late):
            errors.append(f"files dated after Opening Day: {sorted(set(late['source_file']))}")
    else:
        warnings.append("season calendar not found, so dates were not checked against Opening "
                        "Day (run `bucco extract mlb-seasons`)")

    # Batters and pitchers should come in pairs.
    present = df.groupby(["source", "season"])["player_type"].agg(set)
    for (source, season), types in present.items():
        if types != {"batter", "pitcher"}:
            warnings.append(f"{source} {season} has only {sorted(types)}; "
                            "the other player type is still missing")

    clean = df.copy()
    clean["as_of_date"] = clean["as_of_date"].dt.strftime("%Y-%m-%d")
    clean["season"] = clean["season"].astype("Int64")
    clean["team_id"] = clean["team_id"].astype("Int64")
    return clean[OUTPUT_COLUMNS], errors, warnings


def _empty_frame() -> pd.DataFrame:
    """Right columns and types, no rows. Lets dbt build before any files are added."""
    text = {"source", "player_type", "as_of_date", "fangraphs_id", "mlbam_id", "player_name",
            "team_abbr", "source_url", "notes", "source_file"}
    types = {c: ("string" if c in text else "Int64" if c in {"season", "team_id"}
                 else "float64") for c in OUTPUT_COLUMNS}
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in types.items()})


def extract_player_projections() -> None:
    """Read, check and save the hand-downloaded player projection files."""
    files = player_files()
    if not files:
        log.warning("No player projection files found in %s. Saving an empty table so dbt can "
                    "still build.", INPUT_DIR)
        clean = _empty_frame()
    else:
        raw = pd.concat([read_file(p) for p in files], ignore_index=True)
        lookup, _ = load_team_lookup()
        clean, errors, warnings = validate(raw, read_manifest(), lookup, _opening_days())
        for message in warnings:
            log.warning(message)
        if errors:
            raise ProjectionValidationError(
                "Player projection files failed checks:\n  - " + "\n  - ".join(errors))

    write_parquet(clean, OUTPUT_PATH)
    record_run(SOURCE, "player_projections", OUTPUT_PATH, rows=len(clean))
    log.info("Saved %d player projection rows to %s", len(clean), OUTPUT_PATH)
