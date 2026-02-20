"""Plugin factories for bundled implementations.

Each `*_module` setting must be a short key for a bundled implementation
(e.g. `zoom_csv`, `fl_csv`, `chico`).

Bundled implementations live in the optional `plugins` package.
To add support for a new data source, submit a PR.
"""

import importlib
import logging as log
import os
from typing import Any

from src.core.settings import Settings
from src.utils import file_is_stale


def _bundled_import(module_name: str) -> Any:
    """Import a module from the optional `plugins` package.

    Raises a clear error if the bundled plugins package is not available.
    """

    try:
        return importlib.import_module(f"plugins.{module_name}")
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "Bundled plugin implementations are not installed/available. "
            "Please ensure the plugins package is present."
        ) from e


def create_supported_locations(*, settings: Settings) -> Any | None:
    """Create supported locations data (optional)."""

    spec = settings.supported_locations_mode

    if not spec or spec == "none":
        return None

    if spec == "chico":
        slp = _bundled_import("chico_supported_location_parser")

        if not settings.supported_locations_file_path:
            raise FileNotFoundError(
                "No SUPPORTED_LOCATIONS_FILE_PATH Found. This is a required file for Chico mode"
            )
        if file_is_stale(settings.supported_locations_file_path):
            raise RuntimeError("Supported locations file is older than one month. Please update")

        parser = slp.SupportedLocationsParser(settings.supported_locations_file_path)
        return parser.run()

    raise ValueError(f"Invalid SUPPORTED_LOCATIONS_MODE: {spec!r}. Must be 'none' or 'chico'.")


def create_id_matcher(*, settings: Settings, in_docker: bool) -> Any:
    """Create the ID->email matcher module."""

    spec = settings.id_to_email_module

    match spec:
        case None | "":
            raise ValueError("ID_TO_EMAIL_MODULE is required")

        case "zoom_csv":
            id_matcher_from_zoom_users_csv = _bundled_import("id_matcher_from_zoom_users_csv")

            if not settings.zoom_csv_path:
                raise FileNotFoundError("No ZOOM_CSV_PATH found. This is a required file for Zoom CSV mode")
            if file_is_stale(settings.zoom_csv_path):
                raise RuntimeError("Zoom Users Report CSV is older than one month. Please update")
            return id_matcher_from_zoom_users_csv.Matcher(csv_file_path=settings.zoom_csv_path)

        case "ad_api":
            if in_docker:
                raise RuntimeError("Active Directory module is not supported while in Docker")
            id_matcher_from_ad_api = _bundled_import("id_matcher_from_ad_api")
            return id_matcher_from_ad_api.Matcher()

        case "ad_json":
            import subprocess

            _AD_JSON_PATH = "id_and_emails_from_ad.json"

            def _run_ad_query_script() -> None:
                script_path = os.path.join("scripts", "query_ad.ps1")
                if not os.path.exists(script_path):
                    return
                log.info("System is in ad_json mode and not in docker. Querying AD now...")
                result = subprocess.run(
                    ["powershell.exe", "-File", script_path],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                log.info(f"AD query completed successfully:\n{result.stdout}")
                if result.stderr:
                    log.error(f"AD query stderr:\n{result.stderr}")

            json_exists = os.path.exists(_AD_JSON_PATH)

            if json_exists and file_is_stale(_AD_JSON_PATH):
                if in_docker:
                    raise RuntimeError(
                        f"'{_AD_JSON_PATH}' is older than one month. "
                        "Please regenerate the file and rebuild/restart the container."
                        "See /scrips/ad_query.ps1"
                    )
                log.warning(
                    f"'{_AD_JSON_PATH}' is older than one month. "
                    "Attempting to refresh it by re-running 'query_ad.ps1'..."
                )
                _run_ad_query_script()

            elif not json_exists:
                if in_docker:
                    pass  # fall through to the FileNotFoundError below
                else:
                    log.warning(
                        f"Could not find existing '{_AD_JSON_PATH}'. "
                        "Since we are not in docker, we will now run 'query_ad.ps1' to generate the file. "
                        "Be warned that this may take some time depending on the size of your domain."
                    )
                    try:
                        _run_ad_query_script()
                    except Exception:
                        # if generation fails, the missing-file error below triggers.
                        log.exception("AD query script failed")

            if not os.path.exists(_AD_JSON_PATH):
                raise FileNotFoundError(
                    f"No {_AD_JSON_PATH} found. Please run scripts/query_ad.ps1 first to generate this file"
                )

            id_matcher_from_ad_json = _bundled_import("id_matcher_from_ad_json")
            return id_matcher_from_ad_json.Matcher()

        case _:
            raise ValueError(
                f"Invalid ID_TO_EMAIL_MODULE: {spec!r}. Must be 'zoom_csv', 'ad_api', or 'ad_json'."
            )


def create_schedule_loader(*, settings: Settings, supported_locations: Any | None) -> Any:
    """Create the schedule data loader."""

    spec = settings.schedule_module

    if not spec or spec == "none":
        raise ValueError("SCHEDULE_MODULE is required")

    if spec == "fl_csv":
        schedule = _bundled_import("fl_data_loader")

        if not settings.fl_file_path:
            raise FileNotFoundError("No FL_FILE_PATH found. This is a required file for fl_csv mode")
        if file_is_stale(settings.fl_file_path):
            raise RuntimeError("FL schedule CSV is older than one month. Please update")

        return schedule.DataLoader(
            fl_file_path=settings.fl_file_path,
            supported_locations=supported_locations,
        )

    raise ValueError(f"Invalid SCHEDULE_MODULE: {spec!r}. Must be 'fl_csv'.")
