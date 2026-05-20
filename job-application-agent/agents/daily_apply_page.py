import os
import csv
from datetime import date
from pathlib import Path
import logging

logger = logging.getLogger("daily_apply_page")

CANVA_CV_LINKS = {
    "job_002": "https://www.canva.com/d/NfnuoQpjYZo-H_u",
    "job_001": "https://www.canva.com/d/fWwA3H7WxW7ueyC",
    "job_004": "https://www.canva.com/d/aTvUnAA_SbRm9Gg",
    "job_010": "https://www.canva.com/d/42T_Gm-6cEIVpN_",
    "job_005": "https://www.canva.com/d/74uhR-5E870pLOa",
    "job_009": "https://www.canva.com/d/0apE9ULxWUEr5sl",
    "job_007": "https://www.canva.com/d/-fxe19FAlKl7k_X",
}

def generate_daily_page(tracker_path, vault_path):
    today = str(date.today())
    out_path = Path(vault_path) / "03_Applications" / f"Daily_Apply_{today}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read tracker
    jobs = []
    if Path(tracker_path).exists():
        with open(tracker_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date_added") == today or row.get("status") == "new":
                    jobs.append(row)
                    
    # Sort by score descending
    jobs.sort(key=lambda x: int(x.get("score", 0)), reverse=True)
    
    lines = [
        f"# 📅 Daily Applications — {today}",
        "",
        "| شرکت | عنوان شغل | امتیاز | CV | لینک | وضعیت |",
        "|---|---|---|---|---|---|",
    ]
    
    for job in jobs[:15]: # Show top jobs
        job_id = job.get("job_id", "")
        company = job.get("company", "")
        title = job.get("title", "")
        score = job.get("score", "")
        
        real_cv_link = CANVA_CV_LINKS.get(job_id, "https://canva.com")
        cv_link = f"[CV در Canva]({real_cv_link})"
        
        apply_url = job.get("job_url") or job.get("url") or "#"
        apply_link = f"[اپلای کن]({apply_url})"
        status = "⬜ نشده"
        lines.append(f"| {company} | {title} | {score} | {cv_link} | {apply_link} | {status} |")
        
    out_path.write_text("\n".join(lines), encoding="utf-8")
