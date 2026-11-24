"""Lineup scenarios: adding and removing players and reading off what changes."""

import numpy as np
import pandas as pd
import pytest

from bucco.models.lineup_optimizer import POSITIONS
from bucco.models.scenario import REPLACEMENT, ScenarioError, _fold, compare_lineups

REP = 20.0 / 600
RPW = 10.0
ADJ = {"C": 12.5, "1B": -12.5, "2B": 2.5, "3B": 2.5, "SS": 7.5, "LF": -7.5, "CF": 2.5,
       "RF": -7.5, "DH": -17.5}


def _player(i, off600, home, name=None, also=()):
    """A player who fields like an average player at `home` (and at `also`), and can DH."""
    can = {home, *also, "DH"}
    return {"mlbam_id": i, "player_name": name or f"p{i}", "proj_pa": 600.0,
            "o_rate": off600 / 600,
            **{f"def_{q}": (ADJ[q] if q in can else np.nan) for q in POSITIONS}}


def _team():
    homes = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]
    rows = [_player(i + 1, 0.0, q) for i, q in enumerate(homes)]
    rows.append(_player(9, -10.0, "LF", "bench bat", also=("RF", "1B")))
    return pd.DataFrame(rows)


def test_adding_a_better_shortstop_shows_the_gain_and_who_loses_time():
    star = pd.DataFrame([_player(100, 30.0, "SS", "star")])
    change = compare_lineups(_team(), REP, RPW, add=star, team="XXX")
    assert change.gain > 0
    assert change.where("star")[0][0] == "SS"
    # Replacement-level filler goes first, then the old shortstop gives up time at short.
    assert change.losers(1)[0][0] == REPLACEMENT
    assert change.pa_change().loc["p5", "SS"] < 0
    assert "star" not in [n for n, _ in change.losers(5)]
    # PA are only moved around: every slot is still filled.
    assert change.pa_change(min_pa=0)["total"].sum() == pytest.approx(0, abs=1e-6)
    assert change.added == ["star"] and change.team == "XXX"


def test_removing_a_player_hands_his_time_to_others():
    change = compare_lineups(_team(), REP, RPW, remove=[6])
    assert change.removed == ["p6"]
    assert change.gain < 0
    pa = change.pa_change()
    assert pa.loc["p6", "total"] < -500
    assert pa.drop(index="p6")["total"].sum() == pytest.approx(-pa.loc["p6", "total"])


def test_war_change_adds_up_to_the_gain():
    star = pd.DataFrame([_player(100, 30.0, "CF", "star")])
    change = compare_lineups(_team(), REP, RPW, add=star)
    assert change.war_change(min_war=0).sum() == pytest.approx(change.gain)


def test_adding_someone_already_on_the_team_is_an_error():
    with pytest.raises(ScenarioError):
        compare_lineups(_team(), REP, RPW, add=pd.DataFrame([_player(5, 0.0, "SS")]))


def test_report_and_replacement_label():
    change = compare_lineups(_team(), REP, RPW, remove=[1])
    text = change.report()
    assert text.startswith("remove p1: batting WAR") or "remove p1" in text.splitlines()[0]
    assert "PA change" in text and "WAR change" in text
    # With the only catcher gone, replacement level catches.
    assert REPLACEMENT in change.pa_change().index


def test_names_match_without_case_or_accents():
    assert _fold("Endy Rodríguez") == _fold("endy rodriguez")
