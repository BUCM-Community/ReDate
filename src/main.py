"""
src/main.py
CLI Entry point wiring dependencies.
Focus: Composition Root, Type-safe CLI.
"""

import asyncio
from datetime import date
from typing import Annotated

import typer

from .adapter_gemini import GeminiAdapter
from .adapter_image import HybridImageAdapter
from .adapter_storage import HybridStorageAdapter
from .adapter_viki import VikiNewsAdapter
from .adapter_wechat import WeChatAdapter
from .service_news import NewsService
from .utils_date import get_beijing_today
from .utils_telemetry import logger

__all__ = ["app"]

app = typer.Typer(help="ReDate News Automation CLI")


def bootstrap() -> NewsService:
    """Dependency Injection Wiring."""
    return NewsService(
        fetcher=VikiNewsAdapter(),
        storage=HybridStorageAdapter(),
        llm=GeminiAdapter(),
        publisher=WeChatAdapter(),
        image_fetcher=HybridImageAdapter(),
    )


@app.command()
def daily(
    target_date: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
    category: str = "60s",
) -> None:
    """Run daily ingestion (Fetch -> Store). No Push."""
    service = bootstrap()
    d = date.fromisoformat(target_date) if target_date else get_beijing_today()

    try:
        asyncio.run(service.run_daily_workflow(d, category))
    except Exception as e:
        logger.critical("daily_crash", error=str(e))
        raise typer.Exit(code=1) from e


@app.command()
def weekly() -> None:
    """Run the weekly summary pipeline (Trigger on Monday)."""
    service = bootstrap()
    try:
        asyncio.run(service.run_weekly_workflow())
        # Also upload some fresh images for the library
        asyncio.run(service.upload_weekly_images(count=3))
    except Exception as e:
        logger.critical("weekly_crash", error=str(e))
        raise typer.Exit(code=1) from e


@app.command()
def yearly() -> None:
    """Run yearly summary and push."""
    service = bootstrap()
    try:
        asyncio.run(service.run_yearly_workflow())
    except Exception as e:
        logger.critical("yearly_crash", error=str(e))
        raise typer.Exit(code=1) from e


if __name__ == "__main__":
    try:
        app()
    except Exception as e:
        logger.critical("system_crash", error=str(e))
        raise
