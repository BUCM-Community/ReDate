"""
redate/adapter_gemini.py

Google GenAI SDK implementation.

Focus:
- gemini-2.5-flash-preview-09-2025
- Grounding (Google Search)
- Rate Limiting (RPM 5 for Chat, RPM 100 for Embed)
- Batch Embedding
- Structured Outputs (Pydantic)
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

from google import genai
from google.genai import types
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from .config import settings
from .domain_models import KnowledgeExtractionResult, RetrievalContext, WeeklyReport
from .ports import LLMEngine
from .utils_telemetry import logger

if TYPE_CHECKING:
    from datetime import date

    from google.genai.client import AsyncClient

__all__ = ["GeminiAdapter"]


class GeminiAdapter(LLMEngine):
    """
    Adapter for Google's Gemini models via the GenAI SDK.

    Handles strict rate limiting (RPM) and supports structured outputs via Pydantic.
    """

    def __init__(self) -> None:
        """
        Initialize Gemini Adapter with API Keys and Rate Limiters.

        Raises:
            ValueError: If GEMINI_API_KEY is missing.

        """
        # Ensure API keys are present before init
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required for GeminiAdapter")

        self.clients = [genai.Client(api_key=settings.GEMINI_API_KEY.get_secret_value()).aio]
        if settings.GEMINI_API_KEY_ALT:
            self.clients.append(
                genai.Client(api_key=settings.GEMINI_API_KEY_ALT.get_secret_value()).aio
            )
        self._current_index = 0

        # Rate Limiting Semaphores
        # RPM 5 = 1 request every 12 seconds. We use a semaphore and a forced sleep to be safe.
        self._chat_lock = asyncio.Lock()
        self._chat_last_call = 0.0

        # Embedding RPM 100 = 1 request every 0.6 seconds.
        self._embed_lock = asyncio.Lock()

    def _get_client(self) -> AsyncClient:
        client = self.clients[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.clients)
        return client

    async def _enforce_chat_rate_limit(self):
        """
        Strictly enforces 5 RPM (12s interval) for Gemini 2.5 Flash Preview.

        Uses a global lock to prevent race conditions in concurrent executions.
        """
        async with self._chat_lock:
            now = asyncio.get_running_loop().time()
            elapsed = now - self._chat_last_call
            if elapsed < 12.0:
                wait_time = 12.0 - elapsed
                logger.debug("gemini_rate_limit_wait", seconds=wait_time)
                await asyncio.sleep(wait_time)
            self._chat_last_call = asyncio.get_running_loop().time()

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generates text embeddings using `gemini-embedding-001`.

        Enforces a simplified rate limit (approx 0.6s delay) to comply with RPM 100.

        Logic:
        ```mermaid
        graph TD
            A[Start] --> B{Rate Limit?}
            B -->|Yes| C[Sleep 0.6s]
            B -->|No| D[Call API]
            D --> E{Success?}
            E -->|Yes| F[Return Vector]
            E -->|No| G[Retry/Error]
        ```

        Args:
            text: The input text string to embed.

        Returns:
            A list of floats representing the embedding vector.

        """
        try:
            # Enforce simplified rate limit (approx 0.6s delay)
            await asyncio.sleep(0.6)

            safe_text = text[:9000]  # Model limit
            result = await self._get_client().models.embed_content(
                model=settings.MODEL_GEMINI_EMBEDDING, contents=safe_text
            )
            if result.embeddings and result.embeddings[0].values:
                return cast(list[float], result.embeddings[0].values)
            return []
        except Exception as e:
            if "429" in str(e) or "ResourceExhausted" in str(e):
                logger.warning("gemini_quota_limit_hit", error=str(e))
            else:
                logger.error("gemini_embed_fail", error=str(e))
            raise

    @retry(
        wait=wait_fixed(15),  # If we hit a limit, wait > 12s
        stop=stop_after_attempt(2),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def summarize_daily(self, text: str) -> str:
        """
        Summarizes raw news text into a Daily Briefing format using Gemini Chat.

        Enables Google Search tools for fact verification.

        Args:
            text: The raw news content concatenated string.

        Returns:
            HTML formatted string containing the summary.

        """
        await self._enforce_chat_rate_limit()

        # Configure Grounding (Google Search)
        tools: list[types.Tool] | None = None
        if settings.GEMINI_SEARCH_ENABLED:
            tools = [types.Tool(google_search=types.GoogleSearch())]

        prompt = (
            "You are a professional news editor. Summarize the following news items into a "
            "concise Daily Briefing. Use HTML format (<ul>, <li>, <b>). "
            "Discard any promotional or irrelevant content. "
            "Focus on tech, AI, and global impact.\n"
            "Use the Google Search tool to verify facts if necessary.\n\n"
            f"Content:\n{text[:20000]}"
        )
        try:
            response = await self._get_client().models.generate_content(
                model=settings.MODEL_GEMINI_CHAT,
                contents=prompt,
                config=types.GenerateContentConfig(tools=tools),
            )
            if response.text:
                return response.text
            return "No summary generated by AI."
        except Exception as e:
            logger.error("gemini_sum_fail", error=str(e))
            # Don't raise on daily summary fail, return error text to allow flow to continue
            return "<p>Error generating summary. Please check logs.</p>"

    @retry(
        wait=wait_fixed(15),
        stop=stop_after_attempt(2),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def extract_knowledge(self, text: str) -> KnowledgeExtractionResult:
        """
        Extracts structured knowledge (Keywords and Knowledge Graph) from text.

        Uses Gemini's structured output capability to return a Pydantic model directly.

        Args:
            text: The input news text.

        Returns:
            KnowledgeExtractionResult: Object containing keywords and KG triples.

        """
        await self._enforce_chat_rate_limit()

        prompt = (
            "Analyze the following news text. \n"
            "1. Extract the top 5-10 most important keywords (topics, entities).\n"
            "2. Extract Knowledge Graph triples (Subject, Predicate, Object) representing specific events or relationships.\n"
            f"Text:\n{text[:20000]}"
        )

        try:
            # Structured Output via Pydantic Schema
            response = await self._get_client().models.generate_content(
                model=settings.MODEL_GEMINI_CHAT,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=KnowledgeExtractionResult,
                ),
            )

            if response.parsed:
                return cast(KnowledgeExtractionResult, response.parsed)

            if response.text:
                return KnowledgeExtractionResult.model_validate_json(response.text)

            return KnowledgeExtractionResult(keywords=[], triples=[])

        except Exception as e:
            logger.error("gemini_knowledge_extraction_fail", error=str(e))
            return KnowledgeExtractionResult(keywords=[], triples=[])

    @retry(
        wait=wait_fixed(20),  # Conservative wait for large context
        stop=stop_after_attempt(2),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def generate_period_report(
        self,
        context: RetrievalContext,
        start_date: date,
        end_date: date,
        period_type: str = "Weekly",
    ) -> WeeklyReport:
        """
        Generates a comprehensive periodic report (Weekly/Yearly).

        Utilizes the 'Three Ways' methodology (KG, Keywords, Vector Context)
        and Google Search grounding to synthesize the report.

        Args:
            context: Aggregated retrieval context (RAG).
            start_date: Report start date.
            end_date: Report end date.
            period_type: "Weekly" or "Yearly".

        Returns:
            WeeklyReport: Structured report object suitable for JSON serialization.

        """
        await self._enforce_chat_rate_limit()

        context_str = context.to_prompt_string()
        max_chars = 100000 if period_type == "Weekly" else 500000
        safe_context = context_str[:max_chars]

        # Enable Grounding for reports to ensure accuracy of dates/facts
        tools: list[types.Tool] | None = None
        if settings.GEMINI_SEARCH_ENABLED:
            tools = [types.Tool(google_search=types.GoogleSearch())]

        prompt = (
            f"Role: Senior News Editor. Task: Generate a {period_type} Report from {start_date} to {end_date}.\n\n"
            "Methodology (The 'Three Ways'):\n"
            "1. Use the 'Knowledge Graph' section to construct accurate timelines and relationships.\n"
            "2. Use the 'Keyword Highlights' to identify major themes.\n"
            "3. Use the 'Detailed Content' (Vectors) for narrative depth.\n"
            "4. Use the Google Search tool to fill in missing context or verify dates.\n\n"
            f"Source Data:\n{safe_context}\n\n"
            "Requirements:\n"
            "1. Deduplicate events.\n"
            "2. Identify the most significant trends.\n"
            "3. Output valid JSON adhering to the schema.\n"
        )

        try:
            response = await self._get_client().models.generate_content(
                model=settings.MODEL_GEMINI_CHAT,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=tools,
                    response_mime_type="application/json",
                    response_schema=WeeklyReport,
                ),
            )

            if response.parsed:
                report = cast(WeeklyReport, response.parsed)
                return report.model_copy(update={"start_date": start_date, "end_date": end_date})

            resp_text = response.text or "{}"
            # Fallback manual parsing
            try:
                data = json.loads(resp_text)
                return WeeklyReport(
                    start_date=start_date,
                    end_date=end_date,
                    summary_text=data.get("summary_text", f"No {period_type} summary generated."),
                    key_events=data.get("key_events", []),
                    best_cover_image=None,
                )
            except json.JSONDecodeError as err:
                raise ValueError("Failed to parse JSON from LLM response") from err

        except Exception as e:
            logger.error("gemini_report_fail", period=period_type, error=str(e))
            raise
