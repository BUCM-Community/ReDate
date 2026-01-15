import json
from datetime import date
from unittest.mock import MagicMock

import pytest
from google import genai
from pydantic import HttpUrl, SecretStr

# 导入要测试的模块
from src.adapter_gemini import GeminiAdapter
from src.config import Settings
from src.domain_models import WeeklyReport
from src.ports import LLMEngine


# 使用 pytest.fixture 模拟配置
@pytest.fixture(autouse=True)
def mock_settings(mocker):
    """Mock global settings for clean testing."""
    mock_settings_instance = Settings(
        VIKI_API_BASE=HttpUrl("http://viki.moe"),
        R2_ACCOUNT_ID="id",
        R2_ACCESS_KEY_ID=SecretStr("key"),
        R2_SECRET_ACCESS_KEY=SecretStr("secret"),
        R2_ENDPOINT=HttpUrl("http://r2.endpoint.com"),
        R2_BUCKET_NAME="bucket",
        GEMINI_API_KEY=SecretStr("test_key_1"),
        WECHAT_APP_ID=SecretStr("wx_id"),
        WECHAT_APP_SECRET=SecretStr("wx_secret"),
        # Set alternative key for testing client rotation
        GEMINI_API_KEY_ALT=SecretStr("test_key_2"),
    )
    mocker.patch("src.adapter_gemini.settings", mock_settings_instance)
    # Ensure the required pydantic settings are available for import time instantiation
    for key, value in mock_settings_instance.model_dump().items():
        if isinstance(value, SecretStr):
            mocker.patch.dict("os.environ", {key: value.get_secret_value()})
        else:
            mocker.patch.dict("os.environ", {key: str(value)})


@pytest.fixture
def mock_genai_client(mocker):
    """Mocks genai.Client and its async methods."""
    mock_client = MagicMock(spec=genai.Client)
    mock_aio_client = MagicMock()
    mock_client.aio = mock_aio_client

    # Mock models service
    mock_models = MagicMock()
    mock_aio_client.models = mock_models

    # Mock client initialization in the adapter
    mock_init = mocker.patch("src.adapter_gemini.genai.Client", return_value=mock_client)

    return mock_init, mock_aio_client


@pytest.fixture
def adapter(mock_genai_client):
    """Returns an instance of GeminiAdapter with mocked dependencies."""
    # We explicitly need two clients to be created due to GEMINI_API_KEY_ALT
    return GeminiAdapter()


@pytest.mark.asyncio
async def test_adapter_implements_interface(adapter):
    """Test that GeminiAdapter fulfills the LLMEngine Protocol."""
    assert isinstance(adapter, LLMEngine)


@pytest.mark.asyncio
async def test_client_initialization_and_rotation(adapter, mock_genai_client, mock_settings):
    """Test that two clients are initialized and they rotate correctly."""
    mock_client_init, _ = mock_genai_client

    # Check that two clients were initialized with the two keys
    assert mock_client_init.call_count == 2

    # Check client rotation (_get_client)
    client1 = adapter._get_client()
    client2 = adapter._get_client()
    client3 = adapter._get_client()  # Should wrap back to client1

    # Due to how the list is constructed in __init__, we need to check if they are different
    # and if the rotation works.
    assert client1 != client2
    assert client1 == client3


@pytest.mark.asyncio
async def test_generate_embedding_success(adapter, mock_genai_client):
    """Test successful embedding generation."""
    _, mock_aio_client = mock_genai_client

    expected_embedding = [0.1, 0.2, 0.3]
    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock(values=expected_embedding)]
    mock_aio_client.models.embed_content.return_value = mock_response

    result = await adapter.generate_embedding("Test text")

    assert result == expected_embedding
    mock_aio_client.models.embed_content.assert_called_once()
    assert mock_aio_client.models.embed_content.call_args[1]["model"] == adapter.settings.MODEL_EMBEDDING


@pytest.mark.asyncio
async def test_generate_embedding_no_values(adapter, mock_genai_client):
    """Test embedding returns empty list if no values are found."""
    _, mock_aio_client = mock_genai_client

    mock_response = MagicMock()
    mock_response.embeddings = [MagicMock(values=None)]
    mock_aio_client.models.embed_content.return_value = mock_response

    result = await adapter.generate_embedding("Test text")

    assert result == []


@pytest.mark.asyncio
async def test_summarize_daily_success(adapter, mock_genai_client):
    """Test successful daily summary generation."""
    _, mock_aio_client = mock_genai_client

    expected_summary = "<h2>Daily Briefing</h2><ul><li>News 1</li></ul>"
    mock_response = MagicMock(text=expected_summary)
    mock_aio_client.models.generate_content.return_value = mock_response

    result = await adapter.summarize_daily("Some raw text.")

    assert result == expected_summary
    mock_aio_client.models.generate_content.assert_called_once()
    call_args = mock_aio_client.models.generate_content.call_args[1]
    assert "Daily Briefing" in call_args["contents"]
    assert call_args["model"] == adapter.settings.MODEL_CHAT


@pytest.mark.asyncio
async def test_summarize_daily_failure(adapter, mock_genai_client):
    """Test daily summary generation failure returns error message."""
    _, mock_aio_client = mock_genai_client

    # Mocking failure to generate response
    mock_aio_client.models.generate_content.side_effect = Exception("API Down")

    result = await adapter.summarize_daily("Some raw text.")

    assert "Error generating summary" in result


@pytest.mark.asyncio
async def test_generate_period_report_success(adapter, mock_genai_client):
    """Test successful period report generation with JSON output."""
    _, mock_aio_client = mock_genai_client

    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 7)

    json_response = {"summary_text": "<h2>Weekly Summary</h2><p>...<p>", "key_events": ["Event A", "Event B"]}
    mock_response = MagicMock(text=json.dumps(json_response))
    mock_aio_client.models.generate_content.return_value = mock_response

    contexts = ["Context 1", "Context 2"]

    report = await adapter.generate_period_report(contexts, start_date, end_date, "Weekly")

    assert isinstance(report, WeeklyReport)
    assert report.summary_text == json_response["summary_text"]
    assert report.key_events == json_response["key_events"]

    # Check that JSON configuration was passed
    call_args = mock_aio_client.models.generate_content.call_args[1]
    assert call_args["config"] == {"response_mime_type": "application/json"}
    assert "Weekly Report from 2024-01-01 to 2024-01-07" in call_args["contents"]


@pytest.mark.asyncio
async def test_generate_period_report_json_failure(adapter, mock_genai_client):
    """Test period report generation failure due to JSON parsing."""
    _, mock_aio_client = mock_genai_client

    start_date = date(2024, 1, 1)
    end_date = date(2024, 1, 7)

    # Mock response with invalid JSON
    mock_response = MagicMock(text="Not JSON")
    mock_aio_client.models.generate_content.return_value = mock_response

    contexts = ["Context 1"]

    with pytest.raises(Exception):
        await adapter.generate_period_report(contexts, start_date, end_date, "Weekly")

    # Tenacity should stop after 3 attempts
    assert mock_aio_client.models.generate_content.call_count == 3
