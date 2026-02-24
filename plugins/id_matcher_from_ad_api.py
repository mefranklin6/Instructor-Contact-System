"""Active Directory API matcher for EmployeeID -> EmailAddress."""

from enum import Enum, auto
import json
import logging as log
import subprocess


class Matcher:
    """Match Employee IDs to email addresses using PowerShell AD queries."""

    def __init__(self) -> None:
        """Initialize and cache the full mapping from Active Directory."""
        self.all_query = (
            'Get-ADUser -Filter \'Enabled -eq $true -and EmployeeID -like "*" -and '
            'EmailAddress -like "*@*" -and EmailAddress -notlike "*-admin*"\' '
            "-Properties EmployeeID, EmailAddress -ResultPageSize 2000 | "
            "Select-Object @{Name='EmployeeID'; Expression={$_.EmployeeID}}, "
            "@{Name='EmailAddress'; Expression={$_.EmailAddress}} | "
            "ConvertTo-Json -Depth 3"
        )

        self.single_query = (
            'Get-ADUser -Filter \'Enabled -eq $true -and EmployeeID -eq "{id}" -and '
            'EmailAddress -like "*@*" -and EmailAddress -notlike "*-admin*"\' '
            "-Properties EmployeeID, EmailAddress | "
            "Select-Object -ExpandProperty EmailAddress"
        )

        self._id_to_email: dict[str, str] | None = None
        self._load_all_id_and_email_map()

    class ReturnType(Enum):
        """Return types for PowerShell queries."""

        LIST = auto()
        STRING = auto()

    @staticmethod
    def _normalize_employee_id(employee_id: object) -> str:
        """Normalize an EmployeeID to a 9-digit, zero-padded string when numeric."""
        if employee_id is None:
            log.info("Received None for EmployeeID, returning empty string")
            return ""

        value = str(employee_id).strip()
        if not value:
            log.info("Received empty string for EmployeeID, returning empty string")
            return ""

        return value.zfill(9) if value.isdigit() else value

    def _pwsh_query(self, query: str, return_type: ReturnType) -> list[dict[str, str]] | str:
        """Execute a PowerShell query and return the parsed output."""
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
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            log.error("PowerShell query timed out")
            raise
        except Exception as e:
            log.error(f"Failed to execute PowerShell query: {e}")
            raise
        if result.returncode != 0:
            log.error(f"PowerShell command failed with return code {result.returncode}: {result.stderr}")
            raise

        if return_type == self.ReturnType.LIST:
            stdout = (result.stdout or "").strip()
            if not stdout:
                log.warning("PowerShell returned empty output for list query")
                return []
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    return [parsed]
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse JSON from PowerShell output: {e}")
                log.debug(f"Raw PowerShell stdout: {stdout[:500]}")
                raise

        return (result.stdout or "").strip()

    def _load_all_id_and_email_map(self) -> None:
        """Load all EmployeeID->EmailAddress pairs into a dict cache."""
        log.info("Querying Active Directory for all Employee IDs and email addresses...")
        data = self._pwsh_query(self.all_query, self.ReturnType.LIST)

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
            else:
                log.error("Error validating all_id_and_email_map while loading")

        log.info(f"Successfully loaded {len(self._id_to_email)} Employee ID to email mappings")

    def match_id_to_email(self, id: str) -> str:
        """Return the email for `id`, or an empty string if not found."""
        normalized_id = self._normalize_employee_id(id)
        if not normalized_id:
            return ""

        if self._id_to_email is not None and normalized_id in self._id_to_email:
            return self._id_to_email[normalized_id]

        safe_id = normalized_id.replace('"', '""')
        result = self._pwsh_query(self.single_query.format(id=safe_id), self.ReturnType.STRING)

        if result and isinstance(result, str):
            result = next((line.strip() for line in result.splitlines() if line.strip()), "")
            if not result:
                log.warning("No email found for EmployeeID *redacted* in single query")
                return ""
            if self._id_to_email is None:
                self._id_to_email = {}
            self._id_to_email[normalized_id] = result
            return result

        log.warning("PowerShell query returned no valid email for EmployeeID *redacted*")
        return ""


__all__ = ["Matcher"]
