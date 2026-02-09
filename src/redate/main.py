"""
redate/main.py

CLI Entry point wiring dependencies.

Focus:
- Composition Root.
- Type-safe CLI via Typer.
- Dynamic Dependency Injection.
"""

import asyncio
from datetime import date
from typing import Annotated

import typer

# Lazy Import: LLM, migration
from .adapter_image import HybridImageAdapter
from .adapter_storage import HybridStorageAdapter
from .adapter_viki import VikiNewsAdapter
from .adapter_wechat import WeChatAdapter
from .config import settings
from .ports import LLMEngine
from .service_news import NewsService
from .utils_date import get_beijing_today
from .utils_telemetry import logger

__all__ = ["app"]

app = typer.Typer(help="ReDate News Automation CLI")

# Global State for Overrides
state = {"mode": "", "llm": ""}


def _create_llm_engine(provider_override: str | None = None) -> LLMEngine:
    """Factory method to instantiate the configured LLM provider."""
    provider = provider_override or settings.LLM_PROVIDER
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
    """Dependency Injection Wiring with dynamic overrides."""
    # Resolve overrides
    deploy_mode = state.get("mode")  # remote or local
    llm_provider = state.get("llm")

    # Instantiate Adapters
    llm_engine = _create_llm_engine(llm_provider)

    # Pass explicit mode if provided via CLI, else config default
    storage_adapter = HybridStorageAdapter(mode=deploy_mode if deploy_mode else None)

    return NewsService(
        fetcher=VikiNewsAdapter(),
        storage=storage_adapter,
        llm=llm_engine,
        publisher=WeChatAdapter(),
        image_fetcher=HybridImageAdapter(),
    )


@app.callback()
def main(
    mode: Annotated[str, typer.Option(help="Deploy Mode: 'remote' (R2) or 'local' (Seaweed)")] = "",
    llm: Annotated[str, typer.Option(help="LLM Provider: 'gemini' or 'openai'")] = "",
):
    if mode:
        state["mode"] = mode
    if llm:
        state["llm"] = llm


@app.command()
def daily(
    target_date: Annotated[str | None, typer.Option(help="YYYY-MM-DD")] = None,
    category: str = "60s",
) -> None:
    """
    Run the daily ingestion workflow (Fetch -> Store -> Analyze).

    If target_date is not provided, defaults to today (Beijing Time).
    """
    service = bootstrap()
    d = date.fromisoformat(target_date) if target_date else get_beijing_today()

    try:
        asyncio.run(service.run_daily_workflow(d, category))
    except Exception as e:
        logger.critical("daily_crash", error=str(e))
        raise typer.Exit(code=1) from e


@app.command()
def weekly() -> None:
    """Run weekly summary."""
    service = bootstrap()
    try:
        asyncio.run(service.run_weekly_workflow())
        asyncio.run(service.upload_weekly_images(count=3))
    except Exception as e:
        logger.critical("weekly_crash", error=str(e))
        raise typer.Exit(code=1) from e


@app.command()
def yearly() -> None:
    """Run yearly summary."""
    service = bootstrap()
    try:
        asyncio.run(service.run_yearly_workflow())
    except Exception as e:
        logger.critical("yearly_crash", error=str(e))
        raise typer.Exit(code=1) from e


@app.command()
def migrate(
    direction: Annotated[
        str, typer.Option(help="'in' (Cloud->Local) or 'out' (Local->Cloud)")
    ] = "in",
) -> None:
    """
    Migrate data between Cloud (R2) and Local (SeaweedFS).

    Requires strict environment variable configuration for both endpoints.
    """
    from .service_migration import MigrationService

    logger.info("starting_migration_utility", direction=direction)

    # Map CLI arg to internal literal
    mode_map: dict[str, str] = {"in": "cloud_to_local", "out": "local_to_cloud"}

    if direction not in mode_map:
        logger.error("invalid_direction", allowed=["in", "out"])
        raise typer.Exit(code=1)

    try:
        # We don't use bootstrap() here because migration needs BOTH adapters
        service = MigrationService()
        result = asyncio.run(service.run_migration(mode_map[direction]))  # type: ignore

        if not result.is_ok():
            raise RuntimeError(f"Migration Failed: {result.error}")  # type: ignore
        logger.info("migration_success")

    except Exception as e:
        logger.critical("migration_crash", error=str(e))
        raise typer.Exit(code=1) from e


def cli() -> None:
    try:
        app()
    except Exception as e:
        logger.critical("system_crash", error=str(e))
        raise


if __name__ == "__main__":
    cli()
