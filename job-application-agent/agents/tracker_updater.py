"""
agents/tracker_updater.py
=========================
Phase 1 — Tracker Updater

Responsibility:
  - Read scored jobs
  - Write/update tracker.csv without duplicating entries
  - Preserve existing statuses (do not overwrite 'applied', 'follow-up', etc.)
  - Append only new jobs

Design notes:
  - Pure Python (no Claude API calls)
  - Safe: never overwrites a status that was manually set
  - Idempotent: running twice does not duplicate rows
"""

import csv
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tracker_updater")

TRACKER_FIELDS = [
    "job_id", "title", "company", "location",
    "score", "priority", "status",
    "cv_generated", "date_added", "date_applied", "notes"
]

# Statuses set manually by Mina — never auto-overwrite these
PROTECTED_STATUSES = {"applied", "follow_up", "interview", "offer", "declined", "rejected_by_me"}


def load_tracker(tracker_path: str) -> dict:
    """Load tracker CSV into a dict keyed by job_id."""
    existing = {}
    path = Path(tracker_path)
    if not path.exists():
        return existing
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing[row["job_id"]] = row
    return existing


def save_tracker(tracker_path: str, rows: dict) -> None:
    """Save tracker dict back to CSV, sorted by score descending."""
    path = Path(tracker_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows.values(), key=lambda r: int(r.get("score", 0)), reverse=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted_rows)


def update_tracker(scored_jobs: list[dict], tracker_path: str) -> dict:
    """
    Merge scored jobs into existing tracker.
    Returns stats: {added, skipped_protected, updated}.
    """
    existing = load_tracker(tracker_path)
    today = str(date.today())

    stats = {"added": 0, "skipped_protected": 0, "updated_score": 0}

    for job in scored_jobs:
        job_id = job.get("id", "")
        if not job_id:
            continue

        if job_id in existing:
            current_status = existing[job_id].get("status", "")
            if current_status in PROTECTED_STATUSES:
                logger.info(f"  Skipping [{job_id}] — status '{current_status}' is protected")
                stats["skipped_protected"] += 1
                continue
            # Update score/priority if it changed (re-scored)
            existing[job_id]["score"] = str(job.get("match_score", 0))
            existing[job_id]["priority"] = job.get("priority", "")
            stats["updated_score"] += 1
        else:
            # New job — add to tracker
            new_row = {
                "job_id": job_id,
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "location": job.get("location", ""),
                "score": str(job.get("match_score", 0)),
                "priority": job.get("priority", ""),
                "status": "new",
                "cv_generated": "no",
                "date_added": today,
                "date_applied": "",
                "notes": "",
            }
            existing[job_id] = new_row
            stats["added"] += 1
            logger.info(
                f"  Added [{job_id}] {job.get('title')} @ {job.get('company')} "
                f"— Score: {job.get('match_score')}/100 ({job.get('priority')})"
            )

    save_tracker(tracker_path, existing)
    return stats


if __name__ == "__main__":
    # Quick test
    import yaml
    config = yaml.safe_load(open("config/config.yaml", encoding="utf-8"))
    from datetime import date
    test_jobs = json.load(open(f"data/scored/scored_jobs_{date.today()}.json", encoding="utf-8"))
    stats = update_tracker(test_jobs, config["paths"]["tracker"])
    print(f"Tracker updated: {stats}")
