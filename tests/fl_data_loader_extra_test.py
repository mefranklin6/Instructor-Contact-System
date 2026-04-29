"""Additional fl_data_loader tests for paths not covered by the core test suite."""

from datetime import datetime

import pandas as pd
import pytest

from plugins.fl_data_loader import DataLoader  # pyright: ignore[reportMissingImports]


def _row(**overrides):
    """Return a minimal valid FL CSV row dict."""
    base = {
        "INSTRUCTOR1_EMPLID": "1",
        "CLASS_START_DATE": "01-Jan-25",
        "CLASS_END_DATE": "31-Jan-25",
        "START_TIME1": "09:00",
        "END_TIME1": "09:50",
        "DAYS1": "MWF",
        "BUILDING": "SCI",
        "ROOM": "101",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# range_data validation
# ---------------------------------------------------------------------------


def test_range_data_raises_when_start_after_end(monkeypatch):
    """range_data raises ValueError when start_date > end_date."""
    monkeypatch.setattr(
        "plugins.fl_data_loader.csv_to_dataframe",
        lambda _: pd.DataFrame([_row()]),
    )
    loader = DataLoader(fl_file_path="dummy.csv")

    with pytest.raises(ValueError, match="start_date must be less than or equal to end_date"):
        loader.range_data(datetime(2025, 1, 31), datetime(2025, 1, 1))


# ---------------------------------------------------------------------------
# _expand_to_meeting_dates early-exit paths
# ---------------------------------------------------------------------------


def test_range_data_empty_when_all_days_are_empty_string(monkeypatch):
    """range_data returns empty DataFrame when all DAYS1 values are empty strings."""
    df = pd.DataFrame(
        [
            _row(INSTRUCTOR1_EMPLID="1", DAYS1=""),  # empty — not TBA, but no days
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    out = loader.range_data(datetime(2025, 1, 1), datetime(2025, 1, 31))
    assert out.empty


def test_range_data_empty_when_class_dates_outside_query_window(monkeypatch):
    """range_data returns empty DataFrame when no class dates overlap the query window."""
    df = pd.DataFrame(
        [
            # Class ran in 2024; query window is 2025
            _row(
                INSTRUCTOR1_EMPLID="1",
                DAYS1="MWF",
                CLASS_START_DATE="01-Jan-24",
                CLASS_END_DATE="31-May-24",
            ),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    out = loader.range_data(datetime(2025, 1, 1), datetime(2025, 1, 31))
    assert out.empty


def test_range_data_empty_when_days_contain_no_valid_weekday_chars(monkeypatch):
    """range_data returns empty DataFrame when DAYS1 has no recognized weekday characters."""
    df = pd.DataFrame(
        [
            # "Z" is not a valid weekday code (M/T/W/R/F/S/U)
            _row(INSTRUCTOR1_EMPLID="1", DAYS1="Z"),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    out = loader.range_data(datetime(2025, 1, 1), datetime(2025, 1, 31))
    assert out.empty


# ---------------------------------------------------------------------------
# clean_df is None (csv_to_dataframe returns None)
# ---------------------------------------------------------------------------


def test_semester_data_returns_empty_when_clean_df_is_none(monkeypatch):
    """semester_data returns empty DataFrame when csv_to_dataframe returns None."""
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: None)
    loader = DataLoader(fl_file_path="dummy.csv")

    assert loader.clean_df is None
    out = loader.semester_data(datetime(2025, 1, 15))
    assert out is not None
    assert out.empty


def test_range_data_returns_empty_when_clean_df_is_none(monkeypatch):
    """range_data returns empty DataFrame when csv_to_dataframe returns None."""
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: None)
    loader = DataLoader(fl_file_path="dummy.csv")

    out = loader.range_data(datetime(2025, 1, 1), datetime(2025, 1, 31))
    assert out.empty


# ---------------------------------------------------------------------------
# Unparseable dates
# ---------------------------------------------------------------------------


def test_convert_dates_raises_on_unparseable_dates(monkeypatch):
    """DataLoader raises ValueError when date columns cannot be parsed."""
    df = pd.DataFrame(
        [
            _row(CLASS_START_DATE="NOT-A-DATE", CLASS_END_DATE="NOT-A-DATE"),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    with pytest.raises(ValueError, match="Unparseable dates"):
        DataLoader(fl_file_path="dummy.csv")


# ---------------------------------------------------------------------------
# Supported locations filtering
# ---------------------------------------------------------------------------


def test_filter_to_supported_locations_keeps_only_matching_rooms(monkeypatch):
    """DataLoader with supported_locations removes non-listed building/room pairs."""
    df = pd.DataFrame(
        [
            _row(INSTRUCTOR1_EMPLID="1", BUILDING="SCI", ROOM="101"),
            _row(INSTRUCTOR1_EMPLID="2", BUILDING="ART", ROOM="200"),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    loader = DataLoader(fl_file_path="dummy.csv", supported_locations=[("SCI", "101")])

    assert loader.clean_df is not None
    assert set(loader.clean_df["BUILDING"].unique()) == {"SCI"}
    assert set(loader.clean_df["ROOM"].astype(str).unique()) == {"101"}


# ---------------------------------------------------------------------------
# semester_data fallback paths
# ---------------------------------------------------------------------------


def _term_row(term, start, end, **overrides):
    """Build a row that includes a TERM column."""
    row = _row(CLASS_START_DATE=start, CLASS_END_DATE=end, **overrides)
    row["TERM"] = term
    return row


def test_semester_data_picks_upcoming_term_when_between_semesters(monkeypatch):
    """semester_data picks the next upcoming term when the date falls between terms."""
    df = pd.DataFrame(
        [
            _term_row("2241", "23-JAN-25", "19-MAY-25", INSTRUCTOR1_EMPLID="1", BUILDING="SCI", ROOM="101"),
            _term_row("2248", "25-AUG-25", "12-DEC-25", INSTRUCTOR1_EMPLID="2", BUILDING="ART", ROOM="200"),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    # June 15, 2025 is between Spring end (May 19) and Fall start (Aug 25)
    out = loader.semester_data(datetime(2025, 6, 15))
    assert out is not None and not out.empty
    assert set(out["TERM"].astype(str).unique()) == {"2248"}


def test_semester_data_picks_most_recent_term_when_past_all_terms(monkeypatch):
    """semester_data falls back to the most recently ended term when date is past all terms."""
    df = pd.DataFrame(
        [
            _term_row("2241", "23-JAN-25", "19-MAY-25", INSTRUCTOR1_EMPLID="1", BUILDING="SCI", ROOM="101"),
            _term_row("2248", "25-AUG-25", "12-DEC-25", INSTRUCTOR1_EMPLID="2", BUILDING="ART", ROOM="200"),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    # 2027 is past all terms → most recent by end date is Fall 2025 (TERM 2248)
    out = loader.semester_data(datetime(2027, 1, 1))
    assert out is not None and not out.empty
    assert set(out["TERM"].astype(str).unique()) == {"2248"}


def test_semester_data_returns_empty_df_when_clean_df_is_empty(monkeypatch):
    """semester_data returns an empty DataFrame when all rows were cleaned away."""
    # All rows are online (WWW) and will be removed by _clean_dataframe
    df = pd.DataFrame(
        [
            _row(INSTRUCTOR1_EMPLID="1", BUILDING="WWW", ROOM="WWW"),
        ]
    )
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    assert loader.clean_df is not None
    assert loader.clean_df.empty

    out = loader.semester_data(datetime(2025, 1, 1))
    assert out is not None
    assert out.empty


def test_semester_data_raises_on_missing_term_column(monkeypatch):
    """_filter_to_semester raises ValueError when the TERM column is absent."""
    df = pd.DataFrame([_row(INSTRUCTOR1_EMPLID="1")])  # no TERM column
    monkeypatch.setattr("plugins.fl_data_loader.csv_to_dataframe", lambda _: df)
    loader = DataLoader(fl_file_path="dummy.csv")

    with pytest.raises(ValueError, match="missing required column TERM"):
        loader.semester_data(datetime(2025, 1, 1))
