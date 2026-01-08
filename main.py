"""
This is the main entry file

This file should:
- Import and instantiate the individual modules
- Run Flet
"""

import logging as log
import os

import flet as ft

from src import utils

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "DEBUG").upper()
log.basicConfig(
    level=getattr(log, LOGGING_LEVEL, log.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


class InstructorContactSystem:
    def __init__(self):
        pass

    def main(self, page: ft.Page):
        page.title = "Instructor Contact System"
        page.add(ft.Text("Hello World!"))


if __name__ == "__main__":
    import os

    import src.data_loader.data_loader as data_loader

    log.warning("Testing!!!")
    loader = data_loader.DataLoader(file_path="FacilitiesLinkClassScheduleDaily.csv")
    df = loader.load_data()

    app = InstructorContactSystem()
    ft.run(target=app.main, port=8080, view=ft.AppView.WEB_BROWSER)
