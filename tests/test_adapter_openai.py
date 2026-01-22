"""
tests/test_adapter_openai.py
Unit tests for OpenAI Adapter using respx.
Focus: Hybrid Routing, Structured Output Mocking, and HTTPX interception.
"""

import pytest
from httpx import Response

from redate.adapter_openai import OpenAIAdapter
from redate.domain_models import KnowledgeExtractionResult, RetrievalContext


@pytest.mark.asyncio
async def test_generate_embedding_siliconflow(respx_mock):
    """
    Test embedding generation routing to SiliconFlow.
    """
    # Mock SiliconFlow Endpoint
    route = respx_mock.post("https://api.siliconflow.cn/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2, 0.3], "index": 0, "object": "embedding"}
                ]
            },
        )
    )

    adapter = OpenAIAdapter()
    embedding = await adapter.generate_embedding("test text")

    assert embedding == [0.1, 0.2, 0.3]
    assert route.called
    # Verify strict model usage
    assert route.calls.last.request.read().decode().__contains__("BAAI/bge-m3")


@pytest.mark.asyncio
async def test_summarize_daily_openrouter(respx_mock):
    """
    Test daily summary routing to OpenRouter.
    """
    # Mock OpenRouter Chat Endpoint
    route = respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": "<ul><li>Summary</li></ul>"}}]},
        )
    )

    adapter = OpenAIAdapter()
    summary = await adapter.summarize_daily("Some long news text")

    assert "Summary" in summary
    assert route.called


@pytest.mark.asyncio
async def test_extract_knowledge_structured_output(respx_mock):
    """
    Test parsing of structured outputs from OpenRouter/OpenAI.
    """
    # Mock OpenRouter to return valid JSON matching the Pydantic schema
    expected_json = {
        "keywords": ["AI", "Python"],
        "triples": [{"subject": "Google", "predicate": "released", "object": "Gemini"}],
    }

    respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": None, "parsed": expected_json}}]},
        )
    )

    adapter = OpenAIAdapter()
    result = await adapter.extract_knowledge("News text")

    assert isinstance(result, KnowledgeExtractionResult)
    assert result.keywords == ["AI", "Python"]
    assert result.triples[0].subject == "Google"


@pytest.mark.asyncio
async def test_generate_period_report_error_handling(respx_mock):
    """
    Test failure handling when upstream returns 500.
    """
    respx_mock.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(500, text="Internal Server Error")
    )

    adapter = OpenAIAdapter()

    # Mock context
    context = RetrievalContext(
        vector_results=[], keyword_matches=[], knowledge_graph_summary=[]
    )

    from datetime import date

    with pytest.raises(Exception):
        await adapter.generate_period_report(
            context, date(2026, 1, 1), date(2026, 1, 7)
        )
