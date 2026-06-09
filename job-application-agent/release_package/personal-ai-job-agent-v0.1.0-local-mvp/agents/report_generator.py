import os
from datetime import date
from pathlib import Path

def generate_report(stats: dict, ready_jobs: list[dict], output_dir: str):
    """
    Generate a daily markdown report.
    stats dict should contain:
      - raw_collected
      - after_cleaning
      - duplicates_removed (optional)
      - already_applied_skipped
      - relevant_jobs
      - high_priority
      - cvs_generated
    """
    today = str(date.today())
    out_path = Path(output_dir) / f"{today}_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    report = f"## Daily Job Report — {today}\n\n"
    report += f"- Raw jobs collected: {stats.get('raw_collected', 0)}\n"
    report += f"- After cleaning: {stats.get('after_cleaning', 0)}\n"
    report += f"- Duplicates removed: {stats.get('duplicates_removed', 0)}\n"
    report += f"- Already applied (skipped): {stats.get('already_applied_skipped', 0)}\n"
    report += f"- Relevant jobs: {stats.get('relevant_jobs', 0)}\n"
    report += f"- High priority (score >= 85): {stats.get('high_priority', 0)}\n"
    report += f"- CVs generated: {stats.get('cvs_generated', 0)}\n\n"
    
    report += "## Ready to Apply Today\n\n"
    report += "| Company | Role | Location | Mode | Score | CV File | Link |\n"
    report += "|---------|------|----------|------|-------|---------|------|\n"
    
    for job in ready_jobs:
        company = job.get('company', '')
        role = job.get('title', '')
        location = job.get('location', '')
        mode = job.get('type', '')
        score = job.get('match_score', 0)
        
        # Determine CV file name or status
        # Since cv_tailor saves file to tracker, maybe it is in job dict?
        cv_file = job.get('cv_file', 'Not generated')
        link = job.get('url', '')
        
        report += f"| {company} | {role} | {location} | {mode} | {score} | {cv_file} | [Link]({link}) |\n"
        
    out_path.write_text(report, encoding="utf-8")
    return str(out_path)
