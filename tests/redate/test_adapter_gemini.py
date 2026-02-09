"""
tests/redate/test_adapter_gemini.py

Unit tests for Gemini LLM Adapter.

Focus:
- Retry logic.
- Client Rotation.
- API integration mocking.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from redate.adapter_gemini import GeminiAdapter


@pytest.fixture
def mock_genai(mocker):
    """Mock the Google GenAI Client."""
    mock_client_cls = mocker.patch("redate.adapter_gemini.genai.Client")

    # Setup mock instance
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance

    # Setup async methods
    mock_instance.aio.models.embed_content = AsyncMock()
    mock_instance.aio.models.generate_content = AsyncMock()

    return mock_instance


@pytest.mark.asyncio
async def test_generate_embedding_success(mock_genai, mock_sleep):
    """Test simple embedding generation."""
    mock_genai.aio.models.embed_content.return_value.embeddings = [
        MagicMock(values=[0.1, 0.2, 0.3])
    ]

    adapter = GeminiAdapter()
    vec = await adapter.generate_embedding("test")

    assert vec == [0.1, 0.2, 0.3]
    mock_genai.aio.models.embed_content.assert_called_once()


def test_client_rotation(mock_genai):
    """Test that multiple clients are initialized and rotated."""
    # Since we set GEMINI_API_KEY_ALT in conftest, rotation should happen
    adapter = GeminiAdapter()

    client1 = adapter._get_client()
    client2 = adapter._get_client()
    client3 = adapter._get_client()

    # Assuming the mock returns a new instance each time constructor is called,
    # but here our fixture mocks the CLASS, so we need to inspect the side_effect
    # or just trust the logic if we mocked the class correctly.
    # Actually, in the code: self.clients = [Client(...), Client(...)]
    # So the class constructor is called twice.
    assert len(adapter.clients) == 2
    assert client1 != client2
    assert client1 == client3  # Rotation loop


@pytest.mark.asyncio
async def test_summarize_daily_success(mock_genai):
    """Test daily summary generation success."""
    mock_response = MagicMock()
    mock_response.text = "<ul><li>Summary</li></ul>"
    mock_genai.aio.models.generate_content.return_value = mock_response

    adapter = GeminiAdapter()
    summary = await adapter.summarize_daily("News content")

    assert "Summary" in summary
    mock_genai.aio.models.generate_content.assert_called_once()
