import os
import pytest
import sqlite3
from database.db_manager import DBManager

@pytest.fixture(autouse=True)
def mock_env():
    """Forces MockProvider and ensures tests run isolated."""
    os.environ["USE_MOCK_PROVIDER"] = "true"

@pytest.fixture
def test_db(tmp_path):
    """Creates a temporary SQLite DB for testing."""
    db_file = tmp_path / "test_jobs.db"
    
    # Write schema to the same folder so DBManager can find it if needed
    # Actually DBManager looks at its __file__ dir, so we can just instantiate it.
    db = DBManager(db_path=str(db_file))
    yield db
    # Cleanup done automatically by tmp_path
