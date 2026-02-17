"""This module uses an Active Directory saved query to match Employee IDs to email addresses."""

import json
import logging as log
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AD_JSON_PATH = REPO_ROOT / "id_and_emails_from_ad.json"


class Matcher:
    """Class to match Employee IDs to email addresses using Active Directory saved file."""

    def __init__(self) -> None:
        """Initialize the Matcher."""

        self._id_to_email: dict[str, str] | None = None
        self._load_all_id_and_email_map()

    def _load_all_id_and_email_map(self) -> None:

        with AD_JSON_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            log.error("Failed to retrieve data from Active Directory")
            self._id_to_email = {}
            return

        # Convert list of dicts to single dict for O(1) lookups
        self._id_to_email = {}
        for item in data:
            if isinstance(item, dict) and "EmployeeID" in item and "EmailAddress" in item:
                emp_id = str(item["EmployeeID"]).strip()
                email = str(item["EmailAddress"]).strip()
                if emp_id and email:
                    self._id_to_email[emp_id] = email

        log.info(f"Successfully loaded {len(self._id_to_email)} Employee ID to email mappings")
        return

    def match_id_to_email(self, id: str) -> str:
        """Maps a single Employee ID to an email address.

        Args:
            id: The Employee ID to look up.

        Returns:
            str: The email address corresponding to the Employee ID, or an empty string if not found.
        """
        if id is None:
            log.debug("Provided Employee ID is None, returning empty string")
            return ""

        id = str(id).strip()
        if not id:
            log.debug("Provided Employee ID is empty after stripping, returning empty string")
            return ""

        if self._id_to_email is not None and id in self._id_to_email:
            log.debug(f"Cache hit for ID {id}")
            return self._id_to_email[id]

        log.warning(f"No email found for Employee ID: {id}")
        return ""
