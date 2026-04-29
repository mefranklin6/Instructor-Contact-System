"""Tests for SupportedLocationsParser edge cases."""

import pandas as pd
import pytest

from plugins.chico_supported_location_parser import SupportedLocationsParser  # pyright: ignore[reportMissingImports]


def test_parser_skips_none_room_entries(tmp_path):
    """Parser skips rows where the Room value is None."""
    csv_path = tmp_path / "supported.csv"
    pd.DataFrame(
        [
            {"Contact": "CTS", "Room": None},
            {"Contact": "CTS", "Room": "SCI 101"},
        ]
    ).to_csv(csv_path, index=False)

    parser = SupportedLocationsParser(str(csv_path))
    result = parser.run()
    assert ("SCI", "101") in result
    assert len(result) == 1


def test_parser_skips_entries_that_do_not_match_pattern(tmp_path):
    """Parser silently skips rooms that don't match the building-room regex."""
    csv_path = tmp_path / "supported.csv"
    pd.DataFrame(
        [
            {"Contact": "CTS", "Room": "SCI 101"},  # valid
            {"Contact": "CTS", "Room": "12345"},     # all digits — no letter prefix
        ]
    ).to_csv(csv_path, index=False)

    parser = SupportedLocationsParser(str(csv_path))
    result = parser.run()
    assert result == [("SCI", "101")]


def test_parser_returns_empty_list_when_csv_load_returns_none(monkeypatch, tmp_path):
    """Parser returns [] without crashing when csv_to_dataframe returns None."""
    monkeypatch.setattr(
        "plugins.chico_supported_location_parser.csv_to_dataframe", lambda _: None
    )
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("Contact,Room\n")

    parser = SupportedLocationsParser(str(csv_path))
    assert parser.run() == []
