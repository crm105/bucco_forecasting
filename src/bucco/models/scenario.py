"""Lineup scenarios: what happens to a team's batting when players join or leave.

Adding or removing a player and re-running the lineup optimizer shows the whole chain of
changes, not just the new player's own time: who moves position, who loses PA, and the change in
team batting WAR. The free-agent screen in the team outlook is built on this.

    lab = ScenarioLab(season=2027)                     # loads one season's projections once
    change = lab.run("PIT", add=["Ian Happ"], remove=["Bryan Reynolds"])
    change.gain                                        # team batting WAR, after minus before
    change.pa_change()                                 # PA by player and position, after - before
    change.war_change()                                # WAR by player
    change.losers()                                    # who loses the most PA
    print(change.report())

From the command line: `bucco scenario --team PIT --add "Ian Happ" --remove "Bryan Reynolds"`.

Players can be added from the projection file's unsigned list (free agents) or from another
team's roster (a trade). Each keeps his own projection; his fatigue curve stays anchored at his
projected PA. Pitching is not covered: the optimizer only allocates batters.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from bucco.config import DUCKDB_PATH
from bucco.extract.projections import INPUT_DIR
from bucco.models import lineup_optimizer as lo

REPLACEMENT = "replacement level"


class ScenarioError(ValueError):
    """A player or team in a scenario could not be found, or the scenario makes no sense."""


# ---- the comparison ----------------------------------------------------------------------
@dataclass
class LineupChange:
    """One team's optimized lineup before and after a scenario. Allocations are as returned by
    `lineup_optimizer.optimize_team` (one row per player and position, with PA and WAR;
    replacement level has mlbam_id -1)."""

    before: pd.DataFrame
    after: pd.DataFrame
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    team: str = ""

    @property
    def war_before(self) -> float:
        return float(self.before["war"].sum())

    @property
    def war_after(self) -> float:
        return float(self.after["war"].sum())

    @property
    def gain(self) -> float:
        """Change in team batting WAR."""
        return self.war_after - self.war_before

    @staticmethod
    def _by_player(alloc: pd.DataFrame) -> pd.DataFrame:
        return alloc.pivot_table(index="player_name", columns="position", values="pa",
                                 aggfunc="sum", fill_value=0.0)

    def pa_change(self, min_pa: float = 1.0) -> pd.DataFrame:
        """PA after minus before, by player (rows) and position (columns), plus a total. Only
        players whose time changed by at least min_pa somewhere; biggest losers last."""
        b, a = self._by_player(self.before), self._by_player(self.after)
        cols = [q for q in lo.POSITIONS if q in set(b.columns) | set(a.columns)]
        d = a.reindex(columns=cols, fill_value=0.0).sub(
            b.reindex(columns=cols, fill_value=0.0), fill_value=0.0).fillna(0.0)
        d = d[(d.abs() >= min_pa).any(axis=1)]
        d["total"] = d.sum(axis=1)
        return d.sort_values("total", ascending=False)

    def war_change(self, min_war: float = 0.005) -> pd.Series:
        """WAR after minus before, by player, biggest gain first."""
        b = self.before.groupby("player_name")["war"].sum()
        a = self.after.groupby("player_name")["war"].sum()
        d = a.sub(b, fill_value=0.0)
        return d[d.abs() >= min_war].sort_values(ascending=False)

    def where(self, player_name: str) -> list[tuple[str, float]]:
        """A player's PA by position after the change, most first."""
        me = self.after[self.after["player_name"] == player_name]
        s = me.groupby("position")["pa"].sum().sort_values(ascending=False)
        return [(q, float(p)) for q, p in s.items()]

    def losers(self, n: int = 3, min_pa: float = 10.0) -> list[tuple[str, float]]:
        """The players (replacement level included) who lose the most PA, as (name, PA lost)."""
        total = self.pa_change()["total"]
        total = total[~total.index.isin(self.added) & (total <= -min_pa)].sort_values()
        return [(name, float(-pa)) for name, pa in total.head(n).items()]

    def report(self) -> str:
        """Plain-text summary: the headline change, PA moves and WAR moves."""
        moves = []
        if self.added:
            moves.append("add " + ", ".join(self.added))
        if self.removed:
            moves.append("remove " + ", ".join(self.removed))
        head = (f"{self.team} {'; '.join(moves) or 'no change'}: batting WAR "
                f"{self.war_before:.1f} -> {self.war_after:.1f} ({self.gain:+.1f})")
        pa = self.pa_change().round().astype(int)
        war = self.war_change().round(2)
        return "\n\n".join([head, "PA change (after - before):\n" + pa.to_string(),
                            "WAR change:\n" + war.to_string()])


def compare_lineups(team_inputs: pd.DataFrame, rep_runs: float, runs_per_win: float,
                    add: pd.DataFrame | None = None, remove: Iterable[int] = (),
                    before: pd.DataFrame | None = None, team: str = "",
                    options: dict | None = None) -> LineupChange:
    """Re-optimize one team with players added (rows from `lineup_optimizer.player_inputs`) and
    removed (mlbam ids), and compare with its current lineup. Pass `before` (the current
    allocation) to skip re-solving it when running many scenarios for one team. `options`:
    keyword arguments for `lineup_optimizer.optimize_team` (e.g. the relative curve)."""
    options = options or {}
    remove = set(remove)
    if before is None:
        before = lo.optimize_team(team_inputs, rep_runs, runs_per_win, **options)
    after_inputs = team_inputs[~team_inputs["mlbam_id"].isin(remove)]
    if add is not None and len(add):
        dup = set(add["mlbam_id"]) & set(after_inputs["mlbam_id"])
        if dup:
            raise ScenarioError(f"already on the team: {sorted(dup)}")
        after_inputs = pd.concat([after_inputs, add], ignore_index=True)
    after = lo.optimize_team(after_inputs, rep_runs, runs_per_win, **options)
    names = dict(zip(team_inputs["mlbam_id"], team_inputs["player_name"], strict=True))
    return LineupChange(before=before, after=after,
                        added=[] if add is None else list(add["player_name"]),
                        removed=[names[i] for i in remove if i in names], team=team)


# ---- loading a season --------------------------------------------------------------------
def unsigned_players(source: str, season: int, kind: str,
                     directory: Path = INPUT_DIR) -> pd.DataFrame:
    """Players in the projection file with no team (unsigned), in the mart's column names."""
    path = Path(directory) / f"{source}_{kind}_individual_{season}.csv"
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(path, encoding="utf-8-sig")
    raw = raw[raw["Team"].isna() & raw["MLBAMID"].notna()]
    common = {"Name": "player_name", "MLBAMID": "mlbam_id", "WAR": "war", "G": "games"}
    extra = ({"PA": "plate_appearances", "Off": "off_runs", "Def": "def_runs", "Fld": "fld_runs",
              "BsR": "bsr_runs", "wRC+": "wrc_plus"} if kind == "batters"
             else {"IP": "innings_pitched", "GS": "games_started", "FIP": "fip"})
    cols = {k: v for k, v in {**common, **extra}.items() if k in raw}
    out = raw[list(cols)].rename(columns=cols)
    out["mlbam_id"] = out["mlbam_id"].astype("int64")
    for c in out.columns.drop(["player_name", "mlbam_id"]):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "fld_runs" not in out and kind == "batters":
        out["fld_runs"] = np.nan
    return out.reset_index(drop=True)


def _fold(text: str) -> str:
    """Lower case without accents, for name matching (Rodriguez finds Rodríguez)."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(text))
                   if not unicodedata.combining(c)).casefold().strip()


class ScenarioLab:
    """One season's batters, ready for scenarios: every team's optimizer inputs, the unsigned
    players, and the league's runs per win and replacement level. Load once, run many."""

    def __init__(self, season: int | None = None, source: str = "steamer",
                 path=DUCKDB_PATH, projections_dir: Path = INPUT_DIR):
        if not Path(path).exists():
            raise RuntimeError(f"{path} not found. Run `bucco extract all` and `bucco build`.")
        with duckdb.connect(str(path), read_only=True) as con:
            if season is None:
                season = int(con.execute("select max(season) from marts.player_projections "
                                         "where source = ?", [source]).fetchone()[0])
            batters = con.execute(
                "select * from marts.player_projections where source = ? and season = ? and "
                "player_type = 'batter' and team_id is not null and mlbam_id is not null",
                [source, season]).df()
            self.positions = con.execute(
                "select mlbam_id, position, games from marts.player_position_games "
                "where season = ?", [season]).df()
            teams = con.execute("select team_id, team_abbr from seeds.teams").df()
        if batters.empty:
            raise ScenarioError(f"no {source} batter projections for {season}")
        self.season, self.source = season, source
        self.abbr = dict(zip(teams["team_id"], teams["team_abbr"], strict=True))
        self.team_ids = {a: i for i, a in self.abbr.items()}
        self.allocations, self.inputs = lo.optimize_league(batters, self.positions)
        self.runs_per_win = float(self.allocations.attrs["runs_per_win"])
        self.rep_runs = float(self.allocations.attrs["rep_runs"])
        self.unsigned = unsigned_players(source, season, "batters", projections_dir)
        self._unsigned_inputs: pd.DataFrame | None = None

    # -- lookups --
    def team_id(self, team: str | int) -> int:
        if isinstance(team, (int, np.integer)):
            return int(team)
        try:
            return self.team_ids[team.upper()]
        except KeyError:
            raise ScenarioError(f"unknown team {team!r}") from None

    def team_inputs(self, team: str | int) -> pd.DataFrame:
        tid = self.team_id(team)
        return self.inputs[self.inputs["team_id"] == tid].reset_index(drop=True)

    def lineup(self, team: str | int) -> pd.DataFrame:
        """The team's current optimized allocation (as in the forecast)."""
        return self.allocations[self.allocations["team_id"] == self.team_id(team)]

    def _all_players(self) -> pd.DataFrame:
        if self._unsigned_inputs is None:
            pool = self.unsigned
            if len(pool):
                pool = pool[pool["plate_appearances"] > 0]
            self._unsigned_inputs = (lo.player_inputs(pool.assign(team_id=-1), self.positions)
                                     if len(pool) else self.inputs.iloc[0:0])
        return pd.concat([self.inputs, self._unsigned_inputs], ignore_index=True)

    def find(self, player: str | int) -> pd.Series:
        """One player's optimizer inputs, by mlbam id or name (case and accents ignored; a
        unique partial match is accepted). team_id is -1 for an unsigned player."""
        everyone = self._all_players()
        if isinstance(player, (int, np.integer)) or str(player).isdigit():
            hit = everyone[everyone["mlbam_id"] == int(player)]
        else:
            folded = everyone["player_name"].map(_fold)
            hit = everyone[folded == _fold(player)]
            if hit.empty:
                hit = everyone[folded.str.contains(_fold(player), regex=False)]
        if len(hit) == 1:
            return hit.iloc[0]
        if hit.empty:
            raise ScenarioError(f"no {self.season} {self.source} batter matches {player!r}")
        options = ", ".join(f"{r.player_name} ({self.abbr.get(r.team_id, 'unsigned')}, "
                            f"{r.mlbam_id})" for r in hit.head(8).itertuples())
        raise ScenarioError(f"{player!r} matches several players: {options}. Use the id.")

    # -- scenarios --
    def run(self, team: str | int, add: Sequence[str | int] = (),
            remove: Sequence[str | int] = ()) -> LineupChange:
        """Re-optimize `team` with players added (free agents or other teams' players) and
        removed (its own players)."""
        tid = self.team_id(team)
        mine = self.team_inputs(tid)
        out_ids = []
        for p in remove:
            row = self.find(p)
            if row["team_id"] != tid:
                raise ScenarioError(f"{row['player_name']} is not on {self.abbr.get(tid, tid)}")
            out_ids.append(int(row["mlbam_id"]))
        new = [self.find(p) for p in add]
        for row in new:
            if row["team_id"] == tid:
                raise ScenarioError(f"{row['player_name']} is already on {self.abbr[tid]}")
        add_rows = pd.DataFrame(new).assign(team_id=tid) if new else None
        return compare_lineups(mine, self.rep_runs, self.runs_per_win, add=add_rows,
                               remove=out_ids, before=self.lineup(tid).drop(columns="team_id"),
                               team=self.abbr.get(tid, str(tid)))
