"""
redate/adapter_storage.py
Handles Object Storage (aioboto3) and Vector Database (lancedb) via Direct S3.
Focus: Storage-Compute Separation, Pure Async I/O, Direct S3/R2 I/O, Lint-Free Async Context, Dynamic Table Partitioning.
"""

from __future__ import annotations

import re
from collections import Counter
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, cast

import aioboto3
import lancedb

from .config import settings
from .domain_models import RetrievalContext
from .ports import StorageAdapter
from .utils_date import get_beijing_today
from .utils_telemetry import logger

# 1. 类型定义修复
if TYPE_CHECKING:
    from datetime import date

    from types_aiobotocore_s3 import S3Client

    from .domain_models import DailyNewsBatch, KnowledgeExtractionResult

__all__ = ["HybridStorageAdapter"]


class HybridStorageAdapter(StorageAdapter):
    def __init__(self):
        self.session = aioboto3.Session()

        # 2. LanceDB 连接 (S3 mode)
        db_uri = f"s3://{settings.R2_BUCKET_NAME}/lancedb_store"
        logger.info("connecting_lancedb_remote", uri=db_uri)

        self.db = lancedb.connect(
            db_uri,
            storage_options={
                "aws_endpoint_override": str(settings.R2_ENDPOINT),
                "aws_access_key_id": settings.R2_ACCESS_KEY_ID.get_secret_value(),
                "aws_secret_access_key": settings.R2_SECRET_ACCESS_KEY.get_secret_value(),
                "aws_region": "auto",
                "allow_http": "true",
                "timeout": "60s",
            },
        )

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
        显式转换类型，解决 'Attribute __aenter__ is unknown' 报错。
        这是最稳健的 Production-Grade 修复方式。
        """
        ctx = self.session.client(
            "s3",
            endpoint_url=str(settings.R2_ENDPOINT),
            aws_access_key_id=settings.R2_ACCESS_KEY_ID.get_secret_value(),
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY.get_secret_value(),
            region_name="auto",
        )
        # 强制转换为标准异步上下文管理器接口
        return cast(AbstractAsyncContextManager["S3Client"], ctx)

    async def archive_raw(self, filename: str, data: bytes) -> bool:
        try:
            # 使用 Helper 获取强类型的 Context Manager
            async with self._s3_client() as s3:
                await s3.put_object(
                    Bucket=settings.R2_BUCKET_NAME,
                    Key=filename,
                    Body=data,
                    ContentType="application/json",
                )
            logger.info("r2_upload_success", file=filename)
            return True
        except Exception as e:
            logger.error("r2_upload_fail", error=str(e), file=filename)
            return False

    async def check_exists(self, content_hash: str, source: str) -> bool:
        """
        在特定的 Source 表中检查是否存在。
        """
        tables = self._get_table_names(source)
        table_name = tables["meta"]

        # 如果表还没创建，自然不存在
        if table_name not in self.db.table_names():
            return False

        try:
            tbl = self.db.open_table(table_name)
            # Optimize: Limit 1 is sufficient
            results = (
                tbl.search().where(f"hash = '{content_hash}'").limit(1).to_pandas()
            )
            return not results.empty
        except Exception as e:
            logger.warning("lancedb_check_fail", error=str(e), table=table_name)
            return False

    async def save_embedding(self, batch: DailyNewsBatch, vector: list[float]) -> None:
        """
        将数据存入 Source 对应的独立表中 (Meta + Vector)。
        """
        tables = self._get_table_names(batch.source)
        meta_table = tables["meta"]
        vec_table = tables["vec"]

        # 1. 准备数据
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
        data_vec = [
            {
                "date": str(batch.date_str),
                "text": full_text,
                "vector": vector,
                "source": batch.source,
            }
        ]

        # 2. 写入操作
        try:
            self._write_to_table(meta_table, data_meta)
            self._write_to_table(vec_table, data_vec)
            logger.info("db_saved_vector", table=vec_table, date=str(batch.date_str))
        except Exception as e:
            logger.error("db_save_vector_fail", error=str(e), source=batch.source)
            raise

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

        # 1. Flatten Keywords
        data_kw = [
            {"date": date_str, "source": batch.source, "keyword": kw}
            for kw in knowledge.keywords
        ]

        # 2. Flatten Triples
        data_kg = [
            {
                "date": date_str,
                "source": batch.source,
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
            }
            for t in knowledge.triples
        ]

        # 3. 写入操作
        try:
            if data_kw:
                self._write_to_table(kw_table, data_kw)
            if data_kg:
                self._write_to_table(kg_table, data_kg)

            logger.info(
                "db_saved_knowledge",
                kw_count=len(data_kw),
                kg_count=len(data_kg),
                source=batch.source,
            )
        except Exception as e:
            logger.error("db_save_knowledge_fail", error=str(e), source=batch.source)
            # Knowledge saving failure shouldn't necessarily crash the whole flow,
            # but we log strictly. Re-raise if strict consistency is needed.
            raise

    def _write_to_table(self, table_name: str, data: list[dict]) -> None:
        """Helper to create or append to a LanceDB table."""
        if not data:
            return
        if table_name not in self.db.table_names():
            self.db.create_table(table_name, data=data)
        else:
            self.db.open_table(table_name).add(data)

    async def get_comprehensive_context(
        self, start: date, end: date
    ) -> RetrievalContext:
        """
        聚合查询：同时检索 Vector, Keywords, Knowledge Graph 表。
        实现 'Three Ways' 数据检索，辅助 LLM 生成高质量报告。
        """
        all_tables = self.db.table_names()

        # 1. Identify Tables
        vec_tables = [t for t in all_tables if t.startswith("vec_")]
        kw_tables = [t for t in all_tables if t.startswith("kw_")]
        kg_tables = [t for t in all_tables if t.startswith("kg_")]

        vector_results: list[str] = []
        all_keywords: list[str] = []
        kg_sentences: list[str] = []

        date_filter = f"date >= '{start}' AND date <= '{end}'"

        # --- A. Vector Context (Detailed Content) ---
        for t_name in vec_tables:
            try:
                tbl = self.db.open_table(t_name)
                df = tbl.search().where(date_filter).to_pandas()
                if not df.empty:
                    source_label = t_name.replace("vec_", "").replace("_", " ").upper()
                    texts = df["text"].tolist()
                    vector_results.extend([f"[{source_label}] {t}" for t in texts])
            except Exception as e:
                logger.warning("ctx_fetch_vec_fail", table=t_name, error=str(e))

        # --- B. Keyword Context (Topics) ---
        for t_name in kw_tables:
            try:
                tbl = self.db.open_table(t_name)
                df = tbl.search().where(date_filter).to_pandas()
                if not df.empty:
                    all_keywords.extend(df["keyword"].tolist())
            except Exception as e:
                logger.warning("ctx_fetch_kw_fail", table=t_name, error=str(e))

        # Aggregate and rank keywords
        kw_counts = Counter(all_keywords)
        top_keywords = [
            f"{word} ({count})" for word, count in kw_counts.most_common(30)
        ]

        # --- C. Knowledge Graph Context (Relationships) ---
        for t_name in kg_tables:
            try:
                tbl = self.db.open_table(t_name)
                df = tbl.search().where(date_filter).to_pandas()
                if not df.empty:
                    # Format: 2026-01-21 [Wiki]: Google --released--> Gemini 2.0
                    for _, row in df.iterrows():
                        line = (
                            f"{row['date']} [{row['source']}]: "
                            f"{row['subject']} --{row['predicate']}--> {row['object']}"
                        )
                        kg_sentences.append(line)
            except Exception as e:
                logger.warning("ctx_fetch_kg_fail", table=t_name, error=str(e))

        return RetrievalContext(
            vector_results=vector_results,
            keyword_matches=top_keywords,
            knowledge_graph_summary=kg_sentences,
        )
