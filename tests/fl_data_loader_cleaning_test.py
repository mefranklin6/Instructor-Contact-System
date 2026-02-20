"""Unit tests for FacilitiesLink DataLoader cleaning and date conversion.

These tests focus on the core pipeline that prepares schedule data for aggregation:
- Required-column filtering and online/TBA exclusion
- Instructor ID normalization to 9-digit strings
- Date parsing with primary format and fallback inference
"""

from datetime import datetime

import pandas as pd

from plugins.fl_data_loader import DataLoader


def _row(**overrides: object) -> dict[str, object]:
    """Return a minimal CSV row dict with defaults overridden by kwargs."""
    base: dict[str, object] = {
        "INSTRUCTOR1_EMPLID": "2",
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


def test_clean_dataframe_filters_invalid_rows_and_normalizes_ids(monkeypatch) -> None:
    """Cleaned data keeps only valid rows and zero-pads numeric instructor IDs."""
    df = pd.DataFrame(
        [
            _row(INSTRUCTOR1_EMPLID="2", ROOM="101"),  # valid
            _row(INSTRUCTOR1_EMPLID=" 7 ", ROOM="102"),  # valid, whitespace
            _row(INSTRUCTOR1_EMPLID="abc", ROOM="103"),  # removed (non-numeric)
            _row(INSTRUCTOR1_EMPLID="9", ROOM="WWW"),  # removed (online)
            _row(INSTRUCTOR1_EMPLID="10", BUILDING="ONLINE"),  # removed (online)
            _row(INSTRUCTOR1_EMPLID="11", DAYS1="TBA"),  # removed (TBA)
            _row(INSTRUCTOR1_EMPLID="12", ROOM=None),  # removed (missing required)
        ]
    )

    monkeypatch.setattr("ics_bundled_plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    loader = DataLoader(fl_file_path="dummy.csv")
    assert loader.clean_df is not None

    emplids = set(loader.clean_df["INSTRUCTOR1_EMPLID"].astype(str).tolist())
    assert emplids == {"000000002", "000000007"}


def test_convert_dates_parses_primary_and_fallback_formats(monkeypatch) -> None:
    """Date conversion supports both FL's default format and pandas-inferred fallback."""
    df = pd.DataFrame(
        [
            _row(
                INSTRUCTOR1_EMPLID="2",
                CLASS_START_DATE="01-Jan-25",
                CLASS_END_DATE="31-Jan-25",
                ROOM="101",
            ),
            _row(
                INSTRUCTOR1_EMPLID="7",
                CLASS_START_DATE="2025-01-01",
                CLASS_END_DATE="2025-01-31",
                ROOM="102",
            ),
        ]
    )

    monkeypatch.setattr("ics_bundled_plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    loader = DataLoader(fl_file_path="dummy.csv")
    assert loader.clean_df is not None

    # Ensure both rows survived cleaning.
    assert len(loader.clean_df) == 2

    # Ensure date columns are real datetimes and not NaT.
    start_dates = pd.to_datetime(loader.clean_df["CLASS_START_DATE"], errors="coerce")
    end_dates = pd.to_datetime(loader.clean_df["CLASS_END_DATE"], errors="coerce")

    assert not start_dates.isna().any()
    assert not end_dates.isna().any()

    # Sanity check on one known value.
    assert datetime(2025, 1, 1).date() in set(start_dates.dt.date.tolist())


def test_semester_data_filters_to_single_term(monkeypatch) -> None:
    """semester_data() should pick one TERM from a multi-term export."""
    df = pd.DataFrame(
        [
            # Spring-ish term
            _row(
                INSTRUCTOR1_EMPLID="2",
                TERM="2232",
                CLASS_START_DATE="23-JAN-23",
                CLASS_END_DATE="19-MAY-23",
                BUILDING="SCI",
                ROOM="101",
            ),
            # Fall-ish term
            _row(
                INSTRUCTOR1_EMPLID="7",
                TERM="2238",
                CLASS_START_DATE="21-AUG-23",
                CLASS_END_DATE="15-DEC-23",
                BUILDING="ART",
                ROOM="202",
            ),
        ]
    )

    monkeypatch.setattr("ics_bundled_plugins.fl_data_loader.csv_to_dataframe", lambda _: df)

    loader = DataLoader(fl_file_path="dummy.csv")

    # Date within fall term window should only return TERM 2238 rows.
    out = loader.semester_data(datetime(2023, 10, 1))
    assert out is not None
    assert not out.empty
    assert set(out["TERM"].astype(str).unique().tolist()) == {"2238"}
