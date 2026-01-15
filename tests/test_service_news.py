from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.domain_models import DailyNewsBatch, Err, NewsItem, NewsNotFoundError, Ok
from src.service_news import NewsService


@pytest.mark.asyncio
async def test_run_daily_workflow_success():
    # Setup mocks
    mock_fetcher = AsyncMock()
    mock_storage = AsyncMock()
    mock_llm = AsyncMock()
    mock_publisher = AsyncMock()

    batch = DailyNewsBatch(
        date_str=date(2026, 1, 1),
        source="viki-60s",
        items=[NewsItem(content="Test", published_at=date(2026, 1, 1))],
        raw_json_hash="hash123",
    )
    mock_fetcher.fetch_daily.return_value = Ok(batch)
    mock_storage.check_exists.return_value = False
    mock_llm.generate_embedding.return_value = [0.1, 0.2]

    service = NewsService(
        fetcher=mock_fetcher,
        storage=mock_storage,
        llm=mock_llm,
        publisher=mock_publisher,
    )

    await service.run_daily_workflow(date(2026, 1, 1))

    # Assertions
    mock_fetcher.fetch_daily.assert_called_once()
    mock_storage.check_exists.assert_called_once_with("hash123", "viki-60s")
    mock_storage.archive_raw.assert_called_once()
    mock_llm.generate_embedding.assert_called_once()
    mock_storage.save_embedding.assert_called_once()


@pytest.mark.asyncio
async def test_run_daily_workflow_idempotent():
    mock_fetcher = AsyncMock()
    mock_storage = AsyncMock()

    batch = DailyNewsBatch(
        date_str=date(2026, 1, 1), source="viki-60s", items=[], raw_json_hash="hash123"
    )
    mock_fetcher.fetch_daily.return_value = Ok(batch)
    mock_storage.check_exists.return_value = True

    service = NewsService(mock_fetcher, mock_storage, AsyncMock(), AsyncMock())
    await service.run_daily_workflow(date(2026, 1, 1))

    mock_storage.archive_raw.assert_not_called()


@pytest.mark.asyncio
async def test_run_daily_workflow_fetch_error():
    mock_fetcher = AsyncMock()
    mock_fetcher.fetch_daily.return_value = Err(NewsNotFoundError(message="Not found"))

    mock_storage = AsyncMock()
    service = NewsService(mock_fetcher, mock_storage, AsyncMock(), AsyncMock())

    await service.run_daily_workflow(date(2026, 1, 1))

    mock_storage.check_exists.assert_not_called()
