import logging as log

import pandas as pd
from datetime import datetime

from src.utils import raise_error_window


class DataLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        log.debug(f"DataLoader initialized with file path: {file_path}")

    def load_semester_data(self, date: datetime) -> pd.DataFrame:
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

    def load_range_data(self, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        log.error("load_range_data method not yet implemented.")  # TODO
        return pd.DataFrame()

    def _load_and_clean(self) -> pd.DataFrame:
        df = self._csv_to_dataframe()
        df = self._clean_dataframe(df)
        df = self._convert_dates(df)
        return df

    def _csv_to_dataframe(self) -> pd.DataFrame:
        """Load data from a CSV file into a pandas DataFrame."""
        try:
            data = pd.read_csv(self.file_path)
            return data
        except FileNotFoundError:
            raise_error_window(
                f"The file at {self.file_path} was not found.", title="File Not Found"
            )
            return pd.DataFrame()
        except pd.errors.EmptyDataError:
            raise_error_window(
                f"The file at {self.file_path} is empty.", title="Empty File"
            )
            return pd.DataFrame()
        except pd.errors.ParserError:
            raise_error_window(
                f"There was a CSV parsing error while reading the file at {self.file_path}.",
                title="Parsing Error",
            )
            return pd.DataFrame()
        except Exception as e:
            raise_error_window(
                f"An unexpected error occurred while reading the file at {self.file_path}: {str(e)}",
                title="Unexpected Error",
            )
            return pd.DataFrame()

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
            filtered_df = df[
                (df["CLASS_START_DATE"].astype(str).str[:10] <= str(date))
                & (df["CLASS_END_DATE"].astype(str).str[:10] >= str(date))
            ]

            log.debug(
                f"Filtered to current semester. Rows before: {len(df)}, Rows after: {len(filtered_df)}"
            )
            return filtered_df
        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering to the current semester: {str(e)}",
                title="Semester Filtering Error",
            )
            log.error(f"Semester filtering error: {str(e)}")
            return pd.DataFrame()


if __name__ == "__main__":
    pass
