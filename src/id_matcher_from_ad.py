"""This module uses Active Directory to match Employee IDs to email addresses."""

import asyncio
import json
import logging as log
import subprocess


class Matcher:
    """Class to match Employee IDs to email addresses using Active Directory."""

    def __init__(self) -> None:
        """Initialize the Matcher with PowerShell queries for Active Directory."""

        self._all_data = asyncio.run(self._load_all_id_and_email_map())

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

    def _pwsh_query(self, query, return_type) -> object:
        """Execute a PowerShell query and return the result.

        Args:
            query (str): The PowerShell query to execute.
            return_type (str): The expected return type ("dict" or "str").

        Returns:
            dict | str: The result of the PowerShell query, either as a dictionary or a string.
        """
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
        )
        if result.returncode != 0:
            log.error(f"PowerShell command failed: {result.stderr}")
            if return_type == "dict":
                return {}
            else:
                return ""
        if return_type == "dict":
            stdout = (result.stdout or "").strip()
            if not stdout:
                return {}
            try:
                return json.loads(stdout)
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse JSON from PowerShell output: {e}")
                log.debug(f"Raw PowerShell stdout: {stdout}")
                return {}
        return result.stdout.strip()

    async def _load_all_id_and_email_map(self) -> dict[str, str]:
        """Query Active Directory for all Employee IDs and their corresponding email addresses.

        Note: Very expensive
        """
        data = self._pwsh_query(self.all_query, "dict")
        if not isinstance(data, dict):
            log.error("Expected a dictionary from PowerShell query, got something else")
            return {}
        return data

    def match_id_to_email(self, id: str) -> str:
        """Maps a single Employee ID to an email address.

        Args:
            id (str): The Employee ID to look up.

        Returns:
            str: The email address corresponding to the Employee ID, or an empty string if an error occurs.
        """
        if id is None:
            return ""
        id = str(id).strip()
        if not id:
            return ""

        safe_id = id.replace('"', '""')

        if self._all_data:  # Use cached values if we have them
            result = self._all_data.get(safe_id, "")
            if result:
                log.debug(f"Cache hit for ID {safe_id}, returning cached email")
                return result

        # If we don't have cached values or had a cache miss, do a single query
        log.debug(f"No cache or cache miss for ID {safe_id}, performing single query")
        result = self._pwsh_query(self.single_query.format(id=safe_id), "str")
        if isinstance(result, str):
            log.debug(f"Single query result for ID {safe_id}: {result}")
            return result
        else:
            log.warning(f"Single query for ID {safe_id} did not return a string result")
            return ""


if __name__ == "__main__":
    matcher = Matcher()
    print(matcher._load_all_id_and_email_map())
    print(matcher.match_id_to_email("004755830"))
