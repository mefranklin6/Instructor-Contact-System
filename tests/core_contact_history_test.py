"""Tests for contact-history I/O, non-dev send paths, and template validation."""

from datetime import datetime

import pandas as pd
import pytest

from src.core.schedule_aggregator import Aggregator
from src.core.settings import Settings
from src.core.system import InstructorContactSystemCore


# ---------------------------------------------------------------------------
# Shared helpers (mirrors core_system_test._build_core but without I/O stubs)
# ---------------------------------------------------------------------------


class _FakeMatcher:
    def __init__(self, mapping):
        self._mapping = mapping

    def match_id_to_email(self, emp_id):
        return self._mapping.get(str(emp_id), "")


class _FakeEmailSender:
    def __init__(self, *, fail_addrs=None, raise_addrs=None):
        self.sent = []
        self._fail_addrs = fail_addrs or set()
        self._raise_addrs = raise_addrs or set()

    def send(self, to_addr, subject, message, cc_addrs=None):
        if to_addr in self._raise_addrs:
            raise RuntimeError(f"Simulated send failure for {to_addr}")
        if to_addr in self._fail_addrs:
            return False
        self.sent.append((to_addr, subject, message, list(cc_addrs or [])))
        return True


def _build_core(df, mapping, *, dev_mode=True, fail_addrs=None, raise_addrs=None):
    """Build a core instance with injected fakes; contact history I/O is NOT stubbed."""
    settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=dev_mode,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=None,
    )
    core = object.__new__(InstructorContactSystemCore)
    core.in_docker = False
    core.settings = settings
    core.max_failed_display = 50
    core.supported_locations = None
    core.loader = None
    core.df = df
    core.contacted_instructors = {}
    core.id_matcher = _FakeMatcher(mapping)
    core.email_sender = _FakeEmailSender(fail_addrs=fail_addrs, raise_addrs=raise_addrs)
    agg = Aggregator(df=df)
    core.aggregator = agg
    core.contact_by_instructor = agg.by_instructor()
    core.contact_by_location = agg.by_location()
    return core


_SIMPLE_DF = pd.DataFrame(
    [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
)


# ---------------------------------------------------------------------------
# get_contact_file_path
# ---------------------------------------------------------------------------


def test_get_contact_file_path_non_docker():
    """Returns local filename when not running in Docker."""
    core = _build_core(_SIMPLE_DF, {})
    assert core.get_contact_file_path() == "contact_history.json"


def test_get_contact_file_path_docker():
    """Returns /data path when running in Docker."""
    core = _build_core(_SIMPLE_DF, {})
    core.in_docker = True
    assert core.get_contact_file_path() == "/data/contact_history.json"


# ---------------------------------------------------------------------------
# load_contact_history / save_contact_history
# ---------------------------------------------------------------------------


def test_load_contact_history_returns_empty_when_file_missing(tmp_path, monkeypatch):
    """load_contact_history sets contacted_instructors to {} when no file exists."""
    monkeypatch.chdir(tmp_path)
    core = _build_core(_SIMPLE_DF, {})
    core.load_contact_history()
    assert core.contacted_instructors == {}


def test_save_and_load_contact_history_round_trips(tmp_path, monkeypatch):
    """save_contact_history writes JSON that load_contact_history can reload."""
    monkeypatch.chdir(tmp_path)
    core = _build_core(_SIMPLE_DF, {})
    core.contacted_instructors = {"alice@test.edu": {"contact_type": "start of semester"}}
    core.save_contact_history()

    core.contacted_instructors = {}
    core.load_contact_history()
    assert core.contacted_instructors == {"alice@test.edu": {"contact_type": "start of semester"}}


# ---------------------------------------------------------------------------
# get_already_contacted_count
# ---------------------------------------------------------------------------


def test_get_already_contacted_count_only_counts_semester_contacts(tmp_path, monkeypatch):
    """get_already_contacted_count ignores classroom-only contacts."""
    monkeypatch.chdir(tmp_path)
    core = _build_core(_SIMPLE_DF, {})
    core.contacted_instructors = {
        "a@test.edu": {"contact_type": "start of semester"},
        "b@test.edu": {"contact_type": "start of semester"},
        "c@test.edu": {"classroom_messages": [{"contact_type": "all instructors for classroom"}]},
    }
    core.save_contact_history()

    count = core.get_already_contacted_count()
    assert count == 2


# ---------------------------------------------------------------------------
# send_test_email
# ---------------------------------------------------------------------------


def test_send_test_email_raises_on_invalid_address():
    """send_test_email raises ValueError when email lacks an '@'."""
    core = _build_core(_SIMPLE_DF, {})
    with pytest.raises(ValueError, match="valid email"):
        core.send_test_email(email="not-an-email", logging_level="INFO")


def test_send_test_email_dev_mode_returns_log_message():
    """send_test_email in dev mode returns a DEV MODE string without sending."""
    core = _build_core(_SIMPLE_DF, {}, dev_mode=True)
    result = core.send_test_email(email="admin@test.edu", logging_level="INFO")
    assert "DEV MODE" in result


# ---------------------------------------------------------------------------
# send_message_to_classroom — non-dev mode
# ---------------------------------------------------------------------------


def test_send_message_to_classroom_non_dev_updates_history(tmp_path, monkeypatch):
    """Non-dev classroom send records the contact in contacted_instructors."""
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"}, dev_mode=False)

    result = core.send_message_to_classroom(
        building="SCI",
        room="101",
        subject="Test",
        message_template="Hello from {location}",
    )

    assert result.sent == 1
    assert result.failed == []
    history = core.contacted_instructors["alice@test.edu"]["classroom_messages"]
    assert history[0]["contact_type"] == "all instructors for classroom"


def test_send_message_to_classroom_non_dev_records_failure(tmp_path, monkeypatch):
    """Non-dev classroom send records failed recipients."""
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(
        df, {"000000001": "alice@test.edu"}, dev_mode=False, fail_addrs={"alice@test.edu"}
    )

    result = core.send_message_to_classroom(
        building="SCI", room="101", subject="Test", message_template="Hello from {location}"
    )

    assert result.sent == 0
    assert "alice@test.edu" in result.failed


# ---------------------------------------------------------------------------
# Message template validation
# ---------------------------------------------------------------------------


def test_send_message_to_classroom_bad_template_raises():
    """send_message_to_classroom raises ValueError for unrecognised placeholders."""
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"})

    with pytest.raises(ValueError, match="Missing placeholder"):
        core.send_message_to_classroom(
            building="SCI",
            room="101",
            subject="Test",
            message_template="Hello {bad_placeholder}",
        )


def test_execute_deployment_bad_template_raises():
    """execute_deployment raises ValueError for unrecognised template placeholders."""
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"})
    candidates = core.compute_semester_deployment_candidates()

    with pytest.raises(ValueError, match="Missing placeholder"):
        core.execute_deployment(
            instructors=candidates,
            message_template="Hello {bad_placeholder}",
            batch_size=10,
            subject="Test",
        )


# ---------------------------------------------------------------------------
# execute_deployment — non-dev email failure
# ---------------------------------------------------------------------------


def test_execute_deployment_non_dev_records_send_failure(tmp_path, monkeypatch):
    """execute_deployment in non-dev mode records instructors whose sends raise an exception."""
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(
        df, {"000000001": "alice@test.edu"}, dev_mode=False, raise_addrs={"alice@test.edu"}
    )

    candidates = core.compute_semester_deployment_candidates()
    result = core.execute_deployment(
        instructors=candidates,
        message_template="Hello {locations}",
        batch_size=10,
        subject="Test",
    )

    assert result.contacted_this_batch == 0
    assert "alice@test.edu" in result.failed


# ---------------------------------------------------------------------------
# compute_semester_deployment_candidates — no email match
# ---------------------------------------------------------------------------


def test_compute_semester_deployment_skips_instructors_with_no_email():
    """compute_semester_deployment_candidates skips emp_ids with no email match."""
    df = pd.DataFrame(
        [
            {"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"},
            {"INSTRUCTOR1_EMPLID": "000000002", "BUILDING": "ART", "ROOM": "200"},
        ]
    )
    # Only 000000001 has an email
    core = _build_core(df, {"000000001": "alice@test.edu"})
    core.load_contact_history = lambda: None

    candidates = core.compute_semester_deployment_candidates()
    emails = [c["email"] for c in candidates]
    assert emails == ["alice@test.edu"]


# ---------------------------------------------------------------------------
# get_aggregated_data_for_date_range — loader not configured
# ---------------------------------------------------------------------------


def test_get_aggregated_data_raises_when_loader_not_configured():
    """get_aggregated_data_for_date_range raises ModuleNotFoundError without a loader."""
    core = _build_core(_SIMPLE_DF, {})
    # loader is None in _build_core

    with pytest.raises(ModuleNotFoundError, match="Data loader module is not configured"):
        core.get_aggregated_data_for_date_range(datetime(2025, 1, 1), datetime(2025, 1, 31))


# ---------------------------------------------------------------------------
# get_server_diagnostics — smoke test
# ---------------------------------------------------------------------------


def test_get_server_diagnostics_returns_string():
    """get_server_diagnostics returns a non-empty diagnostic report string."""
    core = _build_core(_SIMPLE_DF, {})
    report = core.get_server_diagnostics(logging_level="INFO")
    assert isinstance(report, str)
    assert "DEV_MODE" in report
    assert "Total Instructors" in report


# ---------------------------------------------------------------------------
# get_contact_history_dict
# ---------------------------------------------------------------------------


def test_get_contact_history_dict_returns_dict(tmp_path, monkeypatch):
    """get_contact_history_dict reloads from disk and returns the dict."""
    monkeypatch.chdir(tmp_path)
    core = _build_core(_SIMPLE_DF, {})
    core.contacted_instructors = {"x@test.edu": {"contact_type": "start of semester"}}
    core.save_contact_history()

    core.contacted_instructors = {}
    result = core.get_contact_history_dict()
    assert "x@test.edu" in result


# ---------------------------------------------------------------------------
# get_aggregated_data_for_date_range — with a fake loader
# ---------------------------------------------------------------------------


def test_get_aggregated_data_for_date_range_with_loader():
    """get_aggregated_data_for_date_range returns maps when the loader returns data."""

    class _FakeLoader:
        def range_data(self, start, end):
            return pd.DataFrame(
                [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
            )

    core = _build_core(_SIMPLE_DF, {"000000001": "alice@test.edu"})
    core.loader = _FakeLoader()

    by_instr, by_loc = core.get_aggregated_data_for_date_range(
        datetime(2025, 1, 1), datetime(2025, 1, 31)
    )
    assert "000000001" in by_instr
    assert "SCI 101" in by_loc


def test_get_aggregated_data_raises_when_loader_returns_empty():
    """get_aggregated_data_for_date_range raises ValueError when loader returns empty df."""

    class _EmptyLoader:
        def semester_data(self, date):
            return pd.DataFrame()

    core = _build_core(_SIMPLE_DF, {})
    core.loader = _EmptyLoader()

    with pytest.raises(ValueError, match="No data available"):
        core.get_aggregated_data_for_date_range()  # no dates → semester_data path


# ---------------------------------------------------------------------------
# send_message_to_classroom — remaining uncovered paths
# ---------------------------------------------------------------------------


def test_send_message_to_classroom_raises_when_no_emails_match():
    """send_message_to_classroom raises ValueError when no instructor has an email."""
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    # Empty mapping: no IDs resolve to emails
    core = _build_core(df, {})

    with pytest.raises(ValueError, match="No email matches found"):
        core.send_message_to_classroom(
            building="SCI", room="101", subject="Test", message_template="Hello from {location}"
        )


def test_send_message_to_classroom_non_dev_handles_send_exception(tmp_path, monkeypatch):
    """send_message_to_classroom handles and records exceptions raised by the sender."""
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(
        df, {"000000001": "alice@test.edu"}, dev_mode=False, raise_addrs={"alice@test.edu"}
    )

    result = core.send_message_to_classroom(
        building="SCI", room="101", subject="Test", message_template="Hello from {location}"
    )

    assert result.sent == 0
    # When send raises, ok stays False → failed list
    assert "alice@test.edu" in result.failed


def test_send_message_to_classroom_dev_mode_does_not_send(tmp_path, monkeypatch):
    """send_message_to_classroom in dev mode logs but returns zero sent."""
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"}, dev_mode=True)

    result = core.send_message_to_classroom(
        building="SCI", room="101", subject="Test", message_template="Hello from {location}"
    )

    assert result.sent == 0
    assert result.failed == []
    if core.email_sender:
        assert core.email_sender.sent == []


# ---------------------------------------------------------------------------
# Unconfigured-module guards
# ---------------------------------------------------------------------------


def test_compute_deployment_candidates_raises_when_matcher_none():
    """compute_semester_deployment_candidates raises when id_matcher is None."""
    core = _build_core(_SIMPLE_DF, {})
    core.id_matcher = None

    with pytest.raises(RuntimeError, match="ID matcher"):
        core.compute_semester_deployment_candidates()


def test_execute_deployment_raises_when_matcher_none():
    """execute_deployment raises when id_matcher is None."""
    core = _build_core(_SIMPLE_DF, {})
    core.id_matcher = None

    with pytest.raises(RuntimeError, match="ID matcher"):
        core.execute_deployment(
            instructors=[],
            message_template="Hello {locations}",
            batch_size=10,
            subject="Test",
        )


# ---------------------------------------------------------------------------
# Lookup methods — matcher not configured
# ---------------------------------------------------------------------------


def test_lookup_classroom_emails_raises_when_matcher_none():
    """lookup_classroom_emails raises RuntimeError when id_matcher is None."""
    core = _build_core(_SIMPLE_DF, {})
    core.id_matcher = None

    with pytest.raises(RuntimeError, match="ID matcher"):
        core.lookup_classroom_emails(building="SCI", room="101")


def test_lookup_instructor_locations_raises_when_matcher_none():
    """lookup_instructor_locations raises RuntimeError when id_matcher is None."""
    core = _build_core(_SIMPLE_DF, {})
    core.id_matcher = None

    with pytest.raises(RuntimeError, match="ID matcher"):
        core.lookup_instructor_locations(email="alice@test.edu")


# ---------------------------------------------------------------------------
# send_message_to_classroom — unconfigured and unknown location
# ---------------------------------------------------------------------------


def test_send_message_to_classroom_raises_when_unconfigured():
    """send_message_to_classroom raises RuntimeError when id_matcher is None."""
    core = _build_core(_SIMPLE_DF, {})
    core.id_matcher = None

    with pytest.raises(RuntimeError, match="ID matcher"):
        core.send_message_to_classroom(
            building="SCI", room="101", subject="Test", message_template="Hello {location}"
        )


def test_send_message_to_classroom_raises_on_unknown_location():
    """send_message_to_classroom raises KeyError for an unrecognised location."""
    core = _build_core(_SIMPLE_DF, {"000000001": "alice@test.edu"})

    with pytest.raises(KeyError, match="No classes found"):
        core.send_message_to_classroom(
            building="XXX", room="999", subject="Test", message_template="Hello {location}"
        )


# ---------------------------------------------------------------------------
# get_server_diagnostics — different settings branches
# ---------------------------------------------------------------------------


def test_get_server_diagnostics_ad_api_mode():
    """Diagnostics string reflects ad_api mode (no local file path)."""
    core = _build_core(_SIMPLE_DF, {})
    core.settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="ad_api",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=None,
    )
    report = core.get_server_diagnostics(logging_level="DEBUG")
    assert "Active Directory API" in report


def test_get_server_diagnostics_ad_json_mode():
    """Diagnostics string reflects ad_json mode (includes file size/records lines)."""
    core = _build_core(_SIMPLE_DF, {})
    core.settings = Settings(
        supported_locations_mode="none",
        id_to_email_module="ad_json",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path=None,
    )
    report = core.get_server_diagnostics(logging_level="DEBUG")
    assert "id_and_emails_from_ad.json" in report


def test_get_server_diagnostics_chico_mode():
    """Diagnostics string reflects chico supported-locations mode."""
    core = _build_core(_SIMPLE_DF, {})
    core.settings = Settings(
        supported_locations_mode="chico",
        id_to_email_module="zoom_csv",
        schedule_module="fl_csv",
        dev_mode=True,
        zoom_csv_path=None,
        fl_file_path=None,
        supported_locations_file_path="/path/to/sl.csv",
    )
    report = core.get_server_diagnostics(logging_level="INFO")
    assert "Supported Locations File" in report


# ---------------------------------------------------------------------------
# send_test_email — non-dev mode successful send
# ---------------------------------------------------------------------------


def test_send_test_email_non_dev_mode_sends_successfully():
    """send_test_email in non-dev mode returns success message when sender succeeds."""
    core = _build_core(_SIMPLE_DF, {}, dev_mode=False)
    result = core.send_test_email(email="admin@test.edu", logging_level="INFO")
    assert "sent successfully" in result


def test_send_test_email_non_dev_raises_when_send_fails():
    """send_test_email raises RuntimeError when the email send returns False."""
    core = _build_core(_SIMPLE_DF, {}, dev_mode=False, fail_addrs={"admin@test.edu"})
    with pytest.raises(RuntimeError, match="Failed to send test email"):
        core.send_test_email(email="admin@test.edu", logging_level="INFO")


# ---------------------------------------------------------------------------
# get_server_diagnostics — runtime_value_summary list/set branches
# ---------------------------------------------------------------------------


def test_get_server_diagnostics_with_list_supported_locations():
    """Diagnostics string reflects a list-type supported_locations value."""
    core = _build_core(_SIMPLE_DF, {})
    core.supported_locations = [("SCI", "101"), ("ART", "200")]  # list → hits list branch
    report = core.get_server_diagnostics(logging_level="INFO")
    assert "list (len=2)" in report


def test_get_server_diagnostics_with_set_supported_locations():
    """Diagnostics string reflects a set-type supported_locations value."""
    core = _build_core(_SIMPLE_DF, {})
    core.supported_locations = {("SCI", "101")}  # set → hits set branch
    report = core.get_server_diagnostics(logging_level="INFO")
    assert "set (len=1)" in report


def test_get_server_diagnostics_with_dict_supported_locations():
    """Diagnostics string reflects a dict-type supported_locations value."""
    core = _build_core(_SIMPLE_DF, {})
    core.supported_locations = {"SCI": "101"}  # dict → hits dict branch
    report = core.get_server_diagnostics(logging_level="INFO")
    assert "dict (len=1)" in report


def test_get_server_diagnostics_with_non_container_supported_locations():
    """Diagnostics string handles a non-container supported_locations (default branch)."""
    core = _build_core(_SIMPLE_DF, {})
    core.supported_locations = object()  # not dict/list/set → hits default branch
    report = core.get_server_diagnostics(logging_level="INFO")
    assert isinstance(report, str)


# ---------------------------------------------------------------------------
# send_message_to_classroom — malformed contacted_instructors data
# ---------------------------------------------------------------------------


def test_send_message_to_classroom_handles_malformed_history(tmp_path, monkeypatch):
    """send_message_to_classroom resets malformed history entries gracefully."""
    import json as _json

    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"}, dev_mode=False)
    # Write malformed contact history to disk so load_contact_history picks it up
    (tmp_path / "contact_history.json").write_text(
        _json.dumps({"alice@test.edu": "not-a-dict"}), encoding="utf-8"
    )

    result = core.send_message_to_classroom(
        building="SCI", room="101", subject="Test", message_template="Hello from {location}"
    )

    assert result.sent == 1
    assert isinstance(core.contacted_instructors["alice@test.edu"]["classroom_messages"], list)


def test_send_message_to_classroom_handles_non_list_classroom_messages(tmp_path, monkeypatch):
    """send_message_to_classroom resets classroom_messages when it is not a list."""
    import json as _json

    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"}, dev_mode=False)
    # classroom_messages is a string (not a list) → triggers history = [] reset
    (tmp_path / "contact_history.json").write_text(
        _json.dumps({"alice@test.edu": {"classroom_messages": "bad-data"}}), encoding="utf-8"
    )

    result = core.send_message_to_classroom(
        building="SCI", room="101", subject="Test", message_template="Hello from {location}"
    )

    assert result.sent == 1
    assert isinstance(core.contacted_instructors["alice@test.edu"]["classroom_messages"], list)


def test_execute_deployment_handles_malformed_contacted_record(tmp_path, monkeypatch):
    """execute_deployment resets non-dict existing contact records gracefully."""
    monkeypatch.chdir(tmp_path)
    df = pd.DataFrame(
        [{"INSTRUCTOR1_EMPLID": "000000001", "BUILDING": "SCI", "ROOM": "101"}]
    )
    core = _build_core(df, {"000000001": "alice@test.edu"}, dev_mode=True)
    # Pre-populate with a non-dict entry
    core.contacted_instructors = {"alice@test.edu": "not-a-dict"}  # triggers reset (line 579)
    core.load_contact_history = lambda: None  # don't overwrite with file

    candidates = [
        {
            "email": "alice@test.edu",
            "emp_id": "000000001",
            "locations": ["SCI 101"],
            "contacted": False,
        }
    ]
    result = core.execute_deployment(
        instructors=candidates,
        message_template="Hello {locations}",
        batch_size=10,
        subject="Test",
    )

    assert result.contacted_this_batch == 1
    assert core.contacted_instructors["alice@test.edu"]["contact_type"] == "start of semester"

