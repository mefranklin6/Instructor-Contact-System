"""Extra tests for system_plugins factory error and validation paths."""

import os
import time
from typing import Any

import pandas as pd
import pytest

from src.core.settings import Settings
from src.core.system_plugins import create_id_matcher, create_schedule_loader, create_supported_locations


def _settings(**overrides):
    defaults: dict[str, Any] = dict(
        supported_locations_mode="none",
        id_to_email_module="none",
        schedule_module="none",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# create_id_matcher
# ---------------------------------------------------------------------------


def test_create_id_matcher_raises_on_empty_module_spec():
    """create_id_matcher raises ValueError when id_to_email_module is empty."""
    with pytest.raises(ValueError, match="ID_TO_EMAIL_MODULE is required"):
        create_id_matcher(settings=_settings(id_to_email_module=""), in_docker=False)


def test_create_id_matcher_raises_on_unknown_module_spec():
    """create_id_matcher raises ValueError for an unrecognised module name."""
    with pytest.raises(ValueError, match="Invalid ID_TO_EMAIL_MODULE"):
        create_id_matcher(settings=_settings(id_to_email_module="unknown_module"), in_docker=False)


def test_create_id_matcher_zoom_csv_raises_when_path_missing():
    """create_id_matcher raises FileNotFoundError when zoom_csv_path is None."""
    with pytest.raises(FileNotFoundError, match="ZOOM_CSV_PATH"):
        create_id_matcher(
            settings=_settings(id_to_email_module="zoom_csv", zoom_csv_path=None),
            in_docker=False,
        )


def test_create_id_matcher_ad_api_in_docker_raises():
    """create_id_matcher raises RuntimeError when ad_api mode is requested inside Docker."""
    with pytest.raises(RuntimeError, match="Active Directory module is not supported while in Docker"):
        create_id_matcher(settings=_settings(id_to_email_module="ad_api"), in_docker=True)


# ---------------------------------------------------------------------------
# create_schedule_loader
# ---------------------------------------------------------------------------


def test_create_schedule_loader_raises_on_unknown_module_spec():
    """create_schedule_loader raises ValueError for an unrecognised module name."""
    with pytest.raises(ValueError, match="Invalid SCHEDULE_MODULE"):
        create_schedule_loader(
            settings=_settings(schedule_module="unknown_schedule"),
            supported_locations=None,
        )


def test_create_schedule_loader_fl_csv_raises_when_path_missing():
    """create_schedule_loader raises FileNotFoundError when fl_file_path is None."""
    with pytest.raises(FileNotFoundError, match="FL_FILE_PATH"):
        create_schedule_loader(
            settings=_settings(schedule_module="fl_csv", fl_file_path=None),
            supported_locations=None,
        )


def test_create_schedule_loader_fl_csv_raises_on_stale_file(tmp_path):
    """create_schedule_loader raises RuntimeError when the FL CSV is stale."""
    fl_path = tmp_path / "fl.csv"
    pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "1", "CLASS_START_DATE": "01-Jan-25", "CLASS_END_DATE": "31-Jan-25",
          "START_TIME1": "09:00", "END_TIME1": "09:50", "DAYS1": "M", "BUILDING": "SCI", "ROOM": "101"}]
    ).to_csv(fl_path, index=False)
    old_time = time.time() - (31 * 24 * 60 * 60)
    os.utime(fl_path, (old_time, old_time))

    with pytest.raises(RuntimeError, match="older than one month"):
        create_schedule_loader(
            settings=_settings(schedule_module="fl_csv", fl_file_path=str(fl_path)),
            supported_locations=None,
        )


# ---------------------------------------------------------------------------
# create_supported_locations
# ---------------------------------------------------------------------------


def test_create_supported_locations_raises_on_unknown_mode():
    """create_supported_locations raises ValueError for an unrecognised mode."""
    with pytest.raises(ValueError, match="Invalid SUPPORTED_LOCATIONS_MODE"):
        create_supported_locations(settings=_settings(supported_locations_mode="unknown_mode"))


def test_create_supported_locations_chico_raises_when_path_missing():
    """create_supported_locations raises FileNotFoundError when file path is not configured."""
    with pytest.raises(FileNotFoundError, match="SUPPORTED_LOCATIONS_FILE_PATH"):
        create_supported_locations(
            settings=_settings(
                supported_locations_mode="chico",
                supported_locations_file_path=None,
            )
        )


def test_create_supported_locations_chico_raises_on_stale_file(tmp_path):
    """create_supported_locations raises RuntimeError when the file is older than one month."""
    csv_path = tmp_path / "supported.csv"
    pd.DataFrame([{"Contact": "CTS", "Room": "SCI 101"}]).to_csv(csv_path, index=False)
    old_time = time.time() - (31 * 24 * 60 * 60)
    os.utime(csv_path, (old_time, old_time))

    with pytest.raises(RuntimeError, match="older than one month"):
        create_supported_locations(
            settings=_settings(
                supported_locations_mode="chico",
                supported_locations_file_path=str(csv_path),
            )
        )
