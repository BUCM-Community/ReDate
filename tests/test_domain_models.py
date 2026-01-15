from datetime import date
from typing import cast

from pydantic import HttpUrl

from src.domain_models import DailyNewsBatch, Err, NewsItem, Ok


def test_news_item_fingerprint():
    item1 = NewsItem(
        content="Test Content",
        url=cast(HttpUrl, "https://example.com/1"),
        published_at=date(2026, 1, 1),
    )
    item2 = NewsItem(
        content="Test Content",
        url=cast(HttpUrl, "https://example.com/1"),
        published_at=date(2026, 1, 1),
    )
    item3 = NewsItem(
        content="Different Content",
        url=cast(HttpUrl, "https://example.com/1"),
        published_at=date(2026, 1, 1),
    )

    assert item1.fingerprint == item2.fingerprint
    assert item1.fingerprint != item3.fingerprint


def test_result_pattern():
    ok_res = Ok("value")
    err_res = Err("error")

    assert ok_res.is_ok()
    assert not err_res.is_ok()
    assert ok_res.value == "value"
    assert err_res.error == "error"


def test_daily_news_batch_immutability():
    batch = DailyNewsBatch(
        date_str=date(2026, 1, 1), source="test", items=[], raw_json_hash="abc"
    )
    import pytest

    with pytest.raises(Exception):
        # type: ignore
        batch.source = "new"
