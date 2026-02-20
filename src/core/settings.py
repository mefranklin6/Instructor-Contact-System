"""Application configuration parsed from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings for selecting modules and file paths."""

    supported_locations_mode: str
    id_to_email_module: str
    schedule_module: str
    dev_mode: bool

    # Optional file paths used by specific modes
    zoom_csv_path: str | None
    fl_file_path: str | None
    supported_locations_file_path: str | None

    @staticmethod
    def from_env() -> Settings:
        """Create settings from environment variables."""
        supported_locations_mode = os.getenv("SUPPORTED_LOCATIONS_MODE", "none").lower()
        id_to_email_module = os.getenv("ID_TO_EMAIL_MODULE", "none").lower()
        schedule_module = os.getenv("SCHEDULE_MODULE", "none").lower()
        dev_mode = os.getenv("DEV_MODE", "true").lower() == "true"  # return bool true if string is 'true'

        return Settings(
            supported_locations_mode=supported_locations_mode,
            id_to_email_module=id_to_email_module,
            schedule_module=schedule_module,
            dev_mode=dev_mode,
            zoom_csv_path=os.getenv("ZOOM_CSV_PATH"),
            fl_file_path=os.getenv("FL_FILE_PATH"),
            supported_locations_file_path=os.getenv("SUPPORTED_LOCATIONS_FILE_PATH"),
        )
