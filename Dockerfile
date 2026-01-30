# syntax=docker/dockerfile:1
# ==============================================================================
# Stage 1: Builder - Dependency Resolution & Compilation
# ==============================================================================
# 使用pixi官方基础镜像进行构建
FROM ghcr.io/prefix-dev/pixi:0.63.2-bookworm-slim AS builder

# 设置工作目录
WORKDIR /app

# 1. 复制依赖描述文件 (利用 Docker Layer Cache)
COPY pixi.toml pixi.lock pyproject.toml ./

# 2. 安装生产环境依赖
# -e prod: 指定安装 [environments] 中的 prod 环境
# --locked: 严格遵循 pixi.lock 版本
# --frozen: 不允许更新 lock 文件
# 结果将生成在 /app/.pixi/envs/prod
RUN pixi install -e prod --locked --frozen

# ==============================================================================
# Stage 2: Runtime - Production Environment
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

# 元数据与标签 (OCI Standard)
LABEL org.opencontainers.image.source="https://github.com/BUCM-Community/ReDate"
LABEL org.opencontainers.image.description="ReDate News Automation (Production)"

# 1. Security: 创建专用低权限用户
# 使用固定 UID/GID 提高安全性
RUN groupadd -g 10001 redate && \
    useradd -u 10001 -g redate -s /bin/false -m redate

# 2. System: 仅安装运行时必要的系统库
# curl 用于健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 3. Artifacts: 从 Builder 阶段复制虚拟环境
# 注意：Pixi 生成的环境是可重定位的，或者我们直接复制并修正 PATH
COPY --from=builder /app/.pixi/envs/prod /app/.venv

# 4. Source: 复制业务代码
WORKDIR /app
COPY src/redate ./redate

# 5. Env: 配置环境变量以使用虚拟环境
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_FORMAT=json

# 6. Permissions: 收敛权限
# 使用 Read-Only Root FS，仅允许特定目录写入
RUN chown -R redate:redate /app

# 7. Switch User
USER redate

# 8. 入口点
# 默认执行 help，具体指令由 docker-compose CMD 覆盖
ENTRYPOINT ["python", "-m", "redate.main"]
CMD ["--help"]