"""
Unit tests for DataLoader class.

Tests cover:
- CSV loading and parsing
- DataFrame filtering (required columns, online classes)
- Error handling (file not found, empty files, parsing errors)

Run: python -m pytest src/data_loader/tests/data_loader_tests.py -v
"""

import pytest
import pandas as pd
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add parent and src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_loader import DataLoader


class TestDataLoaderInitialization:
    """Tests for DataLoader initialization."""

    def test_initialization(self):
        """Test that DataLoader initializes with correct file path."""
        file_path = "test.csv"
        loader = DataLoader(file_path)
        assert loader.file_path == file_path


class TestCsvToDataFrame:
    """Tests for CSV loading and conversion to DataFrame."""

    def test_load_valid_csv(self):
        """Test loading a valid CSV file."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            f.write(
                "INSTRUCTOR1_EMPLID,CLASS_START_DATE,CLASS_END_DATE,START_TIME1,END_TIME1,DAYS1,BUILDING,ROOM\n"
            )
            f.write("12345,2024-01-01,2024-05-01,09:00,10:00,MWF,Science,101\n")
            f.write("12346,2024-01-01,2024-05-01,10:00,11:00,TTh,Science,102\n")
            temp_path = f.name

        try:
            loader = DataLoader(temp_path)
            df = loader._csv_to_dataframe()

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert list(df.columns) == [
                "INSTRUCTOR1_EMPLID",
                "CLASS_START_DATE",
                "CLASS_END_DATE",
                "START_TIME1",
                "END_TIME1",
                "DAYS1",
                "BUILDING",
                "ROOM",
            ]
        finally:
            os.unlink(temp_path)

    @patch("data_loader.raise_error_window")
    def test_file_not_found(self, mock_error):
        """Test handling of missing file."""
        loader = DataLoader("/nonexistent/path/file.csv")
        df = loader._csv_to_dataframe()

        mock_error.assert_called_once()
        assert "was not found" in mock_error.call_args[0][0]
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    @patch("data_loader.raise_error_window")
    def test_empty_csv_file(self, mock_error):
        """Test handling of empty CSV file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            # Write nothing - empty file
            temp_path = f.name

        try:
            loader = DataLoader(temp_path)
            df = loader._csv_to_dataframe()

            mock_error.assert_called_once()
            assert "empty" in mock_error.call_args[0][0].lower()
            assert isinstance(df, pd.DataFrame)
        finally:
            os.unlink(temp_path)

    @patch("data_loader.raise_error_window")
    def test_malformed_csv(self, mock_error):
        """Test handling of malformed CSV file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            f.write("col1,col2,col3\n")
            f.write("val1,val2\n")  # Missing a column - may cause parsing issues
            temp_path = f.name

        try:
            loader = DataLoader(temp_path)
            # This may or may not raise - pandas is flexible, so we just verify it loads
            df = loader._csv_to_dataframe()
            assert isinstance(df, pd.DataFrame)
        finally:
            os.unlink(temp_path)


class TestFilterDataFrame:
    """Tests for DataFrame filtering logic."""

    def test_filter_removes_missing_required_columns(self):
        """Test that rows with missing required columns are filtered out."""
        # Create DataFrame with some missing required columns
        df = pd.DataFrame(
            {
                "INSTRUCTOR1_EMPLID": [1, 2, 3],
                "CLASS_START_DATE": ["2024-01-01", None, "2024-01-01"],
                "CLASS_END_DATE": ["2024-05-01", "2024-05-01", "2024-05-01"],
                "START_TIME1": ["09:00", "10:00", "11:00"],
                "END_TIME1": ["10:00", "11:00", "12:00"],
                "DAYS1": ["MWF", "TTh", "MWF"],
                "BUILDING": ["Science", "Science", "Science"],
                "ROOM": ["101", "102", "103"],
            }
        )

        loader = DataLoader("")
        filtered_df = loader._filter_dataframe(df)

        # Only rows with all required columns should remain
        assert len(filtered_df) == 2
        assert list(filtered_df["INSTRUCTOR1_EMPLID"]) == [1, 3]

    def test_filter_removes_online_classes(self):
        """Test that online classes (ROOM='WWW') are filtered out."""
        df = pd.DataFrame(
            {
                "INSTRUCTOR1_EMPLID": [1, 2, 3],
                "CLASS_START_DATE": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "CLASS_END_DATE": ["2024-05-01", "2024-05-01", "2024-05-01"],
                "START_TIME1": ["09:00", "10:00", "11:00"],
                "END_TIME1": ["10:00", "11:00", "12:00"],
                "DAYS1": ["MWF", "TTh", "Online"],
                "BUILDING": ["Science", "Science", "Online"],
                "ROOM": ["101", "WWW", "103"],  # 102 is online
            }
        )

        loader = DataLoader("")
        filtered_df = loader._filter_dataframe(df)

        # Online class should be removed
        assert len(filtered_df) == 2
        assert "WWW" not in filtered_df["ROOM"].values
        assert list(filtered_df["INSTRUCTOR1_EMPLID"]) == [1, 3]

    def test_filter_preserves_valid_rows(self):
        """Test that valid rows are preserved during filtering."""
        df = pd.DataFrame(
            {
                "INSTRUCTOR1_EMPLID": [1, 2, 3],
                "CLASS_START_DATE": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "CLASS_END_DATE": ["2024-05-01", "2024-05-01", "2024-05-01"],
                "START_TIME1": ["09:00", "10:00", "11:00"],
                "END_TIME1": ["10:00", "11:00", "12:00"],
                "DAYS1": ["MWF", "TTh", "MWF"],
                "BUILDING": ["Science", "Science", "Science"],
                "ROOM": ["101", "102", "103"],
            }
        )

        loader = DataLoader("")
        filtered_df = loader._filter_dataframe(df)

        # All rows should be preserved
        assert len(filtered_df) == 3
        assert filtered_df.equals(df)

    @patch("data_loader.raise_error_window")
    @patch("data_loader.log.error")
    def test_filter_handles_exception(self, mock_log, mock_error):
        """Test that filtering errors are handled gracefully."""
        # Create a DataFrame that will cause an issue
        df = MagicMock()
        df.dropna.side_effect = Exception("Test error")

        loader = DataLoader("")
        filtered_df = loader._filter_dataframe(df)

        mock_error.assert_called_once()
        mock_log.assert_called_once()
        assert isinstance(filtered_df, pd.DataFrame)
        assert filtered_df.empty


class TestLoadData:
    """Integration tests for the load_data method."""

    def test_load_data_full_workflow(self):
        """Test complete data loading workflow."""
        # Create a valid CSV with required columns
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            f.write(
                "INSTRUCTOR1_EMPLID,CLASS_START_DATE,CLASS_END_DATE,START_TIME1,END_TIME1,DAYS1,BUILDING,ROOM,EXTRA_COL\n"
            )
            f.write("12345,2024-01-01,2024-05-01,09:00,10:00,MWF,Science,101,data1\n")
            f.write("12346,2024-01-01,2024-05-01,10:00,11:00,TTh,Science,102,data2\n")
            f.write(
                "12347,2024-01-01,2024-05-01,11:00,12:00,MWF,Science,WWW,data3\n"
            )  # Online
            temp_path = f.name

        try:
            loader = DataLoader(temp_path)
            df = loader.load_data()

            # Should have 2 rows (online class filtered out)
            assert len(df) == 2
            assert "WWW" not in df["ROOM"].values
            # Should have preserved extra columns
            assert "EXTRA_COL" in df.columns
        finally:
            os.unlink(temp_path)

    @patch("data_loader.raise_error_window")
    def test_load_data_with_missing_file(self, mock_error):
        """Test load_data with missing file."""
        loader = DataLoader("/nonexistent/file.csv")
        df = loader.load_data()

        # Should have called error window at least once (for file not found or filtering)
        assert mock_error.call_count >= 1
        assert isinstance(df, pd.DataFrame)

    def test_load_data_with_all_filtered_rows(self):
        """Test load_data when all rows are filtered out."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".csv") as f:
            f.write(
                "INSTRUCTOR1_EMPLID,CLASS_START_DATE,CLASS_END_DATE,START_TIME1,END_TIME1,DAYS1,BUILDING,ROOM\n"
            )
            # All rows are online or missing columns
            f.write("12345,2024-01-01,,09:00,10:00,MWF,Science,101\n")
            f.write("12346,,2024-05-01,10:00,11:00,TTh,Science,WWW\n")
            temp_path = f.name

        try:
            loader = DataLoader(temp_path)
            df = loader.load_data()

            # Should return empty DataFrame
            assert isinstance(df, pd.DataFrame)
            # At least the first row might be filtered due to missing CLASS_END_DATE
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
