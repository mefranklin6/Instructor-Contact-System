"""Flet UI for the Instructor Contact System.

This module contains only UI code and delegates all business logic to
`InstructorContactSystemCore`.
"""

from datetime import date, datetime, time
import json
import logging as log
from typing import cast

import flet as ft

from src.core.system import InstructorContactSystemCore


class InstructorContactFletApp:
    """Flet UI wrapper that renders views and calls the core layer."""

    def __init__(
        self,
        *,
        core: InstructorContactSystemCore,
        default_room_contact_subject: str,
        default_room_contact_message: str,
        default_semester_start_subject: str,
        default_semester_start_message: str,
        logging_level: str,
    ) -> None:
        """Create the UI wrapper.

        Parameters
        ----------
        core:
            Initialized core system instance.
        default_*:
            Default subject/message templates shown in the UI.
        logging_level:
            Used for diagnostics in test emails.
        """
        self.core = core
        self.default_room_contact_subject = default_room_contact_subject
        self.default_room_contact_message = default_room_contact_message
        self.default_semester_start_subject = default_semester_start_subject
        self.default_semester_start_message = default_semester_start_message
        self.logging_level = logging_level

        self._deployment_already_contacted_text: ft.Text | None = None

    # ---------- Flet helpers ----------

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

    # ---------- UI ----------

    def main(self, page: ft.Page):
        """Build and display the main Flet UI."""
        page.title = "Instructor Contact System"
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.padding = 0
        page.window.width = 960
        page.window.height = 720

        page.appbar = ft.AppBar(
            title=ft.Text("Instructor Contact System"),
            center_title=False,
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

            selected_dates: dict[str, ft.DateTimeValue | None] = {
                "start": None,
                "end": None,
            }

            date_range_display = ft.Text(
                "Date range: Current semester (default)",
                size=16,
            )

            def _value_to_date(v: ft.DateTimeValue) -> date:
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
                try:
                    date_range_picker.start_value = None
                    date_range_picker.end_value = None
                except Exception:
                    pass
                update_date_display()
                page.update()

            def sync_date_range_from_picker():
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

            date_range_picker = classroom_date_range_picker
            date_range_picker.on_change = lambda e: sync_date_range_from_picker()
            date_range_picker.on_dismiss = lambda e: sync_date_range_from_picker()

            def open_date_range_picker(e):
                date_range_picker.open = True
                page.update()

            subject_input = ft.TextField(
                label="Subject",
                value=self.default_room_contact_subject,
                width=720,
                prefix_icon=ft.Icons.SUBJECT,
            )

            message_input = ft.TextField(
                label="Message template",
                value=self.default_room_contact_message,
                multiline=True,
                min_lines=4,
                max_lines=8,
                width=720,
                prefix_icon=ft.Icons.MESSAGE,
            )

            def _get_date_filtered_location_map() -> dict | None:
                start_dt = selected_dates["start"]
                end_dt = selected_dates["end"]

                if not start_dt and not end_dt:
                    log.debug("No date range selected, using current semester data")
                    _, location_map = self.core.get_aggregated_data_for_date_range()
                    return location_map

                if not start_dt or not end_dt:
                    self._show_snack(
                        page,
                        "Please provide both start and end dates, or clear to use current semester",
                    )
                    return None

                if _value_to_date(start_dt) > _value_to_date(end_dt):
                    self._show_snack(page, "Start date must be before or equal to end date")
                    return None

                start_datetime = datetime.combine(_value_to_date(start_dt), time.min)
                end_datetime = datetime.combine(_value_to_date(end_dt), time.max)

                log.info(f"Using date range filter: {start_datetime} to {end_datetime}")
                _, location_map = self.core.get_aggregated_data_for_date_range(start_datetime, end_datetime)
                log.info(f"Filtered location map contains {len(location_map)} locations")
                return location_map

            def on_search(e):
                if not (building_input.value and room_input.value):
                    self._show_snack(page, "Please enter building and room")
                    return

                location_map = _get_date_filtered_location_map()
                if location_map is None:
                    return

                try:
                    emails = self.core.lookup_classroom_emails(
                        building=building_input.value,
                        room=room_input.value,
                        location_map=location_map,
                    )
                except KeyError as ke:
                    self._show_snack(page, str(ke))
                    return
                except Exception as ex:
                    self._show_snack(page, f"Error: {ex!s}")
                    return

                location_key = f"{building_input.value.upper()} {room_input.value.upper()}"
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
                    email = self.core.id_matcher.match_id_to_email(emp_id)
                    if email:
                        emails.append(email)

                emails = self.core.dedupe_emails(emails)

                if not emails:
                    self._show_snack(page, "No email matches found for instructors in this location")
                    return

                try:
                    rendered_message = message_input.value.format(location=location_key)
                except KeyError:
                    self._show_snack(page, f"Missing placeholder in message: {kes}")
                    return

                recipients_text = "\n".join(emails)
                confirm_body = (
                    f"Are you sure you want to send this message to these recipients?\n\n"
                    f"Subject:\n{subject_input.value}\n\n"
                    f"Message:\n{rendered_message}\n\n"
                    f"Recipients ({len(emails)}):\n{recipients_text}"
                )

                def do_send(_e):
                    self._close_dialog(page)
                    try:
                        result = self.core.send_message_to_classroom(
                            building=building_input.value,
                            room=room_input.value,
                            subject=subject_input.value,
                            message_template=message_input.value,
                            location_map=location_map,
                        )
                    except KeyError as ke:
                        self._show_snack(page, f"Error: {ke}")
                        return
                    except Exception as ex:
                        self._show_snack(page, f"Error: {ex}")
                        return

                    summary = f"""Classroom Message Sent

Location: {result.location_key}
Sent: {result.sent}
Failed: {len(result.failed)}
"""
                    if result.failed:
                        summary += "\nFailed recipients:\n" + "\n".join(
                            result.failed[: self.core.max_failed_display]
                        )
                        if len(result.failed) > self.core.max_failed_display:
                            summary += f"\n...and {len(result.failed) - self.core.max_failed_display} more"

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
                            on_click=do_send,
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
                try:
                    locations = self.core.lookup_instructor_locations(email=email_input.value or "")
                except Exception as ex:
                    self._show_snack(page, f"Error: {ex!s}")
                    return

                dialog = self._create_copyable_dialog(
                    page,
                    f"Classes for {email_input.value}",
                    "\n".join(locations),
                )
                page.show_dialog(dialog)
                page.update()

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
                f"Already contacted: {self.core.get_already_contacted_count()}",
                size=16,
            )
            self._deployment_already_contacted_text = already_contacted_text

            message_input = ft.TextField(
                label="Message template",
                value=self.default_semester_start_message,
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

                    instructors = self.core.compute_semester_deployment_candidates()
                    total = len(instructors)
                    already_contacted = len(self.core.contacted_instructors)

                    body = f"""Semester Deployment Summary

Total instructors to contact: {total}
Already contacted: {already_contacted}
Batch size: {batch_size}

Message template includes instructor locations via {{locations}}.
"""

                    def do_send(_e):
                        self._close_dialog(page)
                        try:
                            result = self.core.execute_deployment(
                                instructors=instructors,
                                message_template=message_input.value,
                                batch_size=batch_size,
                                subject=self.default_semester_start_subject,
                            )
                        except Exception as ex:
                            self._show_snack(page, f"Error: {ex!s}")
                            return

                        if self._deployment_already_contacted_text is not None:
                            self._deployment_already_contacted_text.value = (
                                f"Already contacted: {result.total_contacted}"
                            )

                        summary = f"""Deployment Progress

Contacted this batch: {result.contacted_this_batch}
Total contacted: {result.total_contacted}
Remaining: {result.remaining}
Failed this batch: {len(result.failed)}

Progress: {result.total_contacted}/{result.total_instructors}
"""

                        if result.failed:
                            summary += "\nFailed recipients:\n" + "\n".join(
                                result.failed[: self.core.max_failed_display]
                            )
                            if len(result.failed) > self.core.max_failed_display:
                                summary += (
                                    f"\n...and {len(result.failed) - self.core.max_failed_display} more"
                                )

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

                    dialog = ft.AlertDialog(
                        title=ft.Text("Semester Deployment"),
                        content=ft.Container(ft.Text(body), padding=ft.Padding.all(8)),
                        actions=[
                            ft.FilledButton(
                                "Send",
                                icon=ft.Icons.SEND,
                                on_click=do_send,
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

                except ValueError as ve:
                    self._show_snack(page, f"Invalid batch size: {ve}")
                except Exception as ex:
                    self._show_snack(page, f"Error: {ex}")

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
                data = self.core.get_contact_history_dict()
                content_bytes = json.dumps(data, indent=2).encode("utf-8")

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

            test_email_input = ft.TextField(
                label="Test Email Address",
                width=560,
                prefix_icon=ft.Icons.EMAIL,
                keyboard_type=ft.KeyboardType.EMAIL,
                hint_text="Enter email to receive test message",
            )

            def on_send_test_email(e):
                try:
                    msg = self.core.send_test_email(
                        email=(test_email_input.value or "").strip(),
                        logging_level=self.logging_level,
                    )
                    self._show_snack(page, msg)
                except Exception as ex:
                    self._show_snack(page, f"Error: {ex!s}")

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

        views = [
            build_view_by_classroom,
            build_view_by_instructor,
            build_view_deployment,
            build_view_utility,
        ]

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
            content_host.content = views[index]()
            page.update()

        def on_rail_change(e):
            set_view(rail.selected_index or 0)

        def on_bar_change(e):
            set_view(bar.selected_index or 0)

        rail.on_change = on_rail_change
        bar.on_change = on_bar_change

        def apply_responsive_layout():
            wide = (page.window.width or 0) >= 900
            rail.visible = wide
            bar.visible = not wide
            page.update()

        def on_resized(e):
            apply_responsive_layout()

        page.on_resize = on_resized

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
        set_view(0)
        apply_responsive_layout()
