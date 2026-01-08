import logging as log

import pandas as pd

from utils import raise_error_window


class DataLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path

    def load_data(self) -> pd.DataFrame:
        log.debug(f"Loading data from {self.file_path}")
        dataframe = self._csv_to_dataframe()
        filtered_dataframe = self._filter_dataframe(dataframe)
        return filtered_dataframe

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

    def _filter_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """
        - Removes rows with missing values in critical columns.
        - Excludes online courses.
        - Excludes courses with 'TBA' schedules.
        """
        try:
            initial_rows = len(dataframe)
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
            filtered_df = dataframe.dropna(subset=required_columns)
            filtered_df = filtered_df[filtered_df["ROOM"] != "WWW"]
            filtered_df = filtered_df[filtered_df["DAYS1"] != "TBA"]
            log.debug(
                f"{initial_rows - len(filtered_df)} rows filtered out. Initial size: {initial_rows}, Filtered size: {len(filtered_df)}"
            )
            return filtered_df
        except Exception as e:
            raise_error_window(
                f"An error occurred while filtering the data: {str(e)}",
                title="Filtering Error",
            )
            log.error(f"Filtering error: {str(e)}")
            return pd.DataFrame()


if __name__ == "__main__":
    pass
