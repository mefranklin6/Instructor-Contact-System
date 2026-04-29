"""Tests for Settings.from_env()."""

import pytest

from src.core.settings import Settings


def test_from_env_defaults(monkeypatch):
    """from_env() returns sensible defaults when no env vars are set."""
    for var in [
        "SUPPORTED_LOCATIONS_MODE",
        "ID_TO_EMAIL_MODULE",
        "SCHEDULE_MODULE",
        "DEV_MODE",
        "ZOOM_CSV_PATH",
        "FL_FILE_PATH",
        "SUPPORTED_LOCATIONS_FILE_PATH",
    ]:
        monkeypatch.delenv(var, raising=False)

    s = Settings.from_env()
    assert s.supported_locations_mode == "none"
    assert s.id_to_email_module == "none"
    assert s.schedule_module == "none"
    assert s.dev_mode is True
    assert s.zoom_csv_path is None
    assert s.fl_file_path is None
    assert s.supported_locations_file_path is None


def test_from_env_reads_values(monkeypatch):
    """from_env() reads all values from environment variables."""
    monkeypatch.setenv("SUPPORTED_LOCATIONS_MODE", "CHICO")
    monkeypatch.setenv("ID_TO_EMAIL_MODULE", "zoom_csv")
    monkeypatch.setenv("SCHEDULE_MODULE", "fl_csv")
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("ZOOM_CSV_PATH", "/path/to/zoom.csv")
    monkeypatch.setenv("FL_FILE_PATH", "/path/to/fl.csv")
    monkeypatch.setenv("SUPPORTED_LOCATIONS_FILE_PATH", "/path/to/sl.csv")

    s = Settings.from_env()
    assert s.supported_locations_mode == "chico"  # lowercased
    assert s.id_to_email_module == "zoom_csv"
    assert s.schedule_module == "fl_csv"
    assert s.dev_mode is False
    assert s.zoom_csv_path == "/path/to/zoom.csv"
    assert s.fl_file_path == "/path/to/fl.csv"
    assert s.supported_locations_file_path == "/path/to/sl.csv"


def test_from_env_dev_mode_false(monkeypatch):
    """DEV_MODE=false is parsed as bool False."""
    monkeypatch.setenv("DEV_MODE", "false")
    assert Settings.from_env().dev_mode is False


def test_from_env_dev_mode_true(monkeypatch):
    """DEV_MODE=true is parsed as bool True."""
    monkeypatch.setenv("DEV_MODE", "true")
    assert Settings.from_env().dev_mode is True
