import os
import csv
from datetime import date
from pathlib import Path
import logging

logger = logging.getLogger("daily_apply_page")

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
        company = job.get("company", "")
        title = job.get("title", "")
        score = job.get("score", "")
        cv_link = "[CV در Canva](https://canva.com)"
        apply_url = job.get("job_url") or job.get("url") or "#"
        apply_link = f"[اپلای کن]({apply_url})"
        status = "⬜ نشده"
        lines.append(f"| {company} | {title} | {score} | {cv_link} | {apply_link} | {status} |")
        
    out_path.write_text("\n".join(lines), encoding="utf-8")
