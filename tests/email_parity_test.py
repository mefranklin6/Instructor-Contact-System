"""Parity tests between 'By Classroom' and 'By Instructor' views.

These tests enforce that the schedule aggregation is internally consistent, and that
email-based lookups (classroom -> instructor email -> instructor classes) return
compatible results.
"""

import contextlib
from pathlib import Path

import pandas as pd
import pytest

from src.core.schedule_aggregator import Aggregator


def _repo_root() -> Path:
    """Return the repository root directory.

    This file lives under `tests/`, so the repo root is one level above.
    """
    return Path(__file__).resolve().parent.parent


def _normalize_emplid(value: object) -> str:
    """Normalize an instructor EMPLID to a 9-digit numeric string."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    s = s.replace(".", "")
    if not s.isdigit():
        return ""
    with contextlib.suppress(ValueError, TypeError, OverflowError):
        s = str(int(s))
    return s.zfill(9)


def _load_real_schedule_df() -> pd.DataFrame:
    """Load the real FacilitiesLink schedule CSV as a minimal DataFrame for aggregation."""
    repo_root = _repo_root()
    csv_path = repo_root / "FacilitiesLinkClassScheduleDaily.csv"
    if not csv_path.exists():
        pytest.skip(f"Missing real schedule CSV: {csv_path}")

    try:
        df = pd.read_csv(
            csv_path,
            usecols=["INSTRUCTOR1_EMPLID", "BUILDING", "ROOM"],
            dtype={"INSTRUCTOR1_EMPLID": "string", "BUILDING": "string", "ROOM": "string"},
        )
    except ValueError as e:
        pytest.skip(f"Schedule CSV missing required columns: {e}")

    df = df.dropna(subset=["INSTRUCTOR1_EMPLID", "BUILDING", "ROOM"]).copy()
    df["INSTRUCTOR1_EMPLID"] = df["INSTRUCTOR1_EMPLID"].map(_normalize_emplid)
    df = df[df["INSTRUCTOR1_EMPLID"] != ""]

    df["BUILDING"] = df["BUILDING"].astype(str).str.strip()
    df["ROOM"] = df["ROOM"].astype(str).str.strip()

    # Mirror the DataLoader's cleaning for online entries
    df = df[(df["BUILDING"] != "WWW") & (df["ROOM"] != "WWW")]
    df = df[(df["BUILDING"] != "ONLINE") & (df["ROOM"] != "ONLINE")]

    return df


class DummyMatcher:
    """Simple in-memory matcher used by synthetic tests."""

    def __init__(self, mapping: dict[str, str]) -> None:
        """Create a matcher with a fixed `emplid -> email` mapping."""
        self._mapping = mapping

    def match_id_to_email(self, emp_id: str) -> str:
        """Return the mapped email for an EMPLID, or empty string."""
        return self._mapping.get(str(emp_id), "")


def _emails_for_location(
    contact_by_location: dict[str, list[str]], matcher: DummyMatcher, location: str
) -> list[str]:
    emp_ids = contact_by_location.get(location, [])
    emails: list[str] = []
    for emp_id in emp_ids:
        email = matcher.match_id_to_email(emp_id)
        if email:
            emails.append(email)
    # stable de-dupe
    seen = set()
    return [e for e in emails if not (e in seen or seen.add(e))]


def _ui_style_find_emp_id_by_email(
    contact_by_instructor: dict[str, list[str]], matcher: DummyMatcher, email: str
) -> str | None:
    target = (email or "").strip().lower()
    for emp_id in contact_by_instructor:
        matched = (matcher.match_id_to_email(emp_id) or "").strip().lower()
        if matched == target:
            return emp_id
    return None


def test_aggregator_internal_parity_location_to_instructor() -> None:
    """If a location lists an EMPLID, that EMPLID must list the location."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "ART", "ROOM": "202"},
        ]
    )
    agg = Aggregator(df=df)
    by_instr = agg.by_instructor()
    by_loc = agg.by_location()

    for location, emp_ids in by_loc.items():
        for emp_id in emp_ids:
            assert emp_id in by_instr
            assert location in by_instr[emp_id]


def test_email_parity_by_classroom_to_by_instructor_lookup() -> None:
    """Ensure email-based lookups are consistent between UI views (synthetic data)."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "ART", "ROOM": "202"},
        ]
    )
    agg = Aggregator(df=df)
    by_instr = agg.by_instructor()
    by_loc = agg.by_location()

    matcher = DummyMatcher(
        {
            "000000001": "alice@school.edu",
            "000000002": "bob@school.edu",
        }
    )

    for location in by_loc:
        emails = _emails_for_location(by_loc, matcher, location)

        for email in emails:
            emp_id = _ui_style_find_emp_id_by_email(by_instr, matcher, email)
            assert emp_id is not None, (
                f"By Classroom resolved {email} for {location}, but By Instructor couldn't find it"
            )
            assert location in by_instr[emp_id], (
                f"{email} found, but {location} missing from By Instructor results"
            )


def test_real_data_internal_parity_location_to_instructor() -> None:
    """Validate internal parity on real FacilitiesLink schedule data."""
    df = _load_real_schedule_df()
    if df.empty:
        pytest.skip("Real schedule CSV produced empty DataFrame after cleaning")

    agg = Aggregator(df=df)
    by_instr = agg.by_instructor()
    by_loc = agg.by_location()

    # Both maps are derived from the same DF; this should always hold.
    for location, emp_ids in by_loc.items():
        for emp_id in emp_ids:
            assert emp_id in by_instr
            assert location in by_instr[emp_id]


@pytest.mark.parametrize(
    "matcher_factory",
    [
        pytest.param(
            "ad_json",
            id="ad_json",
        ),
        pytest.param(
            "zoom_csv",
            id="zoom_csv",
        ),
    ],
)
def test_real_data_email_parity_by_classroom_to_by_instructor(matcher_factory: str) -> None:
    """Validate email parity on real data using the configured matcher source."""
    repo_root = _repo_root()
    df = _load_real_schedule_df()
    if df.empty:
        pytest.skip("Real schedule CSV produced empty DataFrame after cleaning")

    agg = Aggregator(df=df)
    by_instr = agg.by_instructor()
    by_loc = agg.by_location()

    if matcher_factory == "ad_json":
        json_path = repo_root / "id_and_emails_from_ad.json"
        if not json_path.exists():
            pytest.skip(f"Missing mapping file: {json_path}")
        from plugins.id_matcher_from_ad_json import (  # pyright: ignore[reportMissingImports]
            Matcher as AdJsonMatcher,  # pyright: ignore[reportMissingImports]
        )

        matcher = AdJsonMatcher()
    elif matcher_factory == "zoom_csv":
        zoom_path = repo_root / "zoomus_users.csv"
        if not zoom_path.exists():
            pytest.skip(f"Missing mapping file: {zoom_path}")
        from plugins.id_matcher_from_zoom_users_csv import (  # pyright: ignore[reportMissingImports]
            Matcher as ZoomMatcher,  # pyright: ignore[reportMissingImports]
        )

        matcher = ZoomMatcher(str(zoom_path))
    else:
        raise ValueError(f"Unknown matcher_factory: {matcher_factory}")

    # Build a deterministic reverse index email -> set(emp_ids)
    email_to_emp_ids: dict[str, set[str]] = {}
    for emp_id in by_instr:
        email = (matcher.match_id_to_email(emp_id) or "").strip().lower()
        if email:
            email_to_emp_ids.setdefault(email, set()).add(emp_id)

    if not email_to_emp_ids:
        pytest.skip("No emails resolved from mapping; cannot test email parity")

    checked = 0
    for location in sorted(by_loc):
        for emp_id in by_loc.get(location, []):
            email = (matcher.match_id_to_email(emp_id) or "").strip().lower()
            if not email:
                continue
            assert email in email_to_emp_ids, (
                f"By Classroom resolved {email} at {location}, but By Instructor can't find it"
            )

            candidates = email_to_emp_ids[email]
            assert any(location in by_instr[cand] for cand in candidates), (
                f"{email} resolved at {location}, but that location is missing when searching by instructor"
            )
            checked += 1

    if checked == 0:
        pytest.skip("No rows had resolvable emails; cannot test email parity")
