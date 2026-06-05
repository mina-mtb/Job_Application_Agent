import pytest
import os
import json
from unittest import mock
from pathlib import Path

from core.daily_runner import DailyRunner
from core.job_collector import JobCollector
from core.knowledge_manager import KnowledgeManager
from database.db_manager import DBManager
from llm.mock_provider import MockProvider

@pytest.fixture
def temp_db_manager(tmp_path):
    db_path = tmp_path / "jobs.db"
    return DBManager(db_path=str(db_path))

@pytest.fixture
def temp_km(tmp_path):
    db_path = tmp_path / "chroma_db"
    raw_dir = tmp_path / "raw_sources"
    processed_dir = tmp_path / "processed_sources"
    km = KnowledgeManager(db_path=str(db_path), raw_dir=str(raw_dir), processed_dir=str(processed_dir))
    dummy_file = tmp_path / "dummy.txt"
    dummy_file.write_text("Mock Candidate Context")
    km.add_source(str(dummy_file))
    return km

@pytest.fixture
def mock_config():
    return {
        'location_filtering': {
            'preferred_locations': ['Gothenburg', 'Göteborg'],
            'allow_remote': True,
            'allow_hybrid': True,
            'reject_relocation_required': True
        }
    }

@pytest.fixture
def test_setup(temp_db_manager, temp_km, mock_config):
    mock_provider = MockProvider()
    
    class MockCollector(JobCollector):
        def __init__(self, db, jobs_to_return):
            super().__init__(db)
            self.jobs_to_return = jobs_to_return
            
        def collect_jobs(self):
            for job in self.jobs_to_return:
                self.db.insert_job(job)
            return {"fetched": len(self.jobs_to_return)}

    def create_runner(jobs):
        collector = MockCollector(temp_db_manager, jobs)
        return DailyRunner(temp_db_manager, collector, temp_km, mock_provider, mock_config)

    return temp_db_manager, create_runner

def test_daily_runner_with_mock_jobs(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "1", "title": "Developer", "description": "Good job", "location": "Gothenburg", "job_link": "link1"}
    ]
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link1")
    assert job['status'] == 'needs_review'
    assert job['suitability_score'] == 85

def test_stage1_rejects_senior_role(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "2", "title": "Senior Dev", "description": "Requires 8+ years of experience", "location": "Gothenburg", "job_link": "link2"}
    ]
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link2")
    assert job['status'] == 'not_suitable'
    assert '8+ years' in job['weaknesses_or_risks'] or '7+ years' in job['weaknesses_or_risks']

def test_stage1_rejects_unpaid_internship(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "3", "title": "Intern", "description": "This is an unpaid internship.", "location": "Gothenburg", "job_link": "link3"}
    ]
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link3")
    assert job['status'] == 'not_suitable'
    assert 'Unpaid' in job['weaknesses_or_risks'] or 'unpaid' in job['weaknesses_or_risks'].lower()

def test_stage1_rejects_native_swedish_only(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "4", "title": "Dev", "description": "Native swedish only", "location": "Gothenburg", "job_link": "link4"}
    ]
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link4")
    assert job['status'] == 'not_suitable'
    assert 'swedish' in job['weaknesses_or_risks'].lower()

def test_stage1_accepts_gothenburg_hybrid(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "5", "title": "Dev", "description": "Great job", "location": "Gothenburg", "job_link": "link5"}
    ]
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link5")
    assert job['status'] == 'needs_review'

def test_stage2_uses_rag_context(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "6", "title": "Dev", "description": "RAG test", "location": "Gothenburg", "job_link": "link6"}
    ]
    runner = create_runner(jobs)
    
    with mock.patch.object(runner.matcher.llm, 'generate_completion', wraps=runner.matcher.llm.generate_completion) as spy:
        runner.run()
        assert spy.called
        call_args = spy.call_args[0][0]
        assert "Mock Candidate Context" in call_args

def test_stage2_updates_database_fields(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "7", "title": "Dev", "description": "Score test", "location": "Gothenburg", "job_link": "link7"}
    ]
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link7")
    assert job['suitability_score'] is not None
    assert job['suitability_category'] is not None
    assert job['reasons_for_match'] is not None
    assert job['status'] == 'needs_review'

def test_applied_jobs_not_reprocessed(test_setup):
    db, create_runner = test_setup
    jobs = [
        {"job_id": "8", "title": "Dev", "description": "Will be applied", "location": "Gothenburg", "job_link": "link8"}
    ]
    
    db.insert_job(jobs[0])
    db.execute_query("UPDATE jobs SET status = 'applied', suitability_score = 100 WHERE job_link = 'link8'")
    
    runner = create_runner(jobs)
    runner.run()
    
    job = db.get_job_by_link("link8")
    assert job['status'] == 'applied'
    assert job['suitability_score'] == 100
