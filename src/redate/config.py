"""
redate/config.py

Application configuration using Pydantic Settings.

Focus: Immutable configuration, Secret management, and Type safety.
Includes specific configs for OpenRouter, SiliconFlow, and Gemini Grounding.
"""

from __future__ import annotations

import tempfile
from typing import Literal

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]


class Settings(BaseSettings):
    """
    Global Application Configuration.

    Loads from environment variables and `.env` files.
    """

    # --- Infrastructure ---
    ENV: Literal["development", "production"] = "development"

    # --- Sources (Viki API) ---
    VIKI_API_BASE: HttpUrl

    # --- Storage Selection ---
    # "remote": Use Cloudflare R2 (S3) + LanceDB S3
    # "local": Use SeaweedFS (S3) + LanceDB Local Disk
    DEPLOY_MODE: Literal["remote", "local"] = "local"

    # --- R2 Storage (Remote / Cloud) ---
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: SecretStr | None = None
    R2_SECRET_ACCESS_KEY: SecretStr | None = None
    R2_ENDPOINT: HttpUrl | None = None
    R2_BUCKET_NAME: str = "redate-cloud"

    # --- SeaweedFS Storage (Local / Edge) ---
    SEAWEED_ACCESS_KEY_ID: SecretStr | None = None
    SEAWEED_SECRET_ACCESS_KEY: SecretStr | None = None
    SEAWEED_ENDPOINT: HttpUrl = "http://localhost:8333"  # type: ignore[assignment]
    SEAWEED_BUCKET_NAME: str = "redate-local"

    # --- LanceDB Configuration ---
    # Path for local vector storage (when using "local" mode)
    LANCEDB_LOCAL_PATH: str = "./data/lancedb_store"
    # Local cache directory for Remote S3 LanceDB (to reduce latency)
    # Using secure temp dir logic via tempfile in post_init or dynamic property is harder in pydantic settings
    # So we default to a safe value or rely on environment overrides.
    LANCEDB_REMOTE_CACHE_DIR: str = f"{tempfile.gettempdir()}/lancedb_cache"

    # --- LLM Selection ---
    LLM_PROVIDER: Literal["gemini", "openai"] = "gemini"

    # --- LLM (Gemini) ---
    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_API_KEY_ALT: SecretStr | None = None
    GEMINI_SEARCH_ENABLED: bool = True
    MODEL_GEMINI_CHAT: str = "gemini-3-flash-preview"
    MODEL_GEMINI_EMBEDDING: str = "gemini-embedding-001"

    # --- LLM (OpenAI Compatible Mode) ---
    # This mode is default to a hybrid strategy: OpenRouter (Chat) + SiliconFlow (Embedding)

    # 1. OpenRouter Configuration (Summaries & Reports)
    OPENROUTER_API_KEY: SecretStr | None = None
    OPENROUTER_BASE_URL: HttpUrl = "https://openrouter.ai/api/v1/"  # type: ignore[assignment]

    # Specific Models for OpenRouter
    MODEL_OPENROUTER_DAILY: str = "google/gemma-3-27b-it:free"
    MODEL_OPENROUTER_WEEKLY: str = "tngtech/deepseek-r1t2-chimera:free"
    MODEL_OPENROUTER_YEARLY: str = "xiaomi/mimo-v2-flash:free"
    MODEL_OPENROUTER_EMBEDDING: str = "qwen/qwen3-embedding-0.6b"

    # 2. SiliconFlow Configuration (Primary Embeddings)
    SILICONFLOW_API_KEY: SecretStr | None = None
    SILICONFLOW_BASE_URL: HttpUrl = "https://api.siliconflow.cn/v1/"  # type: ignore[assignment]
    MODEL_SILICONFLOW_EMBEDDING: str = "BAAI/bge-m3"

    # Fallback/Standard OpenAI
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_BASE_URL: HttpUrl = "https://api.openai.com/v1/"  # type: ignore[assignment]

    # --- Image Sources (Multiple) ---
    UNSPLASH_ACCESS_KEY: SecretStr | None = None
    PEXELS_API_KEY: SecretStr | None = None
    PIXABAY_API_KEY: SecretStr | None = None

    # --- WeChat Publisher ---
    WECHAT_PROXY_URL: str = "socks5://redate-proxy:1080"
    WECHAT_APP_ID: SecretStr
    WECHAT_APP_SECRET: SecretStr

    # Strict environment variable loading
    # Default points to the Gost sidecar in Docker Compose
    model_config = SettingsConfigDict(
        frozen=True, env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
