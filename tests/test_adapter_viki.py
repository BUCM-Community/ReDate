from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapter_viki import VikiNewsAdapter
from src.domain_models import Err, NewsNotFoundError, Ok


@pytest.mark.asyncio
async def test_viki_adapter_success():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={
            "data": [
                {
                    "title": "Test News",
                    "content": "<p>Content</p>",
                    "date": "2026-01-01",
                }
            ]
        }
    )

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_resp

        adapter = VikiNewsAdapter(base_url="http://test.api")
        result = await adapter.fetch_daily(date(2026, 1, 1))

        assert isinstance(result, Ok)
        batch = result.value
        assert len(batch.items) == 1
        assert batch.items[0].title == "Test News"
        await adapter.close()


@pytest.mark.asyncio
async def test_viki_adapter_404():
    mock_resp = MagicMock()
    mock_resp.status = 404

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_resp

        adapter = VikiNewsAdapter(base_url="http://test.api")
        result = await adapter.fetch_daily(date(2026, 1, 1))

        assert isinstance(result, Err)
        assert isinstance(result.error, NewsNotFoundError)
        await adapter.close()
