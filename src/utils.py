import logging as log
import pandas as pd


def raise_error_window(message: str, title: str = "Error") -> None:
    print(f"{title}: {message}")
    log.error(f"{title}: {message}")
    # TODO: Raise pop-up window in Flet


def csv_to_dataframe(file_path: str) -> pd.DataFrame:
    """Load data from a CSV file into a pandas DataFrame."""
    try:
        data = pd.read_csv(file_path)
        return data
    except FileNotFoundError:
        raise_error_window(
            f"The file at {file_path} was not found.", title="File Not Found"
        )
        return pd.DataFrame()
    except pd.errors.EmptyDataError:
        raise_error_window(f"The file at {file_path} is empty.", title="Empty File")
        return pd.DataFrame()
    except pd.errors.ParserError:
        raise_error_window(
            f"There was a CSV parsing error while reading the file at {file_path}.",
            title="Parsing Error",
        )
        return pd.DataFrame()
    except Exception as e:
        raise_error_window(
            f"An unexpected error occurred while reading the file at {file_path}: {str(e)}",
            title="Unexpected Error",
        )
        return pd.DataFrame()
