"""Plugin factories for bundled implementations.

Each `*_module` setting must be a short key for a bundled implementation
(e.g. `zoom_csv`, `fl_csv`, `chico`).

Bundled implementations live in the optional `ics_bundled_plugins` package.
To add support for a new data source, submit a PR.
"""

import importlib
import logging as log
import os
from typing import Any

from src.core.settings import Settings


def _bundled_import(module_name: str) -> Any:
    """Import a module from the optional `ics_bundled_plugins` package.

    Raises a clear error if the bundled plugins package is not available.
    """

    try:
        return importlib.import_module(f"ics_bundled_plugins.{module_name}")
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "Bundled plugin implementations are not installed/available. "
            "Please ensure the ics_bundled_plugins package is present."
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

        parser = slp.SupportedLocationsParser(settings.supported_locations_file_path)
        return parser.run()

    raise ValueError(f"Invalid SUPPORTED_LOCATIONS_MODE: {spec!r}. Must be 'none' or 'chico'.")


def create_id_matcher(*, settings: Settings, in_docker: bool) -> Any:
    """Create the ID->email matcher module."""

    spec = settings.id_to_email_module

    if not spec:
        raise ValueError("ID_TO_EMAIL_MODULE is required")

    if spec == "zoom_csv":
        id_matcher_from_zoom_users = _bundled_import("id_matcher_from_zoom_users")

        if not settings.zoom_csv_path:
            raise FileNotFoundError("No ZOOM_CSV_PATH found. This is a required file for Zoom CSV mode")
        return id_matcher_from_zoom_users.Matcher(csv_file_path=settings.zoom_csv_path)

    if spec == "ad_api":
        if in_docker:
            raise RuntimeError("Active Directory module is not supported while in Docker")
        id_matcher_from_ad_api = _bundled_import("id_matcher_from_ad_api")
        return id_matcher_from_ad_api.Matcher()

    if spec == "ad_json":
        # Convenience: on Windows workstation (not Docker), auto-generate the json if missing.
        if not in_docker and not os.path.exists("id_and_emails_from_ad.json"):
            script_path = os.path.join("scripts", "query_ad.ps1")
            if os.path.exists(script_path):
                try:
                    import subprocess

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
                        log.warning(f"AD query stderr:\n{result.stderr}")
                except Exception:
                    # Keep the original behavior: if generation fails, the missing-file error below triggers.
                    log.exception("AD query script failed")

        if not os.path.exists("id_and_emails_from_ad.json"):
            raise FileNotFoundError(
                "No id_and_emails_from_ad.json found. "
                "Please run scripts/query_ad.ps1 first to generate this file"
            )

        id_matcher_from_ad_json = _bundled_import("id_matcher_from_ad_json")
        return id_matcher_from_ad_json.Matcher()

    raise ValueError(f"Invalid ID_TO_EMAIL_MODULE: {spec!r}. Must be 'zoom_csv', 'ad_api', or 'ad_json'.")


def create_schedule_loader(*, settings: Settings, supported_locations: Any | None) -> Any:
    """Create the schedule data loader."""

    spec = settings.schedule_module

    if not spec or spec == "none":
        raise ValueError("SCHEDULE_MODULE is required")

    if spec == "fl_csv":
        schedule = _bundled_import("fl_data_loader")

        if not settings.fl_file_path:
            raise FileNotFoundError("No FL_FILE_PATH found. This is a required file for fl_csv mode")

        return schedule.DataLoader(
            fl_file_path=settings.fl_file_path,
            supported_locations=supported_locations,
        )

    raise ValueError(f"Invalid SCHEDULE_MODULE: {spec!r}. Must be 'fl_csv'.")
