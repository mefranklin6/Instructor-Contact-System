import logging as log
import re

from src.utils import csv_to_dataframe


class SupportedLocationsParser:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        # Match 3-4 uppercase letters (building), optional whitespace/dash, then rest (room)
        # Potential Chico-ism, adjust as needed
        self.pattern = re.compile(r"^([A-Z]{3,4})[\s\-]*(.+)$")

    def run(self) -> list[tuple[str, str]]:
        """Return a list of (building, room) tuples for CTS supported locations."""
        try:
            result: list[tuple[str, str]] = []
            df = csv_to_dataframe(self.file_path)
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
        except Exception as e:
            log.error(f"Error parsing supported locations: {e}")
            return []


if __name__ == "__main__":
    pass
