"""Checks for the hand-downloaded player projection files."""

from datetime import date

import pandas as pd
import pytest

from bucco.extract import player_projections as pp
from bucco.extract.projections import PLAYER_FILE_PATTERN, load_team_lookup, read_input_files

LOOKUP, _ = load_team_lookup()
TEAMS = ["PIT", "KCR", "SDP", "SFG", "TBR", "WSN", "CHW", "OAK", "ATH"] + [
    "NYY", "BOS", "LAD", "ATL", "HOU", "CHC", "STL", "MIL", "CIN", "CLE", "DET", "MIN", "SEA",
    "TEX", "TOR", "BAL", "LAA", "COL", "ARI", "PHI", "NYM", "MIA"]


def _raw(season=2024, kind="batter", teams=None, n_per_team=2):
    teams = teams or sorted(set(TEAMS) - {"ATH"})  # OAK and ATH are the same franchise
    rows = [{"player_name": f"p{t}{i}", "team_abbr": t, "fangraphs_id": f"{t}{i}",
             "mlbam_id": str(1000 + i), "games": 100.0, "war": 1.0, "plate_appearances": 400.0,
             "season": season, "source": "zips", "player_type": kind,
             "source_file": f"zips_{kind}s_individual_{season}.csv"}
            for t in teams for i in range(n_per_team)]
    return pd.DataFrame(rows)


def _manifest(file="zips_batters_individual_2024.csv", as_of="2024-02-01"):
    return pd.DataFrame({"file": [file], "as_of_date": [as_of], "source_url": [""],
                         "notes": [""]})


def test_file_name_pattern():
    ok = PLAYER_FILE_PATTERN.match("zips_batters_individual_2024.csv")
    assert ok["source"] == "zips" and ok["kind"] == "batters" and ok["season"] == "2024"
    assert not PLAYER_FILE_PATTERN.match("steamer_team_2024.csv")
    assert not PLAYER_FILE_PATTERN.match("_template.csv")


def test_team_reader_skips_player_files(tmp_path):
    (tmp_path / "zips_batters_individual_2024.csv").write_text("Name,Team\nx,PIT\n")
    (tmp_path / "steamer_2024.csv").write_text("season,source\n2024,steamer\n")
    frame = read_input_files(tmp_path)
    assert set(frame["source_file"]) == {"steamer_2024.csv"}


def test_clean_file_passes_and_resolves_team_aliases():
    clean, errors, warnings = pp.validate(
        _raw(), _manifest(), LOOKUP, {2024: date(2024, 3, 28)})
    assert errors == []
    assert clean["team_id"].notna().all()
    assert clean["as_of_date"].eq("2024-02-01").all()
    assert any("only" in w for w in warnings)  # no pitchers yet: flagged, not rejected


def test_missing_date_is_warned_not_rejected():
    _, errors, warnings = pp.validate(_raw(), _manifest(as_of=""), LOOKUP, {2024: date(2024, 3, 28)})
    assert errors == []
    assert any("no as_of_date" in w for w in warnings)


def test_download_after_opening_day_is_rejected():
    _, errors, _ = pp.validate(_raw(), _manifest(as_of="2024-04-15"), LOOKUP,
                               {2024: date(2024, 3, 28)})
    assert any("after Opening Day" in e for e in errors)


def test_partial_league_is_rejected():
    _, errors, _ = pp.validate(_raw(teams=["PIT", "NYY"]), _manifest(), LOOKUP,
                               {2024: date(2024, 3, 28)})
    assert any("expected 30" in e for e in errors)


def test_duplicate_player_is_rejected():
    raw = _raw()
    raw = pd.concat([raw, raw.head(1)], ignore_index=True)
    _, errors, _ = pp.validate(raw, _manifest(), LOOKUP, {2024: date(2024, 3, 28)})
    assert any("repeat a player" in e for e in errors)


def test_unknown_team_and_wild_war_are_rejected():
    raw = _raw()
    raw.loc[0, "team_abbr"] = "XXX"
    raw.loc[1, "war"] = 99.0
    _, errors, _ = pp.validate(raw, _manifest(), LOOKUP, {2024: date(2024, 3, 28)})
    assert any("unrecognised teams" in e for e in errors)
    assert any("WAR outside" in e for e in errors)


def test_missing_required_column_is_rejected(tmp_path):
    path = tmp_path / "zips_batters_individual_2024.csv"
    path.write_text("Name,Team,WAR\nx,PIT,1.0\n")
    with pytest.raises(pp.ProjectionValidationError, match="missing columns"):
        pp.read_file(path)


def test_read_file_handles_bom_and_renames(tmp_path):
    path = tmp_path / "zips_pitchers_individual_2023.csv"
    path.write_text("Name,Team,G,GS,IP,WAR,ERA,PlayerId,MLBAMID\nA B,PIT,30,30,180.5,3.1,3.5,"
                    "123,456\n", encoding="utf-8-sig")
    frame = pp.read_file(path)
    assert frame.loc[0, "innings_pitched"] == 180.5
    assert frame.loc[0, "player_type"] == "pitcher" and frame.loc[0, "season"] == 2023


def test_rows_with_no_team_are_dropped_with_a_warning():
    import pandas as pd

    from bucco.extract import player_projections as pp
    raw = pd.DataFrame({
        "season": [2022, 2022], "source": ["zips", "zips"], "player_type": ["pitcher", "pitcher"],
        "fangraphs_id": ["1", "2"], "mlbam_id": [1, 2], "player_name": ["A", "Free Agent"],
        "team_abbr": ["PIT", None], "war": [1.0, 0.1], "source_file": ["f.csv", "f.csv"],
    })
    _, errors, warnings = pp.validate(raw, pd.DataFrame(columns=["file", "as_of_date", "source_url", "notes"]),
                                      {"PIT": 134})
    assert not any("unrecognised teams" in e for e in errors)
    assert any("no team" in w and "Free Agent" in w for w in warnings)


def _frame(rows, file="f.csv"):
    import pandas as pd
    return pd.DataFrame([{
        "season": 2011, "source": "zips", "player_type": "batter", "fangraphs_id": str(i),
        "mlbam_id": i, "player_name": name, "team_abbr": team, "war": 1.0, "source_file": file,
    } for i, (name, team) in enumerate(rows)])


def test_blank_teams_go_to_the_one_missing_team():
    import pandas as pd

    from bucco.extract import player_projections as pp
    lookup = {"AAA": 1, "BBB": 2}
    raw = _frame([("A", "AAA"), ("Marlin", None)])
    manifest = pd.DataFrame(columns=["file", "as_of_date", "source_url", "notes"])
    clean, _, warnings = pp.validate(raw, manifest, lookup)
    assert clean.loc[clean["player_name"] == "Marlin", "team_id"].iloc[0] == 2
    assert any("assigned to BBB" in w for w in warnings)
    assert len(clean) == 2


def test_a_file_with_no_teams_is_skipped():
    import pandas as pd

    from bucco.extract import player_projections as pp
    raw = _frame([("A", None), ("B", None)], file="old.csv")
    manifest = pd.DataFrame(columns=["file", "as_of_date", "source_url", "notes"])
    clean, _, warnings = pp.validate(raw, manifest, {"AAA": 1})
    assert clean.empty
    assert any("no team on any row" in w for w in warnings)


def test_rows_with_no_name_or_ids_are_dropped():
    import pandas as pd

    from bucco.extract import player_projections as pp
    raw = _frame([("A", "AAA"), (None, "AAA")])
    raw["fangraphs_id"] = ["1", ""]
    raw["mlbam_id"] = ["1", ""]
    manifest = pd.DataFrame(columns=["file", "as_of_date", "source_url", "notes"])
    clean, errors, warnings = pp.validate(raw, manifest, {"AAA": 1})
    assert len(clean) == 1
    assert not any("PlayerId" in e for e in errors)
    assert any("no name or MLB id" in w for w in warnings)
