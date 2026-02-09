"""
tests/redate/test_service_migration.py

Unit tests for Data Migration Service.

Focus:
- Adapter selection.
- Workflow orchestration.
"""

from unittest.mock import AsyncMock, patch

import pytest

from redate.service_migration import MigrationService


def test_migration_init_success():
    """Test that migration service initializes adapters correctly."""
    with (
        patch("redate.service_migration.HybridStorageAdapter") as mock_adapter_cls,
        patch("redate.service_migration.logger"),
    ):
        service = MigrationService()
        assert service.remote_adapter is not None
        assert service.local_adapter is not None
        assert mock_adapter_cls.call_count == 2


@pytest.mark.asyncio
async def test_run_migration_orchestration():
    """Test the orchestration flow of migration (objects then vectors)."""
    with (
        patch("redate.service_migration.HybridStorageAdapter"),
        patch("redate.service_migration.logger"),
    ):
        service = MigrationService()
        service.remote_adapter = AsyncMock()
        service.local_adapter = AsyncMock()

        # Mock internal helper methods to isolate logic
        service._migrate_objects = AsyncMock()  # type: ignore
        service._migrate_lancedb = AsyncMock()  # type: ignore

        result = await service.run_migration("cloud_to_local")

        assert result.is_ok()
        service._migrate_objects.assert_called_once()
        service._migrate_lancedb.assert_called_once()
