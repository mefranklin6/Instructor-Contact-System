"""Tests for the plugin loader layer."""

import pandas as pd

from core.system_plugins import (
    create_id_matcher,
    create_schedule_loader,
    create_supported_locations,
)
from src.core.settings import Settings


def test_builtin_zoom_csv_id_matcher(tmp_path):
    """Built-in matcher loads and normalizes IDs."""
    csv_path = tmp_path / "zoom.csv"
    df = pd.DataFrame(
        [
            {"Employee ID": "1", "Email": "a@example.com"},
        ]
    )
    df.to_csv(csv_path, index=False)

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=str(csv_path),
        fl_file_path=None,
        supported_locations_file_path=None,
    )

    matcher = create_id_matcher(settings=settings, in_docker=False)
    assert matcher.match_id_to_email("1") == "a@example.com"
    assert matcher.match_id_to_email("000000001") == "a@example.com"


def test_builtin_supported_locations_chico(tmp_path):
    """Built-in supported locations parser returns (building, room) tuples."""
    csv_path = tmp_path / "supported.csv"
    pd.DataFrame(
        [
            {"Contact": "CTS", "Room": "SCI 110"},
            {"Contact": "OTHER", "Room": "ART 200"},
        ]
    ).to_csv(csv_path, index=False)

    settings = Settings(
        supported_locations_mode="chico",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=str(csv_path),
    )

    locs = create_supported_locations(settings=settings)
    assert locs is not None
    assert ("SCI", "110") in locs


def test_builtin_schedule_loader_fl_csv(tmp_path):
    """Built-in schedule loader can be constructed from a minimal CSV."""
    # Minimal FacilitiesLink-like CSV row to satisfy cleaning.
    fl_path = tmp_path / "fl.csv"
    pd.DataFrame(
        [
            {
                "INSTRUCTOR1_EMPLID": "1",
                "CLASS_START_DATE": "01-Jan-25",
                "CLASS_END_DATE": "31-Dec-26",
                "START_TIME1": "08:00",
                "END_TIME1": "09:00",
                "DAYS1": "M",
                "BUILDING": "SCI",
                "ROOM": "110",
            }
        ]
    ).to_csv(fl_path, index=False)

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=str(fl_path),
        supported_locations_file_path=None,
    )

    loader = create_schedule_loader(settings=settings, supported_locations=None)
    assert hasattr(loader, "semester_data")
    assert hasattr(loader, "range_data")
