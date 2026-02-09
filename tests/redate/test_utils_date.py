"""
tests/redate/test_utils_date.py

Unit tests for Date Utilities.

Focus:
- Timezone correctness.
- Boundary logic.
"""

from datetime import date

from redate.utils_date import (
    get_beijing_today,
    get_previous_week_range,
    parse_date_string,
)


def test_get_beijing_today_returns_date():
    """Basic sanity check for timezone utility."""
    d = get_beijing_today()
    assert isinstance(d, date)


def test_get_previous_week_range_logic():
    """
    Verify week calculation.

    If reference is Monday 2026-01-12, previous week is Jan 5 (Mon) - Jan 11 (Sun).
    """
    ref_date = date(2026, 1, 12)  # Monday
    start, end = get_previous_week_range(ref_date)
    assert start == date(2026, 1, 5)
    assert end == date(2026, 1, 11)


def test_parse_date_string_formats():
    """Test parsing robustness."""
    assert parse_date_string("2026-01-20") == date(2026, 1, 20)
    assert parse_date_string("2026-01-20 10:00:00") == date(2026, 1, 20)
    assert parse_date_string("invalid") is None
