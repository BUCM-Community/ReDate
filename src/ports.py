"""
src/ports.py
Defines abstract interfaces (Protocols) for infrastructure adapters.
Focus: Dependency Inversion, Logic/Infra decoupling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .domain_models import DailyNewsBatch, NewsNotFoundError, Result, WeeklyReport

if TYPE_CHECKING:
    from datetime import date

__all__ = ["NewsFetcher", "StorageAdapter", "LLMEngine", "Publisher", "ImageFetcher"]


@runtime_checkable
class NewsFetcher(Protocol):
    """Interface for fetching external news."""

    async def fetch_daily(
        self, target_date: date, category: str = "60s"
    ) -> Result[DailyNewsBatch, NewsNotFoundError]: ...

    async def download_image(self, url: str) -> bytes | None: ...


@runtime_checkable
class ImageFetcher(Protocol):
    """Interface for fetching stock images."""

    async def fetch_random_tech_image(self) -> dict[str, str] | None: ...

    async def download_image(self, url: str) -> bytes | None: ...


@runtime_checkable
class StorageAdapter(Protocol):
    """Interface for Persistence (Object Storage + Vector DB)."""

    async def archive_raw(self, filename: str, data: bytes) -> bool:
        """Uploads raw data to Object Storage (R2)."""
        ...

    async def check_exists(self, content_hash: str, source: str) -> bool:
        """Checks idempotency in the specific source table."""
        ...

    async def save_embedding(self, batch: DailyNewsBatch, vector: list[float]) -> None:
        """Saves metadata and vector to LanceDB."""
        ...

    async def get_date_range_context(self, start: date, end: date) -> list[str]:
        """Retrieves raw texts for summaries (Weekly/Yearly)."""
        ...


@runtime_checkable
class LLMEngine(Protocol):
    """Interface for AI operations."""

    async def generate_embedding(self, text: str) -> list[float]: ...

    async def summarize_daily(self, text: str) -> str: ...

    # support both Weekly and Yearly
    async def generate_period_report(
        self, contexts: list[str], start_date: date, end_date: date, period_type: str = "Weekly"
    ) -> WeeklyReport: ...


@runtime_checkable
class Publisher(Protocol):
    """Interface for Publishing (WeChat)."""

    async def publish_article(self, title: str, html_content: str, cover_image: bytes | None) -> str:
        """Returns the publication ID (e.g., media_id) or URL."""
        ...

    async def upload_permanent_material(self, image_data: bytes, filename: str) -> str | None:
        """Uploads a permanent image material."""
        ...
