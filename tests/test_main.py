from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

# Import app to test
from src.main import app, bootstrap
from src.service_news import NewsService

runner = CliRunner()


@pytest.fixture
def mock_news_service(mocker):
    """Mocks the NewsService and run_daily/weekly/yearly_workflow methods."""
    mock_service = MagicMock(spec=NewsService)

    # Patch all async methods as AsyncMock
    mock_service.run_daily_workflow = AsyncMock()
    mock_service.run_weekly_workflow = AsyncMock()
    mock_service.run_yearly_workflow = AsyncMock()
    mock_service.upload_weekly_images = AsyncMock()

    # Patch the bootstrap function to return our mock service
    mocker.patch("src.main.bootstrap", return_value=mock_service)

    return mock_service


@pytest.fixture(autouse=True)
def mock_asyncio_run(mocker):
    """Mock asyncio.run to execute the mocked async functions."""

    # When asyncio.run is called in the CLI, we execute the first positional arg
    def run_mock(coro, *args, **kwargs):
        # We assume the coroutine is the result of an async method call
        # e.g., asyncio.run(service.run_daily_workflow(...))
        if isinstance(coro, MagicMock) and hasattr(coro, "await_count"):
            # Manually simulate the await of the AsyncMock
            coro.await_count += 1
            return coro()
        return MagicMock()

    mock_run = mocker.patch("src.main.asyncio.run", side_effect=run_mock)

    # We must also mock the internal coroutine's side_effect propagation
    # The default AsyncMock behavior is sufficient for the success case.

    return mock_run


def test_bootstrap_wiring():
    """Test that bootstrap correctly wires all adapters."""
    # We need to import the actual classes for the patch context to work
    from src.adapter_gemini import GeminiAdapter
    from src.adapter_image import HybridImageAdapter
    from src.adapter_storage import HybridStorageAdapter
    from src.adapter_viki import VikiNewsAdapter
    from src.adapter_wechat import WeChatAdapter

    with (
        patch.object(VikiNewsAdapter, "__init__", return_value=None),
        patch.object(HybridStorageAdapter, "__init__", return_value=None),
        patch.object(GeminiAdapter, "__init__", return_value=None),
        patch.object(WeChatAdapter, "__init__", return_value=None),
        patch.object(HybridImageAdapter, "__init__", return_value=None),
    ):
        service = bootstrap()

        # Check that all adapters are initialized
        VikiNewsAdapter.__init__.assert_called_once()
        HybridStorageAdapter.__init__.assert_called_once()
        GeminiAdapter.__init__.assert_called_once()
        WeChatAdapter.__init__.assert_called_once()
        HybridImageAdapter.__init__.assert_called_once()

        assert isinstance(service, NewsService)


@pytest.mark.parametrize(
    "target_date_str, expected_date", [("2024-01-15", date(2024, 1, 15)), (None, date(2024, 7, 26))]
)
def test_daily_command_success(mock_news_service, mocker, target_date_str, expected_date):
    """Test the daily command execution flow."""
    # Mock get_beijing_today for the case when target_date is None
    mocker.patch("src.main.get_beijing_today", return_value=date(2024, 7, 26))

    args = ["daily", "--category", "tech"]
    if target_date_str:
        args.extend(["--target-date", target_date_str])

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    mock_news_service.run_daily_workflow.assert_called_once()

    # Check if the date is passed correctly (either parsed or default today)
    call_date, call_category = mock_news_service.run_daily_workflow.call_args[0]
    assert call_date == expected_date
    assert call_category == "tech"


def test_daily_command_failure(mock_news_service, mocker, mock_asyncio_run):
    """Test the daily command handles exceptions and exits with error code."""
    # Mock the underlying service method to raise an exception
    # Need to mock the AsyncMock's side effect correctly
    mock_news_service.run_daily_workflow.side_effect = Exception("Service failure")

    mock_logger = mocker.patch("src.main.logger.critical")

    result = runner.invoke(app, ["daily"])

    assert result.exit_code == 1
    mock_logger.assert_called_once_with("daily_crash", error="Service failure")


def test_weekly_command_success(mock_news_service):
    """Test the weekly command execution flow."""
    result = runner.invoke(app, ["weekly"])

    assert result.exit_code == 0
    mock_news_service.run_weekly_workflow.assert_called_once()
    mock_news_service.upload_weekly_images.assert_called_once_with(count=3)


def test_yearly_command_success(mock_news_service):
    """Test the yearly command execution flow."""
    result = runner.invoke(app, ["yearly"])

    assert result.exit_code == 0
    mock_news_service.run_yearly_workflow.assert_called_once()


def test_main_entry_point_calls_app(mocker):
    """Test that the main block calls the typer app (coverage check)."""
    mock_app = mocker.patch("src.main.app")
    mocker.patch("src.main.__name__", "__main__")

    # Execute the file's content (or just the main block logic)
    # We can mock the logger to ensure no crash is logged
    mocker.patch("src.main.logger")

    with patch.multiple("src.main", app=mock_app, __name__="__main__"):
        pass  # Re-importing to trigger __main__ block

    mock_app.assert_called_once()
