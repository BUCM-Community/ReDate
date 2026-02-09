"""
tests/redate/test_service_news.py

Unit tests for the Business Logic Service.

Focus:
- Orchestration flow.
- Idempotency.
"""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from redate.domain_models import DailyNewsBatch, NewsItem, Ok, RetrievalContext, WeeklyReport
from redate.service_news import NewsService


@pytest.fixture
def mocks():
    """Provide standard mocks for service dependencies."""
    return {
        "fetcher": AsyncMock(),
        "storage": AsyncMock(),
        "llm": AsyncMock(),
        "publisher": AsyncMock(),
    }


@pytest.mark.asyncio
async def test_daily_workflow_happy_path(mocks):
    """Test full flow: Fetch -> Archive -> Embed -> Save."""
    service = NewsService(**mocks)

    # Setup Data
    batch = DailyNewsBatch(
        date_str=date(2026, 1, 1),
        source="viki-60s",
        items=[NewsItem(content="A", published_at=date(2026, 1, 1))],
        raw_json_hash="hash_123",
    )

    # Setup Returns
    mocks["fetcher"].fetch_daily.return_value = Ok(batch)
    mocks["storage"].check_exists.return_value = False  # Not processed yet
    mocks["llm"].generate_embedding.return_value = [0.1, 0.2]

    # Run
    await service.run_daily_workflow(date(2026, 1, 1))

    # Verify
    mocks["fetcher"].fetch_daily.assert_called_once()
    mocks["storage"].check_exists.assert_called_with("hash_123", "viki-60s")
    mocks["storage"].archive_raw.assert_called_once()
    mocks["storage"].save_embedding.assert_called_once()


@pytest.mark.asyncio
async def test_daily_workflow_idempotent_skip(mocks):
    """Test that if data exists, processing stops."""
    service = NewsService(**mocks)

    batch = DailyNewsBatch(
        date_str=date(2026, 1, 1), source="viki-60s", items=[], raw_json_hash="hash_123"
    )

    mocks["fetcher"].fetch_daily.return_value = Ok(batch)
    mocks["storage"].check_exists.return_value = True  # ALREADY EXISTS

    await service.run_daily_workflow(date(2026, 1, 1))

    # Verify fetch happened but storage did NOT
    mocks["fetcher"].fetch_daily.assert_called_once()
    mocks["storage"].archive_raw.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_workflow_execution(mocks):
    """Test weekly reporting workflow."""
    service = NewsService(**mocks)

    # Mock Context Retrieval
    context = RetrievalContext(
        vector_results=["A"], keyword_matches=["B"], knowledge_graph_summary=["C"]
    )
    mocks["storage"].get_comprehensive_context.return_value = context

    # Mock Report Generation
    mocks["llm"].generate_period_report.return_value = WeeklyReport(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 7),
        summary_text="Summary",
        key_events=["E1"],
    )

    await service.run_weekly_workflow()

    mocks["storage"].get_comprehensive_context.assert_called_once()
    mocks["llm"].generate_period_report.assert_called_once()
    mocks["publisher"].publish_article.assert_called_once()
