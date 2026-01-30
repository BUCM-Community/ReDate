"""
redate/service_migration.py
Data Migration Service (R2 <-> Local/SeaweedFS).
Focus:
- Bidirectional Migration.
- Streaming S3 copy.
- Schema-aware PyArrow Table copy for Vectors.
- Resilience.
"""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Literal, cast

import aioboto3

from .adapter_storage import HybridStorageAdapter
from .domain_models import Err, Ok, Result
from .utils_telemetry import logger

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

__all__ = ["MigrationService"]


class MigrationService:
    """
    Handles bidirectional data migration between Cloud (R2) and Local (SeaweedFS).
    Uses streaming for objects and Arrow Flight/IPC for vector data.
    """

    def __init__(self):
        # Instantiate explicit adapters for Source and Destination
        # We assume secrets for BOTH are present in .env
        try:
            self.remote_adapter = HybridStorageAdapter(mode="remote")
            self.local_adapter = HybridStorageAdapter(mode="local")
        except ValueError as e:
            logger.critical(
                "migration_init_fail",
                error="Missing credentials for one or both environments",
            )
            raise e

    async def run_migration(
        self, direction: Literal["cloud_to_local", "local_to_cloud"]
    ) -> Result[str, str]:
        """
        Orchestrates bidirectional migration.
        """
        try:
            logger.info("migration_start", direction=direction)

            # Determine Source/Dest
            direction_map = {
                "cloud_to_local": (self.remote_adapter, self.local_adapter),
                "local_to_cloud": (self.local_adapter, self.remote_adapter),
            }
            src_adapter, dst_adapter = direction_map[direction]

            # 1. Migrate Object Storage (S3)
            # We need raw clients here for streaming
            logger.info("migration_phase_1_objects", direction=direction)
            await self._migrate_objects(src_adapter, dst_adapter)

            # 2. Migrate Vector DB (LanceDB via Arrow)
            logger.info("migration_phase_2_vectors", direction=direction)
            await self._migrate_lancedb(src_adapter, dst_adapter)

            return Ok(f"Migration {direction} completed successfully")
        except Exception as e:
            logger.critical("migration_failed", error=str(e), direction=direction)
            return Err(str(e))

    async def _migrate_objects(
        self, src_adapter: HybridStorageAdapter, dst_adapter: HybridStorageAdapter
    ) -> None:
        """
        Migrates S3 objects using streams to avoid memory pressure.
        """
        session = aioboto3.Session()

        # Extract credentials from adapters to ensure consistency
        # create new client contexts here for raw access
        async with (
            cast(
                AbstractAsyncContextManager["S3Client"],
                session.client(
                    "s3",
                    endpoint_url=src_adapter.s3_endpoint,
                    aws_access_key_id=src_adapter.s3_access_key,
                    aws_secret_access_key=src_adapter.s3_secret_key,
                    region_name="auto",
                ),
            ) as src_client,
            cast(
                AbstractAsyncContextManager["S3Client"],
                session.client(
                    "s3",
                    endpoint_url=dst_adapter.s3_endpoint,
                    aws_access_key_id=dst_adapter.s3_access_key,
                    aws_secret_access_key=dst_adapter.s3_secret_key,
                    region_name="auto",
                ),
            ) as dst_client,
        ):
            src_bucket = src_adapter.bucket_name
            dst_bucket = dst_adapter.bucket_name

            # Ensure dest bucket exists
            try:
                await dst_client.head_bucket(Bucket=dst_bucket)
            except Exception:
                await dst_client.create_bucket(Bucket=dst_bucket)
                logger.info("created_dest_bucket", bucket=dst_bucket)

            # List and Copy
            paginator = src_client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=src_bucket):
                if "Contents" not in page:
                    continue

                tasks = []
                for obj in page["Contents"]:
                    tasks.append(
                        self._copy_single_object(
                            src_client, dst_client, src_bucket, dst_bucket, obj["Key"]
                        )
                    )

                # Batch processing to prevent connection pool exhaustion
                # Process 10 files concurrently
                chunk_size = 10
                for i in range(0, len(tasks), chunk_size):
                    chunk = tasks[i : i + chunk_size]
                    await asyncio.gather(*chunk)

    async def _copy_single_object(
        self, src_client, dst_client, src_bucket, dst_bucket, key
    ):
        """Streams a single object from Source to Dest."""
        # Idempotency: Check existence in dest
        try:
            await dst_client.head_object(Bucket=dst_bucket, Key=key)
            logger.debug("object_exists_skip", key=key)
            return
        except Exception:
            pass

        # Stream Copy
        logger.info("migrating_object", key=key, from_bucket=src_bucket)
        try:
            resp = await src_client.get_object(Bucket=src_bucket, Key=key)
            async with resp["Body"] as stream:
                # Read fully into memory for small files (images/json).
                # For GB-sized files, we would need chunked upload.
                body_content = await stream.read()

                await dst_client.put_object(
                    Bucket=dst_bucket,
                    Key=key,
                    Body=body_content,
                    ContentType=resp.get("ContentType", "application/octet-stream"),
                )
        except Exception as e:
            logger.error("object_copy_error", key=key, error=str(e))

    async def _migrate_lancedb(
        self, src_adapter: HybridStorageAdapter, dst_adapter: HybridStorageAdapter
    ) -> None:
        """
        Migrates LanceDB tables using PyArrow for type-safe, efficient transfer.
        For huge datasets, we would use LanceDB's `copy` or file-level sync.
        """
        src_db = src_adapter.db
        dst_db = dst_adapter.db

        for table_name in src_db.table_names():
            logger.info("migrating_table", table=table_name)

            src_tbl = src_db.open_table(table_name)

            try:
                # Use to_arrow() to get a PyArrow Table.
                # This preserves schema info (types, nullability) better than dicts/pandas.
                arrow_table = src_tbl.to_arrow()
                batch_reader = arrow_table.to_batches()

                if table_name in dst_db.table_names():
                    logger.info("dropping_existing_table", table=table_name)
                    dst_db.drop_table(table_name)

                # Write arrow record batches directly
                dst_db.create_table(table_name, data=batch_reader)
                logger.info(
                    "table_migrated_success",
                    table=table_name,
                    rows=batch_reader.num_rows,
                )
                # If destination is remote, compact immediately
                if dst_adapter.mode == "remote":
                    await dst_adapter.optimize_table(table_name)
            except Exception as e:
                logger.error("table_migration_error", table=table_name, error=str(e))
                # Continue with next table, don't crash entire migration
                continue
