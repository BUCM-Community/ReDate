import subprocess
from pathlib import Path

import pytest

# --- Configuration for E2E Test ---
IMAGE_NAME = "redate-test-e2e"
DOCKERFILE_PATH = Path("Dockerfile")
# The entrypoint command defined inside the Dockerfile (if no ENTRYPOINT is used, use the main file)
# Based on common Python Dockerfile practices, the command should be 'python src/main.py'
APP_ENTRYPOINT = "python"
APP_ARGS = ["src/main.py"]


@pytest.fixture(scope="module")
def build_docker_image():
    """Builds the Docker image once for all tests in this module."""
    if not DOCKERFILE_PATH.exists():
        pytest.skip(f"Dockerfile not found at {DOCKERFILE_PATH}")

    # Check for Docker daemon availability
    try:
        subprocess.run(["docker", "info"], check=True, capture_output=True, timeout=5)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("Docker daemon not running or 'docker' command not found.")

    print(f"\nBuilding Docker image: {IMAGE_NAME}")

    try:
        # Build command with no-cache to ensure fresh build
        build_command = [
            "docker",
            "build",
            "--pull",  # Always attempt to pull a newer version of the base image
            "--rm",
            "-t",
            IMAGE_NAME,
            "-f",
            str(DOCKERFILE_PATH),
            ".",
        ]

        # Execute build command
        subprocess.run(build_command, check=True, capture_output=True, text=True)
        print("Docker build successful.")
        yield IMAGE_NAME

    except subprocess.CalledProcessError as e:
        pytest.fail(f"Docker build failed. Stderr: {e.stderr}. Stdout: {e.stdout}")
    finally:
        # Clean up the image in the background
        try:
            subprocess.run(["docker", "rmi", "-f", IMAGE_NAME], capture_output=True, check=False)
        except Exception:
            pass  # Ignore cleanup failure


@pytest.mark.e2e
def test_docker_image_exists(build_docker_image):
    """Verify that the image was successfully built."""
    # build_docker_image fixture yields the image name upon success
    assert build_docker_image == IMAGE_NAME


@pytest.mark.e2e
def test_app_entrypoint_is_executable(build_docker_image):
    """
    Test the application's main entry point (CLI) runs correctly inside the container
    by asking for help, which should exit successfully.
    """
    command = ["docker", "run", "--rm", build_docker_image, APP_ENTRYPOINT, *APP_ARGS, "--help"]

    try:
        print(f"Running container command: {' '.join(command[3:])}")
        # Capture output for verification
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)

        # Check for successful exit code and expected help output
        assert result.returncode == 0
        assert "ReDate News Automation CLI" in result.stdout

    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"Container failed to run command. Exit code: {e.returncode}. Stderr: {e.stderr}. Stdout: {e.stdout}"
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Container execution timed out.")


@pytest.mark.e2e
def test_cli_mode_check_fail_gracefully(build_docker_image):
    """
    Test a specific sub-command's execution ('daily') which should fail due to missing
    environment variables (VIKI_API_BASE, GEMINI_API_KEY, etc.), but the failure
    should be a controlled application crash (typer exit code 1), not a container crash (exit code 126/137).
    """
    command = ["docker", "run", "--rm", build_docker_image, APP_ENTRYPOINT, *APP_ARGS, "daily"]

    # Execute the command, allowing exit code 1
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)

    # Expected exit code from application error is 1 (see src/main.py)
    assert result.returncode == 1

    # Check that the error output contains evidence of Pydantic/Config failure
    output = result.stderr.lower() + result.stdout.lower()

    # Check for Pydantic error related to missing required config or main crash log
    assert any(keyword in output for keyword in ["critical", "pydantic", "missing", "viki_api_base", "system_crash"])
