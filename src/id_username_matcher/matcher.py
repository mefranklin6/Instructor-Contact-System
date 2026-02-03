import logging as log
import pandas as pd


class Matcher:

    def __init__(self, csv_file_path: str) -> None:
        """Initialize matcher with CSV file containing Employee ID to Email mapping.

        Args:
            csv_file_path: Path to CSV file with 'Employee ID' and 'Email' columns
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

    def match_id_to_email(self, emp_id: str) -> str:
        """Match a single Employee ID to an email.

        Args:
            emp_id: Employee ID to match

        Returns:
            Corresponding email if found, else None
        """
        return self.id_to_email_map.get(emp_id, "")
