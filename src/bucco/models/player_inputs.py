"""Load the player-level inputs the rung-5a models need from the database.

This is the one place that reads `bucco.duckdb` for those models; each model is handed the
resulting `PlayerData`. Each source's data is loaded once per process.
"""

from __future__ import annotations

from functools import lru_cache

import duckdb
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.models import availability as avail
from bucco.models import innings as inn
from bucco.models import lineup_optimizer as lo
from bucco.models import marcel
from bucco.models import milb as mle
from bucco.models.depth_chart_model import DepthChartModel, PlayerData

# source in player_projections -> (name for messages, how playing time is decided)
SOURCES = {"zips": ("ZiPS", "depth_chart"), "steamer": ("Steamer", "as_given")}


@lru_cache(maxsize=4)
def load_player_data(source: str = "zips", path=DUCKDB_PATH,
                     playing_time: str | None = None) -> PlayerData:
    """One source's player projections; `playing_time` overrides the source's default."""
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    label, default = SOURCES[source]
    playing_time = playing_time or default
    with duckdb.connect(str(path), read_only=True) as con:
        proj = con.execute("select * from marts.player_projections where source = ? "
                           "and team_id is not null and mlbam_id is not null", [source]).df()
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
        matchups = con.sql("select season, team_id, opponent_id, games "
                           "from marts.team_matchups").df()
    batters = proj[proj["player_type"] == "batter"].rename(
        columns={"plate_appearances": "pa", "bsr_runs": "bsr"})
    pitchers = proj[proj["player_type"] == "pitcher"].rename(
        columns={"innings_pitched": "ip", "games_started": "gs"})
    return PlayerData(batters, pitchers, positions, source=label, playing_time=playing_time,
                      matchups=matchups)


FIELDING_SOURCES = ("steamer", "zips")    # whose projected Def Marcel borrows (`fielding`)


def external_def_rates(sources: tuple[str, ...] = FIELDING_SOURCES,
                       path=DUCKDB_PATH) -> pd.DataFrame:
    """season, mlbam_id, def_rate: the mean over `sources` of each batter's projected Def per
    PA, over the sources that project him (any team or none). The files are made before
    Opening Day, so the target season's may be used."""
    with duckdb.connect(str(path), read_only=True) as con:
        rows = con.execute(
            "select source, season, mlbam_id, def_runs / plate_appearances as def_rate "
            "from marts.player_projections where player_type = 'batter' "
            "and mlbam_id is not null and plate_appearances > 0 and def_runs is not null "
            "and source in (select unnest(?)) "
            "qualify row_number() over (partition by source, season, mlbam_id "
            "order by plate_appearances desc) = 1", [list(sources)]).df()
    return rows.groupby(["season", "mlbam_id"], as_index=False)["def_rate"].mean()


FIELDING_WEIGHTS = (3.0, 2.0, 1.0)      # last season first; see docs/R&D/fielding.md
FIELDING_REG_PA = 1000.0                # PA of league-average (0) fielding added in


def statcast_fielding_rates(path=DUCKDB_PATH, weights: tuple = FIELDING_WEIGHTS,
                            reg_pa: float = FIELDING_REG_PA) -> pd.DataFrame:
    """season (target), mlbam_id, fld_rate: each batter's Statcast fielding run value per PA
    over the three seasons before (`weights`, last first), with `reg_pa` PA of zero added in. For
    target seasons with at least one fielding season before (from 2017), batters with any."""
    with duckdb.connect(str(path), read_only=True) as con:
        hist = con.sql("select f.season, f.mlbam_id, f.fielding_runs, b.pa "
                       "from staging.stg_savant__fielding f join marts.player_batting_seasons b "
                       "using (season, mlbam_id) where not b.is_pitcher and b.pa > 0").df()
    parts = []
    for k, w in enumerate(weights, 1):
        parts.append(hist.assign(season=hist["season"] + k,
                                 runs=w * hist["fielding_runs"], wpa=w * hist["pa"]))
    tot = pd.concat(parts).groupby(["season", "mlbam_id"], as_index=False)[["runs", "wpa"]].sum()
    tot["fld_rate"] = tot["runs"] / (tot["wpa"] + reg_pa)
    return tot[["season", "mlbam_id", "fld_rate"]]


@lru_cache(maxsize=4)
def marcel_projections(aging: bool = False, prior: str = "league", park: bool = False,
                       fielding: bool = False, innings: str = "marcel",
                       availability: str = "none", milb: float = 0.0,
                       milb_rookies: bool = False, milb_pitching: float = 0.0,
                       components: tuple[float, ...] | None = None,
                       roster_source: str = "steamer", statcast_fielding: bool = False,
                       path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Marcel projections (bucco.models.marcel) for every player with MLB history in the three
    seasons before each target season, on any team or none: (batters, pitchers). `aging`
    applies age curves fitted, for each target season, on earlier seasons only. `prior` is what
    rates are shrunk toward (marcel.PRIORS; "fitted" depends on how much history a player has).
    `park` projects from park-neutral history (and fits the age curves on it). `fielding`
    replaces batters' positional-only Def with the mean of Steamer's and ZiPS's projected Def
    per PA (marcel.apply_external_def); `statcast_fielding` then replaces the fielding part with
    our own projection from Statcast fielding run value wherever a batter has some
    (`statcast_fielding_rates`, targets from 2017). `innings`: "marcel" (Marcel's playing-time formula)
    or "baseline" (bucco.models.innings, fitted on earlier seasons' rostered pitchers), which
    also adds each season's start_penalty for the staff optimizer. `availability`: "none", or
    scale the playing time of players on a preseason roster by their Opening Day 40-man status
    (bucco.models.availability), "relative" to active 40-man players or "absolute". `milb`:
    weight of minor-league PA (major-league equivalents, bucco.models.milb) in batters' history
    (0: none); `milb_rookies` also projects batters with minor-league but no MLB history.
    `milb_pitching`: the same for pitchers (weight of a minor-league batter faced; rookies
    included when above 0), with minor-league innings in the baseline-innings line.
    `components`: batters faced of league average for each part of pitchers' runs
    (marcel.COMPONENTS, in order), each part regressed, aged and translated on its own; None
    regresses pitching runs as one number. `roster_source`: whose preseason rosters the innings
    line and the availability factors are fitted on (`marcel_rosters`)."""
    if not path.exists():
        raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build` first.")
    with duckdb.connect(str(path), read_only=True) as con:
        league = con.sql("select * from marts.league_seasons").df()
        bat_frame = con.sql("select * from marts.batter_projection_frame").df()
        pit_frame = con.sql("select * from marts.pitcher_projection_frame").df()
        bat_history = con.sql("select season, mlbam_id, age, off_runs, off_runs_neutral, pa "
                              "from marts.player_batting_seasons where not is_pitcher").df()
        pit_history = con.sql("select * from marts.player_pitching_seasons").df()
    off_col = "off_runs_neutral" if park else "off_runs"
    runs_col = "pitching_runs_neutral" if park else "pitching_runs"
    if milb:
        bat_frame = with_milb(bat_frame, milb_rookies, path)
    if milb_pitching:
        pit_frame = with_milb_pitching(pit_frame, path, components=components is not None)
    bat_curves = pit_curves = None
    if aging:
        bat_curves = marcel.age_curves(bat_history, off_col, "pa", bat_frame["season"])
        if components is None:
            pit_curves = marcel.age_curves(pit_history, runs_col, "bf", pit_frame["season"])
        else:
            suffix = "_neutral" if park else ""
            pit_curves = {part: marcel.age_curves(pit_history, f"{part}_runs{suffix}", "bf",
                                                  pit_frame["season"])
                          for part in marcel.COMPONENTS}
    batters = marcel.project_batters(bat_frame, league, curves=bat_curves, prior=prior,
                                     park=park, milb_weight=milb)
    if fielding:
        batters = marcel.apply_external_def(batters, external_def_rates(path=path), league)
    if statcast_fielding:
        batters = marcel.apply_fielding_rates(batters, statcast_fielding_rates(path), league)
    pit_frame = pit_frame.reset_index(drop=True)
    pitchers = marcel.project_pitchers(pit_frame, league, curves=pit_curves, prior=prior,
                                       park=park, milb_weight=milb_pitching,
                                       components=None if components is None else
                                       dict(zip(marcel.COMPONENTS, components, strict=True)))
    if innings == "baseline":
        roster = marcel_rosters(roster_source, path=path)
        keys = set(zip(roster.loc[roster["player_type"] == "pitcher", "season"],
                       roster.loc[roster["player_type"] == "pitcher", "mlbam_id"], strict=True))
        rostered = pd.Series([k in keys for k in zip(pit_frame["season"], pit_frame["mlbam_id"],
                                                      strict=True)])
        pitchers = marcel.rescale_innings(pitchers, inn.baseline_ip(pit_frame, rostered).to_numpy())
        penalty = inn.start_penalties(pit_history, runs_col, pitchers["season"])
        pitchers["start_penalty"] = pitchers["season"].map(penalty)
    elif innings != "marcel":
        raise ValueError(f"innings must be 'marcel' or 'baseline', not {innings!r}")
    if availability != "none":
        if availability not in ("relative", "absolute"):
            raise ValueError(f"availability must be 'none', 'relative' or 'absolute', "
                             f"not {availability!r}")
        with duckdb.connect(str(path), read_only=True) as con:
            status = con.sql("select season, mlbam_id, il_group "
                             "from marts.player_preseason_status").df()
        roster = marcel_rosters(roster_source, path=path)
        relative = availability == "relative"
        # what was delivered: 0 for a completed season he did not play, unknown for the upcoming
        bat_real = bat_frame.assign(actual=bat_frame["target_pa"].fillna(0.0).where(
            ~bat_frame["is_upcoming_season"].astype(bool)))
        pit_real = pit_frame.assign(actual=(pit_frame["target_outs"] / 3.0).fillna(0.0).where(
            ~pit_frame["is_upcoming_season"].astype(bool)))
        f = _availability_factor(batters, "pa", bat_real, roster, "batter", status, relative)
        for col in ("pa", "off_runs", "def_runs", "fld_runs", "bsr", "war"):
            batters[col] = batters[col] * f
        batters["availability"] = f
        rookies = set()
        if "milb_rookie" in pit_frame:
            r = pit_frame[pit_frame["milb_rookie"].fillna(False).astype(bool)]
            rookies = set(zip(r["season"], r["mlbam_id"], strict=True))
        f = _availability_factor(pitchers, "ip", pit_real, roster, "pitcher", status, relative,
                                 exempt=rookies)
        pitchers = marcel.rescale_innings(pitchers, pitchers["ip"] * f)
        pitchers["availability"] = f
    return batters, pitchers


def with_milb(bat_frame: pd.DataFrame, rookies: bool, path=DUCKDB_PATH) -> pd.DataFrame:
    """batter_projection_frame with each row's translated minor-league history (y1-y3_milb_pa,
    y1-y3_milb_runs; 0 where none) and, with `rookies`, rows for batters with minor-league but
    no MLB history."""
    with duckdb.connect(str(path), read_only=True) as con:
        minor = con.sql("select season, mlbam_id, player_name, age, level, pa, off_runs "
                        "from marts.minor_batting_seasons").df()
        mlb = con.sql("select season, mlbam_id, pa, off_runs_neutral as off_runs, "
                      "pa as target_pa, off_runs as target_off_runs, "
                      "off_runs_neutral as target_off_runs_neutral "
                      "from marts.player_batting_seasons where not is_pitcher").df()
    history = mle.milb_history(minor, mlb, bat_frame["season"])
    frame = bat_frame
    if rookies:
        upcoming = set(bat_frame.loc[bat_frame["is_upcoming_season"].astype(bool), "season"])
        new = mle.rookie_rows(bat_frame, history, mlb[["season", "mlbam_id", "target_pa",
                                                       "target_off_runs",
                                                       "target_off_runs_neutral"]], upcoming)
        frame = pd.concat([bat_frame, new], ignore_index=True)
    cols = [c for c in history.columns if c.startswith("y")]
    frame = frame.merge(history[["season", "mlbam_id", *cols]], on=["season", "mlbam_id"],
                        how="left")
    frame[cols] = frame[cols].fillna(0.0)
    return frame


def injury_samples(batters: pd.DataFrame, pitchers: pd.DataFrame,
                   path=DUCKDB_PATH) -> dict[int, dict]:
    """Availability draws for each season (bucco.models.injury_sim.fit_availability), fitted
    on earlier seasons' established rostered players: season -> group -> draws."""
    from bucco.models import injury_sim

    with duckdb.connect(str(path), read_only=True) as con:
        actual_b = con.sql("select season, mlbam_id, pa as actual from marts.player_batting_seasons "
                           "where not is_pitcher").df()
        actual_p = con.sql("select season, mlbam_id, outs / 3.0 as actual "
                           "from marts.player_pitching_seasons").df()
    rows = injury_sim.established_rows(batters, pitchers, actual_b, actual_p)
    return {int(s): injury_sim.fit_availability(rows, int(s))
            for s in sorted(set(batters["season"]) | set(pitchers["season"]))}


def with_milb_pitching(pit_frame: pd.DataFrame, path=DUCKDB_PATH,
                       components: bool = False) -> pd.DataFrame:
    """pitcher_projection_frame with translated minor-league history (y1-y3_milb_bf, _runs,
    _outs, _gs, _games; 0 where none) and rows for pitchers with minor-league but no MLB
    history (bucco.models.milb, drops scaled by PITCHER_DROP_SCALE), with the inputs of rookies'
    baseline innings (bucco.models.innings.ROOKIE_FEATURES). `components` also translates each
    part of the runs (marcel.COMPONENTS) with its own drops: y1-y3_milb_<part>_runs."""
    parts = [f"{p}_runs" for p in marcel.COMPONENTS]
    with duckdb.connect(str(path), read_only=True) as con:
        minor = con.sql("select season, mlbam_id, player_name, age, level, bf, pitching_runs, "
                        f"outs, gs, games, {', '.join(parts)} "
                        "from marts.minor_pitching_seasons").df()
        status = con.sql("select season, mlbam_id, il_group "
                         "from marts.player_preseason_status").df()
        mlb = con.sql("select season, mlbam_id, bf, pitching_runs_neutral as pitching_runs, "
                      "outs as target_outs, bf as target_bf, gs as target_gs, "
                      "games as target_games, pitching_runs as target_pitching_runs, "
                      "pitching_runs_neutral as target_pitching_runs_neutral, "
                      + ", ".join(f"{p}_neutral as mlb_{p}, {p} as target_{p}, "
                                  f"{p}_neutral as target_{p}_neutral" for p in parts)
                      + " from marts.player_pitching_seasons").df()
    history = mle.milb_history(minor, mlb, pit_frame["season"], volume="bf",
                               runs="pitching_runs", extra=("outs", "gs", "games"),
                               drop_scale=mle.PITCHER_DROP_SCALE)
    if components:
        for p in parts:
            h = mle.milb_history(minor, mlb[["season", "mlbam_id", "bf", f"mlb_{p}"]].rename(
                columns={f"mlb_{p}": p}), pit_frame["season"], volume="bf", runs=p,
                drop_scale=mle.PITCHER_DROP_SCALE)
            h = h.rename(columns={f"y{k}_milb_runs": f"y{k}_milb_{p}" for k in (1, 2, 3)})
            history = history.merge(h[["season", "mlbam_id",
                                       *[f"y{k}_milb_{p}" for k in (1, 2, 3)]]],
                                    on=["season", "mlbam_id"], how="left")
    upcoming = set(pit_frame.loc[pit_frame["is_upcoming_season"].astype(bool), "season"])
    targets = mlb.drop(columns=["bf", "pitching_runs", *[f"mlb_{p}" for p in parts]])
    new = mle.rookie_rows(pit_frame, history, targets, upcoming, volume="bf",
                          min_volume=mle.ROOKIE_MIN_BF, pitchers=True)
    frame = pd.concat([pit_frame.assign(milb_rookie=False), new], ignore_index=True)
    cols = [c for c in history.columns if c.startswith("y")]
    frame = frame.merge(history[["season", "mlbam_id", *cols]], on=["season", "mlbam_id"],
                        how="left")
    frame[cols] = frame[cols].fillna(0.0)
    # last season's minor-league innings by level and role, for rookies' baseline innings
    m = minor.assign(season=minor["season"] + 1, ip=minor["outs"] / 3.0)
    share = (m["gs"] / m["games"].where(m["games"] > 0)).fillna(0.0)
    level = m["level"].map({"AAA": "aaa", "AA": "aa"}).fillna("low")
    m = m.assign(sp=m["ip"] * share, rp=m["ip"] * (1 - share), level=level)
    wide = m.pivot_table(index=["season", "mlbam_id"], columns="level", values=["sp", "rp"],
                         aggfunc="sum").fillna(0.0)
    feats = pd.DataFrame(index=wide.index)
    for lv in ("aaa", "aa"):
        for role in ("sp", "rp"):
            feats[f"m1_{lv}_{role}"] = wide[role].get(lv, 0.0)
    feats["m1_low"] = sum(wide[role]["low"] for role in ("sp", "rp") if "low" in wide[role])
    frame = frame.merge(feats.reset_index(), on=["season", "mlbam_id"], how="left")
    m1 = list(feats.columns)
    frame[m1] = frame[m1].fillna(0.0)
    # Opening Day 40-man status, for rookies' baseline innings
    st = status.assign(on_40=(status["il_group"] == "none").astype(float),
                       il_40=(status["il_group"] != "none").astype(float))
    frame = frame.merge(st[["season", "mlbam_id", "on_40", "il_40"]], on=["season", "mlbam_id"],
                        how="left").fillna({"on_40": 0.0, "il_40": 0.0})
    return frame.copy()            # one block (the merges leave it fragmented)


def _availability_factor(proj: pd.DataFrame, volume: str, frame: pd.DataFrame,
                         roster: pd.DataFrame, player_type: str, status: pd.DataFrame,
                         relative: bool, exempt: set | None = None) -> pd.Series:
    """Availability factor per projection row: fitted and applied only for players on a
    preseason roster (others, such as unsigned free agents, get 1). `exempt` (season, mlbam_id)
    pairs are left out of both: rookie pitchers, whose baseline innings already use their
    40-man status."""
    keys = roster.loc[roster["player_type"] == player_type, ["season", "mlbam_id"]]
    if exempt:
        keys = keys[[k not in exempt for k in zip(keys["season"], keys["mlbam_id"],
                                                 strict=True)]]
    rows = proj[["season", "mlbam_id", volume]].reset_index().merge(
        keys.drop_duplicates(), on=["season", "mlbam_id"]).merge(
        frame[["season", "mlbam_id", "actual"]].drop_duplicates(["season", "mlbam_id"]),
        on=["season", "mlbam_id"], how="left").set_index("index")
    groups = avail.status_groups(rows, status)
    f = avail.availability(groups, rows[volume], rows["actual"], rows["season"], relative)
    return pd.Series(1.0, index=proj.index).add(f - 1.0, fill_value=0.0)


@lru_cache(maxsize=1)
def park_fit_inputs(path=DUCKDB_PATH) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(batter profiles, team parks, league constants) for the park fit. Team parks for season
    S are the side factors through S - 1 at the ballpark the team plays in during S (from the
    schedule, so known before Opening Day); a team in a new ballpark gets none (neutral)."""
    with duckdb.connect(str(path), read_only=True) as con:
        league = con.sql("select * from marts.league_seasons").df()
        frame = con.sql("select f.*, p.bats from marts.batter_projection_frame f "
                        "left join staging.stg_mlb__people p using (mlbam_id)").df()
        parks = con.sql(
            "select hp.season, hp.team_id, pf.* exclude (season, team_id, venue_id, venue_name, "
            "seasons_pooled) from intermediate.int__team_home_parks hp "
            "join marts.park_factors_by_side pf on pf.team_id = hp.team_id "
            "and pf.season = hp.season - 1 and pf.venue_id = hp.venue_id").df()
    return marcel.batter_profiles(frame, league), parks, league


def with_park_fit(batters: pd.DataFrame, team_means: pd.Series | None = None,
                  path=DUCKDB_PATH) -> pd.DataFrame:
    """Batters on teams (season, mlbam_id, team_id, pa, off_runs, war) with each one's fit to
    his team's park added (marcel.apply_park_fit), centered on `team_means` (default: these
    rows' own team averages)."""
    profiles, parks, league = park_fit_inputs(path)
    runs = marcel.park_runs_per_pa(batters, profiles, parks, league)
    return marcel.apply_park_fit(batters, runs, league, team_means)


def park_fit_team_means(batters: pd.DataFrame, path=DUCKDB_PATH) -> pd.Series:
    """Each team's PA-weighted park runs per PA over its rostered batters (for centering a
    player added to the team, such as a free agent)."""
    profiles, parks, league = park_fit_inputs(path)
    runs = marcel.park_runs_per_pa(batters, profiles, parks, league)
    keys = [batters["season"], batters["team_id"]]
    return (runs * batters["pa"]).groupby(keys).sum() / batters["pa"].groupby(keys).sum()


ROSTER_SOURCES = ("steamer", "mlb", "mlb_org")


def marcel_rosters(roster_source: str = "steamer", path=DUCKDB_PATH) -> pd.DataFrame:
    """Preseason rosters: season, player_type, mlbam_id, team_id, as_of_date. "steamer": the team
    assignments in Steamer's player files (from 2012, players beyond the 40-man included). "mlb":
    each team's Opening Day 40-man roster from the MLB Stats API (marts.player_preseason_status,
    from 2009), pitchers by roster position (two-way players are both). "mlb_org": the same plus
    each organization's minor-league depth (marts.organization_depth: last season's affiliates),
    less anyone on a 40-man roster that Opening Day."""
    if roster_source not in ROSTER_SOURCES:
        raise ValueError(f"roster_source must be one of {ROSTER_SOURCES}, not {roster_source!r}")
    if roster_source in ("mlb", "mlb_org"):
        with duckdb.connect(str(path), read_only=True) as con:
            status = con.sql("select season, mlbam_id, team_id, snapshot_date as as_of_date, "
                             "position from marts.player_preseason_status").df()
        # each team's snapshot is its own Opening Day; date them all to the season's first, so a
        # forecast made on Opening Day keeps teams that open later (the openers abroad)
        status["as_of_date"] = status.groupby("season")["as_of_date"].transform("min")
        keep = ["season", "player_type", "mlbam_id", "team_id", "as_of_date"]
        pitchers = status[status["position"].isin(["P", "TWP"])].assign(player_type="pitcher")
        batters = status[status["position"] != "P"].assign(player_type="batter")
        roster = pd.concat([batters[keep], pitchers[keep]], ignore_index=True)
        if roster_source == "mlb_org":
            with duckdb.connect(str(path), read_only=True) as con:
                depth = con.sql("select season, mlbam_id, team_id, player_type "
                                "from marts.organization_depth").df()
            on_40 = set(zip(status["season"], status["mlbam_id"], strict=True))
            depth = depth[[k not in on_40 for k in zip(depth["season"], depth["mlbam_id"],
                                                       strict=True)]]
            depth = depth[depth["season"].isin(set(status["season"]))]
            dates = status.groupby("season")["as_of_date"].first()
            depth = depth.assign(as_of_date=depth["season"].map(dates).to_numpy())
            roster = pd.concat([roster, depth[keep]], ignore_index=True)
        return roster
    with duckdb.connect(str(path), read_only=True) as con:
        roster = con.execute("select distinct season, player_type, mlbam_id, team_id, as_of_date "
                             "from marts.player_projections where source = ? "
                             "and team_id is not null and mlbam_id is not null",
                             [roster_source]).df()
    return roster.drop_duplicates(["season", "player_type", "mlbam_id"])


def on_rosters(projections: pd.DataFrame, roster: pd.DataFrame, player_type: str) -> pd.DataFrame:
    """Projections of the players on a preseason roster, with their team."""
    rows = roster[roster["player_type"] == player_type].drop(columns="player_type")
    return projections.merge(rows, on=["season", "mlbam_id"])


@lru_cache(maxsize=4)
def load_marcel_data(playing_time: str = "depth_chart", roster_source: str = "steamer",
                     aging: bool = False, prior: str = "league", park: bool = False,
                     park_fit: bool = False, fielding: bool = False,
                     innings: str = "marcel", pitcher_playing_time: str = "depth_chart",
                     availability: str = "none", milb: float = 0.0,
                     milb_rookies: bool = False, relative_fatigue: bool = False,
                     injury_sims: int = 0, milb_pitching: float = 0.0,
                     pitcher_components: bool = False, ml_pitchers: bool = False,
                     pitcher_roster: str | None = None, ml_hitters: bool = False,
                     statcast_fielding: bool = False, path=DUCKDB_PATH) -> PlayerData:
    """Our own Marcel projections on each team's preseason roster.

    Rosters are `roster_source`'s preseason rosters (`marcel_rosters`: Steamer's team
    assignments, or the MLB Stats API's Opening Day 40-man rosters); only who is on which team is
    taken from them. Players on a
    roster with no MLB history in the three prior seasons get no projection (unless
    `milb_rookies`). `park_fit` adds each batter's fit to his 2027 (target-season) park,
    centered on his team. `fielding`, `availability`, `milb` and `milb_rookies`: see
    `marcel_projections`. `innings` ("marcel" or "baseline") and `pitcher_playing_time`
    ("depth_chart" or "optimized": bucco.models.staff_optimizer) set how pitchers' innings are
    projected and shared out. `relative_fatigue`: the lineup optimizer's fatigue curve relative
    to each batter's projected PA (lineup_optimizer.RELATIVE) instead of a 600-PA scale.
    `injury_sims`: team WAR as the mean over this many injury draws (bucco.models.injury_sim),
    the draws fitted for each season on earlier ones. `pitcher_components`: pitchers' runs
    regressed by part (marcel.COMPONENT_REG_BF) instead of as one number. `ml_pitchers`:
    pitchers' innings and rates from the learned models' saved predictions
    (bucco.models.ml.pitchers; run `bucco fit-ml --targets pitchers` first). `pitcher_roster`:
    pitchers join this source's rosters instead of `roster_source`'s (projections unchanged), and
    with `ml_pitchers` take that roster's learned innings. `ml_hitters`: hitters' PA from the
    learned model (bucco.models.ml.hitters; `bucco fit-ml --targets hitters`), from its first
    predicted season on (earlier seasons are dropped)."""
    components = (tuple(marcel.COMPONENT_REG_BF[p] for p in marcel.COMPONENTS)
                  if pitcher_components else None)
    batters, pitchers = marcel_projections(aging, prior, park, fielding, innings,
                                           availability, milb, milb_rookies, milb_pitching,
                                           components, roster_source,
                                           statcast_fielding=statcast_fielding, path=path)
    roster = marcel_rosters(roster_source, path)
    with duckdb.connect(str(path), read_only=True) as con:
        positions = con.sql("select season, mlbam_id, position, games "
                            "from marts.player_position_games").df()
        matchups = con.sql("select season, team_id, opponent_id, games "
                           "from marts.team_matchups").df()
    batters = on_rosters(batters, roster, "batter")
    pitcher_roster = pitcher_roster or roster_source
    p_roster = roster if pitcher_roster == roster_source else marcel_rosters(pitcher_roster, path)
    pitchers = on_rosters(pitchers, p_roster, "pitcher")
    if ml_pitchers:
        from bucco.models.ml import pitchers as mlp
        pitchers = mlp.apply(pitchers, mlp.load_predictions(pitcher_roster))
    if ml_hitters:
        from bucco.models.ml import hitters as mlh
        batters = mlh.apply(batters, mlh.load_predictions())
        batters = batters[batters["season"] >= mlh.FIRST_PREDICTED]
        pitchers = pitchers[pitchers["season"] >= mlh.FIRST_PREDICTED]
    if park_fit:
        batters = with_park_fit(batters, path=path)
    return PlayerData(batters, pitchers, positions, source="Marcel", playing_time=playing_time,
                      matchups=matchups, pitcher_playing_time=pitcher_playing_time,
                      optimizer_options=lo.RELATIVE if relative_fatigue else None,
                      injury_sims=injury_sims,
                      injury_samples=injury_samples(batters, pitchers, path)
                      if injury_sims else None)


def make_marcel_park_model() -> DepthChartModel:
    """Factory for the registry: `marcel_shrunk` on park-neutral history."""
    return DepthChartModel(load_marcel_data(aging=True, prior="fitted", park=True),
                           name="marcel_park")


def make_marcel_park_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_park` with batters through the lineup optimizer and
    fielding borrowed from Steamer's and ZiPS's projected Def."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted", park=True,
                                            fielding=True), name="marcel_park_optimized")


def make_marcel_staff_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_park_optimized` with baseline innings
    (bucco.models.innings) shared out by the staff optimizer (bucco.models.staff_optimizer), and
    playing time scaled by Opening Day 40-man status (bucco.models.availability), and batters'
    and pitchers' minor-league history (major-league equivalents, bucco.models.milb), rookies
    included; batters' fatigue curve relative to their projected PA (lineup_optimizer.RELATIVE);
    pitchers' runs regressed by part (strikeouts, walks, home runs, the rest); on the MLB Stats
    API's Opening Day 40-man rosters, so it is scored from 2009."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted", park=True,
                                            fielding=True, innings="baseline",
                                            pitcher_playing_time="optimized",
                                            availability="absolute", milb=mle.MILB_WEIGHT,
                                            milb_rookies=True, relative_fatigue=True,
                                            milb_pitching=mle.PITCHER_MILB_WEIGHT,
                                            pitcher_components=True, roster_source="mlb"),
                           name="marcel_staff_optimized")


STAFF_SETTINGS = {"aging": True, "prior": "fitted", "park": True, "fielding": True,
                  "innings": "baseline", "pitcher_playing_time": "optimized",
                  "availability": "absolute", "milb": mle.MILB_WEIGHT, "milb_rookies": True,
                  "relative_fatigue": True, "milb_pitching": mle.PITCHER_MILB_WEIGHT,
                  "pitcher_components": True, "roster_source": "mlb", "statcast_fielding": True}


def staff_projection_settings() -> tuple:
    """`marcel_projections` arguments of STAFF_SETTINGS (the learned models' Marcel inputs:
    marcel_staff_optimized's, with our own Statcast fielding), in order."""
    s = STAFF_SETTINGS
    return (s["aging"], s["prior"], s["park"], s["fielding"], s["innings"], s["availability"],
            s["milb"], s["milb_rookies"], s["milb_pitching"],
            tuple(marcel.COMPONENT_REG_BF[p] for p in marcel.COMPONENTS), s["roster_source"],
            s["statcast_fielding"])


def make_marcel_ml_pitchers_model() -> DepthChartModel:
    """Factory for the registry: `marcel_staff_optimized` with pitchers' innings and rates from
    the learned models (bucco.models.ml.pitchers), through the staff optimizer; hitters as in
    marcel_staff_optimized but with our own fielding projection from Statcast fielding run value
    where a hitter has some (from 2017; STAFF_SETTINGS)."""
    return DepthChartModel(load_marcel_data("optimized", ml_pitchers=True, **STAFF_SETTINGS),
                           name="marcel_ml_pitchers")


def make_marcel_ml_hitter_pa_model() -> DepthChartModel:
    """Factory for the registry: `marcel_ml_pitchers` with hitters' PA from the learned model
    (bucco.models.ml.hitters) used as given, without the lineup optimizer; hitters' rates stay
    Marcel's. From 2012, the first season the PA model predicts."""
    return DepthChartModel(load_marcel_data("as_given", ml_pitchers=True, ml_hitters=True,
                                            **STAFF_SETTINGS), name="marcel_ml_hitter_pa")


def make_marcel_parkfit_model() -> DepthChartModel:
    """Factory for the registry: `marcel_park` plus each batter's fit to his team's park."""
    return DepthChartModel(load_marcel_data(aging=True, prior="fitted", park=True,
                                            park_fit=True), name="marcel_parkfit")


def make_marcel_parkfit_optimized_model() -> DepthChartModel:
    """Factory for the registry: `marcel_parkfit` with batters through the lineup optimizer."""
    return DepthChartModel(load_marcel_data("optimized", aging=True, prior="fitted", park=True,
                                            park_fit=True), name="marcel_parkfit_optimized")


def make_depth_chart_model() -> DepthChartModel:
    """Factory for the registry: ZiPS through the depth chart, over shared, cached data."""
    return DepthChartModel(load_player_data("zips"))


def make_steamer_model() -> DepthChartModel:
    """Factory for the registry: Steamer's own playing time, team WAR summed as given."""
    return DepthChartModel(load_player_data("steamer"), name="steamer")


def make_steamer_optimized_model() -> DepthChartModel:
    """Factory for the registry: Steamer batters through the lineup optimizer, pitchers as given."""
    return DepthChartModel(load_player_data("steamer", playing_time="optimized"),
                           name="steamer_optimized")


def make_zips_optimized_model() -> DepthChartModel:
    """Factory for the registry: ZiPS batters through the lineup optimizer; ZiPS pitchers (a raw
    list of every player) through the depth chart."""
    return DepthChartModel(load_player_data("zips", playing_time="optimized"),
                           name="zips_optimized")
