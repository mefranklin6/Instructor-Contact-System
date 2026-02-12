import logging as log
from datetime import datetime, timedelta
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
        self.clean_df = self._load_and_clean()

    def semester_data(self, date: datetime) -> pd.DataFrame:
        """
        Load and filter data to include only classes within the semester of the given date.
        Args:
            date (datetime): A date within the semester to filter for.
        Returns:
            pd.DataFrame: The filtered DataFrame.
        """
        log.debug(f"Loading data from {self.file_path}")
        df = self.clean_df.copy()
        df = self._filter_to_semester(df, date)
        return df

    def range_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Load and filter data to include classes that meet on specific dates within the range.

        Notes:
        - We filter by *actual meeting occurrences* implied by DAYS1 + CLASS_START_DATE/CLASS_END_DATE.
        - We do NOT expand to per-occurrence rows; we keep the original class rows that meet at least once
          in [start_date, end_date].
        """
        try:
            start = pd.to_datetime(start_date).normalize()
            end = pd.to_datetime(end_date).normalize()

            if start > end:
                raise ValueError("start_date must be less than or equal to end_date.")

            log.info(f"Loading data from {self.file_path}")
            log.info(f"Filtering to date range: {start.date()} to {end.date()}")
            df = self.clean_df.copy()

            before_rows = len(df)
            log.info(f"Total rows before date filtering: {before_rows}")

            filtered = self._expand_to_meeting_dates(df, start, end)

            if filtered.empty:
                log.info("No classes meet within the specified date range")
                return pd.DataFrame()

            log.info(
                f"Filtered to date range {start.date()} - {end.date()}. "
                f"Rows before: {before_rows}, Rows after: {len(filtered)}"
            )
            log.info(
                f"Unique locations after filter: {len(filtered.groupby(['BUILDING', 'ROOM']))}"
            )

            return filtered

        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering to date range: {str(e)}",
                title="Range Filtering Error",
            )
            log.error(f"Range filtering error: {str(e)}")
            return pd.DataFrame()

    def _expand_to_meeting_dates(
        self, df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame:
        """
        Filters to class rows that meet at least once within [start_date, end_date],
        using DAYS1 meeting weekdays + class span.

        This does NOT expand to per-occurrence rows; it keeps original class rows.
        """
        # Map day codes to Python weekday numbers (Monday=0, Sunday=6)
        day_map = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}

        # Filter out TBA and empty DAYS1 values
        df = df[
            df["DAYS1"].notna()
            & (df["DAYS1"].astype(str).str.strip() != "")
            & (df["DAYS1"].astype(str).str.upper() != "TBA")
        ].copy()

        if df.empty:
            return pd.DataFrame()

        # Only consider classes whose span overlaps the requested window
        df = df[
            (df["CLASS_START_DATE"] <= end_date) & (df["CLASS_END_DATE"] >= start_date)
        ].copy()
        if df.empty:
            return pd.DataFrame()

        # Per-row search window (intersection of class span and requested range)
        df["search_start"] = df["CLASS_START_DATE"].where(
            df["CLASS_START_DATE"] > start_date, start_date
        )
        df["search_end"] = df["CLASS_END_DATE"].where(
            df["CLASS_END_DATE"] < end_date, end_date
        )

        def parse_days(days_str: str) -> set[int]:
            s = str(days_str).strip().upper()
            return {day_map[ch] for ch in s if ch in day_map}

        df["meeting_weekdays"] = df["DAYS1"].apply(parse_days)
        df = df[df["meeting_weekdays"].apply(bool)].copy()
        if df.empty:
            return pd.DataFrame()

        def meets_in_window(row) -> bool:
            """
            For each meeting weekday, compute the first date >= search_start that has that weekday.
            If any such date is <= search_end, the class meets in the window.
            """
            ss: pd.Timestamp = row["search_start"]
            se: pd.Timestamp = row["search_end"]
            ss_wd = ss.weekday()

            for wd in row["meeting_weekdays"]:
                delta = (wd - ss_wd) % 7
                first = ss + timedelta(days=delta)
                if first <= se:
                    return True
            return False

        mask = df.apply(meets_in_window, axis=1)
        result_df = df.loc[mask].copy()

        return result_df.drop(
            columns=["search_start", "search_end", "meeting_weekdays"]
        )

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

            # Normalize instructor IDs to match Zoom export normalization:
            #  - strip, numeric-only, then zero-pad to 9 digits.
            filtered_df["INSTRUCTOR1_EMPLID"] = (
                filtered_df["INSTRUCTOR1_EMPLID"].astype(str).str.strip()
            )
            filtered_df = filtered_df[
                filtered_df["INSTRUCTOR1_EMPLID"]
                .str.replace(".", "", regex=False)
                .str.isdigit()
            ]
            filtered_df["INSTRUCTOR1_EMPLID"] = (
                filtered_df["INSTRUCTOR1_EMPLID"]
                .astype(str)
                .astype(int)
                .astype(str)
                .str.zfill(9)
            )

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
            # Primary expected format from FacilitiesLink exports
            start = pd.to_datetime(
                df["CLASS_START_DATE"], format="%d-%b-%y", errors="coerce"
            )
            end = pd.to_datetime(
                df["CLASS_END_DATE"], format="%d-%b-%y", errors="coerce"
            )

            # Fallback: let pandas infer format for any rows that didn't parse
            if start.isna().any():
                start_fallback = pd.to_datetime(
                    df.loc[start.isna(), "CLASS_START_DATE"], errors="coerce"
                )
                start.loc[start.isna()] = start_fallback
            if end.isna().any():
                end_fallback = pd.to_datetime(
                    df.loc[end.isna(), "CLASS_END_DATE"], errors="coerce"
                )
                end.loc[end.isna()] = end_fallback

            df["CLASS_START_DATE"] = start
            df["CLASS_END_DATE"] = end

            # If we still have NaTs, fail loudly (downstream logic relies on these)
            if df["CLASS_START_DATE"].isna().any() or df["CLASS_END_DATE"].isna().any():
                bad_start = int(df["CLASS_START_DATE"].isna().sum())
                bad_end = int(df["CLASS_END_DATE"].isna().sum())
                raise ValueError(
                    f"Unparseable dates: CLASS_START_DATE NaT={bad_start}, CLASS_END_DATE NaT={bad_end}"
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
