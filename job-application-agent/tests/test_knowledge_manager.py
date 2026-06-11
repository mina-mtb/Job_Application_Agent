import os
import shutil
import pytest
from pathlib import Path
from core.knowledge_manager import KnowledgeManager

@pytest.fixture
def temp_kb_dirs(tmp_path):
    """Fixture to provide temporary directories for the KnowledgeManager."""
    db_path = tmp_path / "chroma_db"
    raw_dir = tmp_path / "raw_sources"
    processed_dir = tmp_path / "processed_sources"
    
    yield db_path, raw_dir, processed_dir

@pytest.fixture
def sample_profile_path():
    """Returns the path to the sample profile."""
    # This path is relative to the project root (where pytest runs)
    return Path("tests/fixtures/sample_profile.md")

@pytest.fixture
def km(temp_kb_dirs):
    """Provides a fresh KnowledgeManager instance."""
    db_path, raw_dir, processed_dir = temp_kb_dirs
    manager = KnowledgeManager(db_path=str(db_path), raw_dir=str(raw_dir), processed_dir=str(processed_dir))
    return manager

def test_empty_knowledge_base(km):
    """Test query on empty knowledge base."""
    results = km.query_knowledge_base("any query")
    assert len(results) == 0

def test_chunking(km):
    """Test the chunking logic."""
    text = "A" * 2500
    chunks = km.chunk_text(text, chunk_size=1000, chunk_overlap=200)
    # expected:
    # chunk 1: 0 to 1000
    # chunk 2: 800 to 1800
    # chunk 3: 1600 to 2500
    assert len(chunks) == 3
    assert len(chunks[0]) == 1000
    assert len(chunks[1]) == 1000
    assert len(chunks[2]) == 900

def test_add_markdown_source(km, sample_profile_path):
    """Test adding a markdown source."""
    success = km.add_source(str(sample_profile_path))
    assert success[0] is True
    
    # Verify file was copied
    processed_files = list(Path(km.processed_dir).glob("*.md"))
    assert len(processed_files) == 1
    assert processed_files[0].name == sample_profile_path.name
    
    # Verify collection has items
    assert km.collection.count() > 0

def test_duplicate_source_handling(km, sample_profile_path):
    """Test handling of duplicate sources."""
    # First add should succeed
    success1 = km.add_source(str(sample_profile_path))
    assert success1[0] is True
    
    initial_count = km.collection.count()
    
    # Second add should fail and not duplicate chunks
    success2 = km.add_source(str(sample_profile_path))
    assert success2[0] is False
    assert km.collection.count() == initial_count

def test_retrieve_relevant_chunk(km, sample_profile_path):
    """Test retrieving relevant chunk."""
    # Add the source
    km.add_source(str(sample_profile_path))
    
    # Query 1: Cloud and Python
    results = km.query_knowledge_base("Python and cloud experience", top_k=2)
    assert len(results) > 0
    text = results[0]['text'].lower()
    assert "python" in text or "cloud" in text
    
    # Query 2: Healthcare sales
    results2 = km.query_knowledge_base("healthcare sales experience", top_k=1)
    assert len(results2) > 0
    text2 = results2[0]['text'].lower()
    assert "healthcare" in text2 and "sales" in text2
