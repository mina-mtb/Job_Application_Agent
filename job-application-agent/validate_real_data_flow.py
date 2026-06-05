import os
import yaml
from pathlib import Path
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from core.job_matcher import JobMatcher
from core.cv_tailor import CVTailor
from llm.mock_provider import MockProvider
from core.app_helpers import process_manual_entry, update_job_status

def validate():
    print("=== Starting Real Data Flow Validation ===")
    
    # 1. Check for template
    template_path = Path("profile/mina_base_cv_template.md")
    if not template_path.exists():
        print("[ERROR] Template profile/mina_base_cv_template.md is missing!")
        return
        
    profile_path = Path("profile/mina_base_cv.md")
    if not profile_path.exists():
        print("\n[ERROR] profile/mina_base_cv.md not found.")
        print("Please copy profile/mina_base_cv_template.md to profile/mina_base_cv.md and fill it with your real data.")
        return
    else:
        print("[INFO] Found your profile/mina_base_cv.md.")
        
    # Initialize Core Components
    print("[INFO] Initializing Core Components (MockProvider)...")
    db = DBManager()
    km = KnowledgeManager()
    provider = MockProvider()
    config = {
        'reject_relocation_required': True, 
        'allow_remote': True, 
        'allow_hybrid': True, 
        'preferred_locations': ['Gothenburg'],
        'base_cv_path': str(profile_path)
    }
    matcher = JobMatcher(config, km, provider)
    tailor = CVTailor(db, km, provider, config)
    
    # 2. Add Profile to Knowledge Base
    print(f"[INFO] Adding {profile_path} to Knowledge Base...")
    km.add_source(str(profile_path))
    
    # 3. Read realistic job
    job_fixture_path = Path("tests/fixtures/sample_realistic_job.md")
    if not job_fixture_path.exists():
        print(f"[ERROR] Realistic job fixture {job_fixture_path} is missing!")
        return
        
    with open(job_fixture_path, "r", encoding="utf-8") as f:
        job_description = f.read()
        
    job_link = "http://example.com/realistic-job-123"
    job_title = "Senior Cloud & Backend Engineer"
    company = "TechSolutions AB"
    location = "Gothenburg, Sweden"
    
    # 4. Insert and Match
    print("[INFO] Inserting realistic job and running matching...")
    # Clean previous if exists to ensure fresh run
    db.execute_query("DELETE FROM jobs WHERE job_link = ?", (job_link,))
    
    success, msg = process_manual_entry(db, matcher, job_description, job_link, job_title, company, location)
    if not success:
        print(f"[ERROR] Failed to process manual entry: {msg}")
        return
        
    job = db.get_job_by_link(job_link)
    print(f"[SUCCESS] Job processed. Status: {job['status']}")
    print(f"         Score: {job['suitability_score']}")
    print(f"         Category: {job['suitability_category']}")
    print(f"         Reasons: {job['reasons_for_match']}")
    
    # 5. Generate CV if it passed
    if job['status'] == 'needs_review':
        print("\n[INFO] Job passed filtering. Generating tailored CV...")
        result = tailor.generate_tailored_cv(job['job_id'])
        if result:
            updated_job = db.get_job_by_link(job_link)
            print(f"[SUCCESS] CV Generated Successfully at: {updated_job.get('generated_cv_path')}")
            # Ensure status is updated correctly in DB
        else:
            print("[ERROR] CV generation failed.")
    else:
        print(f"\n[INFO] Job did not reach needs_review state. Status is {job['status']}. Skipping CV generation.")
        
    print("=== Validation Complete ===")

if __name__ == "__main__":
    validate()
