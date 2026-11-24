"""Strength of schedule: log5 and the schedule-adjusted win percentage."""

from datetime import date

import pandas as pd
import pytest

from bucco.models.depth_chart_model import DepthChartModel, PlayerData
from bucco.models.schedule import log5, neutral_from_adjusted, schedule_adjusted


def test_log5_basics():
    assert log5(0.5, 0.5) == pytest.approx(0.5)
    assert log5(0.6, 0.5) == pytest.approx(0.6)          # an average opponent changes nothing
    assert log5(0.6, 0.4) + log5(0.4, 0.6) == pytest.approx(1.0)
    assert log5(0.6, 0.6) == pytest.approx(0.5)


def _matchups(pairs):
    rows = []
    for a, b, n in pairs:
        rows += [{"team_id": a, "opponent_id": b, "games": n},
                 {"team_id": b, "opponent_id": a, "games": n}]
    return pd.DataFrame(rows)


def test_a_team_in_a_strong_division_loses_wins_and_the_league_total_is_kept():
    # Teams 1-2 (strong division) play each other a lot; 3-4 (weak) likewise.
    p = pd.Series({1: 0.56, 2: 0.56, 3: 0.48, 4: 0.40})
    games = _matchups([(1, 2, 40), (3, 4, 40), (1, 3, 20), (1, 4, 20), (2, 3, 20), (2, 4, 20)])
    adj = schedule_adjusted(p, games)
    assert adj[1] < p[1] and adj[2] < p[2]
    # Team 3's opponents average .48 (the weak 4 most often); team 4, the worst, never plays
    # itself, so its opponents average .52 and it loses a little too.
    assert adj[3] > p[3]
    assert adj[4] < p[4]
    n = games.groupby("team_id")["games"].sum()
    assert (adj * n).sum() == pytest.approx(n.sum() / 2)  # one win per game


def test_teams_without_a_schedule_keep_their_value():
    p = pd.Series({1: 0.55, 2: 0.45, 9: 0.52})
    adj = schedule_adjusted(p, _matchups([(1, 2, 10)]))
    assert adj[9] == 0.52
    assert schedule_adjusted(p, _matchups([]).reindex(columns=["team_id", "opponent_id",
                                                               "games"])).equals(p)


def test_the_model_applies_the_schedule_when_it_has_one():
    from test_depth_chart_model import _data, _history

    data = _data(strengths=((1.5, 1), (1.0, 500), (0.5, 1000)))
    games = pd.DataFrame([{"season": 2023, "team_id": t, "opponent_id": o, "games": 81}
                          for t in (1, 2, 3) for o in (1, 2, 3) if t != o])
    with_schedule = PlayerData(data.batters, data.pitchers, data.positions, matchups=games)
    feats = pd.DataFrame({"season": 2023, "team_id": [1, 2, 3]})
    hist = pd.concat([_history(), pd.DataFrame([{"season": s, "team_id": 3, "win_pct": 0.44,
                                                  "games_played": 162} for s in (2021, 2022)])])
    hist.loc[hist["team_id"] == 2, "win_pct"] = 0.5
    hist.loc[(hist["team_id"] == 3), "win_pct"] = 0.44
    plain = DepthChartModel(data)
    adj = DepthChartModel(with_schedule)
    off = DepthChartModel(with_schedule, schedule=False)
    for m in (plain, adj, off):
        m.fit(hist)
    a = adj.predict(2023, date(2023, 3, 30), feats)["mean_win_pct"]
    b = plain.predict(2023, date(2023, 3, 30), feats)["mean_win_pct"]
    c = off.predict(2023, date(2023, 3, 30), feats)["mean_win_pct"]
    assert list(b) == pytest.approx(list(c))              # no schedule, or switched off: as before
    assert list(a) != pytest.approx(list(b))
    assert a.sum() == pytest.approx(b.sum())              # league total kept


def test_the_adjustment_can_be_inverted():
    p = pd.Series({1: 0.58, 2: 0.55, 3: 0.47, 4: 0.40})
    games = _matchups([(1, 2, 40), (3, 4, 40), (1, 3, 20), (1, 4, 20), (2, 3, 20), (2, 4, 20)])
    back = neutral_from_adjusted(schedule_adjusted(p, games), games)
    assert list(back) == pytest.approx(list(p), abs=1e-8)
