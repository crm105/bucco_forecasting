"""Projection report: player errors and the rate / playing-time split of team WAR error."""

import pandas as pd
import pytest

from bucco.evaluate import projection_report as pr


def _proj(pt, rates, part="batting"):
    """Two teams, two players each, one season; rates are WAR per unit of playing time."""
    alloc = pd.DataFrame({"season": 2019, "team_id": [1, 1, 2, 2], "mlbam_id": [1, 2, 3, 4],
                          "pt": pt, "war": [p * r for p, r in zip(pt, rates, strict=True)]})
    players = alloc.drop(columns="team_id").assign(rate=rates, own_rate=rates, runs_rate=float("nan"))
    other = "pitching" if part == "batting" else "batting"
    empty = players.iloc[0:0]
    return {part: players, f"{part}_team": alloc, other: empty, f"{other}_team": alloc.iloc[0:0]}


def _actual(pt, rates, part="batting"):
    return pd.DataFrame({"season": 2019, "mlbam_id": [1, 2, 3, 4], "team_id": [1, 1, 2, 2],
                         "part": part, "playing_time": pt, "runs": 0.0,
                         "war": [p * r for p, r in zip(pt, rates, strict=True)]})


def test_right_rates_leave_only_playing_time_error():
    rates = [0.01, 0.002, 0.008, 0.001]
    proj = _proj([600, 100, 300, 400], rates)
    act = _actual([300, 400, 600, 100], rates)
    dec = pr.decomposition(proj, act, [2019])
    assert dec.loc["Perfect playing time (rate error left)", "batting"] == pytest.approx(0.0)
    assert dec.loc["Full projection", "batting"] > 0
    assert dec.loc["Perfect rates (playing-time error left)", "batting"] == pytest.approx(
        dec.loc["Full projection", "batting"])


def test_right_playing_time_leaves_only_rate_error():
    pt = [600, 100, 300, 400]
    proj = _proj(pt, [0.01, 0.002, 0.008, 0.001])
    act = _actual(pt, [0.004, 0.002, 0.012, 0.001])
    dec = pr.decomposition(proj, act, [2019])
    assert dec.loc["Perfect rates (playing-time error left)", "batting"] == pytest.approx(0.0)
    assert dec.loc["Perfect both (unprojected players)", "batting"] == pytest.approx(0.0)


def test_player_table_scores_rate_playing_time_and_production():
    rates = [0.01, 0.002, 0.008, 0.001]
    proj = _proj([600, 100, 300, 400], rates)
    act = _actual([600, 100, 300, 400], rates)
    table = pr.player_table(proj, act)
    row = table.loc["Hitters"]
    assert row["playing time (PA)"] == pytest.approx(0.0)
    assert row["rate (WAR per 600)"] == pytest.approx(0.0)
    assert row["production (WAR)"] == pytest.approx(0.0)
