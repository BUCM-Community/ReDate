"""
redate/domain_models.py

Core business data structures and monadic error handling types.

Focus:
- No-GIL safety (immutability).
- Result Pattern.
- Knowledge Graph Structures.
"""

from __future__ import annotations

from datetime import date
import hashlib

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

__all__ = [
    "AppError",
    "DailyNewsBatch",
    "Err",
    "KnowledgeExtractionResult",
    "KnowledgeTriple",
    "NewsItem",
    "NewsNotFoundError",
    "Ok",
    "Result",
    "RetrievalContext",
    "WeeklyReport",
]


# --- Result Pattern (Monad) for Expected Failures ---
class Ok[T]:
    """Result Monad: Success Case."""

    __match_args__ = ("value",)

    def __init__(self, value: T):
        self.value = value

    def is_ok(self) -> bool:
        """Returns True for Ok."""
        return True


class Err[E]:
    """Result Monad: Failure Case."""

    __match_args__ = ("error",)

    def __init__(self, error: E):
        self.error = error

    def is_ok(self) -> bool:
        """Returns False for Err."""
        return False


type Result[T, E] = Ok[T] | Err[E]


# --- Domain Errors ---
class AppError(BaseModel):
    """Base class for application errors."""

    code: str
    message: str


class NewsNotFoundError(AppError):
    """Error raised when news cannot be found."""

    code: str = "NEWS_NOT_FOUND"


class KnowledgeTriple(BaseModel):
    """Represents a Subject-Predicate-Object relationship in the Knowledge Graph."""

    model_config = ConfigDict(frozen=True)

    subject: str = Field(description="The source entity")
    predicate: str = Field(description="The relationship or action")
    object: str = Field(description="The target entity")


class KnowledgeExtractionResult(BaseModel):
    """Container for AI-analyzed metadata (Keywords and Triples)."""

    model_config = ConfigDict(frozen=True)

    keywords: list[str] = Field(description="Top topical keywords")
    triples: list[KnowledgeTriple] = Field(description="Knowledge graph relationships")


class RetrievalContext(BaseModel):
    """Aggregated context from multiple retrieval strategies."""

    model_config = ConfigDict(frozen=True)

    vector_results: list[str] = Field(description="Semantically similar text chunks")
    keyword_matches: list[str] = Field(description="Content matched by high-frequency keywords")
    knowledge_graph_summary: list[str] = Field(description="Textualized graph relationships")

    def to_prompt_string(self) -> str:
        """Formats the aggregated context into a structured string for LLM ingestion."""
        parts = []
        if self.knowledge_graph_summary:
            parts.append(
                "=== KNOWLEDGE GRAPH (Relationships) ===\n"
                + "\n".join(self.knowledge_graph_summary)
            )
        if self.keyword_matches:
            parts.append("=== KEYWORD HIGHLIGHTS (Topics) ===\n" + "\n".join(self.keyword_matches))
        if self.vector_results:
            parts.append(
                "=== DETAILED CONTENT (Semantic Search) ===\n" + "\n".join(self.vector_results)
            )
        return "\n\n".join(parts)


# --- Domain Entities ---
class NewsItem(BaseModel):
    """Represents a single piece of news (Immutable)."""

    model_config = ConfigDict(frozen=True)

    # API returns varying fields, we normalize them
    title: str | None = None
    content: str = Field(description="The main text body or digest")
    category: str | None = None
    url: HttpUrl | None = None
    published_at: date

    @property
    def fingerprint(self) -> str:
        """Calculates a deterministic SHA256 hash for this item based on content and URL."""
        payload = f"{self.content}|{self.url}".encode()
        return hashlib.sha256(payload).hexdigest()


class DailyNewsBatch(BaseModel):
    """Collection of news items for a specific day and source category."""

    model_config = ConfigDict(frozen=True)

    date_str: date
    source: str  # e.g., "viki-60s", "viki-ai-news"
    items: list[NewsItem]
    cover_image_url: HttpUrl | None = None

    # Pre-calculated hash of the raw JSON response for idempotency
    raw_json_hash: str

    # AI-Enriched Data (Optional, populated after ingestion)
    ai_analysis: KnowledgeExtractionResult | None = None


class WeeklyReport(BaseModel):
    """Structured schema for synthesized weekly or yearly summaries."""

    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    summary_text: str
    key_events: list[str]
    best_cover_image: HttpUrl | None = None
