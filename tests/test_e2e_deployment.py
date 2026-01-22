"""
tests/test_e2e_deployment.py
End-to-End deployment tests using Docker.
Focus: Security (non-root), entrypoint functionality, and safe resource handling.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

# Config
IMAGE_NAME = "redate-test-e2e"
DOCKERFILE = Path("Dockerfile")
# Windows 下 subprocess.run 如果找不到文件会直接抛出 FileNotFoundError
DOCKER_AVAILABLE = shutil.which("docker") is not None


@pytest.fixture(scope="module")
def docker_image():
    """
    Builds the docker image once. Skips if Docker not available.
    """
    if not DOCKER_AVAILABLE:
        pytest.skip("Docker executable not found in PATH")
    if not DOCKERFILE.exists():
        pytest.skip("Dockerfile missing")

    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker daemon is not running or not accessible")

    # Build
    subprocess.run(
        ["docker", "build", "-t", IMAGE_NAME, "."], check=True, capture_output=True
    )

    yield IMAGE_NAME

    # Cleanup
    subprocess.run(["docker", "rmi", "-f", IMAGE_NAME], capture_output=True)


@pytest.mark.e2e
def test_container_help_command(docker_image):
    """
    Smoke test: Ensure the container entrypoint correctly exposes the CLI help.
    """
    cmd = [
        "docker",
        "run",
        "--rm",
        docker_image,
        "python",
        "-m",
        "redate.main",
        "--help",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0
    assert "ReDate News Automation CLI" in result.stdout


@pytest.mark.e2e
def test_container_safe_crash_missing_env(docker_image):
    """
    Security/Stability: Container should exit gracefully (code 1) when env vars are missing,
    rather than hanging or crashing with code 137 (OOM) or similar.
    """
    # Running 'daily' without passing -e ENVS
    cmd = [
        "docker",
        "run",
        "--rm",
        docker_image,
        "python",
        "-m",
        "redate.main",
        "daily",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Typer/Pydantic validation error should exit with 1
    assert result.returncode == 1
    # Should see pydantic validation errors
    assert (
        "validation error" in result.stderr.lower()
        or "validation error" in result.stdout.lower()
    )
