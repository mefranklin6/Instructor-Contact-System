"""Schedule aggregation helpers.

Core expects schedule loaders to return a pandas DataFrame with these columns:

- `BUILDING`
- `ROOM`
- `INSTRUCTOR1_EMPLID`

Schedule loader plugins are responsible for normalizing their source data into
this schema. The aggregator then builds convenient lookup maps.
"""

import pandas as pd


class Aggregator:
    """Aggregate normalized schedule data into lookup maps."""

    def __init__(self, *, df: pd.DataFrame) -> None:
        """Initialize with a normalized schedule DataFrame."""
        self.df = df

    def by_instructor(self) -> dict[str, list[str]]:
        """Return `emplid -> ["BUILDING ROOM", ...]` (unique, sorted)."""
        df = self.df.copy()
        df["building_room"] = (
            df["BUILDING"].fillna("").astype(str).str.cat(df["ROOM"].fillna("").astype(str), sep=" ")
        )

        result: dict[str, list[str]] = {}
        for emplid, group in df.groupby("INSTRUCTOR1_EMPLID"):
            result[str(emplid)] = sorted(group["building_room"].unique().tolist())
        return result

    def by_location(self) -> dict[str, list[str]]:
        """Return `"BUILDING ROOM" -> [emplid, ...]` (unique, sorted)."""
        df = self.df.copy()
        df["building_room"] = (
            df["BUILDING"].fillna("").astype(str).str.cat(df["ROOM"].fillna("").astype(str), sep=" ")
        )

        result: dict[str, list[str]] = {}
        for location, group in df.groupby("building_room"):
            result[str(location)] = sorted(group["INSTRUCTOR1_EMPLID"].astype(str).unique().tolist())
        return result
