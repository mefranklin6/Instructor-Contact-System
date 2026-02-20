"""Core app orchestration (no UI dependencies).

This module owns data loading/aggregation, ID->email matching, contact history,
and email sending. UI layers should depend on this module, not vice-versa.
"""

from dataclasses import dataclass
from datetime import datetime
import json
import logging as log
import os
from typing import Any

import pandas as pd

from core.system_plugins import (
    create_id_matcher,
    create_schedule_loader,
    create_supported_locations,
)
from src import email_sender
from src.core.schedule_aggregator import Aggregator
from src.core.settings import Settings

MAX_FAILED_DISPLAY_DEFAULT = 50


@dataclass(frozen=True, slots=True)
class ClassroomSendResult:
    """Summary of sending a classroom message."""

    location_key: str
    sent: int
    failed: list[str]


@dataclass(frozen=True, slots=True)
class DeploymentResult:
    """Summary of a start-of-semester deployment batch."""

    contacted_this_batch: int
    total_contacted: int
    remaining: int
    failed: list[str]
    total_instructors: int


class InstructorContactSystemCore:
    """Core system orchestrator.

    Owns data loading, aggregation, ID->email matching, contact history, and email sending.
    Contains no UI framework dependencies.
    """

    def __init__(
        self,
        *,
        in_docker: bool,
        settings: Settings | None = None,
        max_failed_display: int = MAX_FAILED_DISPLAY_DEFAULT,
    ) -> None:
        """Initialize core services and load the current semester schedule."""
        self.in_docker = in_docker
        self.settings = settings or Settings.from_env()
        self.max_failed_display = max_failed_display

        self.supported_locations: Any | None = None
        self.loader: Any | None = None
        self.aggregator: Any | None = None
        self.id_matcher: Any | None = None
        self.email_sender: Any | None = None

        self.contact_by_instructor: dict[str, list[str]] = {}
        self.contact_by_location: dict[str, list[str]] = {}
        self.contacted_instructors: dict[str, Any] = {}
        self.df: pd.DataFrame = pd.DataFrame()

        if self.in_docker:
            log.info("Running in Docker")
            data_dir = "/data"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
                log.info(f"Created data directory: {data_dir}")
        else:
            log.info("Not running in Docker")

        self._initialize_data()

    # ---------- Configuration-dependent module init ----------

    def _initialize_plugins(self) -> None:
        """Initialize supported locations, ID matcher, and schedule loader via plugin layer."""
        self.supported_locations = create_supported_locations(settings=self.settings)
        self.id_matcher = create_id_matcher(settings=self.settings, in_docker=self.in_docker)
        self.loader = create_schedule_loader(
            settings=self.settings,
            supported_locations=self.supported_locations,
        )

    def _initialize_aggregator_module(self) -> None:
        if self.df is None or self.df.empty:
            raise FileNotFoundError("Could not initialize aggregator module. self.df is empty or missing")

        self.aggregator = Aggregator(df=self.df)
        self.contact_by_instructor = self.aggregator.by_instructor()
        self.contact_by_location = self.aggregator.by_location()

    def _initialize_data(self) -> None:
        current_date = datetime.now()

        self._initialize_plugins()

        self.email_sender = email_sender.EmailSender(armed=not self.settings.dev_mode)

        if not self.loader:
            raise ModuleNotFoundError("Required module 'loader' missing")

        df = self.loader.semester_data(current_date)
        if df is None:
            raise ValueError("semester_data returned None; cannot continue without schedule data")
        self.df = df

        self._initialize_aggregator_module()
        log.info("Data initialization successful")

    # ---------- Shared helpers ----------

    def get_contact_file_path(self) -> str:
        """Return the contact history JSON path for the current runtime."""
        if self.in_docker:
            return "/data/contact_history.json"
        return "contact_history.json"

    @staticmethod
    def dedupe_emails(emails: list[str]) -> list[str]:
        """Remove duplicate emails while preserving order."""
        seen: set[str] = set()
        return [e for e in emails if not (e in seen or seen.add(e))]

    def get_aggregated_data_for_date_range(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> tuple[dict, dict]:
        """Return instructor/location maps for a date range (or current semester)."""
        if not self.loader:
            raise ModuleNotFoundError("Data loader module is not configured")

        if start_date is not None and end_date is not None:
            df = self.loader.range_data(start_date, end_date)
        else:
            df = self.loader.semester_data(datetime.now())

        if df is None or df.empty:
            raise ValueError("No data available for the specified date range")

        temp_aggregator = Aggregator(df=df)
        return temp_aggregator.by_instructor(), temp_aggregator.by_location()

    # ---------- Contact history ----------

    def load_contact_history(self) -> None:
        """Load contact history JSON into memory (if present)."""
        contact_file = self.get_contact_file_path()
        if os.path.exists(contact_file):
            with open(contact_file, encoding="utf-8-sig") as f:
                self.contacted_instructors = json.load(f)
        else:
            self.contacted_instructors = {}

    def save_contact_history(self) -> None:
        """Persist contact history JSON to disk."""
        contact_file = self.get_contact_file_path()
        with open(contact_file, "w", encoding="utf-8") as f:
            json.dump(self.contacted_instructors, f, indent=2)

    def get_contact_history_dict(self) -> dict:
        """Return contact history as a dict, reloading from disk first."""
        self.load_contact_history()
        return self.contacted_instructors

    def get_already_contacted_count(self) -> int:
        """Count instructors contacted for 'start of semester' deployment only."""
        self.load_contact_history()
        return sum(
            1
            for info in self.contacted_instructors.values()
            if isinstance(info, dict) and info.get("contact_type") == "start of semester"
        )

    # ---------- Diagnostics / email ----------

    def get_server_diagnostics(self, *, logging_level: str) -> str:
        """Gather server diagnostic information for test emails."""
        try:
            import platform
            import sys

            def runtime_impl(obj) -> str:
                if obj is None:
                    return "Not initialized"
                return f"{type(obj).__module__}.{type(obj).__name__}"

            def runtime_value_summary(obj) -> str:
                if obj is None:
                    return "Not initialized"
                if isinstance(obj, dict):
                    return f"dict (len={len(obj)})"
                if isinstance(obj, list):
                    return f"list (len={len(obj)})"
                if isinstance(obj, set):
                    return f"set (len={len(obj)})"
                return type(obj).__name__

            def get_file_mod_time(file_path: str | None) -> str:
                if not file_path:
                    return "Not configured"
                if not os.path.exists(file_path):
                    return "File not found"
                mod_time = os.path.getmtime(file_path)
                return datetime.fromtimestamp(mod_time).isoformat()

            def get_file_size_bytes(file_path: str | None) -> str:
                if not file_path:
                    return "Not configured"
                if not os.path.exists(file_path):
                    return "File not found"
                return str(os.path.getsize(file_path))

            def get_json_record_count(file_path: str | None) -> str:
                if not file_path:
                    return "Not configured"
                if not os.path.exists(file_path):
                    return "File not found"
                try:
                    with open(file_path, encoding="utf-8-sig") as f:
                        payload = json.load(f)
                    if isinstance(payload, dict):
                        return str(len(payload))
                    if isinstance(payload, list):
                        return str(len(payload))
                    return "Unknown"
                except Exception as e:
                    return f"Error: {e}"

            generated = datetime.now().isoformat()

            schedule_file_path = (
                self.settings.fl_file_path if self.settings.schedule_module == "fl_csv" else None
            )

            id_to_email_file_path: str | None = None
            if self.settings.id_to_email_module == "zoom_csv":
                id_to_email_file_path = self.settings.zoom_csv_path
            elif self.settings.id_to_email_module == "ad_json":
                id_to_email_file_path = "id_and_emails_from_ad.json"

            supported_locations_file_path = (
                self.settings.supported_locations_file_path
                if self.settings.supported_locations_mode == "chico"
                else None
            )

            supported_locations_summary = runtime_value_summary(self.supported_locations)
            loader_impl = runtime_impl(self.loader)
            aggregator_impl = runtime_impl(self.aggregator)

            id_matcher_impl = runtime_impl(getattr(self, "id_matcher", None))
            email_sender_impl = runtime_impl(getattr(self, "email_sender", None))

            diagnostics = f"""Server Diagnostics Report
Generated: {generated}

System Information:
- Platform: {platform.system()} {platform.release()}
- Python Version: {sys.version}
- Running in Docker: {self.in_docker}

Application Status:
- DEV_MODE: {self.settings.dev_mode}
- Logging Level: {logging_level}

Configured Modes:
- Supported Locations Mode: {self.settings.supported_locations_mode}
- ID to Email Mode: {self.settings.id_to_email_module}
- Schedule Module: {self.settings.schedule_module}

Runtime Implementations:
- Email Sender: {email_sender_impl}
- ID Matcher: {id_matcher_impl}
- Supported Locations Data: {supported_locations_summary}
- Schedule Loader: {loader_impl}
- Aggregator: {aggregator_impl}

Data Status:
- Total Instructors: {len(self.contact_by_instructor)}
- Total Locations: {len(self.contact_by_location)}
- Contacted Instructors (start of semester): {self.get_already_contacted_count()}

Files:
- Contact History: {self.get_contact_file_path()} ({get_file_mod_time(self.get_contact_file_path())})
"""

            if schedule_file_path is not None or self.settings.schedule_module == "fl_csv":
                diagnostics += (
                    f"- Schedule File (FL): {schedule_file_path or 'Not configured'} "
                    f"({get_file_mod_time(schedule_file_path)})\n"
                )

            if self.settings.id_to_email_module == "ad_api":
                diagnostics += "- ID to Email Source: Active Directory API (no local file)\n"
            else:
                diagnostics += (
                    f"- ID to Email File: {id_to_email_file_path or 'Not configured'} "
                    f"({get_file_mod_time(id_to_email_file_path)})\n"
                )

            if self.settings.id_to_email_module == "ad_json":
                diagnostics += (
                    f"- ID to Email File Size (bytes): {get_file_size_bytes(id_to_email_file_path)}\n"
                    f"- ID to Email File Records: {get_json_record_count(id_to_email_file_path)}\n"
                )

            if self.settings.supported_locations_mode == "chico":
                diagnostics += (
                    f"- Supported Locations File: {supported_locations_file_path or 'Not configured'} "
                    f"({get_file_mod_time(supported_locations_file_path)})\n"
                )
            else:
                diagnostics += "- Supported Locations File: Not used in this mode\n"

            diagnostics += "\nThis is an automated test email from the Instructor Contact System.\n"
            return diagnostics
        except Exception as e:
            log.error(f"Error gathering diagnostics: {e}")
            return f"Error gathering diagnostics: {e}"

    def send_test_email(self, *, email: str, logging_level: str) -> str:
        """Send or log a diagnostic test email (depends on DEV_MODE)."""
        if not email or "@" not in email:
            raise ValueError("Please enter a valid email address")

        subject = "Instructor Contact System - Test Email"
        message = self.get_server_diagnostics(logging_level=logging_level)

        if not self.settings.dev_mode and self.email_sender:
            success = bool(self.email_sender.send(email, subject, message))
            if not success:
                raise RuntimeError("Failed to send test email")
            log.info(f"Test email sent to {email}")
            return f"Test email sent successfully to {email}"

        log.warning(f"DEV MODE: Would have sent test email to {email}")
        log.warning(f"Subject: {subject}")
        log.warning(f"Message:\n{message}")
        return f"DEV MODE: Test email logged (not sent) for {email}"

    # ---------- Core actions used by the UI ----------

    def lookup_classroom_emails(
        self,
        *,
        building: str,
        room: str,
        location_map: dict | None = None,
    ) -> list[str]:
        """Return instructor emails for a building/room."""

        if not self.id_matcher:
            raise RuntimeError("ID matcher module is not configured")

        location_key = f"{building.upper()} {room.upper()}"
        location_map = location_map or self.contact_by_location
        if location_key not in location_map:
            raise KeyError(f"No classes found in {location_key}")

        emp_ids = location_map[location_key]
        emails: list[str] = []
        for emp_id in emp_ids:
            email = self.id_matcher.match_id_to_email(emp_id)
            if email:
                emails.append(email)
        if not emails:
            raise ValueError("No email matches found for instructors in this location")
        return emails

    def lookup_instructor_locations(self, *, email: str) -> list[str]:
        """Return classroom locations for an instructor email."""

        if not self.id_matcher:
            raise RuntimeError("ID matcher module is not configured")

        target_email = (email or "").strip().lower()
        if not target_email:
            raise ValueError("Please enter an email")

        emp_id: str | None = None
        for eid in self.contact_by_instructor:
            matched_email = (self.id_matcher.match_id_to_email(eid) or "").strip().lower()
            if matched_email == target_email:
                emp_id = eid
                break

        if not emp_id or emp_id not in self.contact_by_instructor:
            raise KeyError(f"No classes found for {email}")

        return self.contact_by_instructor[emp_id]

    def send_message_to_classroom(
        self,
        *,
        building: str,
        room: str,
        subject: str,
        message_template: str,
        location_map: dict | None = None,
    ) -> ClassroomSendResult:
        """Send a message to all instructors scheduled in a classroom."""
        if not self.id_matcher or not self.email_sender:
            raise RuntimeError("ID matcher and or email sender module is not configured")

        location_key = f"{building.upper()} {room.upper()}"
        location_map = location_map or self.contact_by_location
        if location_key not in location_map:
            raise KeyError(f"No classes found in {location_key}")

        emp_ids = location_map[location_key]
        emails: list[str] = []
        for emp_id in emp_ids:
            email = self.id_matcher.match_id_to_email(emp_id)
            if email:
                emails.append(email)

        emails = self.dedupe_emails(emails)
        if not emails:
            raise ValueError("No email matches found for instructors in this location")

        try:
            message = message_template.format(location=location_key)
        except KeyError as ke:
            raise ValueError(f"Missing placeholder in message: {ke}") from ke

        sent_count = 0
        failed: list[str] = []

        self.load_contact_history()

        if not self.settings.dev_mode:
            for email in emails:
                ok = False
                try:
                    ok = bool(self.email_sender.send(email, subject, message))
                    log.info(f"Sent: {email}, subject: {subject}, message: {message}")
                except Exception as e:
                    log.error(f"Email send failed to {email}: {e}")

                if ok:
                    existing = self.contacted_instructors.get(email, {})
                    if not isinstance(existing, dict):
                        existing = {}
                    history = existing.get("classroom_messages", [])
                    if not isinstance(history, list):
                        history = []
                    history.append(
                        {
                            "sent_at": datetime.now().isoformat(),
                            "locations": location_key,
                            "contact_type": "all instructors for classroom",
                            "message": message,
                        }
                    )
                    existing["classroom_messages"] = history
                    self.contacted_instructors[email] = existing
                    sent_count += 1
                else:
                    failed.append(email)
        else:
            log.info(f"DEV MODE: Would have sent messages to {emails}")

        if not self.settings.dev_mode:
            self.save_contact_history()

        return ClassroomSendResult(location_key=location_key, sent=sent_count, failed=failed)

    def compute_semester_deployment_candidates(self) -> list[dict[str, Any]]:
        """Return instructors that have not yet been contacted this semester."""
        self.load_contact_history()

        if not self.id_matcher or not self.email_sender:
            raise RuntimeError("ID matcher and or email sender module is not configured")

        all_instructors: list[dict[str, Any]] = []
        for emp_id in self.contact_by_instructor:
            email = self.id_matcher.match_id_to_email(emp_id)
            if not email:
                continue
            # Only skip if already contacted for "start of semester" specifically.
            # Instructors contacted via classroom messages should still be candidates.
            existing = self.contacted_instructors.get(email)
            if isinstance(existing, dict) and existing.get("contact_type") == "start of semester":
                continue
            all_instructors.append(
                {
                    "email": email,
                    "emp_id": emp_id,
                    "locations": self.contact_by_instructor[emp_id],
                    "contacted": False,
                }
            )
        return all_instructors

    def execute_deployment(
        self,
        *,
        instructors: list[dict[str, Any]],
        message_template: str,
        batch_size: int,
        subject: str,
    ) -> DeploymentResult:
        """Send a start-of-semester batch and update contact history."""
        batch_count = 0
        failed: list[str] = []

        if not self.id_matcher or not self.email_sender:
            raise RuntimeError("ID matcher and or email sender module is not configured")

        for instructor in instructors[:batch_size]:
            existing = self.contacted_instructors.get(instructor["email"])
            already_semester = (
                isinstance(existing, dict) and existing.get("contact_type") == "start of semester"
            )
            if not already_semester:
                locations_str = ", ".join(instructor["locations"])
                try:
                    message = message_template.format(locations=locations_str)
                except KeyError as ke:
                    raise ValueError(f"Missing placeholder in message: {ke}") from ke
                ok = False

                if not self.settings.dev_mode:
                    try:
                        ok = bool(self.email_sender.send(instructor["email"], subject, message))
                    except Exception as e:
                        log.error(f"Email send failed to {instructor['email']}: {e}")
                        failed.append(instructor["email"])
                else:
                    ok = True
                    log.info(f"DEV MODE: Would have sent email to {instructor['email']}")

                if ok:
                    # Merge with existing record to preserve classroom_messages etc.
                    existing_record = self.contacted_instructors.get(instructor["email"], {})
                    if not isinstance(existing_record, dict):
                        existing_record = {}
                    existing_record.update(
                        {
                            "contacted_at": datetime.now().isoformat(),
                            "locations": instructor["locations"],
                            "contact_type": "start of semester",
                            "message": message,
                        }
                    )
                    self.contacted_instructors[instructor["email"]] = existing_record
                    batch_count += 1

        if not self.settings.dev_mode:
            self.save_contact_history()

        # Count only semester-type contacts for accurate remaining calculation
        semester_contacted = sum(
            1
            for info in self.contacted_instructors.values()
            if isinstance(info, dict) and info.get("contact_type") == "start of semester"
        )
        total_instructors = sum(
            1 for emp_id in self.contact_by_instructor if self.id_matcher.match_id_to_email(emp_id)
        )
        remaining = total_instructors - semester_contacted

        return DeploymentResult(
            contacted_this_batch=batch_count,
            total_contacted=semester_contacted,
            remaining=remaining,
            failed=failed,
            total_instructors=total_instructors,
        )
