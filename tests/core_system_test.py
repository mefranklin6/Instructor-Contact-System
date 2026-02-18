"""Tests for core system logic (By Classroom, By Instructor, Start of Semester).

These tests use synthetic data and mock plugins to validate the core orchestration
layer without requiring real CSV files, SMTP, or Active Directory.
"""

import pandas as pd
import pytest

from src.core.schedule_aggregator import Aggregator
from src.core.settings import Settings
from src.core.system import InstructorContactSystemCore


class FakeMatcher:
    """In-memory ID->email matcher for testing."""

    def __init__(self, mapping: dict[str, str]) -> None:
        """Create a fake matcher."""
        self._mapping = mapping

    def match_id_to_email(self, emp_id: str) -> str:
        """Return mapped email or empty string."""
        return self._mapping.get(str(emp_id), "")


class FakeEmailSender:
    """Fake email sender that records calls."""

    def __init__(self, *, should_fail: set[str] | None = None) -> None:
        """Create a fake sender; optionally specify emails that should fail."""
        self.sent: list[tuple[str, str, str]] = []
        self._should_fail = should_fail or set()

    def send(self, to_addr: str, subject: str, message: str) -> bool:
        """Record the send attempt and return success/failure."""
        if to_addr in self._should_fail:
            return False
        self.sent.append((to_addr, subject, message))
        return True


def _build_core(
    df: pd.DataFrame,
    mapping: dict[str, str],
    *,
    dev_mode: bool = True,
    should_fail_emails: set[str] | None = None,
) -> InstructorContactSystemCore:
    """Build a core instance with injected fakes (no real files/plugins)."""
    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=dev_mode,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=None,
    )

    # Bypass __init__ to inject fakes
    core = object.__new__(InstructorContactSystemCore)
    core.in_docker = False
    core.settings = settings
    core.max_failed_display = 50
    core.supported_locations = None
    core.loader = None
    core.df = df
    core.contacted_instructors = {}

    core.id_matcher = FakeMatcher(mapping)
    core.email_sender = FakeEmailSender(should_fail=should_fail_emails)

    agg = Aggregator(df=df)
    core.aggregator = agg
    core.contact_by_instructor = agg.by_instructor()
    core.contact_by_location = agg.by_location()

    # Stub out file I/O so tests control contacted_instructors directly
    core.load_contact_history = lambda: None
    core.save_contact_history = lambda: None

    return core


# ---- By Classroom ----


def test_lookup_classroom_emails_returns_correct_emails() -> None:
    """lookup_classroom_emails returns emails for instructors in that room."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000003", "BUILDING": "ART", "ROOM": "200"},
        ]
    )
    mapping = {
        "000000001": "alice@test.edu",
        "000000002": "bob@test.edu",
        "000000003": "carol@test.edu",
    }
    core = _build_core(df, mapping)

    emails = core.lookup_classroom_emails(building="SCI", room="101")
    assert set(emails) == {"alice@test.edu", "bob@test.edu"}


def test_lookup_classroom_emails_raises_on_missing_location() -> None:
    """lookup_classroom_emails raises KeyError for unknown room."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    core = _build_core(df, {"000000001": "a@test.edu"})

    with pytest.raises(KeyError, match="No classes found"):
        core.lookup_classroom_emails(building="SCI", room="999")


def test_lookup_classroom_emails_case_insensitive() -> None:
    """lookup_classroom_emails uppercases building and room."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    core = _build_core(df, {"000000001": "a@test.edu"})

    emails = core.lookup_classroom_emails(building="sci", room="101")
    assert emails == ["a@test.edu"]


def test_lookup_classroom_emails_no_email_match_raises() -> None:
    """lookup_classroom_emails raises ValueError when no emails resolve."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    # Empty mapping: no emails will match
    core = _build_core(df, {})

    with pytest.raises(ValueError, match="No email matches"):
        core.lookup_classroom_emails(building="SCI", room="101")


# ---- By Instructor ----


def test_lookup_instructor_locations_returns_rooms() -> None:
    """lookup_instructor_locations returns all rooms for a given email."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "ART", "ROOM": "200"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    mapping = {
        "000000001": "alice@test.edu",
        "000000002": "bob@test.edu",
    }
    core = _build_core(df, mapping)

    locations = core.lookup_instructor_locations(email="alice@test.edu")
    assert set(locations) == {"SCI 101", "ART 200"}


def test_lookup_instructor_locations_case_insensitive_email() -> None:
    """lookup_instructor_locations matches email case-insensitively."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    core = _build_core(df, {"000000001": "Alice@Test.EDU"})

    locations = core.lookup_instructor_locations(email="alice@test.edu")
    assert locations == ["SCI 101"]


def test_lookup_instructor_locations_raises_on_unknown_email() -> None:
    """lookup_instructor_locations raises KeyError for unknown email."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"})

    with pytest.raises(KeyError, match="No classes found"):
        core.lookup_instructor_locations(email="nobody@test.edu")


def test_lookup_instructor_locations_raises_on_empty_email() -> None:
    """lookup_instructor_locations raises ValueError for empty input."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"})

    with pytest.raises(ValueError, match="Please enter an email"):
        core.lookup_instructor_locations(email="")


# ---- Start of Semester Deployment ----


def test_compute_semester_deployment_excludes_already_contacted() -> None:
    """compute_semester_deployment_candidates skips semester-contacted instructors."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "ART", "ROOM": "200"},
        ]
    )
    mapping = {
        "000000001": "alice@test.edu",
        "000000002": "bob@test.edu",
    }
    core = _build_core(df, mapping)

    # Simulate alice being already contacted for start of semester
    core.contacted_instructors = {
        "alice@test.edu": {
            "contacted_at": "2025-01-01T00:00:00",
            "contact_type": "start of semester",
        }
    }

    candidates = core.compute_semester_deployment_candidates()
    candidate_emails = [c["email"] for c in candidates]
    assert "alice@test.edu" not in candidate_emails
    assert "bob@test.edu" in candidate_emails


def test_compute_semester_deployment_includes_classroom_only_contacts() -> None:
    """Instructors contacted only via classroom message are still deployment candidates."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    mapping = {"000000001": "alice@test.edu"}
    core = _build_core(df, mapping)

    # Alice was contacted via classroom message, NOT semester deployment
    core.contacted_instructors = {
        "alice@test.edu": {
            "classroom_messages": [
                {"sent_at": "2025-01-15T10:00:00", "contact_type": "all instructors for classroom"}
            ]
        }
    }

    candidates = core.compute_semester_deployment_candidates()
    candidate_emails = [c["email"] for c in candidates]
    assert "alice@test.edu" in candidate_emails


def test_execute_deployment_dev_mode_does_not_send() -> None:
    """In dev mode, deployment logs but does not send real emails."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    mapping = {"000000001": "alice@test.edu"}
    core = _build_core(df, mapping, dev_mode=True)

    candidates = core.compute_semester_deployment_candidates()
    result = core.execute_deployment(
        instructors=candidates,
        message_template="Hello, your rooms: {locations}",
        batch_size=10,
        subject="Test",
    )

    assert result.contacted_this_batch == 1
    assert result.total_contacted == 1
    # Fake sender should not have been called in dev mode
    assert len(core.email_sender.sent) == 0


def test_execute_deployment_preserves_classroom_history() -> None:
    """Deployment does not overwrite existing classroom message history."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
        ]
    )
    mapping = {"000000001": "alice@test.edu"}
    core = _build_core(df, mapping, dev_mode=True)

    # Pre-existing classroom contact
    core.contacted_instructors = {
        "alice@test.edu": {
            "classroom_messages": [{"sent_at": "2025-01-15", "contact_type": "all instructors for classroom"}]
        }
    }

    candidates = core.compute_semester_deployment_candidates()
    assert len(candidates) == 1  # Should still be a candidate

    result = core.execute_deployment(
        instructors=candidates,
        message_template="Hello, your rooms: {locations}",
        batch_size=10,
        subject="Test",
    )

    assert result.contacted_this_batch == 1
    record = core.contacted_instructors["alice@test.edu"]
    # Both classroom_messages and semester data should coexist
    assert "classroom_messages" in record
    assert record["contact_type"] == "start of semester"


def test_execute_deployment_batch_size_limits_sends() -> None:
    """Only batch_size instructors are contacted per deployment call."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "ART", "ROOM": "200"},
            {"INSTRUCTOR1_EMPLID": "000000003", "BUILDING": "ENG", "ROOM": "300"},
        ]
    )
    mapping = {
        "000000001": "a@test.edu",
        "000000002": "b@test.edu",
        "000000003": "c@test.edu",
    }
    core = _build_core(df, mapping, dev_mode=True)

    candidates = core.compute_semester_deployment_candidates()
    result = core.execute_deployment(
        instructors=candidates,
        message_template="Hello {locations}",
        batch_size=2,
        subject="Test",
    )

    assert result.contacted_this_batch == 2
    assert result.remaining == 1


def test_execute_deployment_remaining_counts_only_semester() -> None:
    """Remaining count in DeploymentResult only considers semester contacts."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "ART", "ROOM": "200"},
        ]
    )
    mapping = {
        "000000001": "alice@test.edu",
        "000000002": "bob@test.edu",
    }
    core = _build_core(df, mapping, dev_mode=True)

    # Alice has a classroom-only contact (should NOT count as semester-contacted)
    core.contacted_instructors = {"alice@test.edu": {"classroom_messages": [{"sent_at": "2025-01-15"}]}}

    candidates = core.compute_semester_deployment_candidates()
    # Both should be candidates
    assert len(candidates) == 2

    result = core.execute_deployment(
        instructors=candidates,
        message_template="Hello {locations}",
        batch_size=1,
        subject="Test",
    )

    # 1 contacted this batch, total semester contacted = 1, remaining = 2-1 = 1
    assert result.contacted_this_batch == 1
    assert result.total_contacted == 1
    assert result.remaining == 1
    assert result.total_instructors == 2


def test_dedupe_emails_preserves_order() -> None:
    """dedupe_emails removes duplicates while keeping first occurrence order."""
    result = InstructorContactSystemCore.dedupe_emails(
        ["b@test.edu", "a@test.edu", "b@test.edu", "c@test.edu", "a@test.edu"]
    )
    assert result == ["b@test.edu", "a@test.edu", "c@test.edu"]


# ---- Aggregator parity ----


def test_aggregator_by_location_and_by_instructor_are_consistent() -> None:
    """Aggregator maps are internally consistent (bidirectional check)."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "ART", "ROOM": "200"},
        ]
    )
    agg = Aggregator(df=df)
    by_loc = agg.by_location()
    by_instr = agg.by_instructor()

    # Every instructor listed under a location must list that location back
    for location, emp_ids in by_loc.items():
        for emp_id in emp_ids:
            assert emp_id in by_instr, f"{emp_id} missing from by_instructor"
            assert location in by_instr[emp_id], f"{location} missing for {emp_id}"

    # And vice versa
    for emp_id, locations in by_instr.items():
        for location in locations:
            assert location in by_loc, f"{location} missing from by_location"
            assert emp_id in by_loc[location], f"{emp_id} missing at {location}"
