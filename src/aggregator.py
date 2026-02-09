import logging as log

import pandas as pd


class Aggregator:
    """
    param df: The cleansed dataframe derived from the FacilitiesLink schedule CSV
    """
    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df

    def by_instructor(self) -> dict:
        """Group by instructor with aggregated course info.

        Returns a dictionary mapping INSTRUCTOR1_EMPLID to a list of unique building_room combinations.
        """
        # Create a combined building_room column
        df = self.df.copy()
        df["building_room"] = (
            df["BUILDING"]
            .fillna("")
            .astype(str)
            .str.cat(df["ROOM"].fillna("").astype(str), sep=" ")
        )

        # Group by INSTRUCTOR1_EMPLID and get unique building_room values
        result = {}
        for emplid, group in df.groupby("INSTRUCTOR1_EMPLID"):
            unique_locations = sorted(group["building_room"].unique().tolist())
            result[emplid] = unique_locations

        return result

    def by_location(self) -> dict:
        """Group by location with aggregated instructor info.

        Returns a dictionary mapping building_room to a list of unique INSTRUCTOR1_EMPLID values.
        """
        # Create a combined building_room column
        df = self.df.copy()
        df["building_room"] = (
            df["BUILDING"]
            .fillna("")
            .astype(str)
            .str.cat(df["ROOM"].fillna("").astype(str), sep=" ")
        )

        # Group by building_room and get unique INSTRUCTOR1_EMPLID values
        result = {}
        for location, group in df.groupby("building_room"):
            unique_instructors = sorted(group["INSTRUCTOR1_EMPLID"].unique().tolist())
            result[location] = unique_instructors

        return result
