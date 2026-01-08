"""
This is the main entry file

This file should:
- Import and instantiate the individual modules
- Run Flet
"""

import os

import flet as ft

from src import utils


class InstructorContactSystem:
    def __init__(self):
        self.logging_level = os.getenv("LOGGING_LEVEL", "DEBUG").upper()

    def main(self, page: ft.Page):
        page.title = "Instructor Contact System"
        page.add(ft.Text("Hello World!"))


if __name__ == "__main__":
    app = InstructorContactSystem()
    ft.app(target=app.main, port=8080, view=ft.AppView.WEB_BROWSER)
