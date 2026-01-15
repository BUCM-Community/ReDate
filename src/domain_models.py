"""
src/domain_models.py
Core business data structures and monadic error handling types.
Focus: No-GIL safety (immutability), Result Pattern.
"""

from __future__ import annotations

import hashlib
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

__all__ = [
    "Result",
    "Ok",
    "Err",
    "AppError",
    "NewsNotFoundError",
    "NewsItem",
    "DailyNewsBatch",
    "WeeklyReport",
]


# --- Result Pattern (Monad) for Expected Failures ---
class Ok[T]:
    __match_args__ = ("value",)

    def __init__(self, value: T):
        self.value = value

    def is_ok(self) -> bool:
        return True


class Err[E]:
    __match_args__ = ("error",)

    def __init__(self, error: E):
        self.error = error

    def is_ok(self) -> bool:
        return False


type Result[T, E] = Ok[T] | Err[E]


# --- Domain Errors ---
class AppError(BaseModel):
    code: str
    message: str


class NewsNotFoundError(AppError):
    code: str = "NEWS_NOT_FOUND"


# --- Domain Entities ---
class NewsItem(BaseModel):
    """Represents a single piece of news (Immutable)."""

    model_config = ConfigDict(frozen=True)

    # API returns varying fields, we normalize them
    title: str | None = None
    content: str = Field(description="The main text body or digest")
    category: str | None = None
    url: HttpUrl | None = None
    published_at: date

    @property
    def fingerprint(self) -> str:
        """Calculates deterministic hash for this item."""
        payload = f"{self.content}|{self.url}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class DailyNewsBatch(BaseModel):
    """Collection of news for a specific day/category."""

    model_config = ConfigDict(frozen=True)

    date_str: date
    source: str  # e.g., "viki-60s", "viki-ai-news"
    items: list[NewsItem]
    cover_image_url: HttpUrl | None = None

    # Pre-calculated hash of the raw JSON response for idempotency
    raw_json_hash: str


class WeeklyReport(BaseModel):
    """Synthesized weekly or yearly summary."""

    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    summary_text: str
    key_events: list[str]
    best_cover_image: HttpUrl | None = None
