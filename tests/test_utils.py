from datetime import date

from src.utils_date import (
    get_beijing_today,
    get_previous_week_range,
    get_previous_year_range,
)


def test_date_ranges():
    today = date(2026, 1, 5)  # A Monday

    # Previous week should be Monday to Sunday of the last week
    start, end = get_previous_week_range(today)
    assert start == date(2025, 12, 29)
    assert end == date(2026, 1, 4)

    # Previous year
    start_y, end_y = get_previous_year_range(today)
    assert start_y == date(2025, 1, 1)
    assert end_y == date(2025, 12, 31)


def test_beijing_today():
    # This depends on system time but we can check it returns a date
    today = get_beijing_today()
    assert isinstance(today, date)
