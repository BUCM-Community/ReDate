"""
redate/adapter_viki.py
Adapter for Viki News API.
Focus: Input cleaning, Category handling, Mapping to Domain Models, exponential backoff.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from pydantic import HttpUrl
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .domain_models import DailyNewsBatch, Err, NewsItem, NewsNotFoundError, Ok, Result
from .ports import NewsFetcher
from .utils_date import parse_date_string
from .utils_telemetry import logger

__all__ = ["VikiNewsAdapter"]

VIKI_CATEGORIES = ["60s", "ai-news", "epic", "kfc"]
VIKI_ENDPOINTS = {
    "60s": "/60s",
    "ai-news": "/ai-news",
    "epic": "/epic",
    "kfc": "/kfc",
}


class VikiNewsAdapter(NewsFetcher):
    """
    Adapter for fetching news data from Viki API (internal source).
    Supports multiple endpoints and category-specific cleaning.
    """

    def __init__(self, base_url: str | HttpUrl = settings.VIKI_API_BASE):
        # 确保URL没有末尾分隔符
        self.base_url = str(base_url).rstrip("/")
        # Shorter timeout for crawl operations
        self.client = aiohttp.ClientSession(timeout=ClientTimeout(total=30.0))

    # Only retry on standard network errors, not on 404 (which is logic flow).
    @retry(
        retry=retry_if_exception_type(
            (aiohttp.ClientError, aiohttp.ServerDisconnectedError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(5),
        # _levelToName = {
        #     CRITICAL: 'CRITICAL',
        #     ERROR: 'ERROR',
        #     WARNING: 'WARNING',
        #     INFO: 'INFO',
        #     DEBUG: 'DEBUG',
        #     NOTSET: 'NOTSET',
        # }
        before_sleep=before_sleep_log(logger, 2),  # Log before retrying
    )
    async def fetch_daily(
        self, target_date: date, category: str = "60s"
    ) -> Result[DailyNewsBatch, NewsNotFoundError]:
        """
        Fetches news from the specified Viki endpoint(s) and converts them to NewsItem objects.
        If category is None, fetches all.
        """
        if category not in VIKI_ENDPOINTS:
            logger.error("invalid_category", category=category)
            return Err(NewsNotFoundError(message=f"Category {category} not supported"))

        endpoint = VIKI_ENDPOINTS[category]
        url = f"{self.base_url}{endpoint}"
        params = {}

        # Requirement: "/60s" and "/ai-news" use ?date=YYYY-MM-DD
        # "/epic" and "/kfc" do NOT use date param.
        if category in ["60s", "ai-news"]:
            params["date"] = target_date.isoformat()

        try:
            async with self.client.get(url, params=params) as response:
                # 404 is a valid business result (No News), do not retry
                if response.status == 404:
                    return Err(NewsNotFoundError(message=f"No news for {target_date}"))
                # 5xx Errors should trigger the @retry decorator
                response.raise_for_status()
                raw_data = await response.json()

        except aiohttp.ClientResponseError as e:
            # Re-raise to let tenacity handle it ONLY if it's not 404
            if e.status == 404:
                return Err(
                    NewsNotFoundError(message=f"No news (404) for {target_date}")
                )
            raise
        except Exception as e:
            logger.error("viki_fetch_fail", error=str(e), url=url)
            return Err(NewsNotFoundError(message=str(e)))

        # Standardize structure: raw_data might be {"data": [...]} or just [...]
        data_list = (
            raw_data.get("data", raw_data) if isinstance(raw_data, dict) else raw_data
        )

        if not isinstance(data_list, list) or not data_list:
            return Err(NewsNotFoundError(message="Empty or invalid response list"))

        # Cleaning & Mapping
        items: list[NewsItem] = []
        cover_url = None

        for entry in data_list:
            # "60s" specific: Clean HTML, discard unused fields
            content_text = entry.get("summary") or entry.get("content") or ""

            if category == "60s":
                content_text = self._strip_html(content_text)
            # ignore 'image', 'audio' keys as per requirements
            # But we might capture cover from the response metadata if available?
            # Extract common fields
            title = entry.get("title")
            url_link = entry.get("link") or entry.get("url")
            pub_date = parse_date_string(entry.get("published_at") or entry.get("date"))

            # Safety fallback for date
            if not pub_date:
                pub_date = target_date

            if content_text:
                items.append(
                    NewsItem(
                        title=title,
                        content=content_text.strip(),
                        url=url_link,
                        published_at=pub_date,
                    )
                )

        if not items:
            return Err(NewsNotFoundError(message="No valid items after filtering"))

        # Calculate idempotency hash of the RAW cleaned data (Logic Layer decision)
        # Using a stable serialization of items
        raw_dump = json.dumps(
            [i.model_dump() for i in items], default=str, sort_keys=True
        )
        raw_hash = hashlib.sha256(raw_dump.encode("utf-8")).hexdigest()

        return Ok(
            DailyNewsBatch(
                date_str=target_date,
                source=f"viki-{category}",
                items=items,
                cover_image_url=cover_url,  # Viki 60s often doesn't give a cover URL in the list
                raw_json_hash=raw_hash,
            )
        )

    async def download_image(self, url: str) -> bytes | None:
        if not url:
            return None
        try:
            async with self.client.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.warning("image_download_fail", url=url, error=str(e))
        return None

    def _strip_html(self, text: str) -> str:
        if not text:
            return ""
        return BeautifulSoup(text, "html.parser").get_text().strip()

    async def close(self):
        await self.client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
