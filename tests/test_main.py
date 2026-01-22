"""
tests/test_main.py
Unit tests for CLI Entrypoint.
Focus: Argument parsing and wiring.
"""

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from redate.main import app

runner = CliRunner()


@patch("redate.main.bootstrap")
def test_daily_command(mock_bootstrap):
    """Test 'daily' command invokes run_daily_workflow."""
    # Setup Service Mock
    mock_service = AsyncMock()
    mock_bootstrap.return_value = mock_service

    # Mock asyncio.run to just await the mock (or simply ignore if mocked)
    with patch("redate.main.asyncio.run", side_effect=lambda x: None):
        result = runner.invoke(app, ["daily", "--category", "ai-news"])

    assert result.exit_code == 0
    mock_bootstrap.assert_called_once()
    # Verify arguments passed to service
    # call_args[0][1] should be 'ai-news'
    call_args = mock_service.run_daily_workflow.call_args
    assert call_args[0][1] == "ai-news"
