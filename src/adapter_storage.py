"""
src/adapter_storage.py
Handles Object Storage (aioboto3) and Vector Database (lancedb) via Direct S3.
Focus: Storage-Compute Separation, Pure Async I/O, Direct S3/R2 I/O, Lint-Free Async Context, Dynamic Table Partitioning.
"""

from __future__ import annotations

import re
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, cast

import aioboto3
import lancedb

from .config import settings
from .ports import StorageAdapter
from .utils_date import get_beijing_today
from .utils_telemetry import logger

# 1. 类型定义修复
if TYPE_CHECKING:
    from datetime import date

    from types_aiobotocore_s3 import S3Client

    from .domain_models import DailyNewsBatch

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
    def _get_table_names(self, source: str) -> tuple[str, str]:
        """
        根据 source 生成符合 LanceDB/Parquet 命名规范的表名。
        Example: source="viki-60s" -> ("meta_viki_60s", "vec_viki_60s")
        """
        # 将非字母数字字符替换为下划线，防止 SQL/File System 错误
        safe_suffix = re.sub(r"[^a-zA-Z0-9]", "_", source).lower()
        return f"meta_{safe_suffix}", f"vec_{safe_suffix}"

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
                    Bucket=settings.R2_BUCKET_NAME, Key=filename, Body=data, ContentType="application/json"
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
        table_name, _ = self._get_table_names(source)

        # 如果表还没创建，自然不存在
        if table_name not in self.db.table_names():
            return False

        try:
            tbl = self.db.open_table(table_name)
            results = tbl.search().where(f"hash = '{content_hash}'").limit(1).to_pandas()
            return not results.empty
        except Exception as e:
            logger.warning("lancedb_check_fail", error=str(e), table=table_name)
            return False

    async def save_embedding(self, batch: DailyNewsBatch, vector: list[float]) -> None:
        """
        将数据存入 Source 对应的独立表中。
        """
        meta_table_name, vec_table_name = self._get_table_names(batch.source)

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

        # 2. 写入 Meta 表
        try:
            if meta_table_name not in self.db.table_names():
                self.db.create_table(meta_table_name, data=data_meta)
            else:
                self.db.open_table(meta_table_name).add(data_meta)

            # 3. 写入 Vector 表
            if vec_table_name not in self.db.table_names():
                self.db.create_table(vec_table_name, data=data_vec)
            else:
                self.db.open_table(vec_table_name).add(data_vec)

            logger.info("db_saved_remote", table=vec_table_name, date=str(batch.date_str))
        except Exception as e:
            logger.error("db_save_fail", error=str(e), source=batch.source)
            raise

    async def get_date_range_context(self, start: date, end: date) -> list[str]:
        """
        聚合查询：扫描所有以 'vec_' 开头的表，收集指定日期范围内的上下文。
        用于生成包含多个来源（60s, AI News, Bing 等）的周报。
        """
        all_tables = self.db.table_names()
        # 筛选出向量表
        vec_tables = [t for t in all_tables if t.startswith("vec_")]

        combined_texts = []

        for t_name in vec_tables:
            try:
                tbl = self.db.open_table(t_name)
                # LanceDB SQL 过滤
                df = tbl.search().where(f"date >= '{start}' AND date <= '{end}'").to_pandas()

                if not df.empty:
                    # 添加来源前缀，方便 LLM 区分
                    source_label = t_name.replace("vec_", "").replace("_", " ").upper()
                    texts = df["text"].tolist()
                    combined_texts.extend([f"[{source_label}] {t}" for t in texts])

            except Exception as e:
                logger.warning("weekly_context_fetch_fail", table=t_name, error=str(e))
                continue

        return combined_texts
