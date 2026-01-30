"""
redate/adapter_storage.py
Handles Object Storage (aioboto3) and Vector Database (lancedb).
Focus:
- Dynamic Backend Switching by Unified S3 Protocol Interface (R2 vs SeaweedFS).
- LanceDB S3 Integration with Caching & Compaction.
- Uses PyArrow for zero-copy data access
- Pure Async I/O.
"""

from __future__ import annotations

import re
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import TYPE_CHECKING, cast

import aioboto3
import lancedb
import numpy as np
import pyarrow as pa
from tenacity import retry, stop_after_attempt, wait_fixed

from .config import settings
from .domain_models import RetrievalContext
from .ports import StorageAdapter
from .utils_date import get_beijing_today
from .utils_telemetry import logger

if TYPE_CHECKING:
    from datetime import date

    from types_aiobotocore_s3 import S3Client

    from .domain_models import DailyNewsBatch, KnowledgeExtractionResult

__all__ = ["HybridStorageAdapter"]


class HybridStorageAdapter(StorageAdapter):
    def __init__(self, mode: str | None = None):
        """
        Args:
            mode: "remote" (R2) or "local" (SeaweedFS). Defaults to settings.DEPLOY_MODE.
        """
        self.session = aioboto3.Session()
        self.mode = mode or settings.DEPLOY_MODE

        # --- 1. S3 Configuration (Object Storage) ---
        if self.mode == "remote":
            if (
                not settings.R2_ENDPOINT
                or not settings.R2_ACCESS_KEY_ID
                or not settings.R2_SECRET_ACCESS_KEY
            ):
                raise ValueError("R2 credentials missing for remote mode")

            self.s3_endpoint = str(settings.R2_ENDPOINT)
            self.s3_access_key = settings.R2_ACCESS_KEY_ID.get_secret_value()
            self.s3_secret_key = settings.R2_SECRET_ACCESS_KEY.get_secret_value()
            self.bucket_name = settings.R2_BUCKET_NAME
            self.region = "auto"

            # --- 2. LanceDB Configuration (Remote S3) ---
            # enable local caching via storage_options or by relying on local FS sync in higher layers if needed.
            # Standard LanceDB S3 options:
            self.lancedb_uri = f"s3://{self.bucket_name}/lancedb_store"
            self.lancedb_options = {
                "aws_endpoint_override": self.s3_endpoint,
                "aws_access_key_id": self.s3_access_key,
                "aws_secret_access_key": self.s3_secret_key,
                "aws_region": "auto",
                "allow_http": "true",  # R2 sometimes needs this or https explicit
                "timeout": "60s",
            }
            logger.info("connecting_lancedb_remote", uri=self.lancedb_uri)

        elif self.mode == "local":
            if not settings.SEAWEED_ENDPOINT:
                raise ValueError("SEAWEED_ENDPOINT required for local mode")

            self.s3_endpoint = str(settings.SEAWEED_ENDPOINT)
            self.s3_access_key = (
                settings.SEAWEED_ACCESS_KEY_ID.get_secret_value()
                if settings.SEAWEED_ACCESS_KEY_ID
                else "any"
            )
            self.s3_secret_key = (
                settings.SEAWEED_SECRET_ACCESS_KEY.get_secret_value()
                if settings.SEAWEED_SECRET_ACCESS_KEY
                else "any"
            )
            self.bucket_name = settings.SEAWEED_BUCKET_NAME
            self.region = "us-east-1"  # SeaweedFS default

            # --- 2. LanceDB Configuration (Local Disk) ---
            # In local mode, we use the local filesystem for maximum performance
            # independent of SeaweedFS (which stores the raw objects).
            local_path = Path(settings.LANCEDB_LOCAL_PATH)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            self.lancedb_uri = str(local_path)
            self.lancedb_options = None
            logger.info("connecting_lancedb_local", path=self.lancedb_uri)

        else:
            raise ValueError(f"Unknown deploy mode: {self.mode}")

        # Connect to LanceDB
        # storage_options is only valid for remote URIs
        if self.lancedb_options:
            self.db = lancedb.connect(
                self.lancedb_uri, storage_options=self.lancedb_options
            )
        else:
            self.db = lancedb.connect(self.lancedb_uri)

    # --- Helper: 动态表名生成 ---
    def _get_table_names(self, source: str) -> dict[str, str]:
        """
        根据 source 生成符合 LanceDB/Parquet 命名规范的表名。
        Returns dictionary of table names for different data types.
        """
        # 将非字母数字字符替换为下划线，防止 SQL/File System 错误
        safe_suffix = re.sub(r"[^a-zA-Z0-9]", "_", source).lower()
        return {
            "meta": f"meta_{safe_suffix}",
            "vec": f"vec_{safe_suffix}",
            "kw": f"kw_{safe_suffix}",  # Keywords table
            "kg": f"kg_{safe_suffix}",  # Knowledge Graph table
        }

    # --- Helper: 强类型 S3 Context ---
    def _s3_client(self) -> AbstractAsyncContextManager["S3Client"]:
        """
        Creates a properly typed S3 client context manager.
        显式转换类型，解决 'Attribute __aenter__ is unknown' 报错。
        """
        ctx = self.session.client(
            "s3",
            endpoint_url=self.s3_endpoint,
            aws_access_key_id=self.s3_access_key,
            aws_secret_access_key=self.s3_secret_key,
            region_name=self.region,
        )
        # 强制转换为标准异步上下文管理器接口
        return cast(AbstractAsyncContextManager["S3Client"], ctx)

    async def _ensure_bucket_exists(self):
        """Idempotent check to ensure bucket exists (useful for local setup)."""
        try:
            async with self._s3_client() as s3:
                try:
                    await s3.head_bucket(Bucket=self.bucket_name)
                except Exception:
                    await s3.create_bucket(Bucket=self.bucket_name)
                    logger.info("bucket_created", bucket=self.bucket_name)
        except Exception as e:
            logger.warning("bucket_check_fail", error=str(e))

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def archive_raw(self, filename: str, data: bytes) -> bool:
        """
        Uploads raw object to S3 (R2 or SeaweedFS).
        """
        if self.mode == "local":
            await self._ensure_bucket_exists()

        try:
            async with self._s3_client() as s3:
                await s3.put_object(
                    Bucket=self.bucket_name,
                    Key=filename,
                    Body=data,
                    ContentType="application/json",
                )
            logger.info("object_upload_success", provider=self.mode, file=filename)
            return True
        except Exception as e:
            logger.error("object_upload_fail", provider=self.mode, error=str(e))
            return False

    async def check_exists(self, content_hash: str, source: str) -> bool:
        """
        Check if data exists in some table using PyArrow.
        """
        tables = self._get_table_names(source)
        table_name = tables["meta"]

        if table_name not in self.db.table_names():
            return False

        try:
            tbl = self.db.open_table(table_name)
            # Limit 1 + Arrow Table check (metadata only scan usually)
            arrow_tbl = (
                tbl.search().where(f"hash = '{content_hash}'").limit(1).to_arrow()
            )
            return arrow_tbl.num_rows > 0
        except Exception as e:
            logger.warning("lancedb_check_fail", error=str(e))
            return False

    async def save_embedding(self, batch: DailyNewsBatch, vector: list[float]) -> None:
        """
        Saves vector and metadata to LanceDB.
        Triggers compaction periodically for R2 optimization.
        """
        tables = self._get_table_names(batch.source)
        meta_table_name = tables["meta"]
        vec_table_name = tables["vec"]

        # Preparing data as list of dicts (LanceDB handles conversion to Arrow automatically)
        data_meta = [
            {
                "hash": batch.raw_json_hash,
                "date": str(batch.date_str),
                "source": batch.source,
                "created_at": get_beijing_today().isoformat(),
            }
        ]

        # Combine text for vector context
        full_text = "\n".join([f"- {i.content}" for i in batch.items])
        vec_np = np.array([vector], dtype=np.float32)
        data_vec = pa.Table.from_pydict(
            {
                "date": [str(batch.date_str)],
                "text": [full_text],
                "vector": pa.FixedSizeListArray.from_arrays(
                    vec_np.flatten(), list_size=len(vector)
                ),
                "source": [batch.source],
            }
        )

        # 2. 写入操作
        try:
            self._write_to_table(meta_table_name, data_meta)
            self._write_to_table(vec_table_name, data_vec)
            logger.info("db_saved_vector", table=vec_table_name)
            # Compaction Strategy: Compact periodically to avoid small file fragmentation on S3
            # In a real system, this might be a background job, but here we do it opportunistically.
            if self.mode == "remote":
                await self.optimize_table(vec_table_name)
        except Exception as e:
            logger.error("db_save_vector_fail", error=str(e))
            raise

    async def optimize_table(self, table_name: str) -> None:
        """
        Runs compaction on the table. Crucial for R2/S3 performance.
        """
        try:
            tbl = self.db.open_table(table_name)
            # compact_files() merges small fragments
            tbl.compact_files()
            # cleanup_old_versions() removes stale files (good for costs)
            tbl.cleanup_old_versions()
            logger.info("table_optimized", table=table_name)
        except Exception as e:
            logger.warning("optimization_failed", table=table_name, error=str(e))

    async def save_knowledge(
        self, batch: DailyNewsBatch, knowledge: KnowledgeExtractionResult
    ) -> None:
        """
        保存提取的 Knowledge Graph 和 Keywords 到对应的表中。
        """
        tables = self._get_table_names(batch.source)
        kw_table = tables["kw"]
        kg_table = tables["kg"]

        date_str = str(batch.date_str)

        try:
            # 1. Keywords
            # Convert list of strings to Arrow Table
            kw_count = len(knowledge.keywords)
            if kw_count > 0:
                data_kw = pa.Table.from_pydict(
                    {
                        "date": pa.repeat(date_str, kw_count),
                        "source": pa.repeat(batch.source, kw_count),
                        "keyword": pa.array(knowledge.keywords),
                    }
                )
                self._write_to_table(kw_table, data_kw)

            # 2. Triples
            kg_count = len(knowledge.triples)
            if kg_count > 0:
                data_kg = pa.Table.from_pydict(
                    {
                        # Optimization: Use pa.repeat for constant columns (O(1) value storage logic in Arrow)
                        "date": pa.repeat(date_str, kg_count),
                        "source": pa.repeat(batch.source, kg_count),
                        "subject": pa.array([t.subject for t in knowledge.triples]),
                        "predicate": pa.array([t.predicate for t in knowledge.triples]),
                        "object": pa.array([t.object for t in knowledge.triples]),
                    }
                )
                self._write_to_table(kg_table, data_kg)

            logger.info(
                "db_saved_knowledge",
                kw_count=kw_count,
                kg_count=kg_count,
                source=batch.source,
            )
        except Exception as e:
            logger.error("db_save_knowledge_fail", error=str(e), source=batch.source)
            # Knowledge saving failure shouldn't necessarily crash the whole flow,
            # but we log strictly. Re-raise if strict consistency is needed.
            raise

    def _write_to_table(self, table_name: str, data: list[dict] | pa.Table) -> None:
        """
        Helper to create or append to a LanceDB table.
        Supports both list of dicts and PyArrow Tables.
        Explicit type checking prevents static analysis errors.
        """
        # 1. Check for Empty List
        if isinstance(data, list) and not data:
            return
        # 2. Check for Empty Arrow Table
        elif isinstance(data, pa.Table) and data.num_rows == 0:  # type: ignore[reportAttributeAccessIssue]
            return

        if table_name not in self.db.table_names():
            self.db.create_table(table_name, data=data)
        else:
            self.db.open_table(table_name).add(data)

    async def get_comprehensive_context(
        self, start: date, end: date
    ) -> RetrievalContext:
        """
        Retrieves context from Vector, Keywords and Knowledge Graph via PyArrow.
        """
        all_tables = self.db.table_names()
        vec_tables = [t for t in all_tables if t.startswith("vec_")]
        kw_tables = [t for t in all_tables if t.startswith("kw_")]
        kg_tables = [t for t in all_tables if t.startswith("kg_")]

        vector_results: list[str] = []
        kg_sentences: list[str] = []
        all_keywords_chunks: list[pa.Array] = []

        date_filter = f"date >= '{start}' AND date <= '{end}'"

        # --- A. Vector Context (Detailed Content) ---
        for t_name in vec_tables:
            try:
                tbl = self.db.open_table(t_name)
                # Fetch only 'text' column, convert to python list
                # This avoids loading vectors/embeddings into memory
                arrow_tbl = tbl.search().where(date_filter).select(["text"]).to_arrow()

                if arrow_tbl.num_rows > 0:
                    source_label = t_name.replace("vec_", "").replace("_", " ").upper()
                    # PyArrow Column -> Python List
                    texts = arrow_tbl["text"].to_pylist()
                    vector_results.extend([f"[{source_label}] {t}" for t in texts])
            except Exception:
                pass

        # --- B. Keyword Context (Topics) ---
        for t_name in kw_tables:
            try:
                tbl = self.db.open_table(t_name)
                arrow_tbl = (
                    tbl.search().where(date_filter).select(["keyword"]).to_arrow()
                )
                if arrow_tbl.num_rows > 0:
                    # Append the specific column ChunkedArray
                    all_keywords_chunks.append(arrow_tbl["keyword"])
            except Exception as e:
                logger.warning("ctx_fetch_kw_fail", table=t_name, error=str(e))

        # --- C. Knowledge Graph Context (Relationships) ---
        for t_name in kg_tables:
            try:
                tbl = self.db.open_table(t_name)
                # Need multiple columns for reconstruction
                arrow_tbl = tbl.search().where(date_filter).to_arrow()
                if arrow_tbl.num_rows > 0:
                    # Convert whole table to list of dicts for row-wise iteration
                    # (Faster than iterating Arrow scalars in Python loop)
                    rows = arrow_tbl.to_pylist()
                    # Format: 2026-01-21 [Wiki]: Google --released--> Gemini 2.0
                    for row in rows:
                        line = (
                            f"{row['date']} [{row['source']}]: "
                            f"{row['subject']} --{row['predicate']}--> {row['object']}"
                        )
                        kg_sentences.append(line)
            except Exception as e:
                logger.warning("ctx_fetch_kg_fail", table=t_name, error=str(e))

        # Aggregate and rank keywords

        # Zero-copy concatenation of chunks
        combined_array = pa.chunked_array(all_keywords_chunks)
        counts = combined_array.value_counts
        # 排序并取前30 (PyArrow Table 操作)
        top_k = counts.sort_by([("counts", "descending")]).slice(0, 30)
        top_keywords = [
            f"{row['values']} ({row['counts']})" for row in top_k.to_pylist()
        ]

        return RetrievalContext(
            vector_results=vector_results,
            keyword_matches=top_keywords,
            knowledge_graph_summary=kg_sentences,
        )
