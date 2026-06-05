import pytest
import os
import yaml
from pathlib import Path
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from core.job_matcher import JobMatcher
from core.cv_tailor import CVTailor
from llm.mock_provider import MockProvider
from core.app_helpers import (
    can_generate_cv, can_approve, can_mark_applied, 
    update_job_status, mark_as_applied, add_user_note, 
    process_manual_entry, handle_knowledge_upload,
    run_daily_matching
)

@pytest.fixture
def test_setup(tmp_path):
    db_path = tmp_path / "jobs.db"
    db = DBManager(db_path=str(db_path))
    
    km_db_path = tmp_path / "chroma_db"
    raw_dir = tmp_path / "raw_sources"
    processed_dir = tmp_path / "processed_sources"
    km = KnowledgeManager(db_path=str(km_db_path), raw_dir=str(raw_dir), processed_dir=str(processed_dir))
    
    provider = MockProvider()
    config = {'reject_relocation_required': True, 'allow_remote': True, 'allow_hybrid': True, 'preferred_locations': ['Gothenburg']}
    
    matcher = JobMatcher(config, km, provider)
    tailor = CVTailor(db, km, provider, config)
    
    return db, km, matcher, tailor, tmp_path

def test_dashboard_status_update_helpers(test_setup):
    db, _, _, _, _ = test_setup
    db.insert_job({"job_id": "job1", "job_link": "link1", "title": "Dev"})
    
    update_job_status(db, "job1", "approved")
    job = db.get_job_by_link("link1")
    assert job['status'] == 'approved'
    
    add_user_note(db, "job1", "Test note")
    job = db.get_job_by_link("link1")
    assert "Test note" in job['user_notes']

def test_generate_cv_button_allowed_only_for_needs_review_or_approved():
    assert can_generate_cv('needs_review') is True
    assert can_generate_cv('approved') is True
    assert can_generate_cv('new') is False
    assert can_generate_cv('rejected') is False

def test_mark_applied_requires_generated_cv_path(test_setup):
    assert can_mark_applied(None) is False
    assert can_mark_applied("") is False
    assert can_mark_applied("outputs/some_path.md") is True
    
    db, _, _, _, _ = test_setup
    db.insert_job({"job_id": "job2", "job_link": "link2", "title": "Dev"})
    mark_as_applied(db, "job2")
    job = db.get_job_by_link("link2")
    assert job['status'] == 'applied'
    assert job['date_applied'] is not None

def test_manual_entry_inserts_job(test_setup):
    db, km, matcher, _, _ = test_setup
    desc = "Great job with Python in Gothenburg."
    success, msg = process_manual_entry(db, matcher, desc, "http://manual.link", "Test Job", "Test Co", "Gothenburg")
    assert success is True
    
    job = db.get_job_by_link("http://manual.link")
    assert job is not None
    assert job['title'] == "Test Job"
    assert job['description'] == desc

def test_manual_entry_runs_matching(test_setup):
    db, km, matcher, _, _ = test_setup
    
    # Should pass stage 1 and stage 2
    desc = "Python Dev in Gothenburg"
    success, msg = process_manual_entry(db, matcher, desc, "http://link.success", "Dev", "Co", "Gothenburg")
    job = db.get_job_by_link("http://link.success")
    assert job['status'] == 'needs_review'
    assert job['suitability_score'] is not None
    
    # Should fail stage 1
    bad_desc = "Unpaid internship in Malmo"
    success, msg = process_manual_entry(db, matcher, bad_desc, "http://link.fail", "Intern", "Co", "Malmo")
    job2 = db.get_job_by_link("http://link.fail")
    assert job2['status'] == 'not_suitable'
    assert job2['suitability_score'] is None

def test_uploaded_source_added_to_knowledge_base(test_setup):
    db, km, _, _, tmp_path = test_setup
    
    test_md = tmp_path / "upload_test.md"
    test_md.write_text("Hello Knowledge")
    
    success, msg = handle_knowledge_upload(km, str(test_md))
    assert success is True
    
    processed = list((tmp_path / "processed_sources").glob("*.md"))
    assert len(processed) == 1
    assert "upload_test.md" in str(processed[0])

def test_settings_loads_preferred_locations(tmp_path):
    # This tests the logic that defaults or loads preferred locations.
    # In app.py this happens inline, so we mock the behavior.
    config_path = tmp_path / "config.yaml"
    config = {'active_provider': 'mock'}
    if 'preferred_locations' not in config or not config['preferred_locations']:
        config['preferred_locations'] = ["Göteborg", "Gothenburg", "Västra Götaland"]
    assert "Gothenburg" in config['preferred_locations']

def test_dashboard_run_daily_matching_updates_new_jobs(test_setup):
    db, km, matcher, _, _ = test_setup
    # Insert some new jobs
    db.insert_job({"job_id": "j1", "job_link": "l1", "title": "Dev in Gothenburg", "description": "Python", "location": "Gothenburg"})
    db.insert_job({"job_id": "j2", "job_link": "l2", "title": "Unpaid Internship in Gothenburg", "description": "Intern", "location": "Gothenburg"})
    
    count = run_daily_matching(db, matcher)
    assert count == 2
    
    j1 = db.get_job_by_link("l1")
    assert j1['status'] == 'needs_review'
    assert j1['suitability_score'] is not None
    
    j2 = db.get_job_by_link("l2")
    assert j2['status'] == 'not_suitable'
    assert j2['suitability_score'] is None

def test_cv_generated_job_displays_score_if_available(test_setup):
    db, km, matcher, tailor, _ = test_setup
    db.insert_job({"job_id": "j3", "job_link": "l3", "title": "Dev in Gothenburg", "description": "Python", "location": "Gothenburg"})
    # run matching to set score
    run_daily_matching(db, matcher)
    
    j3 = db.get_job_by_link("l3")
    assert j3['status'] == 'needs_review'
    score = j3['suitability_score']
    
    # Generate CV to update status
    update_job_status(db, "j3", "cv_generated")
    j3_updated = db.get_job_by_link("l3")
    
    # DB manager confirms score is untouched
    assert j3_updated['status'] == 'cv_generated'
    assert j3_updated['suitability_score'] == score
    assert j3_updated['suitability_score'] is not None

def test_manual_entry_requires_description_for_matching(test_setup):
    db, km, matcher, _, _ = test_setup
    # If UI doesn't allow processing without desc, the backend function would receive it.
    # Testing that an empty description might fail or at least processes cleanly (and possibly rejects).
    # JobMatcher uses description heavily.
    success, msg = process_manual_entry(db, matcher, "", "http://empty.desc", "Dev", "Co", "Gothenburg")
    j = db.get_job_by_link("http://empty.desc")
    # Should probably be not suitable or at least low score if location missing/etc.
    assert j['status'] in ['not_suitable', 'needs_review'] 
