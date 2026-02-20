"""Shared utility functions for the Instructor Contact System."""

import pandas as pd


def csv_to_dataframe(file_path: str) -> pd.DataFrame:
    """Load data from a CSV file into a pandas DataFrame."""
    return pd.read_csv(file_path)
