"""
tests/redate/test_adapter_storage.py

Unit tests for HybridStorageAdapter using Moto (Stateful S3 Mock).

Focus:
- Correct typing for aioboto3 context managers.
- Stateful verification.
- LanceDB interaction mocking.
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import TYPE_CHECKING, cast

import aioboto3
from moto import mock_aws
import pytest

from redate.adapter_storage import HybridStorageAdapter
from redate.domain_models import DailyNewsBatch

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client


@pytest.mark.asyncio
@mock_aws
async def test_archive_raw_real_moto(mock_lancedb):
    """
    Verifies that files are actually written to the mock S3 bucket using moto.

    Uses strict type casting to satisfy static analysis tools.
    """
    # 1. Setup Moto Environment (Bucket must exist)
    session = aioboto3.Session()

    # Helper to enforce type safety for the test context
    # This resolves "Attribute __aenter__ is unknown"
    def get_s3_ctx() -> AbstractAsyncContextManager[S3Client]:
        return cast(
            AbstractAsyncContextManager["S3Client"],
            session.client("s3", region_name="us-east-1"),
        )

    # Context 1: Create Bucket
    async with get_s3_ctx() as s3:
        await s3.create_bucket(Bucket="mock-bucket")

    # 2. Execute Adapter Logic
    # The adapter internally handles its own connection, which moto intercepts
    adapter = HybridStorageAdapter()
    success = await adapter.archive_raw("test/file.json", b'{"key": "value"}')
    assert success is True

    # 3. Verify Persistence
    # Context 2: Read Validation
    async with get_s3_ctx() as s3:
        resp = await s3.get_object(Bucket="mock-bucket", Key="test/file.json")
        content = await resp["Body"].read()
        assert content == b'{"key": "value"}'


@pytest.mark.asyncio
@mock_aws
async def test_lancedb_saving_logic(mock_lancedb):
    """Tests the logic flow for saving embeddings, ensuring S3 client init is valid."""
    # Ensure bucket exists for the LanceDB S3 connection simulation
    session = aioboto3.Session()

    def get_s3_ctx() -> AbstractAsyncContextManager[S3Client]:
        return cast(
            AbstractAsyncContextManager["S3Client"],
            session.client("s3", region_name="us-east-1"),
        )

    async with get_s3_ctx() as s3:
        await s3.create_bucket(Bucket="mock-bucket")

    adapter = HybridStorageAdapter()

    batch = DailyNewsBatch(
        date_str=date(2026, 1, 1), source="viki-60s", items=[], raw_json_hash="abc"
    )
    vector = [0.1, 0.2, 0.3]

    await adapter.save_embedding(batch, vector)

    # Verify interaction with mocked LanceDB
    # _get_table_names logic: viki-60s -> viki_60s
    mock_lancedb.open_table.assert_called()


@pytest.mark.asyncio
@mock_aws
async def test_get_comprehensive_context(mock_lancedb, mocker):
    """Test context retrieval aggregating logic."""
    session = aioboto3.Session()

    def get_s3_ctx() -> AbstractAsyncContextManager[S3Client]:
        return cast(
            AbstractAsyncContextManager["S3Client"],
            session.client("s3", region_name="us-east-1"),
        )

    async with get_s3_ctx() as s3:
        await s3.create_bucket(Bucket="mock-bucket")

    # Mock DB Tables
    mock_lancedb.table_names.return_value = ["vec_test", "kw_test"]
    mock_table = mocker.MagicMock()
    mock_lancedb.open_table.return_value = mock_table

    # Mock PyArrow conversions
    mock_arrow = mocker.MagicMock()
    # For vector table
    mock_arrow.num_rows = 1
    mock_arrow.__getitem__.return_value.to_pylist.return_value = ["Context Text"]
    # Chain: search() -> where() -> select() -> to_arrow()
    mock_table.search.return_value.where.return_value.select.return_value.to_arrow.return_value = (
        mock_arrow
    )
    # Chain: search() -> where() -> to_arrow() (for KG)
    mock_table.search.return_value.where.return_value.to_arrow.return_value = mock_arrow

    adapter = HybridStorageAdapter()
    context = await adapter.get_comprehensive_context(date(2026, 1, 1), date(2026, 1, 1))

    assert "Context Text" in context.vector_results[0]
