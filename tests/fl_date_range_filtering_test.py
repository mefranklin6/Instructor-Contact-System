"""Tests for FacilitiesLink date-range filtering.

These validate that DataLoader.range_data() includes only classes that actually meet
at least once in the requested [start_date, end_date] window, based on:
- CLASS_START_DATE / CLASS_END_DATE span overlap
- DAYS1 meeting pattern (M/T/W/R/F/S/U)
- exclusions like TBA / empty days
"""

from datetime import datetime

import pandas as pd

from ics_bundled_plugins.fl_data_loader import DataLoader


def _base_row(**overrides: object) -> dict[str, object]:
    """Create a minimal FL row dict for date-range filtering tests."""
    row: dict[str, object] = {
        "INSTRUCTOR1_EMPLID": "1",
        "CLASS_START_DATE": "01-Jan-25",
        "CLASS_END_DATE": "31-Jan-25",
        "START_TIME1": "09:00",
        "END_TIME1": "09:50",
        "DAYS1": "MWF",
        "BUILDING": "SCI",
        "ROOM": "101",
    }
    row.update(overrides)
    return row


def test_range_data_single_day_includes_only_classes_that_meet_that_day(monkeypatch) -> None:
    """Filter to a single day and include only classes meeting that weekday."""
    # Thursday Jan 2, 2025: only DAYS1 containing "R" should meet.
    df = pd.DataFrame(
        [
            _base_row(INSTRUCTOR1_EMPLID="1", DAYS1="MWF", BUILDING="SCI", ROOM="101"),
            _base_row(INSTRUCTOR1_EMPLID="2", DAYS1="R", BUILDING="SCI", ROOM="102"),
            _base_row(  # outside span
                INSTRUCTOR1_EMPLID="3",
                DAYS1="R",
                CLASS_START_DATE="01-Feb-25",
                CLASS_END_DATE="28-Feb-25",
                BUILDING="SCI",
                ROOM="103",
            ),
            _base_row(INSTRUCTOR1_EMPLID="4", DAYS1="TBA", BUILDING="SCI", ROOM="104"),
            _base_row(INSTRUCTOR1_EMPLID="5", DAYS1="", BUILDING="SCI", ROOM="105"),
        ]
    )

    # Patch CSV loader used by DataLoader.__init__ so no real file is needed.
    monkeypatch.setattr("ics_bundled_plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    loader = DataLoader(fl_file_path="dummy.csv")

    out = loader.range_data(datetime(2025, 1, 2), datetime(2025, 1, 2))
    assert not out.empty

    # Only the Thursday course should remain (SCI 102 with emplid 000000002 after normalization).
    assert set(out["ROOM"].astype(str).tolist()) == {"102"}
    assert set(out["INSTRUCTOR1_EMPLID"].astype(str).tolist()) == {"000000002"}


def test_range_data_multi_day_window_includes_any_class_meeting_within_window(monkeypatch) -> None:
    """Include classes that meet at least once within a multi-day window."""
    # Window Thu Jan 2 -> Fri Jan 3, 2025 should include:
    # - R (Thu) and MWF (Fri) courses.
    df = pd.DataFrame(
        [
            _base_row(INSTRUCTOR1_EMPLID="1", DAYS1="MWF", BUILDING="SCI", ROOM="101"),
            _base_row(INSTRUCTOR1_EMPLID="2", DAYS1="R", BUILDING="SCI", ROOM="102"),
            _base_row(INSTRUCTOR1_EMPLID="4", DAYS1="TBA", BUILDING="SCI", ROOM="104"),
        ]
    )

    monkeypatch.setattr("ics_bundled_plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    loader = DataLoader(fl_file_path="dummy.csv")

    out = loader.range_data(datetime(2025, 1, 2), datetime(2025, 1, 3))
    assert not out.empty

    # TBA must be excluded; the other two should be present.
    rooms = set(out["ROOM"].astype(str).tolist())
    assert rooms == {"101", "102"}

    # Ensure helper columns were not leaked by _expand_to_meeting_dates().
    assert "search_start" not in out.columns
    assert "search_end" not in out.columns
    assert "meeting_weekdays" not in out.columns
