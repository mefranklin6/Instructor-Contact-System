import pandas as pd
from utils import raise_error_window


class DataLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.calendar_dataframe = self.load_data()

    def load_data(self) -> pd.DataFrame:
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
                f"There was a parsing error while reading the file at {self.file_path}.",
                title="Parsing Error",
            )
            return pd.DataFrame()
        except Exception as e:
            raise_error_window(
                f"An unexpected error occurred while reading the file at {self.file_path}: {str(e)}",
                title="Unexpected Error",
            )
            return pd.DataFrame()
