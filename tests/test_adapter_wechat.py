import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapter_wechat import WeChatAdapter


@pytest.fixture
def mock_token_cache(tmp_path):
    cache_file = tmp_path / "wx_token.json"
    with patch("src.adapter_wechat.Path", return_value=cache_file):
        yield cache_file


@pytest.mark.asyncio
async def test_wechat_get_token_cached(mock_token_cache):
    # Setup cache
    mock_token_cache.parent.mkdir(parents=True, exist_ok=True)
    mock_token_cache.write_text(
        json.dumps({"token": "cached_token", "expires_at": time.time() + 1000})
    )

    adapter = WeChatAdapter()
    token = await adapter._get_token()
    assert token == "cached_token"
    await adapter.close()


@pytest.mark.asyncio
async def test_wechat_get_token_refresh():
    adapter = WeChatAdapter()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"access_token": "new_token", "expires_in": 7200}
    )

    with patch.object(adapter.aclient, "post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_resp

        # Ensure cache is empty
        with patch("src.adapter_wechat.Path.exists", return_value=False):
            token = await adapter._get_token()
            assert token == "new_token"

    await adapter.close()


@pytest.mark.asyncio
async def test_wechat_publish_article():
    adapter = WeChatAdapter()
    adapter._get_token = AsyncMock(return_value="token123")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"media_id": "draft123"})

    with patch.object(adapter.aclient, "post") as mock_post:
        mock_post.return_value.__aenter__.return_value = mock_resp

        media_id = await adapter.publish_article("Title", "Content", None)
        assert media_id == "draft123"

    await adapter.close()
