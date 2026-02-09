# syntax=docker/dockerfile:1
# ==============================================================================
# Stage 1: Builder - Hermetic Environment Construction via Pixi
# ==============================================================================
# 使用pixi官方基础镜像进行构建
FROM ghcr.io/prefix-dev/pixi:0.63.2-bookworm-slim AS builder

# 设置工作目录
WORKDIR /app

# 1. Copy Manifests (Maximize Layer Caching)
COPY pixi.toml pixi.lock pyproject.toml ./

# 2. Install Dependencies (Production Environment Only)
# -e prod: 指定安装 [environments] 中的 prod 环境
# --locked: 严格遵循 pixi.lock 版本
# --frozen: 不允许更新 lock 文件
# 结果将生成在 /app/.pixi/envs/prod
RUN pixi install -e prod --locked --frozen

# ==============================================================================
# Stage 2: Runtime - Production Environment (Secure, Minimal)
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

# 元数据与标签 (OCI Standard)
LABEL org.opencontainers.image.title="ReDate"
LABEL org.opencontainers.image.description="Ops-Isolated News Aggregation Platform"
LABEL org.opencontainers.image.source="https://github.com/BUCM-Community/ReDate"
LABEL org.opencontainers.image.vendor="BUCM-Community"
LABEL io.podman.rootless="true"

# 1. Security: Create a non-root user with a static UID/GID (10001)
RUN groupadd -g 10001 redate && \
    useradd -u 10001 -g redate -s /bin/false -m redate

# 2. System: Install minimal runtime deps
# ca-certificates is critical for HTTPS (R2/API calls)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. Artifacts: Copy the virtual environment from builder
COPY --from=builder --chown=redate:redate /app/.pixi/envs/prod /app/.venv

# 4. Source: Copy application code
COPY --chown=redate:redate src/redate /app/redate

# 5. Storage Hygiene: Pre-create strict mount points
#    We will run with Read-Only Root, so these MUST be volumes.
RUN mkdir -p /app/data && chown -R redate:redate /app/data
VOLUME ["/app/data", "/tmp"]

# 6. Env: 配置环境变量以使用虚拟环境
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TMPDIR="/tmp" \
    LOG_FORMAT=json

# 7. Switch User
USER redate

# Default execution command (can be overridden by Compose/K8s)
ENTRYPOINT ["python", "-m", "redate.main"]
CMD ["--help"]