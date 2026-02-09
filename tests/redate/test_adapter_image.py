"""
tests/redate/test_adapter_image.py

Unit tests for Image Fetcher Fallback logic.

Focus:
- Provider rotation.
- Download handling.
"""

from unittest.mock import AsyncMock, patch

import pytest

from redate.adapter_image import HybridImageAdapter


@pytest.mark.asyncio
async def test_fallback_strategy():
    """Test that if first source fails, second is tried."""
    adapter = HybridImageAdapter()

    # Mock the internal fetch methods directly to control the flow
    # We want to verify that one fails and the next is called.
    # Logic in code: list is shuffled. We need to patch the methods on the instance
    # or class to return None or valid dict.

    with (
        patch.object(adapter, "_fetch_unsplash", new_callable=AsyncMock) as m_un,
        patch.object(adapter, "_fetch_pexels", new_callable=AsyncMock) as m_pex,
        patch.object(adapter, "_fetch_pixabay", new_callable=AsyncMock) as m_pix,
    ):
        # Setup: Unsplash fails, Pexels succeeds, Pixabay ignored
        m_un.return_value = None
        m_pex.return_value = {"url": "http://ok", "source": "Pexels", "name": "ok"}

        # Since logic shuffles, we can't guarantee order unless we mock random.shuffle
        # Or we just make ALL fail except one.
        m_pix.return_value = None

        result = await adapter.fetch_random_tech_image()

        assert result is not None
        assert result["source"] == "Pexels"

    await adapter.close()


@pytest.mark.asyncio
async def test_download_image_success():
    """Test successful image download."""
    adapter = HybridImageAdapter()

    with patch.object(adapter.client, "get") as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"image_bytes"
        mock_get.return_value.__aenter__.return_value = mock_resp

        data = await adapter.download_image("http://test.com/img.jpg")
        assert data == b"image_bytes"

    await adapter.close()
