"""
redate/main.py
CLI Entry point wiring dependencies.
Focus: Composition Root, Type-safe CLI, Dynamic Dependency Injection.
"""

import asyncio
from datetime import date
from typing import Annotated

import typer

from .adapter_image import HybridImageAdapter
from .adapter_storage import HybridStorageAdapter
from .adapter_viki import VikiNewsAdapter
from .adapter_wechat import WeChatAdapter
from .config import settings

# Lazy import to avoid loading unused SDKs
from .ports import LLMEngine
from .service_news import NewsService
from .utils_date import get_beijing_today
from .utils_telemetry import logger

__all__ = ["app"]

app = typer.Typer(help="ReDate News Automation CLI")


def _create_llm_engine() -> LLMEngine:
    """Factory method to instantiate the configured LLM provider."""
    provider = settings.LLM_PROVIDER

    if provider == "gemini":
        from .adapter_gemini import GeminiAdapter

        logger.info("llm_engine_init", provider="gemini")
        return GeminiAdapter()

    elif provider == "openai":
        from .adapter_openai import OpenAIAdapter

        logger.info("llm_engine_init", provider="openai")
        return OpenAIAdapter()

    else:
        raise ValueError(f"Unsupported LLM Provider: {provider}")


def bootstrap() -> NewsService:
    """Dependency Injection Wiring."""

    # Instantiate adapters
    llm_engine = _create_llm_engine()

    return NewsService(
        fetcher=VikiNewsAdapter(),
        storage=HybridStorageAdapter(),
        llm=llm_engine,
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


def cli():
    try:
        app()
    except Exception as e:
        logger.critical("system_crash", error=str(e))
        raise


if __name__ == "__main__":
    cli()
