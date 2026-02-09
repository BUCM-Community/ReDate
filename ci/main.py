"""
ci/main.py

ReDate CI/CD Pipeline (Dagger + Pixi)
Usage:
  - Build/Test: pixi run ci-build
  - Execute Logic: EXECUTION_MODE=workload JOB_TYPE=daily pixi run ci-build
"""

import json
import os
from pathlib import Path
import sys

import anyio
import dagger

from redate.utils_telemetry import logger

# Configuration Constants
PIXI_IMAGE = "ghcr.io/prefix-dev/pixi:0.63.2-bookworm-slim"
TRIVY_IMAGE = "aquasec/trivy:latest"
NODE_IMAGE = "node:24-bookworm-slim"  # Node LTS for Wrangler
GOST_IMAGE = "gogost/gost:3.2"
PROD_IMAGE_TAG = "ghcr.io/bucm-community/redate:latest"
# Matrix Configuration defined in pixi.toml
PYTHON_MATRIX = ["test-311", "test-312", "test-313", "test-314"]


def get_execution_context():
    """
    Parses GitHub Event payload to determine Execution Mode.

    Returns: (mode, job_type, target_date)
    """
    # 1. Defaults (Local Dev or Basic Push)
    mode = "pipeline"
    job_type = "daily"
    target_date = ""

    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    event_path = Path(os.getenv("GITHUB_EVENT_PATH", ""))

    # 2. Parse GitHub Event JSON if available
    if event_path and event_path.exists():
        with Path.open(event_path) as f:
            payload = json.load(f)

        # Case A: Schedule (Cron)
        if event_name == "schedule":
            mode = "workload"
            cron = payload.get("schedule", "")
            # Mapping Cron to Logic
            if cron == "30 8 * * *":
                job_type = "daily"
            elif cron == "0 1 * * 1":
                job_type = "weekly"
            elif cron == "0 2 1 1 *":
                job_type = "yearly"
            else:
                job_type = "daily"  # Fallback
            logger.info(f"Context: Schedule Triggered ({job_type})")

        # Case B: Manual Dispatch
        elif event_name == "workflow_dispatch":
            mode = "workload"
            inputs = payload.get("inputs", {})
            job_type = inputs.get("job_type", "daily")
            target_date = inputs.get("target_date", "")
            logger.info(f"Context: Manual Dispatch ({job_type}, date={target_date})")

    # 3. Allow Local Overrides (for testing workload locally)
    # E.g., EXECUTION_MODE=workload pixi run ci-build
    if os.getenv("EXECUTION_MODE"):
        mode = os.getenv("EXECUTION_MODE")
        job_type = os.getenv("JOB_TYPE", job_type)
        target_date = os.getenv("TARGET_DATE", target_date)

    return mode, job_type, target_date


async def run_workload(
    client: dagger.Client, src: dagger.Directory, job_type: str, target_date: str
):
    """Runtime Execution Flow: Sidecar (Config File) -> Worker"""
    logger.info(f"[Workload] Initializing with Job: {job_type}...")

    # 1. Setup Network Sidecar (GOST)
    # CRITICAL: We load the REAL config file from source, ensuring consistency.
    gost_config_file = src.file("ops/config/gost-client.yaml")

    gost_service = (
        client.container()
        .from_(GOST_IMAGE)
        # Mount the config file from source
        .with_file("/etc/gost/config.yaml", gost_config_file)
        .with_exec(["-C", "/etc/gost/config.yaml"])
        .with_exposed_port(1080)
        .as_service()
    )

    # 2. Setup Worker Container
    # We use the published image to simulate "Production" exactly
    worker = (
        client.container()
        .from_(PROD_IMAGE_TAG)
        .with_service_binding("proxy-sidecar", gost_service)
        # Network Config matches prod-cloud.yml
        .with_env_variable("APP_ENV", "prod")
        .with_env_variable("ALL_PROXY", "socks5://proxy-sidecar:1080")
        .with_env_variable("WECHAT_PROXY_URL", "socks5://proxy-sidecar:1080")
    )

    # 3. Inject Secrets (Iterative)
    # These must be available in the GHA Runner Environment
    secret_keys = [
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
        "R2_ENDPOINT_URL",
        "GEMINI_API_KEY",
        "WECHAT_APP_ID",
        "WECHAT_APP_SECRET",
        "VPS_HOST",  # If needed for sidecar, though usually handled by Gost config interpolation if simpler
    ]
    for key in secret_keys:
        if val := os.getenv(key):
            worker = worker.with_secret_variable(key, client.set_secret(key, val))

    # 4. Construct Command
    cmd = ["python", "-m", "redate.main", job_type]
    if target_date:
        cmd.extend(["--date", target_date])

    logger.info(f"Executing: {' '.join(cmd)}")

    # 5. Run and Capture Logs
    try:
        result = await worker.with_exec(cmd).stdout()
        logger.info("Workload Output:")
        logger.info(result)
    except Exception as e:
        logger.error("Workload Failed. Inspecting logs...")
        raise e


async def run_pipeline(client: dagger.Client, src: dagger.Directory):
    """Standard CI/CD Flow: Lint -> Test -> Build -> Push"""
    is_ci = os.getenv("CI") == "true"
    git_ref = os.getenv("GITHUB_REF", "")
    is_main = git_ref == "refs/heads/main"

    # [STAGE 1] Static Analysis
    logger.info("[Stage 1] Static Analysis...")
    runner = (
        client.container()
        .from_(PIXI_IMAGE)
        .with_directory("/app", src)
        .with_workdir("/app")
        .with_env_variable("pixi_frozen", "true")
        .with_mounted_cache("/root/.cache/pixi", client.cache_volume("pixi-cache"))
        .with_exec(["pixi", "install", "-e", "default", "--frozen"])
    )
    await (
        runner.with_exec(["pixi", "run", "lint"])
        .with_exec(["pixi", "run", "typecheck"])
        .with_exec(["pixi", "run", "contract-check"])
        .sync()
    )
    logger.info("    Static Analysis Passed.")

    # [STAGE 2] Matrix Tests
    logger.info(f"[Stage 2] Matrix Testing {PYTHON_MATRIX}...")

    async def test_env(env):
        logger.info(f"Testing {env}...")
        await (
            client.container()
            .from_(PIXI_IMAGE)
            .with_directory("/app", src)
            .with_workdir("/app")
            .with_mounted_cache("/root/.cache/pixi", client.cache_volume("pixi-cache"))
            .with_exec(["pixi", "install", "-e", env, "--frozen"])
            .with_exec(["pixi", "run", "-e", env, "test"])
            .sync()
        )
        logger.info(f"    {env} Passed.")

    async with anyio.create_task_group() as tg:
        for env in PYTHON_MATRIX:
            tg.start_soon(test_env, env)

    # [STAGE 3] Docs (Build Only for Pull Requests, Deploy for Main)
    logger.info("[Stage 3] Docs...")
    docs_builder = (
        client.container()
        .from_(PIXI_IMAGE)
        .with_directory("/app", src)
        .with_workdir("/app")
        .with_mounted_cache("/root/.cache/pixi", client.cache_volume("pixi-cache"))
        .with_exec(["pixi", "install", "-e", "docs", "--frozen"])
        .with_exec(["pixi", "run", "-e", "docs", "docs-build"])
    )
    site_dir = docs_builder.directory("site")

    if is_ci and is_main:
        logger.info("    Deploying Docs...")
        # Secrets for Wrangler
        cf_token = client.set_secret("cf_token", os.getenv("CLOUDFLARE_API_TOKEN", ""))
        cf_account = client.set_secret("cf_account", os.getenv("CLOUDFLARE_ACCOUNT_ID", ""))

        await (
            client.container()
            .from_(NODE_IMAGE)
            .with_exec(["npm", "install", "-g", "wrangler@3"])
            .with_directory("/site", site_dir)
            .with_secret_variable("CLOUDFLARE_API_TOKEN", cf_token)
            .with_secret_variable("CLOUDFLARE_ACCOUNT_ID", cf_account)
            .with_exec(
                [
                    "wrangler",
                    "pages",
                    "deploy",
                    "/site",
                    "--project-name",
                    "redate",
                    "--branch",
                    "main",
                    "--commit-dirty=true",
                ]
            )
            .sync()
        )

    # [STAGE 4 & 5 & 6] Build, Scan, Publish
    logger.info("[Stage 4-6] Build, Scan & Publish...")
    builder = src.docker_build(dockerfile="ops/container/Dockerfile", target="builder")
    runtime = src.docker_build(dockerfile="ops/container/Dockerfile", target="runtime")

    # Trivy Scan
    await (
        client.container()
        .from_(TRIVY_IMAGE)
        .with_file("/scan.tar", builder.as_tarball())
        .with_exec(
            [
                "image",
                "--input",
                "/scan.tar",
                "--severity",
                "CRITICAL",
                "--exit-code",
                "1",
            ]
        )
        .sync()
    )

    await (
        client.container()
        .from_(TRIVY_IMAGE)
        .with_file("/scan.tar", runtime.as_tarball())
        .with_exec(
            [
                "image",
                "--input",
                "/scan.tar",
                "--severity",
                "CRITICAL",
                "--exit-code",
                "1",
            ]
        )
        .sync()
    )
    logger.info("    Image Scan Passed.")

    if is_ci and is_main:
        logger.info("    Publishing...")
        gh_token = client.set_secret("gh_token", os.getenv("GITHUB_TOKEN"))  # type: ignore[reportArgumentType]
        await runtime.with_registry_auth(
            "ghcr.io",
            os.getenv("GITHUB_ACTOR"),  # type: ignore[reportArgumentType]
            gh_token,
        ).publish(PROD_IMAGE_TAG, forced_compression=dagger.ImageLayerCompression.Zstd)
        logger.info("   App Image Published.")


async def main():
    mode, job_type, target_date = get_execution_context()

    async with dagger.Connection(dagger.Config(log_output=sys.stderr)) as client:
        # Load source excluding heavy/git files
        src = client.host().directory(".", exclude=[".git", "dist", "site", "__pycache__"])

        if mode == "workload":
            await run_workload(client, src, job_type, target_date)
        else:
            await run_pipeline(client, src)


if __name__ == "__main__":
    try:
        anyio.run(main)
    except Exception as e:
        logger.error(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)
