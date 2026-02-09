"""
redate/adapter_openai.py

OpenAI Response API implementation with Hybrid Routing.

Focus:
- Multi-Provider (OpenRouter + SiliconFlow)
- Task-Specific Models (Gemma, DeepSeek, Mimo, BGE-M3)
- Structured Outputs
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from .config import settings
from .domain_models import KnowledgeExtractionResult, RetrievalContext, WeeklyReport
from .ports import LLMEngine
from .utils_telemetry import logger

if TYPE_CHECKING:
    from datetime import date

__all__ = ["OpenAIAdapter"]


class OpenAIAdapter(LLMEngine):
    """
    LLM Engine implementation using OpenAI-compatible APIs.

    Supports hybrid routing:
    - OpenRouter: For Chat, Summarization, and Reporting tasks.
    - SiliconFlow: Optimized for Embeddings (BAAI/bge-m3).
    """

    def __init__(self) -> None:
        """Initializes multiple clients for the Hybrid Scheme."""
        # 1. OpenRouter Client (Chat, Summaries, Reports)
        if settings.OPENROUTER_API_KEY:
            self.client_router = AsyncOpenAI(
                api_key=settings.OPENROUTER_API_KEY.get_secret_value(),
                base_url=str(settings.OPENROUTER_BASE_URL),
            )
            logger.info("openai_adapter_init", mode="OpenRouter")
        else:
            # Fallback to standard OpenAI if Router key missing (dev safety)
            self.client_router = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY.get_secret_value()
                if settings.OPENAI_API_KEY
                else "dummy",
                base_url=str(settings.OPENAI_BASE_URL),
            )
            logger.warning("openai_adapter_fallback", mode="Standard")

        # 2. SiliconFlow Client (Primary Embeddings)
        if settings.SILICONFLOW_API_KEY:
            self.client_silicon = AsyncOpenAI(
                api_key=settings.SILICONFLOW_API_KEY.get_secret_value(),
                base_url=str(settings.SILICONFLOW_BASE_URL),
            )
            logger.info("openai_adapter_init", mode="SiliconFlow")
        else:
            # Fallback to OpenRouter or Standard if SiliconFlow missing
            self.client_silicon = self.client_router

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=30),
        stop=stop_after_attempt(2),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def generate_embedding(self, text: str) -> list[float]:
        """
        Generates embeddings using the configured SiliconFlow model (default: BAAI/bge-m3).

        Args:
            text: Input text string.

        Returns:
            Embedding vector as a list of floats.

        """
        try:
            # Using SiliconFlow BGE-M3 as per "Default Config" requirements
            client = self.client_silicon
            model = settings.MODEL_SILICONFLOW_EMBEDDING

            # Note: 2026/2025 BGE-M3 via SiliconFlow usually follows standard OpenAI embedding format
            response = await client.embeddings.create(model=model, input=text[:8191])
            return response.data[0].embedding
        except Exception as e:
            logger.error("siliconflow_embed_fail", error=str(e))
            raise

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(2),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def summarize_daily(self, text: str) -> str:
        """Uses OpenRouter: google/gemma-3-27b-it:free"""
        instructions = (
            "You are a professional news editor. Summarize the provided news items into a "
            "concise Daily Briefing. Use HTML format (<ul>, <li>, <b>). "
            "Discard any promotional or irrelevant content. "
            "Focus on tech, AI, and global impact."
        )
        try:
            # Using Responses API (Hypothetical 2026 standard for structured/instructional interactions)
            # If strictly using chat.completions, replace .responses.create with .chat.completions.create
            response = await self.client_router.chat.completions.create(
                model=settings.MODEL_OPENROUTER_DAILY,
                messages=[
                    {"role": "system", "content": instructions},
                    {
                        "role": "user",
                        "content": text[:30000],
                    },  # Gemma has large context
                ],
            )

            content = response.choices[0].message.content
            return content if content else "No summary generated."

        except Exception as e:
            logger.error("openrouter_daily_fail", error=str(e))
            return "<p>Error generating summary. Please check logs.</p>"

    @retry(
        wait=wait_exponential(multiplier=2, min=5, max=60),
        stop=stop_after_attempt(3),
        before_sleep=before_sleep_log(logger, 2),
    )
    async def extract_knowledge(self, text: str) -> KnowledgeExtractionResult:
        """
        Extracts structured knowledge using OpenRouter models (Gemma/DeepSeek).

        Uses `client.beta.chat.completions.parse` for strict Pydantic schema validation.
        """
        instructions = (
            "Analyze the news text. \n"
            "1. Extract top 5-10 keywords.\n"
            "2. Extract Knowledge Graph triples (Subject, Predicate, Object).\n"
        )

        try:
            response = await self.client_router.beta.chat.completions.parse(
                model=settings.MODEL_OPENROUTER_DAILY,  # Gemma 3 supports structured output
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": text[:20000]},
                ],
                response_format=KnowledgeExtractionResult,
            )

            if response.choices[0].message.parsed:
                return response.choices[0].message.parsed

            return KnowledgeExtractionResult(keywords=[], triples=[])

        except Exception as e:
            logger.error("openrouter_knowledge_fail", error=str(e))
            return KnowledgeExtractionResult(keywords=[], triples=[])

    @retry(
        wait=wait_exponential(multiplier=5, min=20, max=120),
        stop=stop_after_attempt(3),
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
        Generates periodic reports using High-Context models (DeepSeek/Mimo).

        Selects the model based on the period type (Weekly vs Yearly) to balance
        cost and context window requirements.
        """
        context_str = context.to_prompt_string()
        max_chars = 100000 if period_type == "Weekly" else 400000
        safe_context = context_str[:max_chars]

        # Select Model based on period
        if period_type == "Weekly":
            model = settings.MODEL_OPENROUTER_WEEKLY
        else:
            model = settings.MODEL_OPENROUTER_YEARLY

        instructions = (
            f"Role: Senior News Editor. Task: Generate a {period_type} Report from {start_date} to {end_date}.\n"
            "Methodology:\n"
            "1. Use 'Knowledge Graph' for timelines.\n"
            "2. Use 'Keyword Highlights' for themes.\n"
            "3. Use 'Detailed Content' for depth.\n"
            "Requirements:\n"
            "1. Deduplicate events.\n"
            "2. Identify trends.\n"
            "3. Output strictly valid JSON matching the schema."
        )

        try:
            response = await self.client_router.beta.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": safe_context},
                ],
                response_format=WeeklyReport,
            )

            if response.choices[0].message.parsed:
                report = response.choices[0].message.parsed
                return report.model_copy(update={"start_date": start_date, "end_date": end_date})

            # Fallback if parsed is None
            raise ValueError("Structured output parsing failed")

        except Exception as e:
            logger.error("openrouter_report_fail", period=period_type, model=model, error=str(e))
            # Critical logic failure -> Raise to alert
            raise
