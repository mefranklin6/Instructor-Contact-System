"""
This is the main entry file

This file should:
- Import and instantiate the individual modules
- Run Flet
"""

import logging as log
import os
from datetime import datetime

import flet as ft

from src import utils
from src import data_loader
from src import chico_supported_location_parser as slp
from src import aggregator as agg
from src import id_matcher_from_zoom_users as matcher

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "DEBUG").upper()
log.basicConfig(
    level=getattr(log, LOGGING_LEVEL, log.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
print(f"Logging level set to {LOGGING_LEVEL}")


class InstructorContactSystem:
    def __init__(self):
        self.supported_locations_filter = False
        if os.getenv("SUPPORTED_LOCATIONS_FILE_PATH"):
            self.supported_locations_filter = True

    def main(self, page: ft.Page):
        page.title = "Instructor Contact System"
        page.add(ft.Text("Hello World!"))


if __name__ == "__main__":
    pass

    # ---- Test for SupportedLocationsParser module ----
    log.warning("Testing SupportedLocationsParser module...")

    parser = slp.SupportedLocationsParser("Supported Locations.csv")
    locations = parser.run()
    # print(locations)

    # ---- Test for DataLoader module ----
    log.warning("Testing DataLoader module...")
    loader = data_loader.DataLoader(
        fl_file_path="FacilitiesLinkClassScheduleDaily.csv",
        supported_locations=locations,
    )
    date = datetime(2026, 1, 22)
    df = loader.semester_data(date)
    df.to_csv("test_output.csv", index=False)

    # # ---- Test for Aggregator module ----
    log.warning("Testing Aggregator module...")
    import json

    aggregator = agg.Aggregator(df=df)
    contact_dict = aggregator.by_instructor()
    # with open("aggregated_output.json", "w") as f:
    #    json.dump(contact_dict, f, indent=2)

    print(f"\nFound {len(contact_dict)} instructors")

    # ---- Test for Matcher module ----
    log.warning("Testing Matcher module...")

    id_matcher = matcher.Matcher(csv_file_path="zoomus_users.csv")
    email_contact_dict = {
        email: locations
        for emp_id, locations in contact_dict.items()
        if (
            email := id_matcher.match_id_to_email(emp_id)
        )  # Only include if email is not empty
    }

    # Save email-based output
    with open("aggregated_output_with_emails.json", "w") as f:
        json.dump(email_contact_dict, f, indent=2)

    print(f"\nMatched {len(email_contact_dict)} instructors with emails")

    # ---- Test for location-based aggregation ----
    log.warning("Testing location-based aggregation...")
    b = aggregator.by_location()
    print(f"Found {len(b)} locations")
    for location, emp_ids in list(b.items()):
        emails = [
            id_matcher.match_id_to_email(emp_id)
            for emp_id in emp_ids
            if id_matcher.match_id_to_email(emp_id)
        ]
        print(f"  {location}: {emails}")

    # app = InstructorContactSystem()
    # ft.run(target=app.main, port=8080, view=ft.AppView.WEB_BROWSER)
