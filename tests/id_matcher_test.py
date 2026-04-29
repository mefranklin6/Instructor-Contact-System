"""Edge-case tests for the bundled ID-to-email matchers."""

import json

import pandas as pd

from plugins.id_matcher_from_zoom_users_csv import Matcher as ZoomMatcher  # pyright: ignore[reportMissingImports]
from plugins.id_matcher_from_ad_json import Matcher as AdJsonMatcher  # pyright: ignore[reportMissingImports]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zoom_matcher(tmp_path, rows=None):
    """Build a ZoomMatcher backed by a minimal CSV in tmp_path."""
    csv_path = tmp_path / "zoom.csv"
    df = pd.DataFrame(rows or [{"Employee ID": "123", "Email": "a@example.com"}])
    df.to_csv(csv_path, index=False)
    return ZoomMatcher(csv_file_path=str(csv_path))


# ---------------------------------------------------------------------------
# ZoomMatcher normalization edge cases
# ---------------------------------------------------------------------------


def test_zoom_matcher_none_id_returns_empty(tmp_path):
    """match_id_to_email(None) returns empty string."""
    assert _zoom_matcher(tmp_path).match_id_to_email(None) == ""


def test_zoom_matcher_empty_string_id_returns_empty(tmp_path):
    """match_id_to_email('') returns empty string."""
    assert _zoom_matcher(tmp_path).match_id_to_email("") == ""


def test_zoom_matcher_non_numeric_id_returns_empty(tmp_path):
    """match_id_to_email with a non-numeric value returns empty string."""
    assert _zoom_matcher(tmp_path).match_id_to_email("not-a-number") == ""


def test_zoom_matcher_unknown_numeric_id_returns_empty(tmp_path):
    """match_id_to_email with a valid-format but unknown ID returns empty string."""
    assert _zoom_matcher(tmp_path).match_id_to_email("000000999") == ""


# ---------------------------------------------------------------------------
# AdJsonMatcher normalization + load edge cases
# ---------------------------------------------------------------------------


def test_ad_json_normalize_none_returns_empty():
    """_normalize_employee_id(None) returns empty string."""
    assert AdJsonMatcher._normalize_employee_id(None) == ""


def test_ad_json_matcher_non_list_json_yields_empty_map(tmp_path, monkeypatch):
    """Matcher uses empty mapping when the JSON file does not contain a list."""
    json_path = tmp_path / "ad.json"
    json_path.write_text(json.dumps({"key": "value"}), encoding="utf-8")

    import plugins.id_matcher_from_ad_json as mod

    monkeypatch.setattr(mod, "AD_JSON_PATH", json_path)

    matcher = AdJsonMatcher()
    assert matcher.match_id_to_email("000000001") == ""


def _ad_matcher(tmp_path, monkeypatch, records=None):
    """Build an AdJsonMatcher backed by a temp JSON file."""
    json_path = tmp_path / "ad.json"
    json_path.write_text(
        json.dumps(records or [{"EmployeeID": "123", "EmailAddress": "a@example.com"}]),
        encoding="utf-8",
    )
    import plugins.id_matcher_from_ad_json as mod

    monkeypatch.setattr(mod, "AD_JSON_PATH", json_path)
    return AdJsonMatcher()


def test_ad_json_matcher_unknown_id_returns_empty(tmp_path, monkeypatch):
    """match_id_to_email returns empty string for IDs absent from the map."""
    matcher = _ad_matcher(tmp_path, monkeypatch)
    assert matcher.match_id_to_email("000000999") == ""


def test_ad_json_matcher_empty_id_returns_empty(tmp_path, monkeypatch):
    """match_id_to_email('') returns empty string (normalized_id is falsy)."""
    matcher = _ad_matcher(tmp_path, monkeypatch)
    assert matcher.match_id_to_email("") == ""


def test_ad_json_matcher_known_id_returns_email(tmp_path, monkeypatch):
    """match_id_to_email returns the email for a known ID."""
    matcher = _ad_matcher(tmp_path, monkeypatch)
    assert matcher.match_id_to_email("123") == "a@example.com"
