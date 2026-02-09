"""
tests/conftest.py

Global fixtures for ReDate test suite.

Focus:
- Environment isolation.
- AsyncIO configuration.
- Dependency Mocking.
"""

import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import pytest

# Ensure the project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))


@pytest.fixture(scope="session", autouse=True)
def set_env():
    """
    Sets environment variables for the entire test session before any imports.

    This ensures Pydantic Settings can initialize without errors.
    """
    old_environ = dict(os.environ)
    os.environ.update(
        {
            "ENV": "development",
            "LOG_LEVEL": "DEBUG",
            "VIKI_API_BASE": "https://mock.viki.moe",
            "R2_ACCOUNT_ID": "mock_r2_id",
            "R2_ACCESS_KEY_ID": "mock_r2_key",
            "R2_SECRET_ACCESS_KEY": "mock_r2_secret",
            "R2_BUCKET_NAME": "mock-bucket",
            "R2_ENDPOINT": "https://mock.r2.cloudflarestorage.com",
            "GEMINI_API_KEY": "mock_gemini_key",
            "GEMINI_API_KEY_ALT": "mock_gemini_key_2",
            "OPENROUTER_API_KEY": "mock_router_key",
            "SILICONFLOW_API_KEY": "mock_silicon_key",
            "WECHAT_APP_ID": "mock_wx_id",
            "WECHAT_APP_SECRET": "mock_wx_secret",
            "WECHAT_PROXY_URL": "socks5://mock-proxy:1080",
            "UNSPLASH_ACCESS_KEY": "mock_unsplash",
            "PEXELS_API_KEY": "mock_pexels",
            "PIXABAY_API_KEY": "mock_pixabay",
        }
    )
    yield
    os.environ.clear()
    os.environ.update(old_environ)


@pytest.fixture
def mock_sleep(mocker):
    """Skip asyncio.sleep to speed up tests involving retries."""
    return mocker.patch("asyncio.sleep", new_callable=AsyncMock)


@pytest.fixture
def mock_lancedb(mocker):
    """
    Global mock for LanceDB to prevent local DB file creation during unit tests.

    Individual tests can override return values.
    """
    mock_module = mocker.patch("redate.adapter_storage.lancedb")
    mock_conn = mocker.MagicMock()
    mock_module.connect.return_value = mock_conn
    return mock_conn
