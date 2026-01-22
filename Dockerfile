# ==============================================================================
# Stage 1: Builder - 编译与依赖解析
# ==============================================================================
FROM python:3.12-slim-bookworm AS builder

# 1. 环境准备
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. 安装 uv (高性能包管理器)
# 使用官方镜像复制二进制文件，比 pip 安装更安全快速
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /build

# 3. 依赖安装
# 复制 pyproject.toml
COPY pyproject.toml .
# 创建虚拟环境并安装依赖
# --no-dev: 不安装开发依赖 (ruff, pytest 等)
# --compile: 编译字节码以加快启动速度
ENV VIRTUAL_ENV=/build/.venv
RUN uv venv $VIRTUAL_ENV && \
    uv pip install -r pyproject.toml --no-cache --compile

# ==============================================================================
# Stage 2: Runtime - 生产环境 (Distroless 理念)
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

# 1. 元数据与标签 (OCI Standard)
LABEL org.opencontainers.image.source="https://github.com/BUCM-Community/ReDate"
LABEL org.opencontainers.image.description="ReDate News Automation"

# 2. 安全基线：创建非 Root 用户
# 使用固定 UID/GID 提高安全性
RUN groupadd -g 10001 redate && \
    useradd -u 10001 -g redate -s /bin/false -m redate

# 3. 安装运行时必需的系统库 (如需)
# 这里的 curl 用于健康检查，gost 用于 Pod 内部可能的本地代理转发(可选)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4. 复制虚拟环境
COPY --from=builder /build/.venv /app/.venv

# 5. 复制源代码
WORKDIR /app
COPY src/redate/ ./redate/

# 6. 配置环境变量
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # 配置日志为 JSON 格式 (配合 structlog)
    LOG_FORMAT=json

# 7. 权限收敛
# 更改所有权给 redate 用户
RUN chown -R redate:redate /app

# 8. 切换用户
USER redate

# 9. 入口点
# 容器默认行为，强制要求参数
ENTRYPOINT ["python", "redate/main.py"]