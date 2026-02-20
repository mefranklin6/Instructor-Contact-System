"""Tests that stale (>1 month old) input files are detected and rejected.

Uses tmp_path fixtures + os.utime to backdate file modification times so no
real data files are needed.
"""

import os
import time

import pandas as pd
import pytest

from core.system_plugins import (
    create_id_matcher,
    create_schedule_loader,
)
from src.core.settings import Settings
from src.utils import file_is_stale

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ONE_MONTH_SECONDS = 30 * 24 * 60 * 60


def _backdate(path, seconds_ago: int) -> None:
    """Set the mtime of *path* to *seconds_ago* seconds in the past."""
    old_time = time.time() - seconds_ago
    os.utime(path, (old_time, old_time))


# ---------------------------------------------------------------------------
# Unit tests for file_is_stale()
# ---------------------------------------------------------------------------


def test_fresh_file_is_not_stale(tmp_path):
    """A newly created file should not be considered stale."""
    f = tmp_path / "fresh.txt"
    f.write_text("data")
    assert not file_is_stale(str(f))


def test_file_just_under_threshold_is_not_stale(tmp_path):
    """A file 29 days old should not be stale."""
    f = tmp_path / "almost.txt"
    f.write_text("data")
    _backdate(f, 29 * 24 * 60 * 60)
    assert not file_is_stale(str(f))


def test_file_exactly_over_threshold_is_stale(tmp_path):
    """A file 31 days old should be stale."""
    f = tmp_path / "old.txt"
    f.write_text("data")
    _backdate(f, 31 * 24 * 60 * 60)
    assert file_is_stale(str(f))


# ---------------------------------------------------------------------------
# Plugin factory — zoom_csv
# ---------------------------------------------------------------------------


def test_zoom_csv_stale_raises(tmp_path):
    """create_id_matcher raises RuntimeError when the Zoom CSV is stale."""
    csv_path = tmp_path / "zoom.csv"
    pd.DataFrame([{"Employee ID": "1", "Email": "a@example.com"}]).to_csv(csv_path, index=False)
    _backdate(csv_path, 31 * 24 * 60 * 60)

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="none",
        dev_mode=True,
        zoom_csv_path=str(csv_path),
        fl_file_path=None,
        supported_locations_file_path=None,
    )

    with pytest.raises(RuntimeError, match="older than one month"):
        create_id_matcher(settings=settings, in_docker=False)


def test_zoom_csv_fresh_does_not_raise(tmp_path):
    """create_id_matcher succeeds when the Zoom CSV is fresh."""
    csv_path = tmp_path / "zoom.csv"
    pd.DataFrame([{"Employee ID": "1", "Email": "a@example.com"}]).to_csv(csv_path, index=False)
    # File is brand-new; no backdating needed.

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="none",
        dev_mode=True,
        zoom_csv_path=str(csv_path),
        fl_file_path=None,
        supported_locations_file_path=None,
    )

    matcher = create_id_matcher(settings=settings, in_docker=False)
    assert matcher.match_id_to_email("1") == "a@example.com"


# ---------------------------------------------------------------------------
# Plugin factory — fl_csv (schedule loader)
# ---------------------------------------------------------------------------


def _write_minimal_fl_csv(path) -> None:
    """Write the bare-minimum columns required by the FL data loader."""
    pd.DataFrame(
        [
            {
                "Section": "CSCI-101-01",
                "Instructor": "Smith, John",
                "Employee ID": "123",
                "Start Date": "01/01/2026",
                "End Date": "05/01/2026",
                "Building": "BUTTE",
                "Room": "101",
                "Days": "MWF",
                "Start Time": "09:00 AM",
                "End Time": "09:50 AM",
            }
        ]
    ).to_csv(path, index=False)


def test_fl_csv_stale_raises(tmp_path):
    """create_schedule_loader raises RuntimeError when the FL CSV is stale."""
    fl_path = tmp_path / "fl.csv"
    _write_minimal_fl_csv(fl_path)
    _backdate(fl_path, 31 * 24 * 60 * 60)

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=str(fl_path),
        supported_locations_file_path=None,
    )

    with pytest.raises(RuntimeError, match="older than one month"):
        create_schedule_loader(settings=settings, supported_locations=None)


def test_fl_csv_fresh_does_not_raise_stale_error(tmp_path):
    """create_schedule_loader does not raise a staleness error when the FL CSV is fresh."""
    fl_path = tmp_path / "fl.csv"
    _write_minimal_fl_csv(fl_path)

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=str(fl_path),
        supported_locations_file_path=None,
    )

    # We only care that no staleness RuntimeError is raised.
    # Other exceptions (e.g. schema validation) are out of scope for this test.
    try:
        create_schedule_loader(settings=settings, supported_locations=None)
    except Exception as exc:
        assert not (isinstance(exc, RuntimeError) and "older than one month" in str(exc)), (
            f"Unexpected stale-file error: {exc}"
        )


# ---------------------------------------------------------------------------
# Plugin factory — ad_json in Docker (stale → RuntimeError)
# ---------------------------------------------------------------------------


def test_ad_json_stale_in_docker_raises(tmp_path, monkeypatch):
    """create_id_matcher raises RuntimeError for a stale ad_json file when in Docker."""
    json_path = tmp_path / "id_and_emails_from_ad.json"
    json_path.write_text('{"employees": []}')
    _backdate(json_path, 31 * 24 * 60 * 60)

    # Redirect os.path.exists and os.path.getmtime to the tmp file.
    monkeypatch.chdir(tmp_path)

    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="ad_json",
        schedule_module="none",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=None,
    )

    with pytest.raises(RuntimeError, match="older than one month"):
        create_id_matcher(settings=settings, in_docker=True)
