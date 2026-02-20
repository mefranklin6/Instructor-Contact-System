"""
Chico Supported Locations Parser.

This module is specific to Chico State's 'Supported Locations' Sharepoint export.
"""

import logging as log
import re

from src.utils import csv_to_dataframe


class SupportedLocationsParser:
    """Optional Chico-specific Sharepoint CSV parser."""

    def __init__(self, file_path: str) -> None:
        """Initialize with the path to the Supported Locations CSV export."""
        self.file_path = file_path
        # Match 3-4 uppercase letters (building), optional whitespace/dash, then rest (room)
        self.pattern = re.compile(r"^([A-Z]{3,4})[\s\-]*(.+)$")

    def run(self) -> list[tuple[str, str]]:
        """Return a list of (building, room) tuples for CTS supported locations."""
        result: list[tuple[str, str]] = []
        df = csv_to_dataframe(self.file_path)
        if df is None:
            log.error("Failed to load supported locations CSV.")
            return []
        df = df[df["Contact"] == "CTS"]
        building_room = df["Room"].tolist()

        for entry in building_room:
            if entry is None or not isinstance(entry, str):
                continue

            entry = entry.upper().strip()
            match = self.pattern.match(entry)

            if match:
                building = match.group(1)
                room = match.group(2).strip()
                result.append((building, room))

        return result


__all__ = ["SupportedLocationsParser"]
