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

        # Create mapping, filtering out rows with missing Employee ID
        mapping = {}
        for _, row in df.iterrows():
            emp_id = row.get("Employee ID")
            email = row.get("Email")

            if pd.notna(emp_id) and pd.notna(email):
                try:
                    # Convert to string and remove any whitespace
                    # Handle cases where emp_id might already be a string or contain non-numeric data
                    emp_id_str = str(emp_id).strip()

                    # Skip if it looks like an email or is not numeric
                    if "@" in emp_id_str or not emp_id_str.replace(".", "").isdigit():
                        continue

                    # Pad with zeros to 9 digits if needed
                    emp_id_str = str(int(float(emp_id_str))).zfill(9)
                    email_str = str(email).strip()
                    mapping[emp_id_str] = email_str
                except (ValueError, TypeError) as e:
                    log.error(f"Skipping invalid Employee ID: {emp_id}")
                    continue

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
