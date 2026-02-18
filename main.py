"""Entrypoint for running the Instructor Contact System (Flet UI)."""

import logging as log
import os

from dotenv import load_dotenv
import flet as ft

from src.core.settings import Settings
from src.core.system import InstructorContactSystemCore
from src.ui.flet_app import InstructorContactFletApp


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


settings = Settings.from_env()
log.info(f"Using supported locations mode: {settings.supported_locations_mode}")
log.info(f"Using ID to email module: {settings.id_to_email_module}")
log.info(f"Using schedule module: {settings.schedule_module}")

if settings.dev_mode:
    log.warning("System is in Dev Mode. Emails will not be sent. Change by setting DEV_MODE in .env")
else:
    log.info("System is in production mode. Emails will be sent")


if __name__ == "__main__":
    try:
        core = InstructorContactSystemCore(in_docker=IN_DOCKER, settings=settings)
        ui = InstructorContactFletApp(
            core=core,
            default_room_contact_subject=default_room_contact_subject,
            default_room_contact_message=default_room_contact_message,
            default_semester_start_subject=default_semester_start_subject,
            default_semester_start_message=default_semester_start_message,
            logging_level=LOGGING_LEVEL,
        )
        ft.run(ui.main, port=8080, view=ft.AppView.WEB_BROWSER)
    except Exception as e:
        log.error(f"Fatal error starting app: {e!s}")
        if not IN_DOCKER:
            from time import sleep

            sleep(15)
        raise
