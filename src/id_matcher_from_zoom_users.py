import logging as log
import pandas as pd


class Matcher:
    """
    This module is designed to take the Zoom Users exported report under:
    Zoom Admin > Users > Export.
    The local path to this file is param 'csv_file_path'

    This is only one way of gathering this data, but you could also use the Zoom API,
    or a Peoplesoft report, etc.  Replace this module with your perferred method.
    """

    def __init__(self, csv_file_path: str) -> None:
        """
        Args:
            csv_file_path: Path to CSV file exported from Zoom Users report
        """
        self.csv_file_path = csv_file_path
        self.id_to_email_map = self._load_mapping()

    def _load_mapping(self) -> dict:
        """Load Employee ID to Email mapping from CSV file.

        Returns:
            Dictionary mapping Employee ID to Email
        """
        log.debug(f"Loading ID to email mapping from {self.csv_file_path}")
        df = pd.read_csv(self.csv_file_path)

        # Filter out rows with missing Employee ID or Email
        df = df.dropna(subset=["Employee ID", "Email"])

        # Convert to strings and strip whitespace
        df["Employee ID"] = df["Employee ID"].astype(str).str.strip()
        df["Email"] = df["Email"].astype(str).str.strip()

        # Filter out empty strings
        df = df[(df["Employee ID"] != "") & (df["Email"] != "")]

        # Filter out Employee IDs that contain "@" or are not numeric
        df = df[~df["Employee ID"].str.contains("@", na=False)]
        df = df[df["Employee ID"].str.replace(".", "", regex=False).str.isdigit()]

        # Convert to numeric and pad with zeros to 9 digits
        df["Employee ID"] = (
            df["Employee ID"].astype(float).astype(int).astype(str).str.zfill(9)
        )

        # Filter out invalid emails (must contain "@" and not be empty)
        df = df[df["Email"].str.contains("@", na=False)]
        df = df[df["Email"] != ""]

        # Create mapping dictionary
        mapping = df.set_index("Employee ID")["Email"].to_dict()

        log.info(f"Loaded {len(mapping)} ID to email mappings")
        return mapping

    def _normalize_emp_id(self, emp_id) -> str:
        if emp_id is None:
            return ""
        s = str(emp_id).strip()
        if not s:
            return ""
        # Handle common "123.0" shape from CSV/Excel casts
        if s.replace(".", "", 1).isdigit():
            try:
                s = str(int(float(s)))
            except Exception:
                pass
        if not s.isdigit():
            return ""
        return s.zfill(9)

    def match_id_to_email(self, emp_id: str) -> str:
        """Match a single Employee ID to an email."""
        normalized = self._normalize_emp_id(emp_id)
        if not normalized:
            return ""
        email = self.id_to_email_map.get(normalized, "")
        if not email:
            log.warning("Could not match id %s to an email", normalized)
        return email
