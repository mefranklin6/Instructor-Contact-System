"""
This is the main entry file

This file should:
- Import the individual modules
- Run Flet
"""

import flet as ft


class InstructorContactSystem:
    def __init__(self):
        pass

    def main(self, page: ft.Page):
        page.title = "Instructor Contact System"
        page.add(ft.Text("Hello World!"))


if __name__ == "__main__":
    app = InstructorContactSystem()
    ft.app(target=app.main, port=8080, view=ft.AppView.WEB_BROWSER)
