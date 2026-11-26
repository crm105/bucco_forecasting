"""Injured-list transactions: parsing and checks."""

import pandas as pd
import pytest

from bucco.extract import mlb_transactions as mt


def _tx(i, text, pid=1, date="2024-04-01"):
    return {"id": i, "person": {"id": pid, "fullName": "A"}, "toTeam": {"id": 134},
            "date": date, "effectiveDate": date, "description": text}


def test_parse_reads_event_list_length_and_retroactive_date():
    payload = {"transactions": [
        _tx(1, "Pirates placed RHP A on the 15-day injured list retroactive to March 25, 2024."),
        _tx(2, "Pirates transferred RHP A from the 15-day injured list to the 60-day injured list."),
        _tx(3, "Pirates activated RHP A from the 60-day injured list."),
        _tx(4, "Rangers placed C A on the 10 day disabled list."),
        _tx(5, "Pirates reinstated LHP A from the 10-day disabled list."),
        _tx(6, "Pirates optioned RHP A to Indianapolis Indians."),        # not about the list
    ]}
    rows = pd.DataFrame(mt.parse_transactions(payload, 2024, "now"))
    assert list(rows["event"]) == ["placed", "transferred", "activated", "placed", "activated"]
    assert list(rows["list_days"]) == [15, 15, 60, 10, 10]
    assert rows.loc[0, "retro_date"] == "2024-03-25" and rows["retro_date"].iloc[1:].isna().all()


def test_checks_reject_thin_or_unreadable_years():
    good = pd.DataFrame({"transaction_id": range(600), "event": ["placed"] * 600,
                         "list_days": [15] * 600})
    mt.validate_transactions(good, 2024)
    with pytest.raises(ValueError, match="only"):
        mt.validate_transactions(good.iloc[:10], 2024)
    bad = good.assign(list_days=None)
    with pytest.raises(ValueError, match="list length"):
        mt.validate_transactions(bad, 2024)
