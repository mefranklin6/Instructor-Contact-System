"""Data loader for FacilitiesLink schedule CSV exports."""

from datetime import datetime, timedelta
import logging as log

import pandas as pd

from src.utils import csv_to_dataframe, raise_error_window


class DataLoader:
    """Load and filter data from a FacilitiesLink schedule CSV export."""

    def __init__(
        self,
        fl_file_path: str,
        supported_locations: list[tuple[str, str]] | None = None,
    ) -> None:
        """Initialize with a FacilitiesLink CSV path and optional location filter."""
        self.file_path = fl_file_path
        self.supported_locations = supported_locations
        self.clean_df = self._load_and_clean()

    def semester_data(self, date: datetime) -> pd.DataFrame | None:
        """Return schedule rows within the semester containing the given date."""
        if self.clean_df is None:
            log.error("Failed to load clean dataframe")
            return pd.DataFrame()

        log.debug(f"Loading data from {self.file_path}")
        df = self.clean_df.copy()
        df = self._filter_to_semester(df, date)
        return df

    def range_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """Return schedule rows that meet at least once within [start_date, end_date]."""
        try:
            if self.clean_df is None:
                log.error("Failed to load clean dataframe")
                return pd.DataFrame()

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
            log.info(f"Unique locations after filter: {len(filtered.groupby(['BUILDING', 'ROOM']))}")

            return filtered

        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering to date range: {e!s}",
                title="Range Filtering Error",
            )
            log.error(f"Range filtering error: {e!s}")
            return pd.DataFrame()

    def _expand_to_meeting_dates(
        self, df: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp
    ) -> pd.DataFrame:
        """Filter to class rows that meet at least once within [start_date, end_date]."""
        day_map = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}

        df = df[
            df["DAYS1"].notna()
            & (df["DAYS1"].astype(str).str.strip() != "")
            & (df["DAYS1"].astype(str).str.upper() != "TBA")
        ].copy()

        if df.empty:
            return pd.DataFrame()

        df = df[(df["CLASS_START_DATE"] <= end_date) & (df["CLASS_END_DATE"] >= start_date)].copy()
        if df.empty:
            return pd.DataFrame()

        df["search_start"] = df["CLASS_START_DATE"].where(df["CLASS_START_DATE"] > start_date, start_date)
        df["search_end"] = df["CLASS_END_DATE"].where(df["CLASS_END_DATE"] < end_date, end_date)

        def parse_days(days_str: str) -> set[int]:
            s = str(days_str).strip().upper()
            return {day_map[ch] for ch in s if ch in day_map}

        df["meeting_weekdays"] = df["DAYS1"].apply(parse_days)
        df = df[df["meeting_weekdays"].apply(bool)].copy()
        if df.empty:
            return pd.DataFrame()

        def meets_in_window(row) -> bool:
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
        return result_df.drop(columns=["search_start", "search_end", "meeting_weekdays"])

    def _load_and_clean(self) -> pd.DataFrame | None:
        df = csv_to_dataframe(self.file_path)
        if df is not None:
            df = self._clean_dataframe(df)
            if df is not None:
                df = self._convert_dates(df)
            if df is not None and self.supported_locations:
                return self._filter_to_supported_locations(df)
            return df
        return None

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """Drop invalid rows and normalize key fields."""
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

            filtered_df["INSTRUCTOR1_EMPLID"] = filtered_df["INSTRUCTOR1_EMPLID"].astype(str).str.strip()
            filtered_df = filtered_df[
                filtered_df["INSTRUCTOR1_EMPLID"].str.replace(".", "", regex=False).str.isdigit()
            ]
            filtered_df["INSTRUCTOR1_EMPLID"] = (
                filtered_df["INSTRUCTOR1_EMPLID"].astype(str).astype(int).astype(str).str.zfill(9)
            )

            log.debug(
                f"{initial_rows - len(filtered_df)} rows initially cleansed. "
                f"Initial size: {initial_rows}, Filtered size: {len(filtered_df)}"
            )
            return filtered_df
        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering the data: {e!s}",
                title="Filtering Error",
            )
            log.error(f"Filtering error: {e!s}")
            return None

    def _convert_dates(self, df: pd.DataFrame) -> pd.DataFrame | None:
        """Convert FacilitiesLink date columns to pandas datetimes."""
        try:
            start = pd.to_datetime(df["CLASS_START_DATE"], format="%d-%b-%y", errors="coerce")
            end = pd.to_datetime(df["CLASS_END_DATE"], format="%d-%b-%y", errors="coerce")

            if start.isna().any():
                start_fallback = pd.to_datetime(df.loc[start.isna(), "CLASS_START_DATE"], errors="coerce")
                start.loc[start.isna()] = start_fallback
            if end.isna().any():
                end_fallback = pd.to_datetime(df.loc[end.isna(), "CLASS_END_DATE"], errors="coerce")
                end.loc[end.isna()] = end_fallback

            df["CLASS_START_DATE"] = start
            df["CLASS_END_DATE"] = end

            if df["CLASS_START_DATE"].isna().any() or df["CLASS_END_DATE"].isna().any():
                bad_start = int(df["CLASS_START_DATE"].isna().sum())
                bad_end = int(df["CLASS_END_DATE"].isna().sum())
                raise ValueError(
                    f"Unparseable dates: CLASS_START_DATE NaT={bad_start}, CLASS_END_DATE NaT={bad_end}"
                )

            return df
        except Exception as e:
            raise_error_window(
                f"An error occurred while converting dates: {e!s}",
                title="Date Conversion Error",
            )
            log.error(f"Date conversion error: {e!s}")
            return None

    def _filter_to_supported_locations(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter schedule to only explicitly supported (building, room) tuples."""
        if not self.supported_locations:
            return df
        supported = {(b.upper().strip(), r.upper().strip()) for b, r in self.supported_locations}
        df = df.copy()
        df["BUILDING"] = df["BUILDING"].astype(str).str.upper().str.strip()
        df["ROOM"] = df["ROOM"].astype(str).str.upper().str.strip()
        return df[df.apply(lambda r: (r["BUILDING"], r["ROOM"]) in supported, axis=1)].copy()

    def _filter_to_semester(self, df: pd.DataFrame, date: datetime) -> pd.DataFrame:
        """Filter rows to a single academic term (“semester”) near `date`.

        The FacilitiesLink export may contain many terms (multiple years). Pre-change
        behavior expected `semester_data()` to return *one* current term, not the full export.

        Selection strategy:
        1) Prefer a TERM whose overall date window contains `date`.
        2) If none contain it (between terms), pick the next upcoming TERM by start date.
        3) If there's no upcoming term, fall back to the most recent TERM.
        """

        if df.empty:
            return df

        if "TERM" not in df.columns:
            raise ValueError("FacilitiesLink data is missing required column TERM")

        target = pd.to_datetime(date).normalize()

        # Compute per-TERM window using min start + max end.
        term_windows = (
            df.groupby("TERM", dropna=False)
            .agg(term_start=("CLASS_START_DATE", "min"), term_end=("CLASS_END_DATE", "max"))
            .reset_index()
        )

        # 1) Terms containing the target date
        containing = term_windows[
            (term_windows["term_start"] <= target) & (target <= term_windows["term_end"])
        ].copy()
        if not containing.empty:
            # If multiple overlap (unlikely), pick the one with the latest start.
            chosen_term = containing.sort_values("term_start", ascending=False).iloc[0]["TERM"]
            return df[df["TERM"] == chosen_term].copy()

        # 2) Next upcoming term
        upcoming = term_windows[term_windows["term_start"] > target].copy()
        if not upcoming.empty:
            chosen_term = upcoming.sort_values("term_start", ascending=True).iloc[0]["TERM"]
            return df[df["TERM"] == chosen_term].copy()

        # 3) Most recent term
        chosen_term = term_windows.sort_values("term_end", ascending=False).iloc[0]["TERM"]
        return df[df["TERM"] == chosen_term].copy()


__all__ = ["DataLoader"]
