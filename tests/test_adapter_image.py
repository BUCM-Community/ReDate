from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapter_image import HybridImageAdapter


@pytest.mark.asyncio
async def test_image_adapter_fallback():
    adapter = HybridImageAdapter()
    adapter.unsplash_key = MagicMock()
    adapter.pexels_key = MagicMock()
    adapter.pixabay_key = MagicMock()

    with (
        patch.object(adapter, "_fetch_unsplash", return_value=None) as mock_un,
        patch.object(adapter, "_fetch_pexels", return_value=None) as mock_pex,
        patch.object(
            adapter,
            "_fetch_pixabay",
            return_value={"url": "http://img", "source": "Pixabay", "name": "test"},
        ) as mock_pix,
    ):
        result = await adapter.fetch_random_tech_image()

        assert result is not None
        assert result["source"] == "Pixabay"
        assert result["url"] == "http://img"

    await adapter.close()


@pytest.mark.asyncio
async def test_image_download_bytes():
    adapter = HybridImageAdapter()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read = AsyncMock(return_value=b"\x00\x01")

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_resp

        data = await adapter.download_image("http://test.com/img.jpg")
        assert data == b"\x00\x01"

    await adapter.close()
