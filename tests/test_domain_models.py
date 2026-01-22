"""
tests/test_domain_models.py
Unit tests for Core Domain Logic.
Focus: Immutability, Hashing, Result Monad behavior.
"""

from datetime import date
from typing import cast

import pytest
from pydantic import HttpUrl, ValidationError

from redate.domain_models import (
    Err,
    NewsItem,
    NewsNotFoundError,
    Ok,
)


def test_news_item_immutability():
    """Ensure NewsItems are frozen (immutable)."""
    item = NewsItem(
        title="Test",
        content="Content",
        published_at=date(2026, 1, 1),
        url=cast(HttpUrl, "https://example.com"),
    )
    with pytest.raises(ValidationError):
        item.title = "Changed"  # type: ignore


def test_news_item_fingerprint_deterministic():
    """Ensure fingerprint is stable based on content and URL."""
    item1 = NewsItem(
        content="A", url=cast(HttpUrl, "https://a.com"), published_at=date.today()
    )
    item2 = NewsItem(
        content="A", url=cast(HttpUrl, "https://a.com"), published_at=date.today()
    )
    item3 = NewsItem(
        content="B", url=cast(HttpUrl, "https://a.com"), published_at=date.today()
    )

    assert item1.fingerprint == item2.fingerprint
    assert item1.fingerprint != item3.fingerprint


def test_result_monad_behavior():
    """Test Ok/Err pattern matching helper methods."""
    success = Ok(100)
    failure = Err(NewsNotFoundError(message="oops"))

    assert success.is_ok() is True
    assert failure.is_ok() is False
    assert success.value == 100
    assert isinstance(failure.error, NewsNotFoundError)
