"""Checks for the team outlook: helpers, text validation, charts, free-agent maths and a render."""

import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest

from bucco.report import outlook_data as od
from bucco.report import outlook_render as orr


# ---- helpers -----------------------------------------------------------------------------
def test_ordinals_and_joins():
    assert [od.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 30)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "30th"]
    assert orr.and_join(["a"]) == "a"
    assert orr.and_join(["a", "b", "c"]) == "a, b and c"
    assert orr.wins_text(1.2) == "1 win" and orr.wins_text(7.6) == "8 wins"


def test_surnames_keep_suffixes():
    assert orr.surname("Jake Mangum") == "Mangum"
    assert orr.surname("Rafael Flores Jr.") == "Flores Jr."
    assert orr.losers_text([]) == "—"


def test_short_names():
    assert orr.short_name("Pittsburgh Pirates") == "Pirates"
    assert orr.short_name("Boston Red Sox") == "Red Sox"
    assert orr.short_name("Toronto Blue Jays") == "Blue Jays"


def test_headline_follows_the_team_profile():
    assert orr.headline_key(5, 27) == "pitching_led"
    assert orr.headline_key(27, 5) == "batting_led"
    assert orr.headline_key(3, 8) == "both_strong"
    assert orr.headline_key(25, 28) == "both_weak"
    assert orr.headline_key(14, 16) == "balanced"


def test_pitcher_roles():
    p = pd.DataFrame({"games": [30, 60, 0], "games_started": [30, 2, 0]})
    assert list(od.pitcher_roles(p)) == ["SP", "RP", "RP"]
    assert list(od.pitcher_roles(p.assign(role=["RP", "SP", "RP"]))) == ["RP", "SP", "RP"]


# ---- text --------------------------------------------------------------------------------
def test_the_text_file_is_valid():
    text = orr.load_text()
    assert set(orr.HEADLINES) <= set(text["headlines"])


def test_an_unknown_placeholder_is_rejected(tmp_path):
    text = orr.TEXT_PATH.read_text(encoding="utf-8").replace(
        'kicker: "Bucco Forecasting · team outlook"', 'kicker: "Hello {nope}"')
    bad = tmp_path / "outlook_text.yml"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(orr.OutlookTextError, match="kicker"):
        orr.load_text(bad)


# ---- free agents -------------------------------------------------------------------------
def test_pitching_gain_is_measured_against_the_weakest_starter():
    team = pd.DataFrame({"team_id": 1, "player_name": ["Ace", "Mid", "Weak", "Pen"],
                         "games": [30, 30, 30, 60], "games_started": [30, 30, 30, 0],
                         "innings_pitched": [180.0, 170.0, 150.0, 60.0],
                         "war": [5.0, 3.0, 1.5, 0.6]})
    unsigned = pd.DataFrame({"player_name": ["Good SP", "Bad SP", "Good RP"],
                             "games": [30, 30, 70], "games_started": [30, 30, 0],
                             "innings_pitched": [175.0, 175.0, 70.0], "war": [3.5, 1.0, 1.4],
                             "fip": [3.6, 4.8, 2.9]})
    top, base = od.free_agent_pitchers(unsigned, team, team_id=1, n=3)
    assert base["weakest_sp"] == "Weak"
    good = top.set_index("name").loc["Good SP", "gain"]
    assert good == pytest.approx((3.5 / 175 - 1.5 / 150) * od.SP_IP)
    assert top.iloc[0]["name"] in {"Good SP", "Good RP"}
    assert (top["gain"].diff().dropna() <= 0).all()          # sorted, best first


# ---- render ------------------------------------------------------------------------------
def _spot(spot, war, avg, rank, pitchers=False):
    who = ([{"name": "Arm One", "war": 3.0}] if pitchers else
           [{"name": "Bat One", "pa": 500.0, "replacement": False},
            {"name": "x", "pa": 100.0, "replacement": True}])
    return {"spot": spot, "war": war, "avg": avg, "rank": rank, "best": avg + 3,
            "best_team": "AAA", "who": who}


def _data():
    spots = [_spot("Rotation", 15.0, 11.0, 3, True), _spot("Bullpen", 4.0, 3.3, 11, True)]
    spots += [_spot(q, 1.0 + i * 0.3, 2.0, 5 + i * 3) for i, q in enumerate(
        ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"])]
    scatter = [{"team": t, "batting": 15 + i * 0.4, "pitching": 10 + (i % 7)}
               for i, t in enumerate(["PIT", "MIL", "CHC", "STL", "CIN"]
                                     + [f"T{i}" for i in range(25)])]
    div = [{"team": t, "name": n, "wins": w, "batting": 20.0, "pitching": 15.0}
           for t, n, w in [("MIL", "Milwaukee Brewers", 88.7), ("PIT", "Pittsburgh Pirates", 81.1),
                           ("CHC", "Chicago Cubs", 80.1)]]
    summary = {"value": 18.3, "avg": 22.7, "rank": 27}
    return {
        "team": "PIT", "team_id": 134, "team_name": "Pittsburgh Pirates", "season": 2027,
        "model": "steamer_optimized", "source": "steamer", "as_of": "2026-11-23",
        "park": "PNC Park",
        "today": "2026-11-23",
        "forecast": {"wins": 81.1, "low": 68.8, "high": 93.5, "rank": 13},
        "total": {"value": 37.4, "avg": 37.3, "rank": 13}, "batting": summary,
        "pitching": {"value": 19.1, "avg": 14.6, "rank": 5},
        "spots": spots, "scatter": scatter,
        "runs": {"batting": {"value": -3.8, "avg": 35.5, "rank": 27},
                 "baserunning": {"value": 0.9, "avg": -0.3, "rank": 11},
                 "defense": {"value": -29.9, "avg": -20.9, "rank": 23}},
        "leaders": {"batters": [{"name": "Bat One", "position": "SS", "pa": 650.0,
                                 "where": [("SS", 600.0), ("2B", 50.0)],
                                 "wrc_plus": 108.0, "war": 3.5}],
                    "pitchers": [{"name": f"Arm {i}", "role": "SP", "ip": 170.0, "fip": None,
                                  "where": [("SP", 170.0)], "leverage": None,
                                  "war": w} for i, w in enumerate([4.7, 3.8, 3.3])]
                    + [{"name": "Closer", "role": "RP", "ip": 65.0, "fip": 3.1,
                        "where": [("RP", 65.0)], "leverage": "closer", "war": 2.0}]},
        "division": {"name": "NL Central", "rows": div},
        "schedule": {"wins": 0.3, "easiest_rank": 9},
        "free_agents": {
            "batters": [{"name": "Corner Bat", "mlbam_id": 1, "gain": 2.0, "pa": 625.0,
                         "where": [("3B", 385.0), ("RF", 175.0)], "natives": ["RF"],
                         "off_position": True, "wrc_plus": 120.0, "war600": 2.4,
                         "proj_war": 3.4, "proj_pa": 590.0,
                         "losers": [("Rafael Flores Jr.", 135.0), ("replacement level", 40.0)],
                         "last_team": "CHC", "park_fit": -1.24},
                        {"name": "Our Guy", "mlbam_id": 2, "gain": 1.3, "pa": 600.0,
                         "where": [("2B", 600.0)], "natives": ["2B"], "off_position": False,
                         "wrc_plus": np.nan, "war600": 2.5, "proj_war": 2.9, "proj_pa": 610.0, "last_team": "PIT"}],
            "pair": {"names": ["Corner Bat", "Our Guy"], "gain": 3.2, "separate": 3.3},
            "pitchers": [{"name": "Starter", "role": "SP", "ip": 175.0, "fip": 3.8, "war": 3.2,
                          "gain": 1.5}],
            "pitching_base": {"weakest_sp": "Arm 9", "weakest_sp_war": 1.5,
                              "weakest_sp_ip": 156.0, "weakest_rp": None}},
        "scores": {"rmse": 9.67, "first": 2012, "last": 2026, "rmse_recent": 9.46,
                   "recent_first": 2022},
        "runs_per_win": 9.76,
    }


def test_render_produces_valid_charts_and_the_key_facts():
    page = orr.render_outlook(_data())
    for svg in re.findall(r"<svg.*?</svg>", page, re.DOTALL):
        ET.fromstring(svg)
    assert page.count("<svg") == 2
    text = re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL))
    assert "A strong pitching staff carrying a below-average lineup" in text
    assert "81.1" in text and "8 wins behind the Brewers" in text
    assert "worth +0.3 wins" in text and "9th easiest" in text
    assert "Corner Bat *" in text                      # off-position flag
    assert "<td>3.4</td><td>590</td><td>+2.0</td>" in page   # projected WAR and PA beside gain
    assert "Flores Jr. 135, replacement 40" in text    # who loses time
    assert "Corner Bat and Our Guy" in text            # the pair, and-joined
    assert "Arm 0, Arm 1 and Arm 2" in text            # rotation concentration note
    assert 'class="mine"><td>Our Guy' in page          # last season's own player highlighted
    assert "<td>+2.0</td><td>−1.2</td>" in page        # park fit beside the gain
    assert "<td>+1.3</td><td>—</td>" in page           # unknown park fit: a dash
    assert "at PNC Park compared with" in text and "not in the gain" in text
    assert "SS 600, 2B 50" in text and "RP 65 (closer)" in text   # leaders' positions
    assert "{" not in text                             # every placeholder filled


def test_every_source_has_its_wording_and_marcel_says_where_its_numbers_come_from():
    text = orr.load_text()
    assert set(od.MODEL_SOURCE.values()) <= set(text["source_notes"])
    data = _data() | {"model": "marcel_park_optimized", "source": "marcel_park_fielding"}
    data["free_agents"]["batters"][0]["last_team"] = np.nan   # no MLB team last season
    page = orr.render_outlook(data)
    plain = re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL))
    assert "Steamer file lists with no team" in plain and "depth chart" in plain
    assert ">nan<" not in page and "&amp;#x27;" not in page
    assert "{" not in plain


def test_outlook_path_names_model_team_and_date(tmp_path):
    path = orr.outlook_path(_data(), tmp_path)
    assert path == tmp_path / "2027" / "steamer_optimized_pit_outlook_2026-11-23.html"


def test_leaders_list_every_position_and_role_with_leverage_tiers():
    alloc = pd.DataFrame({"team_id": [1, 1, 1, 2], "mlbam_id": [10, 10, 11, 20],
                          "player_name": ["Util", "Util", "Cat", "Other"],
                          "position": ["2B", "1B", "C", "SS"],
                          "pa": [211.0, 114.0, 500.0, 600.0], "war": [0.2, 0.1, 2.0, 3.0]})
    batters = pd.DataFrame({"team_id": [1, 1], "mlbam_id": [10, 11], "wrc_plus": [90.0, 100.0]})
    pitchers = pd.DataFrame({"team_id": [1, 1], "player_name": ["Ace", "Closer"],
                             "role": ["SP", "RP"], "innings_pitched": [190.0, 65.0],
                             "sp_ip": [180.0, 0.0], "rp_ip": [10.0, 65.0],
                             "leverage": [None, "closer"], "fip": [3.0, 2.8],
                             "war": [5.0, 2.4]})
    bats, arms = od.leaders(alloc, batters, pitchers, 1)
    assert [b["name"] for b in bats] == ["Cat", "Util"]
    assert bats[1]["where"] == [("2B", 211.0), ("1B", 114.0)] and bats[1]["position"] == "2B"
    assert arms[0]["where"] == [("SP", 180.0), ("RP", 10.0)] and arms[0]["leverage"] is None
    assert arms[1]["where"] == [("RP", 65.0)] and arms[1]["leverage"] == "closer"
