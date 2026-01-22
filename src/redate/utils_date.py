"""
redate/utils_date.py
Date calculation utilities.
Focus: Pure functions, Timezone agnostic logic (operates on date objects).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

__all__ = [
    "get_beijing_today",
    "get_previous_week_range",
    "get_previous_year_range",
    "parse_date_string",
]

# 1. 显式定义业务时区为北京时间
TZ_SHANGHAI = ZoneInfo("Asia/Shanghai")


def get_beijing_today() -> date:
    """
    获取当前的北京日期，不受服务器系统时区影响。
    Crucial for consistent behavior across UTC (GitHub Actions) and Local envs.
    """
    return datetime.now(TZ_SHANGHAI).date()


def get_previous_week_range(reference_date: date | None = None) -> tuple[date, date]:
    """
    Calculates the start (Monday) and end (Sunday) of the previous week.

    Args:
        reference_date: The anchor date (usually 'today').
                        If None, defaults to get_beijing_today().

    Returns:
        (start_date, end_date) where:
        - start_date is the Monday of the previous week.
        - end_date is the Sunday of the previous week.

    Example:
        If today is Monday 2026-01-12:
        Returns (2026-01-05, 2026-01-11)
    """
    if reference_date is None:
        reference_date = get_beijing_today()

    # Python's weekday(): Monday=0, Sunday=6
    current_weekday = reference_date.weekday()

    # Calculate days to subtract to get to LAST week's Monday
    # Logic: Go back to this week's Monday (current_weekday), then go back 7 more days (Monday to Monday).
    days_to_subtract = current_weekday + 7

    start_date = reference_date - timedelta(days=days_to_subtract)
    end_date = start_date + timedelta(days=6)

    return start_date, end_date


def get_previous_year_range(reference_date: date | None = None) -> tuple[date, date]:
    """Returns (Jan 1, Dec 31) of the previous year."""
    if reference_date is None:
        reference_date = get_beijing_today()

    prev_year = reference_date.year - 1
    return date(prev_year, 1, 1), date(prev_year, 12, 31)


def parse_date_string(date_str: str | None) -> date | None:
    """Safely parses partial date strings or timestamps."""
    if not date_str:
        return None
    try:
        # Try ISO format first (YYYY-MM-DD)
        return date.fromisoformat(date_str.split(" ")[0])
    except ValueError:
        return None
