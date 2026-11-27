"""Baseball Savant (Statcast) season leaderboards: contact quality and plate discipline.

Three CSV requests per season, from 2015 (the first Statcast season):

* the custom leaderboard for batters and for pitchers (what hitters did against them), every
  player with at least one PA: PA, strikeout and walk rates, xwOBA, average exit velocity and
  launch angle, barrel, hard-hit and sweet-spot rates, whiff rate, swing rates outside and inside
  the zone, contact rate inside the zone, and sprint speed (batters);
* the pitch-arsenal leaderboard: each pitcher's average speed by pitch type (four-seam, sinker,
  cutter, slider), joined to his row.

Rates are percentages as Savant gives them (whiff_percent 25.3 means 25.3%). player_id is the
MLBAM id. One file per season with batters and pitchers (player_type).

Fielding (`extract_fielding`), from 2016 (the first season with fielding run value): each
fielder's Statcast fielding run value in runs, total and by part (range, arm, double plays,
receiving at first; for catchers framing, throwing and blocking), and the outs he was on the
field for at each position (outs_2 catcher ... outs_9 right field). Savant's fielding run value
counts framing only from 2018; for 2016 and 2017 the framing runs of the older catcher-framing
leaderboard are added to framing, catching and total runs (framing_source "framing_leaderboard").

Saved files (rebuildable, so they live in the gitignored cache):
    data/cache/savant/players/season=<year>.parquet
    data/cache/savant/fielding/season=<year>.parquet
"""

from __future__ import annotations

import io
import logging

import pandas as pd

from bucco.config import CACHE_DIR
from bucco.extract._io import get_text, record_run, utc_now_iso, write_parquet
from bucco.extract.mlb_api import SEASONS_PATH, completed_seasons, extract_seasons

log = logging.getLogger(__name__)

SOURCE = "baseball_savant"
PLAYERS_DIR = CACHE_DIR / "savant" / "players"
FIELDING_DIR = CACHE_DIR / "savant" / "fielding"
FIRST_FIELDING_SEASON = 2016
FIRST_FRV_FRAMING = 2018          # fielding run value includes framing from this season
FRV_URL = "https://baseballsavant.mlb.com/leaderboard/fielding-run-value"
FRAMING_URL = "https://baseballsavant.mlb.com/catcher_framing"
FIELDING_RUNS = ["total_runs", "inf_of_runs", "range_runs", "arm_runs", "dp_runs",
                 "fielding_runs_prevented_on_rec1b", "catching_runs", "framing_runs",
                 "throwing_runs", "blocking_runs"]
OUTS = ["outs_total", *[f"outs_{p}" for p in range(2, 10)]]
FIELDING_COLUMNS = ["season", "mlbam_id", *FIELDING_RUNS, *OUTS, "framing_source", "fetched_at"]
MIN_FIELDERS = 500
MIN_OUTS = 300_000        # outs on the field in a season, all fielders (2020: about 370,000)
FIRST_SEASON = 2015
CUSTOM_URL = "https://baseballsavant.mlb.com/leaderboard/custom"
ARSENAL_URL = "https://baseballsavant.mlb.com/leaderboard/pitch-arsenals"
STATS = ["pa", "k_percent", "bb_percent", "xwoba", "exit_velocity_avg", "launch_angle_avg",
         "barrel_batted_rate", "hard_hit_percent", "sweet_spot_percent", "whiff_percent",
         "oz_swing_percent", "z_swing_percent", "iz_contact_percent"]
BATTER_ONLY = ["sprint_speed"]
SPEEDS = {"ff_avg_speed": "ff_speed", "si_avg_speed": "si_speed", "fc_avg_speed": "fc_speed",
          "sl_avg_speed": "sl_speed"}
COLUMNS = ["season", "mlbam_id", "player_type", *STATS, *BATTER_ONLY, *SPEEDS.values(),
           "fetched_at"]
MIN_ROWS = 400            # players of each type in a season (2020: about 500)
MIN_PA = 60_000           # plate appearances of each type in a season (2020: about 66,000)
MIN_SPEED_SHARE = 0.9     # of pitchers with 100+ PA against, the share with a pitch speed


def parse_custom(text: str, season: int, player_type: str, fetched_at: str) -> pd.DataFrame:
    """One custom-leaderboard CSV to our columns, exact repeats dropped (a player listed twice
    with different numbers is left for `validate_players` to refuse)."""
    df = pd.read_csv(io.StringIO(text))
    out = pd.DataFrame({"season": season, "mlbam_id": df["player_id"].astype("int64"),
                        "player_type": player_type})
    for c in STATS + BATTER_ONLY:
        out[c] = pd.to_numeric(df[c], errors="coerce") if c in df else float("nan")
    if player_type == "pitcher":
        out[BATTER_ONLY] = float("nan")
    out["fetched_at"] = fetched_at
    return out.drop_duplicates(ignore_index=True)    # Savant sometimes repeats a row exactly


def parse_speeds(text: str) -> pd.DataFrame:
    """The pitch-arsenal CSV: mlbam_id and average speed by pitch type."""
    df = pd.read_csv(io.StringIO(text))
    out = pd.DataFrame({"mlbam_id": df["pitcher"].astype("int64")})
    for api, ours in SPEEDS.items():
        out[ours] = pd.to_numeric(df[api], errors="coerce") if api in df else float("nan")
    return out.drop_duplicates("mlbam_id")


def fetch_players(season: int) -> pd.DataFrame:
    fetched_at = utc_now_iso()
    frames = []
    for player_type in ("batter", "pitcher"):
        selections = STATS + (BATTER_ONLY if player_type == "batter" else [])
        text = get_text(CUSTOM_URL, params={
            "year": season, "type": player_type, "filter": "", "min": 1,
            "selections": ",".join(selections), "chart": "false", "csv": "true"}, pause=2.0)
        frames.append(parse_custom(text, season, player_type, fetched_at))
    speeds = parse_speeds(get_text(ARSENAL_URL, params={
        "year": season, "min": 1, "type": "avg_speed", "hand": "", "csv": "true"}, pause=2.0))
    players = pd.concat(frames, ignore_index=True)
    pitchers = players["player_type"] == "pitcher"
    joined = players.loc[pitchers, ["mlbam_id"]].merge(speeds, on="mlbam_id", how="left")
    for c in SPEEDS.values():
        players[c] = float("nan")
        players.loc[pitchers, c] = joined[c].to_numpy()
    return players[COLUMNS]


def validate_players(df: pd.DataFrame, season: int) -> None:
    """Enough batters and pitchers with enough PA, no player twice in a type, and a pitch speed
    for nearly every pitcher who faced 100 or more batters."""
    problems = []
    if df.duplicated(["mlbam_id", "player_type"]).any():
        problems.append("a player appears twice in one type")
    for kind in ("batter", "pitcher"):
        rows = df[df["player_type"] == kind]
        if len(rows) < MIN_ROWS:
            problems.append(f"only {len(rows)} {kind}s")
        if rows["pa"].sum() < MIN_PA:
            problems.append(f"only {int(rows['pa'].sum()):,} {kind} PA")
    busy = df[(df["player_type"] == "pitcher") & (df["pa"] >= 100)]
    has_speed = busy[list(SPEEDS.values())].notna().any(axis=1)
    if len(busy) and has_speed.mean() < MIN_SPEED_SHARE:
        problems.append(f"pitch speed for only {has_speed.mean():.0%} of busy pitchers")
    if problems:
        raise ValueError(f"Savant players for {season} failed checks: " + "; ".join(problems))


def extract_players(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Statcast batter and pitcher leaderboards for completed seasons from FIRST_SEASON, one file
    per season."""
    if not SEASONS_PATH.exists():
        extract_seasons()
    available = [s for s in completed_seasons(pd.read_parquet(SEASONS_PATH))
                 if s >= FIRST_SEASON]
    for season in seasons if seasons else available:
        if season not in available:
            log.warning("Skipping %d: not a completed Statcast season", season)
            continue
        out = PLAYERS_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_players(season)
        validate_players(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "savant_players", out, rows=len(df), season=season, url=CUSTOM_URL)
        log.info("Saved %d Savant player rows for %d", len(df), season)


# ---- fielding --------------------------------------------------------------------------------
def parse_fielding(text: str, season: int, fetched_at: str) -> pd.DataFrame:
    """The fielding-run-value CSV to our columns: runs blank -> 0 for anyone with outs on the
    field (a part he had no chance at), rows with no outs dropped."""
    df = pd.read_csv(io.StringIO(text))
    out = pd.DataFrame({"season": season, "mlbam_id": df["id"].astype("int64")})
    def column(c: str) -> pd.Series:                    # a part Savant leaves out counts 0
        return pd.to_numeric(df[c], errors="coerce").fillna(0) if c in df \
            else pd.Series(0, index=df.index)

    for c in OUTS:
        out[c] = column(c).astype("int64")
    for c in FIELDING_RUNS:
        out[c] = column(c).astype(float)
    out["framing_source"] = "fielding_run_value" if season >= FIRST_FRV_FRAMING else "none"
    out["fetched_at"] = fetched_at
    return out[out["outs_total"] > 0].drop_duplicates(ignore_index=True)


def parse_framing(text: str) -> pd.DataFrame:
    """The older catcher-framing CSV: mlbam_id and framing runs."""
    df = pd.read_csv(io.StringIO(text))
    out = pd.DataFrame({"mlbam_id": pd.to_numeric(df["player_id"], errors="coerce"),
                        "framing": pd.to_numeric(df["runs_extra_strikes"], errors="coerce")})
    out = out.dropna()                                  # summary rows have no player
    return out.astype({"mlbam_id": "int64"}).drop_duplicates("mlbam_id")


def add_framing(fielding: pd.DataFrame, framing: pd.DataFrame) -> pd.DataFrame:
    """Before FIRST_FRV_FRAMING: the framing leaderboard's runs into framing, catching and total
    runs, for catchers on it."""
    f = fielding.merge(framing, on="mlbam_id", how="left")
    has = f["framing"].notna()
    for c in ("framing_runs", "catching_runs", "total_runs"):
        f.loc[has, c] = f.loc[has, c] + f.loc[has, "framing"]
    f.loc[has, "framing_source"] = "framing_leaderboard"
    return f.drop(columns="framing")


def fetch_fielding(season: int) -> pd.DataFrame:
    fetched_at = utc_now_iso()
    text = get_text(FRV_URL, params={
        "gameType": "Regular", "seasonStart": season, "seasonEnd": season, "type": "fielder",
        "position": "", "minInnings": 0, "minResults": 1, "csv": "true"}, pause=3.0)
    df = parse_fielding(text, season, fetched_at)
    if season < FIRST_FRV_FRAMING:
        framing = parse_framing(get_text(FRAMING_URL, params={
            "year": season, "team": "", "min": 1, "type": "catcher", "csv": "true"}, pause=3.0))
        df = add_framing(df, framing)
    return df[FIELDING_COLUMNS]


def validate_fielding(df: pd.DataFrame, season: int) -> None:
    """Enough fielders and outs, nobody twice, the parts adding up to the total, and framing for
    the catchers."""
    problems = []
    if len(df) < MIN_FIELDERS:
        problems.append(f"only {len(df)} fielders")
    if df["mlbam_id"].duplicated().any():
        problems.append("a fielder appears twice")
    if df["outs_total"].sum() < MIN_OUTS:
        problems.append(f"only {int(df['outs_total'].sum()):,} outs on the field")
    gap = (df["total_runs"] - df["inf_of_runs"] - df["catching_runs"]).abs().max()
    if gap > 0.01:
        problems.append(f"total runs differ from their parts by up to {gap:.2f}")
    catchers = df[df["outs_2"] >= 1500]                 # 500 innings or more behind the plate
    if len(catchers) and (catchers["framing_runs"] == 0).mean() > 0.2:
        problems.append("no framing for most catchers")
    if problems:
        raise ValueError(f"Savant fielding for {season} failed checks: " + "; ".join(problems))


def extract_fielding(seasons: list[int] | None = None, refresh: bool = False) -> None:
    """Statcast fielding run value for completed seasons from FIRST_FIELDING_SEASON, one file
    per season."""
    if not SEASONS_PATH.exists():
        extract_seasons()
    available = [s for s in completed_seasons(pd.read_parquet(SEASONS_PATH))
                 if s >= FIRST_FIELDING_SEASON]
    for season in seasons if seasons else available:
        if season not in available:
            log.warning("Skipping %d: not a completed season with fielding run value", season)
            continue
        out = FIELDING_DIR / f"season={season}.parquet"
        if out.exists() and not refresh:
            log.info("Skipping %d: already saved (use --refresh to fetch again)", season)
            continue
        df = fetch_fielding(season)
        validate_fielding(df, season)
        write_parquet(df, out)
        record_run(SOURCE, "savant_fielding", out, rows=len(df), season=season, url=FRV_URL)
        log.info("Saved %d Savant fielding rows for %d", len(df), season)
