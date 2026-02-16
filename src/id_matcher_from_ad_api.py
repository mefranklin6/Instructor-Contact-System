"""This module uses Active Directory to match Employee IDs to email addresses."""

import json
import logging as log
import subprocess


class Matcher:
    """Class to match Employee IDs to email addresses using Active Directory."""

    def __init__(self, lazy_load: bool = True) -> None:
        """Initialize the Matcher with PowerShell queries for Active Directory.

        Args:
            lazy_load: If True, delays loading AD data until first access.
                      If False, loads all data immediately at initialization.
        """

        self.all_query = (
            "Get-ADUser -Filter 'Enabled -eq $true' "
            "-Properties EmployeeID, EmailAddress | "
            "Where-Object { -not [string]::IsNullOrWhiteSpace($_.EmployeeID) -and $_.EmailAddress -and "
            "$_.EmailAddress -match '@' } | "
            "Select-Object @{Name='EmployeeID'; Expression={$_.EmployeeID}}, "
            "@{Name='EmailAddress'; Expression={$_.EmailAddress}} | "
            "ConvertTo-Json -Depth 3"
        )

        self.single_query = (
            "Get-ADUser -Filter 'Enabled -eq $true -and EmployeeID -eq \"{id}\"' "
            "-Properties EmployeeID, EmailAddress | "
            "Where-Object {{ -not [string]::IsNullOrWhiteSpace($_.EmployeeID) -and "
            "-not [string]::IsNullOrWhiteSpace($_.EmailAddress) -and $_.EmailAddress -match '@' }} | "
            "Select-Object -ExpandProperty EmailAddress"
        )

        self._id_to_email: dict[str, str] | None = None

        if not lazy_load:
            # Eagerly load data at initialization
            self.load_all_id_and_email_map()

    @property
    def id_to_email_map(self) -> dict[str, str]:
        """Get the cached mapping of Employee IDs to email addresses.

        Lazily loads the data on first access if not already loaded.

        Returns:
            dict[str, str]: A dictionary mapping Employee IDs to email addresses.
        """
        if self._id_to_email is None:
            log.info("ID to email mapping not loaded yet, loading from Active Directory...")
            self.load_all_id_and_email_map()
        return self._id_to_email or {}

    def _pwsh_query(self, query: str, return_type: str) -> list | str:
        """Execute a PowerShell query and return the result.

        Args:
            query: The PowerShell query to execute.
            return_type: The expected return type ("list" or "str").

        Returns:
            list | str: The result of the PowerShell query, either as a list or a string.
        """
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    query,
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for large AD queries
            )
        except subprocess.TimeoutExpired:
            log.error("PowerShell query timed out after 300 seconds")
            return [] if return_type == "list" else ""
        except Exception as e:
            log.error(f"Failed to execute PowerShell query: {e}")
            return [] if return_type == "list" else ""

        if result.returncode != 0:
            log.error(f"PowerShell command failed with return code {result.returncode}: {result.stderr}")
            return [] if return_type == "list" else ""

        if return_type == "list":
            stdout = (result.stdout or "").strip()
            if not stdout:
                log.warning("PowerShell returned empty output for list query")
                return []
            try:
                parsed = json.loads(stdout)
                # Handle single object case - PowerShell returns object instead of array
                if isinstance(parsed, dict):
                    return [parsed]
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse JSON from PowerShell output: {e}")
                log.debug(f"Raw PowerShell stdout: {stdout[:500]}")  # Log first 500 chars
                return []

        return result.stdout.strip()

    def load_all_id_and_email_map(self) -> None:
        """Query Active Directory for all Employee IDs and their corresponding email addresses.

        Stores the results as a dictionary for O(1) lookup performance.
        Note: This operation can be expensive for large Active Directory environments.
        """
        log.info("Querying Active Directory for all Employee IDs and email addresses...")
        data = self._pwsh_query(self.all_query, "list")

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
            return ""

        id = str(id).strip()
        if not id:
            return ""

        # Check cached dictionary first (O(1) lookup)
        if self._id_to_email is not None and id in self._id_to_email:
            log.debug(f"Cache hit for ID {id}")
            return self._id_to_email[id]

        # If cache miss or not loaded, perform single query
        safe_id = id.replace('"', '""')
        log.debug(f"Cache miss for ID {id}, performing single AD query")

        result = self._pwsh_query(self.single_query.format(id=safe_id), "str")

        if result and isinstance(result, str):
            # Add to cache for future lookups
            if self._id_to_email is None:
                self._id_to_email = {}
            self._id_to_email[id] = result
            log.debug(f"Single query result for ID {id}: {result}")
            return result

        log.warning(f"No email found for Employee ID: {id}")
        return ""


if __name__ == "__main__":
    # Example 1: Lazy loading (default) - data loaded on first access
    matcher = Matcher()
    print("Matcher initialized with lazy loading")
    print(f"Email for 004755830: {matcher.match_id_to_email('004755830')}")

    # Example 2: Eager loading - loads all data at initialization
    # matcher = Matcher(lazy_load=False)
    # print(f"Loaded {len(matcher.id_to_email_map)} mappings at initialization")
