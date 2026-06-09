import os
import uuid
from datetime import datetime
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from core.job_matcher import JobMatcher

def can_generate_cv(status: str) -> bool:
    return status in ['needs_review', 'approved']

def can_approve(status: str) -> bool:
    return status in ['needs_review', 'cv_generated']

def can_mark_applied(cv_path: str) -> bool:
    return bool(cv_path)

def update_job_status(db: DBManager, job_id: str, new_status: str):
    db.execute_query("UPDATE jobs SET status = ? WHERE job_id = ?", (new_status, job_id))

def mark_as_applied(db: DBManager, job_id: str):
    # Only update status and date_applied
    db.execute_query("UPDATE jobs SET status = 'applied', date_applied = CURRENT_TIMESTAMP WHERE job_id = ?", (job_id,))

def add_user_note(db: DBManager, job_id: str, note: str):
    # Retrieve existing
    jobs = db.execute_query("SELECT user_notes FROM jobs WHERE job_id = ?", (job_id,))
    if jobs:
        existing = jobs[0]['user_notes'] or ""
        new_notes = existing + f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {note}"
        db.execute_query("UPDATE jobs SET user_notes = ? WHERE job_id = ?", (new_notes.strip(), job_id))

def process_manual_entry(db: DBManager, matcher: JobMatcher, description: str, job_link: str, title: str = "Manual Entry", company: str = "Unknown", location: str = "Unknown"):
    job_id = f"manual_{uuid.uuid4().hex[:8]}"
    job_data = {
        "job_id": job_id,
        "title": title,
        "company": company,
        "location": location,
        "job_link": job_link or f"manual_link_{job_id}",
        "description": description
    }
    
    # Insert job
    inserted = db.insert_job(job_data)
    if not inserted:
        return False, "Job with this link already exists."

    # Run Stage 1 & Stage 2 matching
    result1 = matcher.evaluate_stage1(job_data)
    if result1.get('status') == 'not_suitable':
        db.execute_query("UPDATE jobs SET status = 'not_suitable', weaknesses_or_risks = ? WHERE job_id = ?", (str(result1.get('weaknesses_or_risks', [])), job_id))
        return True, "Job processed but rejected in Stage 1."
        
    result2 = matcher.evaluate_stage2(job_data)
    db.execute_query(
        """UPDATE jobs SET 
           suitability_score = ?, suitability_category = ?, 
           reasons_for_match = ?, weaknesses_or_risks = ?, 
           status = ? 
           WHERE job_id = ?""",
        (
            result2.get('suitability_score'),
            result2.get('suitability_category'),
            str(result2.get('reasons_for_match', [])),
            str(result2.get('weaknesses_or_risks', [])),
            result2.get('status', 'needs_review'),
            job_id
        )
    )
    return True, f"Job processed successfully. Status: {result2.get('status', 'needs_review')}"

def run_daily_matching(db: DBManager, matcher: JobMatcher) -> dict:
    jobs = db.execute_query("SELECT * FROM jobs WHERE status = 'new'")
    
    stats = {
        "processed": 0,
        "duplicates": 0,  # Currently not tracked as insert handles duplicates before this
        "suitable": 0,
        "rejected": 0,
        "cv_generated": 0,
        "errors": 0
    }
    
    for job in jobs:
        try:
            stats["processed"] += 1
            result1 = matcher.evaluate_stage1(dict(job))
            
            if result1.get('status') == 'not_suitable':
                db.execute_query("UPDATE jobs SET status = 'not_suitable', weaknesses_or_risks = ? WHERE job_id = ?", (str(result1.get('weaknesses_or_risks', [])), job['job_id']))
                stats["rejected"] += 1
            else:
                result2 = matcher.evaluate_stage2(dict(job))
                status = result2.get('status', 'needs_review')
                if status in ['needs_review', 'approved']:
                    stats["suitable"] += 1
                else:
                    stats["rejected"] += 1
                    
                db.execute_query(
                    """UPDATE jobs SET 
                       suitability_score = ?, suitability_category = ?, 
                       reasons_for_match = ?, weaknesses_or_risks = ?, 
                       status = ? 
                       WHERE job_id = ?""",
                    (
                        result2.get('suitability_score'),
                        result2.get('suitability_category'),
                        str(result2.get('reasons_for_match', [])),
                        str(result2.get('weaknesses_or_risks', [])),
                        status,
                        job['job_id']
                    )
                )
        except Exception as e:
            stats["errors"] += 1
            db.execute_query("UPDATE jobs SET status = 'failed', weaknesses_or_risks = ? WHERE job_id = ?", (f"['Error: {str(e)}']", job['job_id']))
            
    return stats

def handle_knowledge_upload(km: KnowledgeManager, file_path: str):
    if not os.path.exists(file_path):
        return False, "File does not exist."
    if not (file_path.lower().endswith('.md') or file_path.lower().endswith('.txt') or file_path.lower().endswith('.pdf') or file_path.lower().endswith('.docx')):
        return False, "Only .md, .txt, .pdf, and .docx files are supported."
        
    try:
        km.add_source(file_path)
        return True, "File successfully added to Knowledge Base."
    except Exception as e:
        return False, f"Failed to add file: {str(e)}"
