import logging as log
import os
from datetime import datetime
from typing import Optional

import pandas as pd

from src.utils import csv_to_dataframe, raise_error_window


class DataLoader:
    """
    Args:
        fl_file_path: The calendar CSV that gets exported to FacilitiesLink

        supported_locations: optional list of tuples (building, room) you want included.
        If used, any location not in the list will be filtered out
    """

    def __init__(
        self,
        fl_file_path: str,
        supported_locations: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        self.file_path = fl_file_path
        self.supported_locations = supported_locations

    def semester_data(self, date: datetime) -> pd.DataFrame:
        """
        Load and filter data to include only classes within the semester of the given date.
        Args:
            date (datetime): A date within the semester to filter for.
        Returns:
            pd.DataFrame: The filtered DataFrame.
        """
        log.debug(f"Loading data from {self.file_path}")
        df = self._load_and_clean()
        df = self._filter_to_semester(df, date)
        return df

    def range_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        log.error("range_data method not yet implemented.")  # TODO
        return pd.DataFrame()

    def _load_and_clean(self) -> pd.DataFrame:
        df = csv_to_dataframe(self.file_path)
        df = self._clean_dataframe(df)
        df = self._convert_dates(df)
        if self.supported_locations:
            df = self._filter_to_supported_locations(df)
        return df

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        - Removes rows with missing values in critical columns.
        - Excludes online courses.
        - Excludes courses with 'TBA' schedules.
        """
        try:
            initial_rows = len(df)
            required_columns = [
                "INSTRUCTOR1_EMPLID",
                "CLASS_START_DATE",
                "CLASS_END_DATE",
                "START_TIME1",
                "END_TIME1",
                "DAYS1",
                "BUILDING",
                "ROOM",
            ]
            filtered_df = df.dropna(subset=required_columns)
            filtered_df = filtered_df[filtered_df["ROOM"] != "WWW"]
            filtered_df = filtered_df[filtered_df["BUILDING"] != "WWW"]
            filtered_df = filtered_df[filtered_df["ROOM"] != "ONLINE"]
            filtered_df = filtered_df[filtered_df["BUILDING"] != "ONLINE"]
            filtered_df = filtered_df[filtered_df["DAYS1"] != "TBA"]
            log.debug(
                f"{initial_rows - len(filtered_df)} rows initially cleansed. Initial size: {initial_rows}, Filtered size: {len(filtered_df)}"
            )
            return filtered_df
        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering the data: {str(e)}",
                title="Filtering Error",
            )
            log.error(f"Filtering error: {str(e)}")
            return pd.DataFrame()

    def _convert_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert date columns from string format to datetime objects."""
        try:
            df["CLASS_START_DATE"] = pd.to_datetime(
                df["CLASS_START_DATE"], format="%d-%b-%y"
            )
            df["CLASS_END_DATE"] = pd.to_datetime(
                df["CLASS_END_DATE"], format="%d-%b-%y"
            )
            return df
        except Exception as e:
            raise_error_window(
                f"An error occurred while converting dates: {str(e)}",
                title="Date Conversion Error",
            )
            log.error(f"Date conversion error: {str(e)}")
            return df

    def _filter_to_semester(self, df: pd.DataFrame, date: datetime) -> pd.DataFrame:
        try:
            before_rows = len(df)
            target_date = pd.to_datetime(date).normalize()  # Strip time component
            df = df[
                (df["CLASS_START_DATE"] <= target_date)
                & (df["CLASS_END_DATE"] >= target_date)
            ]

            # All classes within a semester should have the same TERM value
            term_is_all_the_same = df["TERM"].nunique() <= 1
            if term_is_all_the_same:
                log.debug(f"All rows have the same TERM value: {df['TERM'].iloc[0]}")
            else:
                log.warning(f"Multiple TERM values found: {df['TERM'].unique()}")

            log.debug(
                f"Filtered to current semester. Rows before: {before_rows}, Rows after: {len(df)}"
            )
            return df
        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering to the current semester: {str(e)}",
                title="Semester Filtering Error",
            )
            log.error(f"Semester filtering error: {str(e)}")
            return pd.DataFrame()

    def _filter_to_supported_locations(self, df: pd.DataFrame) -> pd.DataFrame:
        try:
            initial_rows = len(df)

            supported_set = set(self.supported_locations or [])
            df["_location_tuple"] = list(zip(df["BUILDING"], df["ROOM"]))
            df = df[df["_location_tuple"].isin(supported_set)]
            df = df.drop(columns=["_location_tuple"])
            log.debug(
                f"Filtered to supported locations. Rows before: {initial_rows}, Rows after: {len(df)}"
            )
            return df

        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering to supported locations: {str(e)}",
                title="Supported Locations Filtering Error",
            )
            log.error(f"Supported locations filtering error: {str(e)}")
            return pd.DataFrame()
