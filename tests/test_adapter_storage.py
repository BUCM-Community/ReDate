from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import modules to test
from src.adapter_storage import HybridStorageAdapter
from src.domain_models import DailyNewsBatch, NewsItem
from src.ports import StorageAdapter


# Mock external libraries at the highest level
@pytest.fixture(autouse=True)
def mock_external_libs(mocker):
    # 1. Mock aioboto3 Session and Client
    mock_s3_client = AsyncMock()
    mock_session = MagicMock()
    # Mock the async context manager entry point: async with self._s3_client() as s3:
    mock_session.client.return_value.__aenter__.return_value = mock_s3_client
    mocker.patch("src.adapter_storage.aioboto3.Session", return_value=mock_session)

    # 2. Mock lancedb connection
    mock_db = MagicMock()
    mocker.patch("src.adapter_storage.lancedb.connect", return_value=mock_db)

    # Mock lancedb functions/objects we interact with
    mock_db.table_names.return_value = []

    # Mock open_table and the search chain
    mock_table = MagicMock()
    mock_table.add = MagicMock()

    mock_search = MagicMock()
    mock_search.to_pandas.return_value = MagicMock(empty=True)
    mock_search.limit.return_value = mock_search  # for check_exists
    mock_search.where.return_value = mock_search
    mock_search.search.return_value = mock_search
    mock_table.search.return_value = mock_search
    mock_db.open_table.return_value = mock_table

    return mock_s3_client, mock_db, mock_table


# Mock settings with the minimal required data
@pytest.fixture(autouse=True)
def mock_settings(mocker):
    """Mock global settings for clean testing."""
    mock_settings_instance = MagicMock()
    mock_settings_instance.R2_BUCKET_NAME = "test-bucket"
    mock_settings_instance.R2_ENDPOINT = "http://r2.endpoint.com"
    mock_settings_instance.R2_ACCESS_KEY_ID.get_secret_value.return_value = "key_id"
    mock_settings_instance.R2_SECRET_ACCESS_KEY.get_secret_value.return_value = "secret_key"
    mocker.patch("src.adapter_storage.settings", mock_settings_instance)

    # Mock get_beijing_today for save_embedding
    mocker.patch("src.adapter_storage.get_beijing_today", return_value=date(2024, 7, 26))


@pytest.fixture
def adapter(mock_external_libs):
    """Returns an instance of HybridStorageAdapter."""
    return HybridStorageAdapter()


@pytest.fixture
def daily_batch():
    """Returns a mock DailyNewsBatch object."""
    pub_date = date(2024, 7, 25)
    return DailyNewsBatch(
        date_str=pub_date,
        source="viki-60s-tech",
        raw_json_hash="test_hash_123",
        items=[
            NewsItem(title="News 1", content="Content 1", published_at=pub_date),
            NewsItem(title="News 2", content="Content 2", published_at=pub_date),
        ],
    )


@pytest.mark.asyncio
async def test_adapter_implements_interface(adapter):
    """Test that HybridStorageAdapter fulfills the StorageAdapter Protocol."""
    assert isinstance(adapter, StorageAdapter)


def test_get_table_names(adapter):
    """Test table name sanitization helper."""
    meta, vec = adapter._get_table_names("Source-With-Special!Chars/1")
    assert meta == "meta_source_with_special_chars_1"
    assert vec == "vec_source_with_special_chars_1"


def test_initialization(mock_external_libs):
    """Test that LanceDB connection is established upon initialization."""
    _, mock_db, _ = mock_external_libs

    # Check if lancedb.connect was called with the correct S3 options
    mock_db.connect.assert_called_once()

    call_args, call_kwargs = mock_db.connect.call_args
    assert call_args[0] == "s3://test-bucket/lancedb_store"
    assert call_kwargs["storage_options"]["aws_endpoint_override"] == "http://r2.endpoint.com"


@pytest.mark.asyncio
async def test_archive_raw_success(adapter, mock_external_libs):
    """Test successful raw data archiving to R2 (S3)."""
    mock_s3_client, _, _ = mock_external_libs

    filename = "test/file.json"
    data = b"some raw json data"

    result = await adapter.archive_raw(filename, data)

    assert result is True
    mock_s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket", Key=filename, Body=data, ContentType="application/json"
    )


@pytest.mark.asyncio
async def test_check_exists_false_table_missing(adapter, mock_external_libs):
    """Test existence check returns False if the table does not exist."""
    mock_s3_client, mock_db, _ = mock_external_libs
    mock_db.table_names.return_value = ["other_table"]

    result = await adapter.check_exists("hash", "viki-60s")

    assert result is False
    mock_db.open_table.assert_not_called()


@pytest.mark.asyncio
async def test_check_exists_true(adapter, mock_external_libs, mock_table):
    """Test existence check returns True if hash is found."""
    mock_s3_client, mock_db, _ = mock_external_libs

    # Mock table exists
    mock_db.table_names.return_value = ["meta_viki_60s"]

    # Mock search result to be non-empty (i.e., hash found)
    mock_table.search.return_value.where.return_value.limit.return_value.to_pandas.return_value.empty = False

    result = await adapter.check_exists("found_hash", "viki-60s")

    assert result is True
    mock_db.open_table.assert_called_once_with("meta_viki_60s")
    mock_table.search.assert_called_once()


@pytest.mark.asyncio
async def test_save_embedding_table_creation(adapter, mock_external_libs, daily_batch):
    """Test saving embedding when tables need to be created."""
    mock_s3_client, mock_db, mock_table = mock_external_libs

    vector_data = [0.5, 0.6]
    mock_db.table_names.return_value = []  # Tables do not exist

    await adapter.save_embedding(daily_batch, vector_data)

    # Expected meta data structure
    expected_meta = [
        {
            "hash": "test_hash_123",
            "date": "2024-07-25",
            "source": "viki-60s-tech",
            "created_at": "2024-07-26",
        }
    ]
    # Expected vec data structure
    expected_vec = [
        {
            "date": "2024-07-25",
            "text": "- Content 1\n- Content 2",
            "vector": vector_data,
            "source": "viki-60s-tech",
        }
    ]

    # Check Meta table creation
    mock_db.create_table.assert_any_call("meta_viki_60s_tech", data=expected_meta)
    # Check Vector table creation
    mock_db.create_table.assert_any_call("vec_viki_60s_tech", data=expected_vec)

    # Should not call add() since tables were created
    mock_table.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_embedding_table_addition(adapter, mock_external_libs, daily_batch, mock_table):
    """Test saving embedding when tables already exist."""
    mock_s3_client, mock_db, _ = mock_external_libs

    vector_data = [0.5, 0.6]
    # Tables exist
    mock_db.table_names.return_value = ["meta_viki_60s_tech", "vec_viki_60s_tech"]

    # Mock open_table to return the mock_table which has an add method
    mock_db.open_table.return_value = mock_table

    await adapter.save_embedding(daily_batch, vector_data)

    # Check open_table calls
    mock_db.open_table.assert_any_call("meta_viki_60s_tech")
    mock_db.open_table.assert_any_call("vec_viki_60s_tech")

    # Check add calls (2 calls: one for meta, one for vec)
    assert mock_table.add.call_count == 2

    # Check if create_table was not called
    mock_db.create_table.assert_not_called()


@pytest.mark.asyncio
async def test_get_date_range_context(adapter, mock_external_libs, mock_db):
    """Test retrieval of context texts across date range and multiple tables."""
    mock_s3_client, _, _ = mock_external_libs

    start_date = date(2024, 7, 20)
    end_date = date(2024, 7, 26)

    # Mock table names for iteration
    mock_db.table_names.return_value = ["vec_table_a", "meta_table_b", "vec_table_c"]

    # Mock data for table A
    mock_df_a = MagicMock()
    mock_df_a.empty = False
    mock_df_a["text"].tolist.return_value = ["Text from A1", "Text from A2"]

    # Mock data for table C
    mock_df_c = MagicMock()
    mock_df_c.empty = False
    mock_df_c["text"].tolist.return_value = ["Text from C"]

    # Mock search chain for tables A and C
    def mock_search_chain(t_name):
        mock_tbl = MagicMock()
        mock_search = mock_tbl.search.return_value.where.return_value
        if t_name == "vec_table_a":
            mock_search.to_pandas.return_value = mock_df_a
        elif t_name == "vec_table_c":
            mock_search.to_pandas.return_value = mock_df_c
        else:
            mock_search.to_pandas.return_value = MagicMock(empty=True)
        return mock_tbl

    # Need to correctly mock open_table behavior
    # Instead of using side_effect, I'll use the general mock_table and check the call args

    # Since search chain is the same for all tables, I'll use a single mock_table
    mock_tbl_a = MagicMock()
    mock_tbl_c = MagicMock()

    # Configure open_table to return different mock tables based on table name
    def open_table_side_effect(name):
        if name == "vec_table_a":
            mock_tbl_a.search.return_value.where.return_value.to_pandas.return_value = mock_df_a
            return mock_tbl_a
        elif name == "vec_table_c":
            mock_tbl_c.search.return_value.where.return_value.to_pandas.return_value = mock_df_c
            return mock_tbl_c
        return MagicMock()

    mock_db.open_table.side_effect = open_table_side_effect

    result = await adapter.get_date_range_context(start_date, end_date)

    expected_texts = [
        "[TABLE A] Text from A1",
        "[TABLE A] Text from A2",
        "[TABLE C] Text from C",
    ]

    assert result == expected_texts

    # Check the where clause logic for one of the tables
    where_call_a = mock_tbl_a.search.return_value.where.call_args[0][0]
    assert where_call_a == "date >= '2024-07-20' AND date <= '2024-07-26'"
