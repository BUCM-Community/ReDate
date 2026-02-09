"""
redate/service_news.py

Orchestrates the data pipeline (Fetch -> Store -> Analyze -> Publish).

Focus:
- Idempotency via Hashing.
- Logical Flow Control.
- Error handling via Result Monad.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .domain_models import Err, Ok
from .utils_date import (
    get_beijing_today,
    get_previous_week_range,
    get_previous_year_range,
)
from .utils_telemetry import logger

if TYPE_CHECKING:
    from datetime import date

    from .ports import ImageFetcher, LLMEngine, NewsFetcher, Publisher, StorageAdapter

__all__ = ["NewsService"]


class NewsService:
    """
    Core Domain Service for News Processing.

    Coordinates the interaction between Fetchers, Storage, LLM, and Publishers.
    """

    def __init__(
        self,
        fetcher: NewsFetcher,
        storage: StorageAdapter,
        llm: LLMEngine,
        publisher: Publisher,
        image_fetcher: ImageFetcher | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.storage = storage
        self.llm = llm
        self.publisher = publisher
        self.image_fetcher = image_fetcher
        self.today = get_beijing_today()

    async def run_daily_workflow(self, target_date: date, category: str = "60s") -> None:
        """
        Executes the Daily News Ingestion Pipeline.

        Steps:
        1. Fetch News from the configured source.
        2. Check Idempotency (Skip if hash exists in DB).
        3. Archive Raw JSON to Object Storage.
        4. Analyze text (Embedding + Knowledge Extraction).
        5. Save Vectors and Metadata to LanceDB.

        Args:
            target_date: The date to fetch news for.
            category: The news category (e.g., '60s', 'ai-news').

        """
        logger.info("daily_job_start", date=str(target_date), category=category)

        # 1. Fetch
        result = await self.fetcher.fetch_daily(target_date, category)
        match result:
            case Err(e):
                logger.warning("fetch_skipped", reason=e.message)
                return
            case Ok(batch):
                logger.info("fetch_success", count=len(batch.items))

        # 2. Idempotency Check (Check-Then-Act)
        if await self.storage.check_exists(batch.raw_json_hash, batch.source):
            logger.info("job_skipped_idempotent", hash=batch.raw_json_hash)
            return

        # 3. Archive Raw (R2)
        raw_json_bytes = json.dumps(
            [item.model_dump() for item in batch.items], default=str
        ).encode("utf-8")
        archive_key = f"news/{category}/{target_date.isoformat()}.json"
        await self.storage.archive_raw(archive_key, raw_json_bytes)

        # 4. AI Analysis & Vectorization
        # Create a single text blob for the day for embedding
        full_text_blob = "\n".join([f"{i.title}: {i.content}" for i in batch.items])

        try:
            # A. Embedding (RAG)
            vector = await self.llm.generate_embedding(full_text_blob)

            # B. Knowledge Extraction (KG + Keyword)
            # This creates the Knowledge Graph data for the "Three Ways" report later
            knowledge_result = await self.llm.extract_knowledge(full_text_blob)

            # 5. Save (LanceDB + Metadata)
            await self.storage.save_embedding(batch, vector)
            await self.storage.save_knowledge(batch, knowledge_result)

            logger.info(
                "daily_analysis_complete",
                keywords=len(knowledge_result.keywords),
                triples=len(knowledge_result.triples),
            )

        except Exception as e:
            logger.error("daily_analysis_failed", error=str(e))
            # If AI fails, we re-throw because our data is incomplete for RAG
            raise

    async def run_weekly_workflow(self) -> None:
        """
        Executes the Weekly Summary Pipeline.

        Summarizes the previous week (Monday to Sunday) using the 'Three Ways'
        retrieval context.
        """
        start_date, end_date = get_previous_week_range(self.today)
        logger.info(
            "weekly_job_start",
            trigger_date=str(self.today),
            report_start=str(start_date),
            report_end=str(end_date),
        )
        await self._run_period_report(start_date, end_date, "Weekly")

    async def run_yearly_workflow(self) -> None:
        """
        Shared internal logic for generating and publishing periodic reports.

        Args:
            start: Start date of the period.
            end: End date of the period.
            period_type: Label for the report (e.g., "Weekly", "Yearly").

        """
        start_date, end_date = get_previous_year_range(self.today)
        await self._run_period_report(start_date, end_date, "Yearly")

    async def _run_period_report(self, start: date, end: date, period_type: str) -> None:
        """Shared logic for periodic reporting using Hybrid Context."""
        logger.info(
            f"{period_type.lower()}_job_start",
            trigger_date=str(self.today),
            start=str(start),
            end=str(end),
        )

        # 1. Retrieve Comprehensive Context (Vector + Keywords + KG)
        # This fulfills the "Three Ways" requirement
        retrieval_context = await self.storage.get_comprehensive_context(start, end)

        # Check if we have *any* data
        if not retrieval_context.vector_results and not retrieval_context.knowledge_graph_summary:
            logger.warning(f"no_data_for_{period_type.lower()}_report")
            return

        # 2. LLM Synthesis
        # Pass the context to the LLM to generate the report
        try:
            report = await self.llm.generate_period_report(
                retrieval_context, start, end, period_type
            )
        except Exception as e:
            logger.error("report_generation_failed", error=str(e))
            raise

        # 3. Publish
        try:
            draft_id = await self.publisher.publish_article(
                title=f"ReDate {period_type} Review: {start} ~ {end}",
                html_content=(
                    f"<h1>{period_type} Review</h1>"
                    f"<p>{report.summary_text}</p>"
                    "<h3>Key Highlights</h3><ul>"
                    + "".join([f"<li>{k}</li>" for k in report.key_events])
                    + "</ul>"
                ),
                cover_image=None,
            )
            logger.info(f"{period_type.lower()}_job_complete", draft_id=draft_id)
        except Exception as e:
            logger.error("publish_failed", error=str(e))

    async def upload_weekly_images(self, count: int = 5) -> None:
        """
        Weekly Job: Fetch images from Unsplash and upload to WeChat.

        Naming: YYMMDD_{name}
        """
        if not self.image_fetcher:
            logger.warning("image_fetcher_not_configured")
            return

        logger.info("weekly_image_upload_start", count=count)
        date_prefix = self.today.strftime("%y%m%d")

        for _ in range(count):
            img_info = await self.image_fetcher.fetch_random_tech_image()
            if not img_info:
                continue

            img_data = await self.image_fetcher.download_image(img_info["url"])
            if not img_data:
                continue

            filename = f"{date_prefix}_{img_info['name']}.jpg"
            await self.publisher.upload_permanent_material(img_data, filename)
