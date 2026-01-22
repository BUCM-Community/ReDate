"""
tests/test_adapter_viki.py
Unit tests for VikiNewsAdapter.
Focus: Resilience, parsing logic, and correct handling of 404s.
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from redate.adapter_viki import VikiNewsAdapter
from redate.domain_models import Err, NewsNotFoundError, Ok


@pytest.mark.asyncio
async def test_fetch_daily_success_parsing(mocker):
    """
    Test parsing of Viki HTML content.
    """
    # Mock Data with HTML
    mock_json = {
        "data": [
            {
                "title": "Tech News",
                "content": "<p><b>Bold</b> move.</p>",
                "url": "http://viki.moe/1",
                "date": "2026-01-22",
            }
        ]
    }

    # Setup aiohttp mock
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = mock_json

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_response

    mocker.patch("aiohttp.ClientSession.get", return_value=mock_ctx)

    async with VikiNewsAdapter() as adapter:
        result = await adapter.fetch_daily(date(2026, 1, 22), "60s")

    assert isinstance(result, Ok)
    item = result.value.items[0]
    # Check HTML stripping
    assert item.content == "Bold move."
    assert item.published_at == date(2026, 1, 22)


@pytest.mark.asyncio
async def test_fetch_daily_404_handled_as_result(mocker):
    """
    Ensure 404 returns an Err result object, not raising an exception.
    """
    mock_response = AsyncMock()
    mock_response.status = 404

    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = mock_response

    mocker.patch("aiohttp.ClientSession.get", return_value=mock_ctx)

    async with VikiNewsAdapter() as adapter:
        result = await adapter.fetch_daily(date(2026, 1, 22))

    assert isinstance(result, Err)
    assert isinstance(result.error, NewsNotFoundError)


@pytest.mark.asyncio
async def test_fetch_daily_retry_on_500(mocker, mock_sleep):
    """
    Ensure tenacity retry logic is triggered on server errors.
    """
    # 1. Setup Mock to fail twice then succeed
    mock_fail = AsyncMock()
    mock_fail.status = 500
    mock_fail.raise_for_status.side_effect = Exception("Server Error")

    mock_success = AsyncMock()
    mock_success.status = 200
    mock_success.json.return_value = {"data": [{"title": "OK"}]}

    mock_ctx_fail = AsyncMock()
    mock_ctx_fail.__aenter__.return_value = mock_fail

    mock_ctx_success = AsyncMock()
    mock_ctx_success.__aenter__.return_value = mock_success

    # aiohttp.ClientSession.get called multiple times
    mock_get = mocker.patch(
        "aiohttp.ClientSession.get",
        side_effect=[mock_ctx_fail, mock_ctx_fail, mock_ctx_success],
    )

    async with VikiNewsAdapter() as adapter:
        result = await adapter.fetch_daily(date(2026, 1, 22))

    assert isinstance(result, Ok)
    assert mock_get.call_count == 3  # 2 fails + 1 success
