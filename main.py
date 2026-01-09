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
from src.data_loader import data_loader

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
            import src.chico_supported_locations.parser as slp

    def main(self, page: ft.Page):
        page.title = "Instructor Contact System"
        page.add(ft.Text("Hello World!"))


if __name__ == "__main__":
    pass

    # ---- Test for SupportedLocationsParser module ----
    log.warning("Testing SupportedLocationsParser module...")
    import src.chico_supported_locations.parser as slp

    parser = slp.SupportedLocationsParser("Supported Locations.csv")
    locations = parser.run()
    # print(locations)

    # ---- Test for DataLoader module ----
    log.warning("Testing DataLoader module...")
    loader = data_loader.DataLoader(
        file_path="FacilitiesLinkClassScheduleDaily.csv", supported_locations=locations
    )
    date = datetime(2025, 10, 1)
    df = loader.semester_data(date)
    df.to_csv("test_output.csv", index=False)

    # # ---- Test for Aggregator module ----
    log.warning("Testing Aggregator module...")
    import src.aggregation.aggregator as agg
    import json

    aggregator = agg.Aggregator(df=df)
    contact_dict = aggregator.by_instructor()

    # Save as JSON
    with open("aggregated_output.json", "w") as f:
        json.dump(contact_dict, f, indent=2)

    print(f"\nFound {len(contact_dict)} instructors")

    # ---- Test for Matcher module ----
    log.warning("Testing Matcher module...")
    import src.id_username_matcher.matcher as matcher

    id_matcher = matcher.Matcher(csv_file_path="zoomus_users (1).csv")
    email_contact_dict = id_matcher.match_id_to_email(contact_dict)

    # Save email-based output
    with open("aggregated_output_with_emails.json", "w") as f:
        json.dump(email_contact_dict, f, indent=2)

    print(f"\nMatched {len(email_contact_dict)} instructors with emails")
    print(f"Sample output (first 3 instructors with emails):")
    for i, (email, locations) in enumerate(list(email_contact_dict.items())[:3]):
        print(f"  {email}: {locations}")

    b = aggregator.by_location()
    print(f"Found {len(b)} locations")
    for location, instructors in list(b.items()):
        print(f"{location}: {instructors}")

    # app = InstructorContactSystem()
    # ft.run(target=app.main, port=8080, view=ft.AppView.WEB_BROWSER)
