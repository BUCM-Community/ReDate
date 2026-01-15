"""
src/config.py
Application configuration using Pydantic Settings.
Focus: Immutable configuration, Secret management, and Type safety.
"""

from __future__ import annotations

from typing import Literal

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["settings", "Settings"]


class Settings(BaseSettings):
    # --- Infrastructure ---
    ENV: Literal["development", "production"] = "development"

    # --- Sources (Viki API) ---
    # URL structure: https://60s.viki.moe/v2/{category}?encoding=json
    # 从环境变量读取，避免因API更换而修改代码
    VIKI_API_BASE: HttpUrl

    # --- R2 Storage (S3 Compatible) ---
    R2_ACCOUNT_ID: str
    R2_ACCESS_KEY_ID: SecretStr
    R2_SECRET_ACCESS_KEY: SecretStr
    # R2 Endpoint (e.g. https://<account_id>.r2.cloudflarestorage.com)
    R2_ENDPOINT: HttpUrl
    R2_BUCKET_NAME: str

    # --- LLM (Gemini) ---
    GEMINI_API_KEY: SecretStr
    GEMINI_API_KEY_ALT: SecretStr | None = None
    MODEL_CHAT: str = "gemini-2.0-flash"
    MODEL_EMBEDDING: str = "gemini-embedding-001"

    # --- Image Sources (Multiple) ---
    UNSPLASH_ACCESS_KEY: SecretStr | None = None
    PEXELS_API_KEY: SecretStr | None = None
    PIXABAY_API_KEY: SecretStr | None = None

    # --- WeChat Publisher ---
    # Proxies are mandatory for WeChat in this architecture
    # Default points to the Gost sidecar in Docker Compose
    WECHAT_PROXY_URL: str = "socks5://redate-proxy:1080"
    WECHAT_APP_ID: SecretStr
    WECHAT_APP_SECRET: SecretStr

    # Strict environment variable loading
    model_config = SettingsConfigDict(frozen=True, env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()  # type: ignore[call-arg]
