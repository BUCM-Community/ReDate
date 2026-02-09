"""
redate/adapter_wechat.py

WeChat API Client.

Focus: Sidecar Proxy via env vars, async I/O, Token Management.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import ClientTimeout, FormData
from pydantic import BaseModel

from .config import settings
from .ports import Publisher
from .utils_telemetry import logger

if TYPE_CHECKING:
    from types import TracebackType

__all__ = ["WeChatAdapter"]


class TokenCache(BaseModel):
    """Schema for the locally cached access token."""

    token: str
    expires_at: float


class WeChatAdapter(Publisher):
    """
    WeChat Official Account Publisher Adapter.

    Handles token lifecycle management and content publishing.
    Relies on an external proxy sidecar for network access.

    Logic:
    ```mermaid
    graph TD
        A[Publish] --> B[Get Token]
        B --> C{Cache Valid?}
        C -->|Yes| D[Return Token]
        C -->|No| E[Fetch API]
        E --> F[Update Cache]
        F --> D
        D --> G[Upload Media]
        G --> H[Create Draft]
    ```
    """

    def __init__(self) -> None:
        """
        Initializes the WeChat adapter.

        Configures the client session to trust environment variables (for proxy support)
        and sets up the local token cache path.
        """
        # Decouple ClientSession and Proxy via sidecar container.
        self.aclient = aiohttp.ClientSession(
            timeout=ClientTimeout(total=45.0),
            trust_env=True,  # Explicitly use WECHAT_PROXY_URL env vars
        )

        # Local cache for Access Token (persisted in data volume)
        self.token_cache_path = Path("data/wx_token.json")

    async def _get_token(self) -> str:
        """Retrieves or refreshes Access Token."""
        # 1. Check Cache
        if self.token_cache_path.exists():
            try:
                # Use Pydantic to strictly parse and type-check the JSON content
                cache = TokenCache.model_validate_json(self.token_cache_path.read_text())
                # Buffer of 5 minutes
                if cache.expires_at > time.time() + 300:
                    return cache.token
            except Exception:
                logger.warning("token_cache_corrupt")

        # 2. Fetch New
        # The infrastructure intercepts this request if HTTPS_PROXY is set.
        url = "https://api.weixin.qq.com/cgi-bin/stable_token"
        payload = {
            "grant_type": "client_credential",
            "appid": settings.WECHAT_APP_ID.get_secret_value(),
            "secret": settings.WECHAT_APP_SECRET.get_secret_value(),
        }

        logger.info("fetching_wechat_token", url=url)

        try:
            async with self.aclient.post(url, json=payload) as resp:
                resp.raise_for_status()
                data = await resp.json()

                if "access_token" not in data:
                    logger.error("wechat_auth_fail", response=data)
                    raise RuntimeError(f"WeChat Auth Fail: {data.get('errmsg')}")

                token = data["access_token"]
                expires_in = data.get("expires_in", 7200)

                # 3. Save Cache
                self.token_cache_path.parent.mkdir(exist_ok=True, parents=True)
                self.token_cache_path.write_text(
                    json.dumps({"token": token, "expires_at": time.time() + expires_in})
                )
                return token

        except aiohttp.ClientError as e:
            logger.error("wechat_network_error", error=str(e))
            raise

    async def publish_article(
        self, title: str, html_content: str, cover_image: bytes | None
    ) -> str:
        """
        Publishes an article to WeChat Drafts.

        Args:
            title: Article Title.
            html_content: HTML Body.
            cover_image: Optional cover image bytes.

        Returns:
            The Media ID of the created draft.

        """
        token = await self._get_token()

        # 1. Upload Cover (if exists)
        media_id = None
        if cover_image:
            url_upload = "https://api.weixin.qq.com/cgi-bin/material/add_material"

            # Prepare Multipart/Form-Data using standard aiohttp
            data = FormData()
            data.add_field("media", cover_image, filename="cover.png", content_type="image/png")

            try:
                async with self.aclient.post(
                    url_upload,
                    params={"access_token": token, "type": "image"},
                    data=data,
                ) as resp:
                    resp.raise_for_status()
                    res_data = await resp.json()

                    if "media_id" in res_data:
                        media_id = res_data["media_id"]
                    else:
                        logger.warning("cover_upload_fail", resp=res_data)
            except Exception as e:
                logger.error("cover_upload_error", error=str(e))
                # Strategy: Log error but attempt to publish article without cover
                # to ensure delivery continuity.

        # 2. Create Draft
        draft_payload = {
            "articles": [
                {
                    "title": title,
                    "author": "ReDate AI",
                    "digest": "Daily News Summary",
                    "content": html_content,
                    "content_source_url": "https://github.com/redate",
                    # Pass media_id only if available
                    **({"thumb_media_id": media_id} if media_id else {}),
                }
            ]
        }

        url_draft = "https://api.weixin.qq.com/cgi-bin/draft/add"

        async with self.aclient.post(
            url_draft,
            params={"access_token": token},
            json=draft_payload,
        ) as resp:
            resp.raise_for_status()
            draft_res = await resp.json()

            if "media_id" not in draft_res:
                logger.error("draft_create_fail", response=draft_res)
                raise RuntimeError(f"Draft creation failed: {draft_res}")

            return draft_res["media_id"]

    async def upload_permanent_material(self, image_data: bytes, filename: str) -> str | None:
        """
        Uploads a permanent image material to WeChat.

        Args:
            image_data: Raw bytes of the image.
            filename: Name of the file (e.g., image.jpg).

        Returns:
            Media ID if successful, None otherwise.

        """
        token = await self._get_token()
        url = "https://api.weixin.qq.com/cgi-bin/material/add_material"

        data = FormData()
        data.add_field("media", image_data, filename=filename, content_type="image/jpeg")

        try:
            async with self.aclient.post(
                url, params={"access_token": token, "type": "image"}, data=data
            ) as resp:
                resp.raise_for_status()
                res_data = await resp.json()
                if "media_id" in res_data:
                    logger.info("permanent_material_uploaded", media_id=res_data["media_id"])
                    return res_data["media_id"]
                else:
                    logger.warning("permanent_upload_fail", resp=res_data)
        except Exception as e:
            logger.error("permanent_upload_error", error=str(e))
        return None

    async def close(self) -> None:
        """Resource cleanup."""
        await self.aclient.close()

    async def __aenter__(self) -> WeChatAdapter:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close()
