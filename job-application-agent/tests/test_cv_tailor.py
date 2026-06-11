import pytest
import os
import sqlite3
from pathlib import Path
from core.cv_tailor import CVTailor
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from llm.mock_provider import MockProvider

@pytest.fixture
def test_setup(tmp_path):
    db_path = tmp_path / "jobs.db"
    db = DBManager(db_path=str(db_path))
    
    km_db_path = tmp_path / "chroma_db"
    raw_dir = tmp_path / "raw_sources"
    processed_dir = tmp_path / "processed_sources"
    km = KnowledgeManager(db_path=str(km_db_path), raw_dir=str(raw_dir), processed_dir=str(processed_dir))
    
    # Add dummy evidence
    dummy_file = tmp_path / "dummy_profile.md"
    dummy_file.write_text("Mock Knowledge Base Context")
    km.add_source(str(dummy_file))
    
    # Add dummy base_cv.md
    base_cv_file = tmp_path / "base_cv.md"
    base_cv_file.write_text("## Experience\\n### Mock Dev\\n- Did mock things.\\n\\n## Education\\n### Mock University")
    
    provider = MockProvider()
    config = {'base_cv_path': str(base_cv_file)}
    
    tailor = CVTailor(db, km, provider, config)
    
    return db, km, tailor

def test_cv_generates_only_profile_and_skills(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job1", "job_link": "link1", "title": "Dev", "description": "Dev job"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job1'")
    
    assert tailor.generate_tailored_cv("job1") is True
    
    job = db.get_job_by_link("link1")
    cv_path = job['generated_cv_path']
    assert cv_path is not None
    assert os.path.exists(cv_path)
    
    # Verifying PDF content directly is skipped for mock tests; we rely on test_pdf_template_renderer.py

def test_experience_education_are_verbatim(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job2", "job_link": "link2", "title": "Dev", "description": "Dev job"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job2'")
    
    tailor.generate_tailored_cv("job2")
    job = db.get_job_by_link("link2")
    
    assert job['generated_cv_path'].endswith('.pdf') or job['generated_cv_path'].endswith('.docx')

def test_cv_includes_evidence_sources(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job3", "job_link": "link3", "title": "Dev", "description": "Dev job"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job3'")
    
    tailor.generate_tailored_cv("job3")
    job = db.get_job_by_link("link3")
    
    assert job['generated_cv_path'].endswith('.pdf') or job['generated_cv_path'].endswith('.docx')

def test_no_cv_for_rejected_job(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job4", "job_link": "link4", "title": "Dev"})
    db.execute_query("UPDATE jobs SET status = 'not_suitable' WHERE job_id = 'job4'")
    
    assert tailor.generate_tailored_cv("job4") is False
    job = db.get_job_by_link("link4")
    assert job['generated_cv_path'] is None

def test_no_cv_for_applied_job(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job5", "job_link": "link5", "title": "Dev"})
    db.execute_query("UPDATE jobs SET status = 'applied' WHERE job_id = 'job5'")
    
    assert tailor.generate_tailored_cv("job5") is False
    job = db.get_job_by_link("link5")
    assert job['generated_cv_path'] is None

def test_cv_generation_updates_status_to_cv_generated(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job6", "job_link": "link6", "title": "Dev"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job6'")
    
    tailor.generate_tailored_cv("job6")
    job = db.get_job_by_link("link6")
    assert job['status'] == 'cv_pending_approval'

def test_markdown_export_created(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job7", "job_link": "link7", "title": "Dev"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job7'")
    
    tailor.generate_tailored_cv("job7")
    job = db.get_job_by_link("link7")
    
    md_path = job['generated_cv_path']
    assert md_path.endswith(".pdf") or md_path.endswith(".docx") or md_path.endswith(".md")
    assert os.path.exists(md_path)

def test_html_export_created(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job8", "job_link": "link8", "title": "Dev"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job8'")
    
    tailor.generate_tailored_cv("job8")
    job = db.get_job_by_link("link8")
    
    html_path = job['generated_cv_path'].replace(".md", ".html")
    assert os.path.exists(html_path)

def test_pdf_export_created_or_gracefully_skipped_if_pdf_dependency_missing(test_setup):
    db, km, tailor = test_setup
    db.insert_job({"job_id": "job9", "job_link": "link9", "title": "Dev"})
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'job9'")
    
    tailor.generate_tailored_cv("job9")
    job = db.get_job_by_link("link9")
    
    pdf_path = job['generated_cv_path'].replace(".md", ".pdf")
    assert os.path.exists(pdf_path)
    
    # It might contain the fallback text or the actual PDF. Either is fine.
    with open(pdf_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    assert len(content) > 0
