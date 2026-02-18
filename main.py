"""Main application logic and Flet UI for the Instructor Contact System."""

from datetime import date, datetime, time
import json
import logging as log
import os
from typing import cast

from dotenv import load_dotenv
import flet as ft
import pandas as pd

from src import email_sender


def in_docker() -> bool:
    """Detect if the application is running inside a Docker container."""
    try:
        if os.path.exists("/.dockerenv"):
            return True
        with open("/proc/1/cgroup") as f:
            return "docker" in f.read()
    except Exception:
        return False


IN_DOCKER = in_docker()
if not IN_DOCKER:
    load_dotenv()
    log.info("Loaded environment variables locally from .env file")

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO").upper()
log.basicConfig(
    level=getattr(log, LOGGING_LEVEL, log.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log.info(f"Logging level set to {LOGGING_LEVEL}")

try:
    from messages import (
        default_room_contact_message,
        default_room_contact_subject,
        default_semester_start_message,
        default_semester_start_subject,
    )
except ImportError:
    log.warning("Could not import messages.py module")
    (
        default_room_contact_message,
        default_room_contact_subject,
        default_semester_start_message,
        default_semester_start_subject,
    ) = "Set default values in messages.py"


SUPPORTED_LOCATIONS_MODE = os.getenv("SUPPORTED_LOCATIONS_MODE", "none").lower()
if SUPPORTED_LOCATIONS_MODE == "chico":
    from src import chico_supported_location_parser as slp
else:
    slp = None
log.info(f"Using supported locations mode: {SUPPORTED_LOCATIONS_MODE}")

ID_TO_EMAIL_MODULE = os.getenv("ID_TO_EMAIL_MODULE", "").lower()
id_matcher_from_zoom_users = None
id_matcher_from_ad_api = None
id_matcher_from_ad_json = None

match ID_TO_EMAIL_MODULE:
    case "zoom_csv":
        from src import id_matcher_from_zoom_users
    case "ad_api":
        if IN_DOCKER:
            raise RuntimeError("Active Directory module is not supported while in Docker")
        from src import id_matcher_from_ad_api
    case "ad_json":
        from src import id_matcher_from_ad_json
    case _:
        raise ValueError(
            f"Invalid ID_TO_EMAIL_MODULE: {ID_TO_EMAIL_MODULE}. Must be 'zoom_csv', 'ad_api', or 'ad_json'."
        )

log.info(f"Using ID to email module: {ID_TO_EMAIL_MODULE}")

SCHEDULE_MODULE = os.getenv("SCHEDULE_MODULE", "none").lower()

match SCHEDULE_MODULE:
    case "fl_csv":
        from src import fl_aggregator as agg, fl_data_loader as schedule
    case _:
        raise ValueError(f"Invalid SCHEDULE_MODULE: {SCHEDULE_MODULE}. Must be 'fl_csv'.")

log.info(f"Using schedule module: {SCHEDULE_MODULE}")

# If True, disables the actual sending of emails.
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

if DEV_MODE:
    log.warning("System is in Dev Mode.Emails will not be sent. Change by setting DEV_MODE in .env")
else:
    log.info("System is in production mode. Emails will be sent")

# Maximum number of failed recipients to display in error messages
MAX_FAILED_DISPLAY = 50


class InstructorContactSystem:
    """Main application class for the Instructor Contact System."""

    def __init__(self) -> None:
        """Initialize the Instructor Contact System."""
        self.supported_locations = None
        self.loader = None
        self.aggregator = None
        # self.id_matcher =
        self.contact_by_instructor = {}
        self.contact_by_location = {}
        self.contacted_instructors = {}
        self._clipboard = None
        self._deployment_already_contacted_text = None
        self.df: pd.DataFrame = pd.DataFrame()

        if IN_DOCKER:
            log.info("Running in Docker")
            # Ensure data directory exists for persistent storage
            data_dir = "/data"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
                log.info(f"Created data directory: {data_dir}")
        else:
            log.info("Not running in Docker")

        self._initialize_data()

    def _not_in_docker_initialize(self) -> None:
        if ID_TO_EMAIL_MODULE == "ad_json":
            import subprocess

            if not os.path.exists("id_and_emails_from_ad.json"):
                if not os.path.exists("\\scripts\\query_ad.ps1"):
                    log.warning("Missing required script in this configuration: '\\scripts\\query_ad.ps1'")
                    return
                log.info("System is in ad_json mode and not in docker. Querying AD now...")
                subprocess.run("\\scripts\\./query_ad.ps1")

    def _initialize_id_to_email_module(self) -> None:
        match ID_TO_EMAIL_MODULE:
            case "zoom_csv":
                if not id_matcher_from_zoom_users:
                    raise ValueError("ID Matcher module not found or invalid configuration")
                zoom_file = os.getenv("ZOOM_CSV_PATH")
                if not zoom_file:
                    raise FileNotFoundError("""No ZOOM_CSV_PATH found. 
                                            This is a required file for Zoom CSV mode""")

                self.id_matcher = id_matcher_from_zoom_users.Matcher(csv_file_path=zoom_file)

            case "ad_api":
                if not id_matcher_from_ad_api:
                    raise ValueError("ID Matcher module not found or invalid configuration")
                self.id_matcher = id_matcher_from_ad_api.Matcher()

            case "ad_json":
                if not os.path.exists("id_and_emails_from_ad.json"):
                    raise FileNotFoundError("""No id_and_emails_from_ad.json found. 
                    Please run scripts/query_ad.ps1 first to generate this file""")
                if not id_matcher_from_ad_json:
                    raise ValueError("ID Matcher module not found or invalid configuration")
                self.id_matcher = id_matcher_from_ad_json.Matcher()

            case _:
                raise ValueError(f"Invalid ID_TO_EMAIL_MODULE configuration: {ID_TO_EMAIL_MODULE}")

    def _initialize_supported_locations_module(self) -> None:
        if slp and SUPPORTED_LOCATIONS_MODE == "chico":
            slp_csv = os.getenv("SUPPORTED_LOCATIONS_FILE_PATH")
            if not slp_csv:
                raise FileNotFoundError(
                    """No SUPPORTED_LOCATIONS_FILE_PATH Found. 
                    This is a required file for Chico mode"""
                )
            parser = slp.SupportedLocationsParser(slp_csv)
            self.supported_locations = parser.run()

    def _initialize_schedule_module(self) -> None:
        if not schedule:
            log.error("No valid schedule module configured, cannot load schedule data")
            raise ValueError("Invalid SCHEDULE_MODULE configuration")
        if SCHEDULE_MODULE == "fl_csv":
            fl_file = os.getenv("FL_FILE_PATH")
            if not fl_file:
                raise FileNotFoundError("""No FL_FILE_PATH found. 
                This is a required file for fl_csv mode""")

            self.loader = schedule.DataLoader(
                fl_file_path=fl_file,
                supported_locations=self.supported_locations,
            )

    def _initialize_aggregator_module(self):
        if self.df is not None and not self.df.empty:
            self.aggregator = agg.Aggregator(df=self.df)
            self.contact_by_instructor = self.aggregator.by_instructor()
            self.contact_by_location = self.aggregator.by_location()
        else:
            raise FileNotFoundError("Could not initialize aggregator module. self.df is empty or missing")

    def _initialize_data(self) -> None:
        """Initialize data loaders and aggregators."""

        current_date = datetime.now()

        if not IN_DOCKER:
            self._not_in_docker_initialize()

        self._initialize_id_to_email_module()
        self._initialize_supported_locations_module()
        self._initialize_schedule_module()

        # Emails (universal)
        self.email_sender = email_sender.EmailSender()

        if not self.loader:
            raise ModuleNotFoundError("Required module 'loader' missing")

        df = self.loader.semester_data(current_date)
        if df is None:
            raise ValueError("semester_data returned None; cannot continue without schedule data")
        self.df = df

        self._initialize_aggregator_module()

        log.info("Data initialization successful")

    # ---------- Flet 0.80.x helpers ----------

    def _show_snack(self, page: ft.Page, message: str):
        page.show_dialog(ft.SnackBar(ft.Text(message)))
        page.update()

    def _close_dialog(self, page: ft.Page):
        page.pop_dialog()
        page.update()

    def _create_copyable_dialog(self, page: ft.Page, title: str, content: str) -> ft.AlertDialog:
        return ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Container(
                content=ft.Column(
                    [ft.Text(content, selectable=True)],
                    scroll=ft.ScrollMode.AUTO,
                    height=320,
                    width=560,
                    tight=True,
                ),
                padding=ft.Padding.all(12),
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda e: self._close_dialog(page)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    def _get_contact_file_path(self) -> str:
        if IN_DOCKER:
            return "/data/contact_history.json"
        return "contact_history.json"

    def _dedupe_emails(self, emails: list[str]) -> list[str]:
        """Remove duplicate emails while preserving order."""
        seen = set()
        return [e for e in emails if not (e in seen or seen.add(e))]

    def _get_aggregated_data_for_date_range(
        self, start_date: datetime | None = None, end_date: datetime | None = None
    ) -> tuple[dict, dict]:
        """Get aggregated data for a specific date range, or current semester if no range is provided."""
        try:
            if not self.loader:
                raise ModuleNotFoundError("Data loader module is not configured")

            if start_date is not None and end_date is not None:
                df = self.loader.range_data(start_date, end_date)
            else:
                df = self.loader.semester_data(datetime.now())

            if not agg:
                raise ModuleNotFoundError("Aggregator module is not configured")

            if df is None or df.empty:
                raise ValueError("No data available for the specified date range")

            temp_aggregator = agg.Aggregator(df=df)
            return temp_aggregator.by_instructor(), temp_aggregator.by_location()
        except Exception as e:
            log.error(f"Error getting data for date range: {e}")
            return {}, {}

    # ---------- App logic ----------

    def _load_contact_history(self):
        contact_file = self._get_contact_file_path()
        if os.path.exists(contact_file):
            with open(contact_file) as f:
                self.contacted_instructors = json.load(f)
        else:
            self.contacted_instructors = {}

    def _get_already_contacted_count(self) -> int:
        """Count instructors contacted for 'start of semester' deployment only."""
        contact_file = self._get_contact_file_path()
        if not os.path.exists(contact_file):
            return 0

        with open(contact_file) as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Only count those with contact_type "start of semester"
            count = sum(1 for email, info in data.items() if info.get("contact_type") == "start of semester")
            return count
        return 0

    def _save_contact_history(self):
        contact_file = self._get_contact_file_path()
        with open(contact_file, "w") as f:
            json.dump(self.contacted_instructors, f, indent=2)

    def _get_contact_history_dict(self) -> dict:
        """Return the contact history dictionary."""
        self._load_contact_history()
        return self.contacted_instructors

    def _get_server_diagnostics(self) -> str:
        """Gather server diagnostic information."""
        try:
            import platform
            import sys

            def get_file_mod_time(file_path: str | None) -> str:
                if not file_path:
                    return "Not configured"
                if not os.path.exists(file_path):
                    return "File not found"
                mod_time = os.path.getmtime(file_path)
                return datetime.fromtimestamp(mod_time).isoformat()

            generated = datetime.now().isoformat()

            # --- Mode-dependent file paths ---
            schedule_file_path: str | None = None
            if SCHEDULE_MODULE == "fl_csv":
                schedule_file_path = os.getenv("FL_FILE_PATH")

            id_to_email_file_path: str | None = None
            match ID_TO_EMAIL_MODULE:
                case "zoom_csv":
                    id_to_email_file_path = os.getenv("ZOOM_CSV_PATH")
                case "ad_json":
                    # This is the file generated by scripts/query_ad.ps1 in this repo.
                    id_to_email_file_path = "id_and_emails_from_ad.json"
                case "ad_api":
                    id_to_email_file_path = None
                case _:
                    id_to_email_file_path = None

            supported_locations_file_path: str | None = None
            if SUPPORTED_LOCATIONS_MODE == "chico":
                supported_locations_file_path = os.getenv("SUPPORTED_LOCATIONS_FILE_PATH")

            # --- Module/load status ---
            supported_locations_loaded = bool(self.supported_locations)
            loader_loaded = self.loader is not None
            aggregator_loaded = self.aggregator is not None

            id_matcher_loaded = self.id_matcher is not None
            email_sender_loaded = self.email_sender is not None

            # Imported module references (globals)
            schedule_module_loaded = bool(schedule)
            aggregator_module_loaded = bool(agg)
            slp_module_loaded = slp is not None
            id_zoom_module_loaded = id_matcher_from_zoom_users is not None
            id_ad_api_module_loaded = id_matcher_from_ad_api is not None
            id_ad_json_module_loaded = id_matcher_from_ad_json is not None

            # --- Render ---
            diagnostics = f"""Server Diagnostics Report
Generated: {generated}

System Information:
- Platform: {platform.system()} {platform.release()}
- Python Version: {sys.version}
- Running in Docker: {IN_DOCKER}

Application Status:
- DEV_MODE: {DEV_MODE}
- Logging Level: {LOGGING_LEVEL}

Configured Modes:
- Supported Locations Mode: {SUPPORTED_LOCATIONS_MODE}
- ID to Email Mode: {ID_TO_EMAIL_MODULE}
- Schedule Module: {SCHEDULE_MODULE}

Loaded Components:
- Email Sender: {email_sender_loaded}
- ID Matcher: {id_matcher_loaded}
- Supported Locations Data: {supported_locations_loaded}
- Schedule Loader: {loader_loaded}
- Aggregator: {aggregator_loaded}

Imported Modules:
- Schedule Module Imported: {schedule_module_loaded}
- Aggregator Module Imported: {aggregator_module_loaded}
- Supported Locations Parser Imported: {slp_module_loaded}
- ID Matcher (zoom_csv) Imported: {id_zoom_module_loaded}
- ID Matcher (ad_api) Imported: {id_ad_api_module_loaded}
- ID Matcher (ad_json) Imported: {id_ad_json_module_loaded}

Data Status:
- Total Instructors: {len(self.contact_by_instructor)}
- Total Locations: {len(self.contact_by_location)}
- Contacted Instructors (start of semester): {self._get_already_contacted_count()}

Files:
- Contact History: {self._get_contact_file_path()} ({get_file_mod_time(self._get_contact_file_path())})
"""

            if schedule_file_path is not None or SCHEDULE_MODULE == "fl_csv":
                diagnostics += (
                    f"- Schedule File (FL): {schedule_file_path or 'Not configured'} "
                    f"({get_file_mod_time(schedule_file_path)})\n"
                )

            if ID_TO_EMAIL_MODULE == "ad_api":
                diagnostics += "- ID to Email Source: Active Directory API (no local file)\n"
            else:
                diagnostics += (
                    f"- ID to Email File: {id_to_email_file_path or 'Not configured'} "
                    f"({get_file_mod_time(id_to_email_file_path)})\n"
                )

            if SUPPORTED_LOCATIONS_MODE == "chico":
                diagnostics += (
                    f"- Supported Locations File: {supported_locations_file_path or 'Not configured'} "
                    f"({get_file_mod_time(supported_locations_file_path)})\n"
                )
            else:
                diagnostics += "- Supported Locations File: Not used in this mode\n"

            diagnostics += "\nThis is an automated test email from the Instructor Contact System.\n"

            return diagnostics
        except Exception as e:
            log.error(f"Error gathering diagnostics: {e!s}")
            return f"Error gathering diagnostics: {e!s}"

    def _send_test_email(self, page: ft.Page, email: str):
        """Send a test email with diagnostic information."""
        try:
            if not email or "@" not in email:
                self._show_snack(page, "Please enter a valid email address")
                return

            if not self.email_sender:
                self._show_snack(page, "Email sender is not configured")
                return

            subject = "Instructor Contact System - Test Email"
            message = self._get_server_diagnostics()

            if not DEV_MODE:
                success = self.email_sender.send(email, subject, message)
                if success:
                    self._show_snack(page, f"Test email sent successfully to {email}")
                    log.info(f"Test email sent to {email}")
                else:
                    self._show_snack(page, "Failed to send test email")
                    log.error(f"Failed to send test email to {email}")
            else:
                log.info(f"DEV MODE: Would have sent test email to {email}")
                log.info(f"Subject: {subject}")
                log.info(f"Message:\n{message}")
                self._show_snack(page, f"DEV MODE: Test email logged (not sent) for {email}")

        except Exception as e:
            log.error(f"Error sending test email: {e!s}")
            self._show_snack(page, f"Error: {e!s}")

    def _on_save_file_result(self, page: ft.Page, e):
        """Handle the file picker result for saving contact history."""
        try:
            if e.path:
                contact_file = self._get_contact_file_path()
                if os.path.exists(contact_file):
                    with open(contact_file) as source:
                        data = source.read()
                    with open(e.path, "w") as dest:
                        dest.write(data)
                    self._show_snack(page, f"Contact history saved to {e.path}")
                    log.info(f"Contact history downloaded to {e.path}")
                else:
                    self._show_snack(page, "No contact history file found")
        except Exception as ex:
            log.error(f"Error saving contact history: {ex!s}")
            self._show_snack(page, f"Error saving file: {ex!s}")

    def _send_message_to_classroom(
        self,
        page: ft.Page,
        building: str,
        room: str,
        subject: str,
        message_template: str,
        location_map: dict | None = None,
    ):
        try:
            location_key = f"{building.upper()} {room.upper()}"

            # Use provided location_map or fall back to cached data
            if location_map is None:
                location_map = self.contact_by_location

            if location_key not in location_map:
                self._show_snack(page, f"No classes found in {location_key}")
                return

            emp_ids = location_map[location_key]
            emails = []
            for emp_id in emp_ids:
                email = self.id_matcher.match_id_to_email(emp_id)
                if email:
                    emails.append(email)

            # de-dupe but keep stable order
            emails = self._dedupe_emails(emails)

            if not emails:
                self._show_snack(page, "No email matches found for instructors in this location")
                return

            message = message_template.format(location=location_key)

            if not self.email_sender:
                self._show_snack(page, "Email sender is not configured")
                return

            sent_count = 0
            failed = []
            self._load_contact_history()
            if not DEV_MODE:
                for email in emails:
                    ok = False
                    try:
                        ok = bool(self.email_sender.send(email, subject, message))
                        log.info(f"Sent: {email}, subject: {subject}, message: {message}")
                    except Exception as e:
                        log.error(f"Email send failed to {email}: {e!s}")

                    if ok:
                        existing = self.contacted_instructors.get(email, {})
                        history = existing.get("classroom_messages", [])
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
            else:  # dev mode
                log.info(f"DEV MODE: Would have sent messages to {emails}")
            self._save_contact_history()

            summary = f"""Classroom Message Sent

Location: {location_key}
Sent: {sent_count}
Failed: {len(failed)}
"""

            if failed:
                summary += "\nFailed recipients:\n" + "\n".join(failed[:MAX_FAILED_DISPLAY])
                if len(failed) > MAX_FAILED_DISPLAY:
                    summary += f"\n...and {len(failed) - MAX_FAILED_DISPLAY} more"

            dialog = ft.AlertDialog(
                title=ft.Text("Send complete"),
                content=ft.Container(ft.Text(summary), padding=ft.Padding.all(8)),
                actions=[
                    ft.TextButton("Close", on_click=lambda e: self._close_dialog(page)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            page.update()

        except KeyError as ke:
            self._show_snack(page, f"Missing placeholder in message: {ke!s}")
        except Exception as e:
            log.error(f"Error sending classroom message: {e!s}")
            self._show_snack(page, f"Error: {e!s}")

    def _lookup_classroom(self, page: ft.Page, building: str, room: str):
        try:
            location_key = f"{building.upper()} {room.upper()}"

            if location_key not in self.contact_by_location:
                self._show_snack(page, f"No classes found in {location_key}")
                return

            emp_ids = self.contact_by_location[location_key]
            emails = [
                self.id_matcher.match_id_to_email(emp_id)
                for emp_id in emp_ids
                if self.id_matcher.match_id_to_email(emp_id)
            ]

            if not emails:
                self._show_snack(page, "No email matches found for instructors in this location")
                return

            dialog = self._create_copyable_dialog(
                page,
                f"Instructors in {location_key}",
                "\n".join(emails),
            )
            page.show_dialog(dialog)
            page.update()

        except Exception as e:
            log.error(f"Error looking up classroom: {e!s}")
            self._show_snack(page, f"Error: {e!s}")

    def _lookup_instructor(self, page: ft.Page, email: str):
        try:
            target_email = (email or "").strip().lower()
            if not target_email:
                self._show_snack(page, "Please enter an email")
                return

            emp_id = None
            for eid in self.contact_by_instructor:
                matched_email = (self.id_matcher.match_id_to_email(eid) or "").strip().lower()
                if matched_email == target_email:
                    emp_id = eid
                    break

            if not emp_id or emp_id not in self.contact_by_instructor:
                self._show_snack(page, f"No classes found for {email}")
                return

            locations = self.contact_by_instructor[emp_id]
            dialog = self._create_copyable_dialog(
                page,
                f"Classes for {email}",
                "\n".join(locations),
            )
            page.show_dialog(dialog)
            page.update()

        except Exception as e:
            log.error(f"Error looking up instructor: {e}")
            self._show_snack(page, f"Error: {e}")

    def _start_semester_deployment(self, page: ft.Page, message_template: str, batch_size: int):
        try:
            self._load_contact_history()

            all_instructors = []
            for emp_id in self.contact_by_instructor:
                email = self.id_matcher.match_id_to_email(emp_id)
                if email and email not in self.contacted_instructors:
                    all_instructors.append(
                        {
                            "email": email,
                            "emp_id": emp_id,
                            "locations": self.contact_by_instructor[emp_id],
                            "contacted": False,
                        }
                    )

            total = len(all_instructors)
            already_contacted = len(self.contacted_instructors)

            body = f"""Semester Deployment Summary

Total instructors to contact: {total}
Already contacted: {already_contacted}
Batch size: {batch_size}

Message template includes instructor locations via {{locations}}.
"""

            dialog = ft.AlertDialog(
                title=ft.Text("Semester Deployment"),
                content=ft.Container(ft.Text(body), padding=ft.Padding.all(8)),
                actions=[
                    ft.FilledButton(
                        "Send",
                        icon=ft.Icons.SEND,
                        on_click=lambda e: self._execute_deployment(
                            page, all_instructors, message_template, batch_size
                        ),
                    ),
                    ft.OutlinedButton(
                        "Cancel",
                        icon=ft.Icons.CLOSE,
                        on_click=lambda e: self._close_dialog(page),
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            page.update()

        except Exception as e:
            log.error(f"Error starting deployment: {e!s}")
            self._show_snack(page, f"Error: {e!s}")

    def _execute_deployment(self, page: ft.Page, instructors: list, message_template: str, batch_size: int):
        try:
            batch_count = 0
            failed = []

            if not self.email_sender:
                self._show_snack(page, "Email sender is not configured")
                return

            subject = default_semester_start_subject

            for instructor in instructors[:batch_size]:
                if instructor["email"] not in self.contacted_instructors:
                    locations_str = ", ".join(instructor["locations"])
                    message = message_template.format(locations=locations_str)
                    ok = False
                    if not DEV_MODE:
                        try:
                            ok = bool(self.email_sender.send(instructor["email"], subject, message))
                        except Exception as e:
                            log.error(f"Email send failed to {instructor['email']}: {e!s}")
                            failed.append(instructor["email"])

                    else:  # dev mode
                        ok = True
                        log.info(f"DEV MODE: Would have sent email to {instructor['email']}")
                    if ok:
                        self.contacted_instructors[instructor["email"]] = {
                            "contacted_at": datetime.now().isoformat(),
                            "locations": instructor["locations"],
                            "contact_type": "start of semester",
                            "message": message,
                        }
                        batch_count += 1

            self._save_contact_history()

            if self._deployment_already_contacted_text is not None:
                self._deployment_already_contacted_text.value = (
                    f"Already contacted: {len(self.contacted_instructors)}"
                )
                page.update()

            contacted = len(self.contacted_instructors)
            total_instructors = sum(
                1 for emp_id in self.contact_by_instructor if self.id_matcher.match_id_to_email(emp_id)
            )
            remaining = total_instructors - contacted

            summary = f"""Deployment Progress

Contacted this batch: {batch_count}
Total contacted: {contacted}
Remaining: {remaining}
Failed this batch: {len(failed)}

Progress: {contacted}/{total_instructors}
"""

            if failed:
                summary += "\nFailed recipients:\n" + "\n".join(failed[:MAX_FAILED_DISPLAY])
                if len(failed) > MAX_FAILED_DISPLAY:
                    summary += f"\n...and {len(failed) - MAX_FAILED_DISPLAY} more"

            dialog = ft.AlertDialog(
                title=ft.Text("Deployment Complete"),
                content=ft.Container(ft.Text(summary), padding=ft.Padding.all(8)),
                actions=[
                    ft.TextButton("Close", on_click=lambda e: self._close_dialog(page)),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
            page.update()

        except Exception as e:
            log.error(f"Error executing deployment: {e!s}")
            self._show_snack(page, f"Error: {e!s}")

    # ---------- UI ----------

    def main(self, page: ft.Page):
        """Build and display the main flet UI."""

        page.title = "Instructor Contact System"
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.padding = 0
        page.window.width = 960
        page.window.height = 720

        page.appbar = ft.AppBar(
            title=ft.Text("Instructor Contact System"),
            center_title=False,
        )

        # ---- Views ----
        def build_view_by_classroom() -> ft.Control:
            building_input = ft.TextField(
                label="Building",
                width=240,
                autofocus=True,
                prefix_icon=ft.Icons.LOCATION_CITY,
            )
            room_input = ft.TextField(
                label="Room",
                width=240,
                prefix_icon=ft.Icons.MEETING_ROOM,
            )

            # Store selected date range (optional)
            selected_dates: dict[str, ft.DateTimeValue | None] = {
                "start": None,
                "end": None,
            }

            # Display for selected date range
            date_range_display = ft.Text(
                "Date range: Current semester (default)",
                size=16,
            )

            def _value_to_date(v: ft.DateTimeValue) -> date:
                # Flet may provide either date or datetime depending on platform/version
                if isinstance(v, datetime):
                    return v.date()
                return cast(date, v)

            def update_date_display():
                start_v = selected_dates["start"]
                end_v = selected_dates["end"]
                if start_v and end_v:
                    s = _value_to_date(start_v).strftime("%Y-%m-%d")
                    ed = _value_to_date(end_v).strftime("%Y-%m-%d")
                    date_range_display.value = f"Date range: {s} to {ed}"
                elif start_v:
                    s = _value_to_date(start_v).strftime("%Y-%m-%d")
                    date_range_display.value = f"Start date: {s} (select end date)"
                elif end_v:
                    ed = _value_to_date(end_v).strftime("%Y-%m-%d")
                    date_range_display.value = f"End date: {ed} (select start date)"
                else:
                    date_range_display.value = "Date range: Current semester (default)"

            def clear_date_range(e):
                selected_dates["start"] = None
                selected_dates["end"] = None
                # Keep the picker state in sync with the UI state
                try:
                    date_range_picker.start_value = None
                    date_range_picker.end_value = None
                except Exception:
                    pass
                update_date_display()
                page.update()

            def sync_date_range_from_picker():
                # In many builds, the final selection is committed on "Save" (dismiss),
                # so read directly from the control's properties.
                selected_dates["start"] = cast(
                    ft.DateTimeValue | None,
                    getattr(date_range_picker, "start_value", None),
                )
                selected_dates["end"] = cast(
                    ft.DateTimeValue | None,
                    getattr(date_range_picker, "end_value", None),
                )
                update_date_display()
                page.update()

            # ---- Date range picker (single shared overlay control) ----
            date_range_picker = classroom_date_range_picker
            date_range_picker.on_change = lambda e: sync_date_range_from_picker()
            date_range_picker.on_dismiss = lambda e: sync_date_range_from_picker()

            def open_date_range_picker(e):
                date_range_picker.open = True
                page.update()

            subject_input = ft.TextField(
                label="Subject",
                value=default_room_contact_subject,
                width=720,
                prefix_icon=ft.Icons.SUBJECT,
            )

            message_input = ft.TextField(
                label="Message template",
                value=default_room_contact_message,
                multiline=True,
                min_lines=4,
                max_lines=8,
                width=720,
                prefix_icon=ft.Icons.MESSAGE,
            )

            def _get_date_filtered_location_map() -> dict | None:
                start_dt = selected_dates["start"]
                end_dt = selected_dates["end"]

                # If no dates selected, fetch current semester data
                if not start_dt and not end_dt:
                    log.debug("No date range selected, using current semester data")
                    _, location_map = self._get_aggregated_data_for_date_range()
                    return location_map

                # Both dates must be provided if one is provided
                if not start_dt or not end_dt:
                    self._show_snack(
                        page,
                        "Please provide both start and end dates, or clear to use current semester",
                    )
                    return None

                # Validate date range
                if _value_to_date(start_dt) > _value_to_date(end_dt):
                    self._show_snack(page, "Start date must be before or equal to end date")
                    return None

                # Convert to inclusive datetime bounds for the data loader
                start_datetime = datetime.combine(_value_to_date(start_dt), time.min)
                end_datetime = datetime.combine(_value_to_date(end_dt), time.max)

                log.info(f"Using date range filter: {start_datetime} to {end_datetime}")
                _, location_map = self._get_aggregated_data_for_date_range(start_datetime, end_datetime)
                log.info(f"Filtered location map contains {len(location_map)} locations")
                return location_map

            def on_search(e):
                if not (building_input.value and room_input.value):
                    self._show_snack(page, "Please enter building and room")
                    return

                location_map = _get_date_filtered_location_map()
                if location_map is None:
                    return

                location_key = f"{building_input.value.upper()} {room_input.value.upper()}"
                if location_key not in location_map:
                    self._show_snack(page, f"No classes found in {location_key}")
                    return

                emp_ids = location_map[location_key]
                emails = [
                    self.id_matcher.match_id_to_email(emp_id)
                    for emp_id in emp_ids
                    if self.id_matcher.match_id_to_email(emp_id)
                ]

                if not emails:
                    self._show_snack(page, "No email matches found for instructors in this location")
                    return

                dialog = self._create_copyable_dialog(
                    page,
                    f"Instructors in {location_key}",
                    "\n".join(emails),
                )
                page.show_dialog(dialog)
                page.update()

            def on_send(e):
                if not (building_input.value and room_input.value):
                    self._show_snack(page, "Please enter building and room")
                    return
                if not subject_input.value:
                    self._show_snack(page, "Please enter a subject")
                    return
                if not message_input.value:
                    self._show_snack(page, "Please enter a message")
                    return

                location_map = _get_date_filtered_location_map()
                if location_map is None:
                    return

                location_key = f"{building_input.value.upper()} {room_input.value.upper()}"
                if location_key not in location_map:
                    self._show_snack(page, f"No classes found in {location_key}")
                    return

                emp_ids = location_map[location_key]
                emails = []
                for emp_id in emp_ids:
                    email = self.id_matcher.match_id_to_email(emp_id)
                    if email:
                        emails.append(email)

                emails = self._dedupe_emails(emails)

                if not emails:
                    self._show_snack(
                        page,
                        "No email matches found for instructors in this location",
                    )
                    return

                try:
                    rendered_message = message_input.value.format(location=location_key)
                except KeyError as ke:
                    self._show_snack(page, f"Missing placeholder in message: {ke!s}")
                    return

                recipients_text = "\n".join(emails)
                confirm_body = (
                    f"Are you sure you want to send this message to these recipients?\n\n"
                    f"Subject:\n{subject_input.value}\n\n"
                    f"Message:\n{rendered_message}\n\n"
                    f"Recipients ({len(emails)}):\n{recipients_text}"
                )

                dialog = ft.AlertDialog(
                    title=ft.Text("Confirm send"),
                    content=ft.Container(
                        content=ft.Column(
                            [ft.Text(confirm_body, selectable=True)],
                            scroll=ft.ScrollMode.AUTO,
                            height=360,
                            width=640,
                            tight=True,
                        ),
                        padding=ft.Padding.all(12),
                    ),
                    actions=[
                        ft.OutlinedButton(
                            "Cancel",
                            icon=ft.Icons.CLOSE,
                            on_click=lambda e: self._close_dialog(page),
                        ),
                        ft.FilledButton(
                            "Send",
                            icon=ft.Icons.SEND,
                            on_click=lambda e: (
                                self._close_dialog(page),
                                self._send_message_to_classroom(
                                    page,
                                    building_input.value,
                                    room_input.value,
                                    subject_input.value,
                                    message_input.value,
                                    location_map,
                                ),
                            ),
                        ),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                page.show_dialog(dialog)
                page.update()

            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Lookup instructors by classroom",
                            size=24,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "Optional: select a date range to filter classes. If not specified, "
                            "defaults to current semester. Use {location} as a placeholder in the message.",
                            size=16,
                        ),
                        ft.Row([building_input, room_input], spacing=12, wrap=True),
                        ft.Row(
                            [
                                ft.OutlinedButton(
                                    "Select date range",
                                    icon=ft.Icons.DATE_RANGE,
                                    on_click=open_date_range_picker,
                                ),
                                ft.OutlinedButton(
                                    "Clear dates",
                                    icon=ft.Icons.CLEAR,
                                    on_click=clear_date_range,
                                ),
                            ],
                            spacing=12,
                            wrap=True,
                        ),
                        date_range_display,
                        ft.Row(
                            [
                                ft.FilledButton(
                                    "Search",
                                    icon=ft.Icons.SEARCH,
                                    on_click=on_search,
                                ),
                                ft.OutlinedButton(
                                    "Send message",
                                    icon=ft.Icons.SEND,
                                    on_click=on_send,
                                ),
                            ],
                            spacing=12,
                            wrap=True,
                        ),
                        ft.Container(
                            content=subject_input,
                            padding=ft.Padding(top=24, left=0, right=0, bottom=0),
                        ),
                        ft.Container(
                            content=message_input,
                            padding=ft.Padding(top=12, left=0, right=0, bottom=0),
                        ),
                    ],
                    spacing=16,
                ),
                padding=ft.Padding.all(16),
            )

        def build_view_by_instructor() -> ft.Control:
            email_input = ft.TextField(
                label="Instructor email",
                width=560,
                prefix_icon=ft.Icons.EMAIL,
                keyboard_type=ft.KeyboardType.EMAIL,
            )

            def on_search(e):
                if email_input.value:
                    self._lookup_instructor(page, email_input.value.strip())
                else:
                    self._show_snack(page, "Please enter an email")

            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Lookup classes by instructor",
                            size=24,
                            weight=ft.FontWeight.W_600,
                        ),
                        email_input,
                        ft.FilledButton("Search", icon=ft.Icons.SEARCH, on_click=on_search),
                    ],
                    spacing=16,
                ),
                padding=ft.Padding.all(16),
            )

        def build_view_deployment() -> ft.Control:
            already_contacted_text = ft.Text(
                f"Already contacted: {self._get_already_contacted_count()}", size=16
            )
            self._deployment_already_contacted_text = already_contacted_text

            message_input = ft.TextField(
                label="Message template",
                value=default_semester_start_message,
                multiline=True,
                min_lines=6,
                max_lines=10,
                width=720,
                prefix_icon=ft.Icons.MESSAGE,
            )
            batch_size_input = ft.TextField(
                label="Batch size",
                value="50",
                width=240,
                prefix_icon=ft.Icons.NUMBERS,
                keyboard_type=ft.KeyboardType.NUMBER,
            )

            def on_start(e):
                try:
                    batch_size = int(batch_size_input.value)
                    if batch_size <= 0:
                        raise ValueError("Batch size must be positive")
                    self._start_semester_deployment(page, message_input.value, batch_size)
                except ValueError as ve:
                    self._show_snack(page, f"Invalid batch size: {ve!s}")

            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Start of semester deployment",
                            size=24,
                            weight=ft.FontWeight.W_600,
                        ),
                        already_contacted_text,
                        message_input,
                        ft.Row(
                            [
                                batch_size_input,
                                ft.FilledButton(
                                    "Start deployment",
                                    icon=ft.Icons.PLAY_ARROW,
                                    on_click=on_start,
                                ),
                            ],
                            spacing=12,
                            wrap=True,
                        ),
                    ],
                    spacing=16,
                    scroll=ft.ScrollMode.AUTO,
                ),
                padding=ft.Padding(left=16, right=16, top=0, bottom=16),
            )

        def build_view_utility() -> ft.Control:

            async def on_download_history(e: ft.Event[ft.Button]):
                # Build the bytes you want to download
                data = self._get_contact_history_dict()  # <- whatever you have
                content_bytes = json.dumps(data, indent=2).encode("utf-8")

                # Desktop: save_file() returns a path; YOU write the file (Flet doesn't create it)
                # Web/iOS/Android: you MUST pass src_bytes (Flet will download/save it)
                if page.web or page.platform in (
                    ft.PagePlatform.IOS,
                    ft.PagePlatform.ANDROID,
                ):
                    await ft.FilePicker().save_file(
                        file_name="contact_history.json",
                        src_bytes=content_bytes,
                    )
                    return

                save_path = await ft.FilePicker().save_file(file_name="contact_history.json")
                if save_path:
                    with open(save_path, "wb") as f:
                        f.write(content_bytes)

            # Test email UI elements
            test_email_input = ft.TextField(
                label="Test Email Address",
                width=560,
                prefix_icon=ft.Icons.EMAIL,
                keyboard_type=ft.KeyboardType.EMAIL,
                hint_text="Enter email to receive test message",
            )

            def on_send_test_email(e):
                if test_email_input.value:
                    self._send_test_email(page, test_email_input.value.strip())
                else:
                    self._show_snack(page, "Please enter an email address")

            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text("Utility", size=24, weight=ft.FontWeight.W_600),
                        ft.Divider(),
                        ft.Text("Contact History", size=22, weight=ft.FontWeight.W_500),
                        ft.Text(
                            "Download the contact history JSON file to view all contacted instructors.",
                            size=16,
                        ),
                        ft.FilledButton(
                            content="Download Contact History",
                            icon=ft.Icons.DOWNLOAD,
                            on_click=on_download_history,
                        ),
                        ft.Divider(),
                        ft.Text("Test Email", size=22, weight=ft.FontWeight.W_500),
                        ft.Text(
                            "Send a test email with server diagnostic information.",
                            size=16,
                        ),
                        test_email_input,
                        ft.FilledButton(
                            "Send Test Email",
                            icon=ft.Icons.SEND,
                            on_click=on_send_test_email,
                        ),
                    ],
                    spacing=16,
                ),
                padding=16,
            )

        # ---- Initialize shared UI components (overlays) once ----
        # DateRangePicker for classroom view - create once to avoid Windows serialization issues
        # On Windows, Flet/msgpack may attempt to timezone-convert default min/max datetimes
        # which can raise OSError: [Errno 22] Invalid argument. Constrain to a safe range.
        classroom_date_range_picker = ft.DateRangePicker(
            first_date=date(2000, 1, 1),
            last_date=date(2100, 12, 31),
        )
        page.overlay.append(classroom_date_range_picker)

        views = [
            build_view_by_classroom,
            build_view_by_instructor,
            build_view_deployment,
            build_view_utility,
        ]

        # ---- Navigation + content swapping ----
        selected_index = 0
        content_host = ft.Container(expand=True)

        rail = ft.NavigationRail(
            selected_index=0,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=72,
            min_extended_width=220,
            extended=True,
            destinations=[
                ft.NavigationRailDestination(
                    icon=ft.Icons.MEETING_ROOM_OUTLINED,
                    selected_icon=ft.Icons.MEETING_ROOM,
                    label="By Classroom",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.PERSON_SEARCH_OUTLINED,
                    selected_icon=ft.Icons.PERSON_SEARCH,
                    label="By Instructor",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.ROCKET_LAUNCH_OUTLINED,
                    selected_icon=ft.Icons.ROCKET_LAUNCH,
                    label="Start of Semester",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.BUILD_OUTLINED,
                    selected_icon=ft.Icons.BUILD,
                    label="Utility",
                ),
            ],
        )

        bar = ft.NavigationBar(
            selected_index=0,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.MEETING_ROOM, label="Classroom"),
                ft.NavigationBarDestination(icon=ft.Icons.PERSON_SEARCH, label="Instructor"),
                ft.NavigationBarDestination(icon=ft.Icons.ROCKET_LAUNCH, label="Deploy"),
                ft.NavigationBarDestination(icon=ft.Icons.BUILD, label="Utility"),
            ],
        )

        def set_view(index: int):
            nonlocal selected_index
            selected_index = index
            rail.selected_index = index
            bar.selected_index = index
            content_host.content = views[index]()  # rebuild view to keep controls fresh/simple
            page.update()

        def on_rail_change(e):
            set_view(rail.selected_index or 0)

        def on_bar_change(e):
            set_view(bar.selected_index or 0)

        rail.on_change = on_rail_change
        bar.on_change = on_bar_change

        def apply_responsive_layout():
            # Simple breakpoint; adjust if you want
            wide = (page.window.width or 0) >= 900

            rail.visible = wide
            bar.visible = not wide

            page.update()

        def on_resized(e):
            apply_responsive_layout()

        page.on_resize = on_resized

        # Root layout
        root = ft.Column(
            [
                ft.Row(
                    [
                        rail,
                        ft.VerticalDivider(width=1),
                        content_host,
                    ],
                    expand=True,
                ),
                bar,
            ],
            expand=True,
        )

        page.add(root)

        # initial render
        set_view(0)
        apply_responsive_layout()


if __name__ == "__main__":
    try:
        app = InstructorContactSystem()
        ft.run(app.main, port=8080, view=ft.AppView.WEB_BROWSER)
    except Exception as e:
        log.error(f"Fatal error starting app: {e!s}")
        if not IN_DOCKER:
            from time import sleep

            sleep(15)  # Allow time to see the error in the console before it closes
        exit(1)
