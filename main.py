"""
Main entry file

- Imports and instantiates individual modules
- Runs Flet
"""

import logging as log
import os
from datetime import datetime
import json

import flet as ft

from src import aggregator as agg

SUPPORTED_LOCATIONS = os.getenv("SUPPORTED_LOCATIONS", "Chico")
if SUPPORTED_LOCATIONS == "Chico":
    from src import chico_supported_location_parser as slp
else:
    slp = None

from src import data_loader
from src import id_matcher_from_zoom_users as matcher

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "INFO").upper()
log.basicConfig(
    level=getattr(log, LOGGING_LEVEL, log.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
print(f"Logging level set to {LOGGING_LEVEL}")


class InstructorContactSystem:
    def __init__(self):
        self.supported_locations_filter = False
        self.supported_locations = None
        self.loader = None
        self.aggregator = None
        self.id_matcher = None
        self.contact_by_instructor = {}
        self.contact_by_location = {}
        self.contacted_instructors = {}

        self._initialize_data()

    def _initialize_data(self):
        """Initialize data loaders and aggregators."""
        try:
            if os.getenv("SUPPORTED_LOCATIONS_FILE_PATH"):
                self.supported_locations_filter = True
                if slp:
                    parser = slp.SupportedLocationsParser("Supported Locations.csv")
                    self.supported_locations = parser.run()

            fl_file = os.getenv("FL_FILE_PATH", "FacilitiesLinkClassScheduleDaily.csv")
            self.loader = data_loader.DataLoader(
                fl_file_path=fl_file,
                supported_locations=self.supported_locations,
            )

            current_date = datetime.now()
            df = self.loader.semester_data(current_date)

            self.aggregator = agg.Aggregator(df=df)
            self.contact_by_instructor = self.aggregator.by_instructor()
            self.contact_by_location = self.aggregator.by_location()

            zoom_file = os.getenv("ZOOM_FILE_PATH", "zoomus_users.csv")
            self.id_matcher = matcher.Matcher(csv_file_path=zoom_file)

            log.info("Data initialization successful")
        except Exception as e:
            log.error(f"Error initializing data: {str(e)}")

    # ---------- Flet 0.80.x helpers ----------

    def _show_snack(self, page: ft.Page, message: str):
        page.show_dialog(ft.SnackBar(ft.Text(message)))
        page.update()

    def _close_dialog(self, page: ft.Page):
        page.pop_dialog()
        page.update()

    def _create_copyable_dialog(
        self, page: ft.Page, title: str, content: str
    ) -> ft.AlertDialog:
        def copy_to_clipboard(e):
            page.set_clipboard(content)
            self._show_snack(page, "Copied to clipboard!")

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
                padding=ft.padding.all(12),
            ),
            actions=[
                ft.FilledButton(
                    "Copy all",
                    icon=ft.Icons.CONTENT_COPY,
                    on_click=copy_to_clipboard,
                ),
                ft.TextButton("Close", on_click=lambda e: self._close_dialog(page)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # ---------- App logic ----------

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
            contact_file = "contacted_instructors.json"
            if os.path.exists(contact_file):
                with open(contact_file, "r") as f:
                    self.contacted_instructors = json.load(f)
            else:
                self.contacted_instructors = {}

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
                content=ft.Container(ft.Text(body), padding=ft.padding.all(8)),
                actions=[
                    ft.FilledButton(
                        "Proceed",
                        icon=ft.Icons.PLAY_ARROW,
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
            contact_file = "contacted_instructors.json"
            batch_count = 0

            for instructor in instructors[:batch_size]:
                if instructor["email"] not in self.contacted_instructors:
                    locations_str = ", ".join(instructor["locations"])
                    message = message_template.format(locations=locations_str)

                    # TODO: Actually send email here
                    log.warning(
                        f"[SIMULATED] Would send email to {instructor['email']}"
                    )
                    log.warning(message)
                    log.debug(f"Message: {message}")

                    self.contacted_instructors[instructor["email"]] = {
                        "contacted_at": datetime.now().isoformat(),
                        "locations": instructor["locations"],
                        "message": message,
                    }
                    batch_count += 1

            with open(contact_file, "w") as f:
                json.dump(self.contacted_instructors, f, indent=2)

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

Progress: {contacted}/{total_instructors}
"""

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

            def on_search(e):
                if building_input.value and room_input.value:
                    self._lookup_classroom(page, building_input.value, room_input.value)
                else:
                    self._show_snack(page, "Please enter building and room")

            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Lookup instructors by classroom",
                            size=20,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Row([building_input, room_input], spacing=12, wrap=True),
                        ft.FilledButton(
                            "Search", icon=ft.Icons.SEARCH, on_click=on_search
                        ),
                    ],
                    spacing=16,
                ),
                padding=ft.padding.all(16),
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
                padding=ft.padding.all(16),
            )

        def build_view_deployment() -> ft.Control:
            message_input = ft.TextField(
                label="Message template",
                value="Hello, you teach in: {locations}",
                multiline=True,
                min_lines=6,
                max_lines=10,
                width=720,
                prefix_icon=ft.Icons.MESSAGE,
            )
            batch_size_input = ft.TextField(
                label="Batch size",
                value="10",
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
                            size=20,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Text(
                            "Use {locations} as a placeholder for instructor classroom locations.",
                            size=12,
                        ),
                        message_input,
                        ft.Row(
                            [
                                batch_size_input,
                                ft.FilledButton(
                                    "Start deployment",
                                    icon=ft.Icons.SEND,
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
                padding=ft.padding.all(16),
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
                    label="Deployment",
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
