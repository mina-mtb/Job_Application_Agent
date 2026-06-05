import os
import json
import pytest
from datetime import date
from unittest.mock import patch

from agents.job_cleaner import clean_jobs
from agents.tracker_updater import update_tracker, save_tracker
from agents.cv_tailor import run as cv_run

@pytest.fixture
def config():
    return {
        "rejection_filters": {
            "max_experience_years": 7,
            "unpaid": True,
            "irrelevant_keywords": ["native swedish only"],
            "required_experience_flags": ["8+ years", "10+ years"]
        },
        "paths": {
            "scored_jobs": "data/scored/",
            "base_cv": "profile/base_cv.md",
            "tailored_cvs": "cvs/tailored/",
            "tracker": "outputs/tracker.csv"
        }
    }

def test_duplicate_jobs(config):
    jobs = [
        {"title": "Dev", "company": "A", "description": "backend c#", "location": "Gothenburg", "type": "Hybrid", "compensation": "paid"},
        {"title": "Dev", "company": "A", "description": "backend c#", "location": "Gothenburg", "type": "Hybrid", "compensation": "paid"}
    ]
    cleaned, rejected = clean_jobs(jobs, config)
    assert len(cleaned) == 1
    assert len(rejected) == 1
    assert "duplicate" in rejected[0]["clean_rejection_reason"].lower()

def test_applied_job_skipped(tmp_path):
    tracker_path = tmp_path / "tracker.csv"
    existing = {
        "job_1": {"job_id": "job_1", "status": "Applied", "score": "90"}
    }
    save_tracker(str(tracker_path), existing)
    
    scored_jobs = [
        {"id": "job_1", "title": "Dev", "company": "A", "match_score": 95, "priority": "excellent"}
    ]
    stats = update_tracker(scored_jobs, str(tracker_path))
    assert stats["skipped_protected"] == 1
    assert stats["added"] == 0
    assert stats["updated_score"] == 0

def test_gothenburg_hybrid_job(config):
    jobs = [
        {"title": "Dev", "company": "A", "description": "backend c#", "location": "Gothenburg", "type": "Hybrid", "compensation": "paid"}
    ]
    cleaned, rejected = clean_jobs(jobs, config)
    assert len(cleaned) == 1
    assert len(rejected) == 0

def test_senior_8_plus_years_job(config):
    jobs = [
        {"title": "Senior Dev", "company": "A", "description": "backend c# Requires 8+ years of experience", "location": "Gothenburg", "type": "Hybrid", "compensation": "paid"}
    ]
    cleaned, rejected = clean_jobs(jobs, config)
    assert len(cleaned) == 0
    assert len(rejected) == 1
    assert "8+ years" in rejected[0]["clean_rejection_reason"]

def test_unpaid_internship(config):
    jobs = [
        {"title": "Dev Intern", "company": "A", "description": "backend c#", "location": "Gothenburg", "type": "Hybrid", "compensation": "unpaid"}
    ]
    cleaned, rejected = clean_jobs(jobs, config)
    assert len(cleaned) == 0
    assert len(rejected) == 1
    assert "unpaid" in rejected[0]["clean_rejection_reason"].lower()

@patch("agents.cv_tailor.call_claude")
def test_high_match_job_cv_generated(mock_claude, tmp_path, config):
    # Mock claude to avoid API call
    mock_claude.return_value = "[\"mock_suggestion\"]" # First call is CV, but optimizer returns JSON. We can just return a string that won't break json load if we want, or handle Exception.
    # Actually, first call is CV (returns markdown), second is optimizer (returns JSON).
    mock_claude.side_effect = ["Mocked CV content", '["mock_keyword"]']

    # Setup directories
    scored_dir = tmp_path / "data/scored"
    scored_dir.mkdir(parents=True)
    today = str(date.today())
    scored_file = scored_dir / f"scored_jobs_{today}.json"
    
    # 6. High match job (score >= 85), 7. Low match job (score < 60)
    jobs = [
        {"id": "job_high", "match_score": 90, "title": "Dev", "company": "A"},
        {"id": "job_low", "match_score": 50, "title": "Dev", "company": "B"}
    ]
    scored_file.write_text(json.dumps(jobs), encoding="utf-8")
    
    base_cv = tmp_path / "profile/base_cv.md"
    base_cv.parent.mkdir(parents=True)
    base_cv.write_text("Base CV", encoding="utf-8")
    
    tracker_file = tmp_path / "outputs/tracker.csv"
    tracker_file.parent.mkdir(parents=True)
    tracker_file.write_text("job_id,title,status,cv_generated,score,notes\njob_high,Dev,new,no,90,\njob_low,Dev,new,no,50,\n", encoding="utf-8")
    
    config["paths"]["scored_jobs"] = str(scored_dir)
    config["paths"]["base_cv"] = str(base_cv)
    config["paths"]["tailored_cvs"] = str(tmp_path / "cvs/tailored")
    config["paths"]["tracker"] = str(tracker_file)
    
    import yaml
    config_file = tmp_path / "config.yaml"
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f)
        
    summary = cv_run(str(config_file), min_score=85)
    
    assert summary["total_qualifying"] == 1
    assert summary["generated"] == 1

def test_low_match_job_rejected():
    # Tested as part of the test_high_match_job_cv_generated (only 1 job qualified)
    pass

def test_native_swedish_only(config):
    jobs = [
        {"title": "Dev", "company": "A", "description": "backend c# native Swedish only", "location": "Gothenburg", "type": "Hybrid", "compensation": "paid"}
    ]
    cleaned, rejected = clean_jobs(jobs, config)
    assert len(cleaned) == 0
    assert len(rejected) == 1
    assert "native swedish only" in rejected[0]["clean_rejection_reason"].lower()
