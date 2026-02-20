"""Shared utility functions for the Instructor Contact System."""

import os
import time

import pandas as pd


def csv_to_dataframe(file_path: str) -> pd.DataFrame:
    """Load data from a CSV file into a pandas DataFrame."""
    return pd.read_csv(file_path)


def file_is_stale(file_path) -> bool:
    """Returns true if the file is over one month old."""
    _ONE_MONTH_SECONDS = 30 * 24 * 60 * 60
    return (time.time() - os.path.getmtime(file_path)) > _ONE_MONTH_SECONDS
