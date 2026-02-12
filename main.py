import json
import logging as log
import os
from datetime import date, datetime, time
from typing import Optional, cast

import flet as ft

from src import aggregator as agg

from messages_ import (
    default_room_contact_message,
    default_room_contact_subject,
    default_semester_start_message,
    default_semester_start_subject,
)
from src import data_loader, email_sender
from src import id_matcher_from_zoom_users as matcher

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO").upper()
log.basicConfig(
    level=getattr(log, LOGGING_LEVEL, log.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log.info(f"Logging level set to {LOGGING_LEVEL}")

# Maximum number of failed recipients to display in error messages
MAX_FAILED_DISPLAY = 50

SUPPORTED_LOCATIONS_MODE = os.getenv("SUPPORTED_LOCATIONS_MODE", "none").lower()
if SUPPORTED_LOCATIONS_MODE == "chico":
    from src import chico_supported_location_parser as slp
else:
    slp = None
log.info(f"Using supported locations mode: {SUPPORTED_LOCATIONS_MODE}")

# If True, disables the actual sending of emails.
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

if DEV_MODE:
    log.warning(
        "System is in Dev Mode. Emails will not be sent. Change by setting DEV_MODE in .env"
    )
else:
    log.info("System is in production mode. Emails will be sent")


class InstructorContactSystem:
    def __init__(self) -> None:
        self.supported_locations = None
        self.loader = None
        self.aggregator = None
        # self.id_matcher = None # appease
        self.email_sender = None
        self.contact_by_instructor = {}
        self.contact_by_location = {}
        self.contacted_instructors = {}
        self._clipboard = None
        self._deployment_already_contacted_text = None

        self.is_in_docker: bool = self.in_docker()
        if self.is_in_docker:
            log.info("Running in Docker")
            # Ensure data directory exists for persistent storage
            data_dir = "/data"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
                log.info(f"Created data directory: {data_dir}")
        else:
            log.info("Not running in Docker")

        self._initialize_data()

    def _initialize_data(self) -> None:
        """Initialize data loaders and aggregators."""
        try:
            if slp and SUPPORTED_LOCATIONS_MODE == "chico":
                slp_csv = os.getenv("SUPPORTED_LOCATIONS_FILE_PATH")
                if not slp_csv:
                    raise FileNotFoundError(
                        "No SUPPORTED_LOCATIONS_FILE_PATH Found. This is a required file for Chico mode"
                    )
                parser = slp.SupportedLocationsParser(slp_csv)
                self.supported_locations = parser.run()

            fl_file = os.getenv("FL_FILE_PATH")
            if not fl_file:
                raise FileNotFoundError(
                    "No FL_FILE_PATH found. This is a required file."
                )
            self.loader = data_loader.DataLoader(
                fl_file_path=fl_file,
                supported_locations=self.supported_locations,
            )

            current_date = datetime.now()
            df = self.loader.semester_data(current_date)

            self.aggregator = agg.Aggregator(df=df)
            self.contact_by_instructor = self.aggregator.by_instructor()
            self.contact_by_location = self.aggregator.by_location()

            zoom_file = os.getenv("ZOOM_FILE_PATH")
            if not zoom_file:
                raise FileNotFoundError(
                    "No ZOOM_FILE_PATH found. This is a required file."
                )
            self.id_matcher = matcher.Matcher(csv_file_path=zoom_file)
            if not self.id_matcher:
                raise ValueError("ID Matcher failed to initialize")

            self.email_sender = email_sender.EmailSender()

            log.info("Data initialization successful")
        except Exception as e:
            log.error(f"Error initializing data: {str(e)}")
            raise

    # ---------- Flet 0.80.x helpers ----------

    def _get_clipboard(self, page: ft.Page) -> ft.Clipboard:
        if self._clipboard is None:
            self._clipboard = ft.Clipboard()
            page.overlay.append(self._clipboard)
            page.update()
        return self._clipboard

    def _show_snack(self, page: ft.Page, message: str):
        page.show_dialog(ft.SnackBar(ft.Text(message)))
        page.update()

    def _close_dialog(self, page: ft.Page):
        page.pop_dialog()
        page.update()

    def _create_copyable_dialog(
        self, page: ft.Page, title: str, content: str
    ) -> ft.AlertDialog:
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

    def in_docker(self) -> bool:
        try:
            if os.path.exists("/.dockerenv"):
                return True
            with open("/proc/1/cgroup", "rt") as f:
                return "docker" in f.read()
        except Exception:
            return False

    def _get_contact_file_path(self) -> str:
        if self.is_in_docker:
            return "/data/contact_history.json"
        return "contact_history.json"

    def _dedupe_emails(self, emails: list[str]) -> list[str]:
        """Remove duplicate emails while preserving order."""
        seen = set()
        return [e for e in emails if not (e in seen or seen.add(e))]

    def _get_aggregated_data_for_date_range(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> tuple[dict, dict]:
        """Get aggregated data for a specific date range, or current semester if no range is provided."""
        try:
            if not self.loader:  # appease
                log.error("Data loader is not initialized")
                return {}, {}
            if start_date is not None and end_date is not None:
                df = self.loader.range_data(start_date, end_date)
            else:
                df = self.loader.semester_data(datetime.now())

            if df is None or df.empty:
                return {}, {}

            temp_aggregator = agg.Aggregator(df=df)
            return temp_aggregator.by_instructor(), temp_aggregator.by_location()
        except Exception as e:
            log.error(f"Error getting data for date range: {str(e)}")
            return {}, {}

    # ---------- App logic ----------

    def _load_contact_history(self):
        contact_file = self._get_contact_file_path()
        if os.path.exists(contact_file):
            with open(contact_file, "r") as f:
                self.contacted_instructors = json.load(f)
        else:
            self.contacted_instructors = {}

    def _get_already_contacted_count(self) -> int:
        """Count instructors contacted for 'start of semester' deployment only."""
        contact_file = self._get_contact_file_path()
        if not os.path.exists(contact_file):
            return 0
        try:
            with open(contact_file, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Only count those with contact_type "start of semester"
                count = sum(
                    1
                    for email, info in data.items()
                    if info.get("contact_type") == "start of semester"
                )
                return count
            return 0
        except Exception:
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

            # Get file modification times
            def get_file_mod_time(file_path):
                if file_path and os.path.exists(file_path):
                    mod_time = os.path.getmtime(file_path)
                    return datetime.fromtimestamp(mod_time).isoformat()
                return "File not found"

            fl_file = os.getenv("FL_FILE_PATH")
            zoom_file = os.getenv("ZOOM_FILE_PATH")
            slp_file = os.getenv("SUPPORTED_LOCATIONS_FILE_PATH")

            fl_mod_time = get_file_mod_time(fl_file) if fl_file else "Not configured"
            zoom_mod_time = (
                get_file_mod_time(zoom_file) if zoom_file else "Not configured"
            )
            slp_mod_time = get_file_mod_time(slp_file) if slp_file else "Not configured"

            diagnostics = f"""Server Diagnostics Report
Generated: {datetime.now().isoformat()}

System Information:
- Platform: {platform.system()} {platform.release()}
- Python Version: {sys.version}
- Running in Docker: {self.is_in_docker}

Application Status:
- DEV_MODE: {DEV_MODE}
- Logging Level: {LOGGING_LEVEL}
- Supported Locations Mode: {SUPPORTED_LOCATIONS_MODE}

Data Status:
- Total Instructors: {len(self.contact_by_instructor)}
- Total Locations: {len(self.contact_by_location)}
- Contacted Instructors: {self._get_already_contacted_count()}
- Email Sender Configured: {self.email_sender is not None}
- ID Matcher Configured: {self.id_matcher is not None}

File Paths:
- Contact History: {self._get_contact_file_path()}
- FL File Path: {fl_file or "Not configured"}
- Zoom File Path: {zoom_file or "Not configured"}
- Supported Locations File: {slp_file or "Not configured"}

File Modification Dates:
- FL File: {fl_mod_time}
- Zoom File: {zoom_mod_time}
- Supported Locations File: {slp_mod_time}

This is an automated test email from the Instructor Contact System.
"""
            return diagnostics
        except Exception as e:
            log.error(f"Error gathering diagnostics: {str(e)}")
            return f"Error gathering diagnostics: {str(e)}"

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
                self._show_snack(
                    page, f"DEV MODE: Test email logged (not sent) for {email}"
                )

        except Exception as e:
            log.error(f"Error sending test email: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

    def _download_contact_history(self, page: ft.Page, file_picker: ft.FilePicker):
        """Allow user to download the contact history JSON file."""
        try:
            contact_file = self._get_contact_file_path()
            if not os.path.exists(contact_file):
                self._show_snack(page, "No contact history found")
                return

            # Trigger the file picker to save
            _ = file_picker.save_file(
                file_name="contact_history.json",
                allowed_extensions=["json"],
            )

        except Exception as e:
            log.error(f"Error downloading contact history: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

    def _on_save_file_result(self, page: ft.Page, e):
        """Handle the file picker result for saving contact history."""
        try:
            if e.path:
                contact_file = self._get_contact_file_path()
                if os.path.exists(contact_file):
                    with open(contact_file, "r") as source:
                        data = source.read()
                    with open(e.path, "w") as dest:
                        dest.write(data)
                    self._show_snack(page, f"Contact history saved to {e.path}")
                    log.info(f"Contact history downloaded to {e.path}")
                else:
                    self._show_snack(page, "No contact history file found")
        except Exception as ex:
            log.error(f"Error saving contact history: {str(ex)}")
            self._show_snack(page, f"Error saving file: {str(ex)}")

    def _send_message_to_classroom(
        self,
        page: ft.Page,
        building: str,
        room: str,
        message_template: str,
        location_map: Optional[dict] = None,
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
                self._show_snack(
                    page, "No email matches found for instructors in this location"
                )
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
                        subject = default_room_contact_subject
                        ok = bool(self.email_sender.send(email, subject, message))
                        log.info(
                            f"Sent: {email}, subject: {subject}, message: {message}"
                        )
                    except Exception as e:
                        log.error(f"Email send failed to {email}: {str(e)}")

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
                summary += "\nFailed recipients:\n" + "\n".join(
                    failed[:MAX_FAILED_DISPLAY]
                )
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
            self._show_snack(page, f"Missing placeholder in message: {str(ke)}")
        except Exception as e:
            log.error(f"Error sending classroom message: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

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
                self._show_snack(
                    page, "No email matches found for instructors in this location"
                )
                return

            dialog = self._create_copyable_dialog(
                page,
                f"Instructors in {location_key}",
                "\n".join(emails),
            )
            page.show_dialog(dialog)
            page.update()

        except Exception as e:
            log.error(f"Error looking up classroom: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

    def _lookup_instructor(self, page: ft.Page, email: str):
        try:
            emp_id = None
            for eid in self.contact_by_instructor:
                if self.id_matcher.match_id_to_email(eid) == email:
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
            log.error(f"Error looking up instructor: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

    def _start_semester_deployment(
        self, page: ft.Page, message_template: str, batch_size: int
    ):
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
            log.error(f"Error starting deployment: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

    def _execute_deployment(
        self, page: ft.Page, instructors: list, message_template: str, batch_size: int
    ):
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
                            ok = bool(
                                self.email_sender.send(
                                    instructor["email"], subject, message
                                )
                            )
                        except Exception as e:
                            log.error(
                                f"Email send failed to {instructor['email']}: {str(e)}"
                            )
                            failed.append(instructor["email"])

                    else:  # dev mode
                        ok = True
                        log.info(
                            f"DEV MODE: Would have sent email to {instructor['email']}"
                        )
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
                1
                for emp_id in self.contact_by_instructor
                if self.id_matcher.match_id_to_email(emp_id)
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
                summary += "\nFailed recipients:\n" + "\n".join(
                    failed[:MAX_FAILED_DISPLAY]
                )
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
            log.error(f"Error executing deployment: {str(e)}")
            self._show_snack(page, f"Error: {str(e)}")

    # ---------- UI ----------

    def main(self, page: ft.Page):
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
            selected_dates: dict[str, Optional[ft.DateTimeValue]] = {
                "start": None,
                "end": None,
            }

            # Display for selected date range
            date_range_display = ft.Text(
                "Date range: Current semester (default)",
                size=12,
                color=ft.Colors.BLUE_GREY_700,
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
                update_date_display()
                page.update()

            def sync_date_range_from_picker():
                # In many builds, the final selection is committed on "Save" (dismiss),
                # so read directly from the control's properties.
                selected_dates["start"] = cast(
                    Optional[ft.DateTimeValue],
                    getattr(date_range_picker, "start_value", None),
                )
                selected_dates["end"] = cast(
                    Optional[ft.DateTimeValue],
                    getattr(date_range_picker, "end_value", None),
                )
                update_date_display()
                page.update()

            # ---- Date range picker (single control) ----
            date_range_picker = ft.DateRangePicker(
                on_change=lambda e: sync_date_range_from_picker(),
                on_dismiss=lambda e: sync_date_range_from_picker(),
            )
            page.overlay.append(date_range_picker)

            def open_date_range_picker(e):
                date_range_picker.open = True
                page.update()

            # (optional) keep this if referenced elsewhere; otherwise you can delete it
            def handle_date_range_change(e):
                sync_date_range_from_picker()

            message_input = ft.TextField(
                label="Message template",
                value=default_room_contact_message,
                multiline=True,
                min_lines=4,
                max_lines=8,
                width=720,
                prefix_icon=ft.Icons.MESSAGE,
            )

            def _get_date_filtered_location_map() -> Optional[dict]:
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
                    self._show_snack(
                        page, "Start date must be before or equal to end date"
                    )
                    return None

                # Convert to inclusive datetime bounds for the data loader
                start_datetime = datetime.combine(_value_to_date(start_dt), time.min)
                end_datetime = datetime.combine(_value_to_date(end_dt), time.max)

                log.info(f"Using date range filter: {start_datetime} to {end_datetime}")
                _, location_map = self._get_aggregated_data_for_date_range(
                    start_datetime, end_datetime
                )
                log.info(
                    f"Filtered location map contains {len(location_map)} locations"
                )
                return location_map

            def on_search(e):
                if not (building_input.value and room_input.value):
                    self._show_snack(page, "Please enter building and room")
                    return

                location_map = _get_date_filtered_location_map()
                if location_map is None:
                    return

                location_key = (
                    f"{building_input.value.upper()} {room_input.value.upper()}"
                )
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
                    self._show_snack(
                        page, "No email matches found for instructors in this location"
                    )
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
                if not message_input.value:
                    self._show_snack(page, "Please enter a message")
                    return

                location_map = _get_date_filtered_location_map()
                if location_map is None:
                    return

                location_key = (
                    f"{building_input.value.upper()} {room_input.value.upper()}"
                )
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
                    self._show_snack(page, f"Missing placeholder in message: {str(ke)}")
                    return

                recipients_text = "\n".join(emails)
                confirm_body = (
                    f"Are you sure you want to send this message to these recipients?\n\n"
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
                            size=20,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "Optional: select a date range to filter classes. If not specified, defaults to current semester. Use {location} as a placeholder in the message.",
                            size=12,
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
                        message_input,
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
                            size=20,
                            weight=ft.FontWeight.W_600,
                        ),
                        email_input,
                        ft.FilledButton(
                            "Search", icon=ft.Icons.SEARCH, on_click=on_search
                        ),
                    ],
                    spacing=16,
                ),
                padding=ft.Padding.all(16),
            )

        def build_view_deployment() -> ft.Control:
            already_contacted_text = ft.Text(
                f"Already contacted: {self._get_already_contacted_count()}", size=12
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
                    self._start_semester_deployment(
                        page, message_input.value, batch_size
                    )
                except ValueError as ve:
                    self._show_snack(page, f"Invalid batch size: {str(ve)}")

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
                padding=ft.Padding.all(16),
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

                save_path = await ft.FilePicker().save_file(
                    file_name="contact_history.json"
                )
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
                        ft.Text("Contact History", size=18, weight=ft.FontWeight.W_500),
                        ft.Text(
                            "Download the contact history JSON file to view all contacted instructors.",
                            size=12,
                        ),
                        ft.FilledButton(
                            content="Download Contact History",
                            icon=ft.Icons.DOWNLOAD,
                            on_click=on_download_history,
                        ),
                        ft.Divider(),
                        ft.Text("Test Email", size=18, weight=ft.FontWeight.W_500),
                        ft.Text(
                            "Send a test email with server diagnostic information.",
                            size=12,
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
                    label="By classroom",
                ),
                ft.NavigationRailDestination(
                    icon=ft.Icons.PERSON_SEARCH_OUTLINED,
                    selected_icon=ft.Icons.PERSON_SEARCH,
                    label="By instructor",
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
                ft.NavigationBarDestination(
                    icon=ft.Icons.MEETING_ROOM, label="Classroom"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.PERSON_SEARCH, label="Instructor"
                ),
                ft.NavigationBarDestination(
                    icon=ft.Icons.ROCKET_LAUNCH, label="Deploy"
                ),
                ft.NavigationBarDestination(icon=ft.Icons.BUILD, label="Utility"),
            ],
        )

        def set_view(index: int):
            nonlocal selected_index
            selected_index = index
            rail.selected_index = index
            bar.selected_index = index
            content_host.content = views[
                index
            ]()  # rebuild view to keep controls fresh/simple
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
    app = InstructorContactSystem()
    ft.run(app.main, port=8080, view=ft.AppView.WEB_BROWSER)
