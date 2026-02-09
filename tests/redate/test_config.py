"""
tests/redate/test_config.py

Unit tests for Configuration Management.

Focus:
- Pydantic Settings validation.
- Environment Variable loading.
"""

from pydantic import SecretStr, ValidationError
import pytest

from redate.config import Settings


def test_settings_load_valid_env(monkeypatch):
    """Test that valid environment variables load correctly."""
    # Env vars are already set by conftest autouse fixture,
    # but we can override specific ones here if needed
    settings = Settings()  # type: ignore[call-arg]
    assert settings.ENV == "development"
    assert isinstance(settings.GEMINI_API_KEY, SecretStr)
    assert settings.GEMINI_API_KEY.get_secret_value() == "mock_gemini_key"


def test_settings_missing_required_env(monkeypatch):
    """Test strict validation for missing keys."""
    monkeypatch.delenv("R2_ACCESS_KEY_ID")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
