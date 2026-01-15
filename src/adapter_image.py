"""
src/adapter_image.py
Adapter for fetching images from free stock photo sites (Unsplash, Pexels, Pixabay).
Implements a multi-source fallback strategy with keyword targeting.
"""

from __future__ import annotations

import asyncio
import random
from typing import ClassVar, cast

import aiohttp
from aiohttp import ClientTimeout
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import settings
from .ports import ImageFetcher
from .utils_telemetry import logger

__all__ = ["HybridImageAdapter"]


class HybridImageAdapter(ImageFetcher):
    """
    Production-grade adapter that rotates between Unsplash, Pexels, and Pixabay.
    Includes keyword targeting and fallback logic.
    """

    # Optimized search terms for Tech/AI news context
    KEYWORDS: ClassVar[list[str]] = [
        "technology",
        "artificial intelligence",
        "futuristic city",
        "robotics",
        "data science",
        "cybersecurity",
        "microchip",
        "innovation",
        "computer network",
    ]

    def __init__(self) -> None:
        self.unsplash_key = (
            settings.UNSPLASH_ACCESS_KEY.get_secret_value()
            if settings.UNSPLASH_ACCESS_KEY
            else None
        )
        self.pexels_key = (
            settings.PEXELS_API_KEY.get_secret_value()
            if settings.PEXELS_API_KEY
            else None
        )
        self.pixabay_key = (
            settings.PIXABAY_API_KEY.get_secret_value()
            if settings.PIXABAY_API_KEY
            else None
        )

        self.client = aiohttp.ClientSession(timeout=ClientTimeout(total=15.0))

    def _get_query(self) -> str:
        """Rotates a random keyword from the list for variety."""
        return random.choice(self.KEYWORDS)

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    async def _fetch_unsplash(self) -> dict[str, str] | None:
        """Unsplash API: /photos/random"""
        if not self.unsplash_key:
            return None

        query = self._get_query()
        url = "https://api.unsplash.com/photos/random"
        params = {
            "query": query,
            "orientation": "landscape",
            "client_id": self.unsplash_key,
        }

        try:
            async with self.client.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "url": cast(str, data["urls"]["regular"]),
                        "name": f"unsplash_{data['id']}",
                        "download_url": cast(str, data["links"]["download_location"]),
                        "source": "Unsplash",
                        "credit": f"Photo by {data['user']['name']} on Unsplash",
                    }
                elif resp.status == 403 or resp.status == 429:
                    logger.warning(
                        "unsplash_rate_limit_or_auth_fail", status=resp.status
                    )
                else:
                    logger.debug("unsplash_fetch_fail", status=resp.status)
        except Exception as e:
            logger.error("unsplash_error", error=str(e))
        return None

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    async def _fetch_pexels(self) -> dict[str, str] | None:
        """Pexels API: /v1/search"""
        if not self.pexels_key:
            return None

        query = self._get_query()
        url = "https://api.pexels.com/v1/search"
        params = {
            "query": query,
            "orientation": "landscape",
            "per_page": 1,
            "page": random.randint(1, 20),
        }
        headers = {"Authorization": self.pexels_key}

        try:
            async with self.client.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    photos = data.get("photos", [])
                    if photos:
                        photo = photos[0]
                        return {
                            "url": cast(str, photo["src"]["large"]),
                            "name": f"pexels_{photo['id']}",
                            "download_url": cast(str, photo["src"]["original"]),
                            "source": "Pexels",
                            "credit": f"Photo by {photo['photographer']} on Pexels",
                        }
        except Exception as e:
            logger.error("pexels_error", error=str(e))
        return None

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    async def _fetch_pixabay(self) -> dict[str, str] | None:
        """Pixabay API: /api/"""
        if not self.pixabay_key:
            return None

        query = self._get_query()
        url = "https://pixabay.com/api/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "image_type": "photo",
            "orientation": "horizontal",
            "per_page": 5,  # Fetch a small batch to pick random
            "safesearch": "true",
        }

        try:
            async with self.client.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    hits = data.get("hits", [])
                    if hits:
                        hit = random.choice(hits)
                        return {
                            "url": cast(str, hit["webformatURL"]),
                            "name": f"pixabay_{hit['id']}",
                            "download_url": cast(str, hit["largeImageURL"]),
                            "source": "Pixabay",
                            "credit": f"Image by {hit['user']} from Pixabay",
                        }
        except Exception as e:
            logger.error("pixabay_error", error=str(e))
        return None

    async def fetch_random_tech_image(self) -> dict[str, str] | None:
        """
        Fetches a random image using a randomized fallback strategy.
        Returns: Dict with url, name, download_url, source.
        """
        # Shuffle order to distribute load and variety
        strategies = [self._fetch_unsplash, self._fetch_pexels, self._fetch_pixabay]
        random.shuffle(strategies)

        for fetcher in strategies:
            result = await fetcher()
            if result:
                # Trigger download event for Unsplash compliance (Fire & Forget)
                if result["source"] == "Unsplash" and "download_url" in result:
                    asyncio.create_task(
                        self._trigger_unsplash_download(result["download_url"])
                    )

                logger.info(
                    "image_fetched", source=result["source"], name=result["name"]
                )
                return result

        logger.error("all_image_sources_exhausted")
        return None

    async def _trigger_unsplash_download(self, url: str) -> None:
        """Hit the Unsplash download endpoint to increment stats (API Requirement)."""
        if not self.unsplash_key:
            return
        try:
            async with self.client.get(
                url, params={"client_id": self.unsplash_key}
            ) as _:
                pass
        except Exception:
            pass  # Fail silently for stats

    async def download_image(self, url: str) -> bytes | None:
        """Stream download the image bytes."""
        try:
            async with self.client.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
                logger.warning("image_download_status_fail", status=resp.status)
        except Exception as e:
            logger.error("image_download_error", url=url, error=str(e))
        return None

    async def close(self) -> None:
        await self.client.close()

    async def __aenter__(self) -> "HybridImageAdapter":
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        await self.close()
