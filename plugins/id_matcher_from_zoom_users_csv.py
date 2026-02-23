"""ID to Email matcher using the Zoom Users CSV export."""

import contextlib
import logging as log

import pandas as pd


class Matcher:
    """Match employee IDs to emails using the Zoom Users CSV export."""

    def __init__(self, csv_file_path: str) -> None:
        """Initialize with the path to the Zoom Users CSV export."""
        self.csv_file_path = csv_file_path
        self.all_id_to_email_map = self._load_mapping()

    def _load_mapping(self) -> dict[str, str]:
        """Load the ID->email mapping from the CSV file."""
        log.debug(f"Loading ID to email mapping from {self.csv_file_path}")
        df = pd.read_csv(self.csv_file_path)

        df = df.dropna(subset=["Employee ID", "Email"])
        df["Employee ID"] = df["Employee ID"].astype(str).str.strip()
        df["Email"] = df["Email"].astype(str).str.strip()
        df = df[(df["Employee ID"] != "") & (df["Email"] != "")]

        df = df[~df["Employee ID"].str.contains("@", na=False)]
        df = df[df["Employee ID"].str.replace(".", "", regex=False).str.isdigit()]
        df["Employee ID"] = df["Employee ID"].astype(float).astype(int).astype(str).str.zfill(9)

        df = df[df["Email"].str.contains("@", na=False)]
        df = df[df["Email"] != ""]

        mapping = df.set_index("Employee ID")["Email"].to_dict()
        log.info(f"Loaded {len(mapping)} ID to email mappings")
        return mapping

    def _normalize_emp_id(self, emp_id: object) -> str:
        if emp_id is None:
            log.warning("Received None for EmployeeID, returning empty string")
            return ""
        s = str(emp_id).strip()
        if not s:
            log.warning("Employee ID is empty after stripping: %r", emp_id)
            return ""
        if s.replace(".", "", 1).isdigit():
            with contextlib.suppress(Exception):
                s = str(int(float(s)))
        if not s.isdigit():
            log.warning("Employee ID is not numeric after normalization: %r", emp_id)
            return ""
        return s.zfill(9)

    def match_id_to_email(self, emp_id: str) -> str:
        """Return the email for `emp_id`, or an empty string if not found."""
        normalized = self._normalize_emp_id(emp_id)
        if not normalized:
            log.warning("Could not normalize Employee ID %r, returning empty string", emp_id)
            return ""
        email = self.all_id_to_email_map.get(normalized, "")
        if not email:
            log.warning("Could not match id %s to an email", normalized)
        return email


__all__ = ["Matcher"]
