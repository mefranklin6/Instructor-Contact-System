import json
import logging as log
import os
from datetime import datetime

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

SUPPORTED_LOCATIONS = os.getenv("SUPPORTED_LOCATIONS", "none")
if SUPPORTED_LOCATIONS == "Chico":
    from src import chico_supported_location_parser as slp
else:
    slp = None
log.info(f"Using supported locations mode: {SUPPORTED_LOCATIONS}")

# If True, disables the actual sending of emails.
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO").upper()
log.basicConfig(
    level=getattr(log, LOGGING_LEVEL, log.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
print(f"Logging level set to {LOGGING_LEVEL}")

if DEV_MODE:
    log.warning(
        "System is in Dev Mode. Emails will not be sent. Change by setting DEV_MODE on main.py"
    )
else:
    log.info("System is in production mode. Emails will be sent")


class InstructorContactSystem:
    def __init__(self):
        self.supported_locations = None
        self.loader = None
        self.aggregator = None
        self.id_matcher = None
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

    def _initialize_data(self):
        """Initialize data loaders and aggregators."""
        try:
            if slp and SUPPORTED_LOCATIONS == "Chico":
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
            exit(1)

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
        return False

    def _get_contact_file_path(self) -> str:
        """Get the path to the contact history file.

        Returns /data/contact_history.json when in Docker (for persistent volume),
        or ./contact_history.json when running locally.
        """
        if self.is_in_docker:
            return "/data/contact_history.json"
        return "contact_history.json"

    # ---------- App logic ----------

    def _load_contact_history(self):
        contact_file = self._get_contact_file_path()
        if os.path.exists(contact_file):
            with open(contact_file, "r") as f:
                self.contacted_instructors = json.load(f)
        else:
            self.contacted_instructors = {}

    def _was_contacted_for_semester_start(self, email: str) -> bool:
        """Check if an instructor was contacted for 'start of semester' deployment."""
        if email not in self.contacted_instructors:
            return False
        contact_info = self.contacted_instructors[email]
        # Check if they have the top-level contact_type field set to "start of semester"
        return contact_info.get("contact_type") == "start of semester"

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

    def _send_message_to_classroom(
        self, page: ft.Page, building: str, room: str, message_template: str
    ):
        try:
            location_key = f"{building.upper()} {room.upper()}"

            if location_key not in self.contact_by_location:
                self._show_snack(page, f"No classes found in {location_key}")
                return

            emp_ids = self.contact_by_location[location_key]
            emails = []
            for emp_id in emp_ids:
                email = self.id_matcher.match_id_to_email(emp_id)  # type: ignore
                if email:
                    emails.append(email)

            # de-dupe but keep stable order
            seen = set()
            emails = [e for e in emails if not (e in seen or seen.add(e))]

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
                summary += "\nFailed recipients:\n" + "\n".join(failed[:50])
                if len(failed) > 50:
                    summary += f"\n...and {len(failed) - 50} more"

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
                self.id_matcher.match_id_to_email(emp_id)  # type: ignore
                for emp_id in emp_ids
                if self.id_matcher.match_id_to_email(emp_id)  # type: ignore
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
                if self.id_matcher.match_id_to_email(eid) == email:  # type: ignore
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
                email = self.id_matcher.match_id_to_email(emp_id)  # type: ignore
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
                        else:
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
                if self.id_matcher.match_id_to_email(emp_id)  # type: ignore
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
                summary += "\nFailed recipients:\n" + "\n".join(failed[:50])
                if len(failed) > 50:
                    summary += f"\n...and {len(failed) - 50} more"

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

            message_input = ft.TextField(
                label="Message template",
                value=default_room_contact_message,
                multiline=True,
                min_lines=4,
                max_lines=8,
                width=720,
                prefix_icon=ft.Icons.MESSAGE,
            )

            def on_search(e):
                if building_input.value and room_input.value:
                    self._lookup_classroom(page, building_input.value, room_input.value)
                else:
                    self._show_snack(page, "Please enter building and room")

            def on_send(e):
                if not (building_input.value and room_input.value):
                    self._show_snack(page, "Please enter building and room")
                    return
                if not message_input.value:
                    self._show_snack(page, "Please enter a message")
                    return

                location_key = (
                    f"{building_input.value.upper()} {room_input.value.upper()}"
                )
                if location_key not in self.contact_by_location:
                    self._show_snack(page, f"No classes found in {location_key}")
                    return

                emp_ids = self.contact_by_location[location_key]
                emails = []
                for emp_id in emp_ids:
                    email = self.id_matcher.match_id_to_email(emp_id)  # type: ignore
                    if email:
                        emails.append(email)

                seen = set()
                emails = [
                    email for email in emails if not (email in seen or seen.add(email))
                ]

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
                            "Optional: write a message and send it to all instructors teaching in that classroom. Use {location} as a placeholder.",
                            size=12,
                        ),
                        ft.Row([building_input, room_input], spacing=12, wrap=True),
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

        views = [
            build_view_by_classroom,
            build_view_by_instructor,
            build_view_deployment,
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
    print("Started...")
    app = InstructorContactSystem()
    ft.run(app.main, port=8080, view=ft.AppView.WEB_BROWSER)
