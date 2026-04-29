"""Active Directory saved JSON matcher for EmployeeID -> EmailAddress."""

import json
import logging as log
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AD_JSON_PATH = REPO_ROOT / "id_and_emails_from_ad.json"


class Matcher:
    """Match Employee IDs to emails using a saved AD JSON export."""

    def __init__(self) -> None:
        """Initialize and load the mapping into memory."""
        self._id_to_email: dict[str, str] | None = None
        self._load_all_id_and_email_map()

    @staticmethod
    def _normalize_employee_id(employee_id: object) -> str:
        """Normalize an EmployeeID to a 9-digit, zero-padded string when numeric."""
        if employee_id is None:
            log.warning("Received None for EmployeeID, returning empty string")
            return ""

        value = str(employee_id).strip()
        if not value:
            log.warning("Received empty string for EmployeeID, returning empty string")
            return ""

        return value.zfill(9) if value.isdigit() else value

    def _load_all_id_and_email_map(self) -> None:
        with AD_JSON_PATH.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)

        if not isinstance(data, list):
            log.error("Failed to retrieve data from Active Directory")
            self._id_to_email = {}
            return

        self._id_to_email = {}
        for item in data:
            if isinstance(item, dict) and "EmployeeID" in item and "EmailAddress" in item:
                emp_id = self._normalize_employee_id(item["EmployeeID"])
                email = str(item["EmailAddress"]).strip()
                if emp_id and email:
                    self._id_to_email[emp_id] = email

        log.info(f"Successfully loaded {len(self._id_to_email)} Employee ID to email mappings")

    def match_id_to_email(self, id: str | None) -> str:
        """Return the email for `id`, or an empty string if not found."""
        normalized_id = self._normalize_employee_id(id)
        if not normalized_id:
            log.warning("Received empty or invalid EmployeeID, returning empty string")
            return ""

        if self._id_to_email is not None and normalized_id in self._id_to_email:
            return self._id_to_email[normalized_id]

        log.warning("No email found for Employee ID: *redacted*")
        return ""


__all__ = ["Matcher"]
