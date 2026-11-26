"""Team-WAR check: projected vs actual team WAR, centered by season."""

import pandas as pd
import pytest

from bucco.evaluate import team_war


def _frame(rows):
    return pd.DataFrame(rows, columns=["season", "team_id", "batting", "pitching", "total"])


def test_errors_are_centered_by_season_and_skip_2020():
    proj = _frame([(2019, 1, 12, 8, 20), (2019, 2, 8, 2, 10), (2020, 1, 5, 5, 10),
                   (2020, 2, 1, 1, 2)])
    actual = _frame([(2019, 1, 30, 20, 50), (2019, 2, 20, 10, 30), (2020, 1, 1, 1, 2),
                     (2020, 2, 1, 1, 2)])
    err = team_war.errors(proj, actual)
    assert set(err["season"]) == {2019}
    # projected spread 10 (20 vs 10), actual spread 20: each team off by 5 after centering
    assert list(err["total"]) == [-5.0, 5.0]
    s = team_war.score(err)
    assert s["total_rmse"] == pytest.approx(5.0) and s["n"] == 2


def test_projected_reads_the_models_parts():
    class Data:
        def team_war_parts(self, season, as_of):
            return pd.DataFrame({"batting": [3.0], "pitching": [1.0]},
                                index=pd.Index([134], name="team_id"))

    class Model:
        data = Data()

    features = pd.DataFrame({"season": [2019], "opening_day": ["2019-03-28"]})
    out = team_war.projected(Model(), features, [2019])
    assert out.loc[0, "total"] == 4.0 and out.loc[0, "team_id"] == 134
