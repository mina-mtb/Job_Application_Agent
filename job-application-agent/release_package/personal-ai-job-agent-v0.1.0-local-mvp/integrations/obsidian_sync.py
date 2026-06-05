"""
integrations/obsidian_sync.py
==============================
Phase 4 — Obsidian Vault Sync

Responsibility:
  - After each pipeline run, update the Obsidian vault with latest results
  - Write scored jobs as individual markdown notes in 02_Jobs/Scored_Jobs/
  - Update Application_Tracker.md with current tracker.csv data
  - Write a daily summary note in 02_Jobs/

Token optimization:
  - Writes small focused markdown files
  - Never reads the full vault — only writes to specific paths
  - Each job note is ~30 lines max

Design notes:
  - Pure Python, no API calls
  - Idempotent: safe to run multiple times
  - Uses today's date in filenames to avoid overwriting history
"""

import csv
import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("obsidian_sync")


# ── Job note template ──────────────────────────────────────────────────────────

def make_job_note(job: dict) -> str:
    """Generate a compact Obsidian markdown note for one scored job."""
    score     = job.get("match_score", 0)
    priority  = job.get("priority", "").upper()
    breakdown = job.get("score_breakdown", {})

    # Build score breakdown table
    bd_lines = []
    for dim, data in breakdown.items():
        s   = data.get("score", 0)
        mx  = data.get("max", 0)
        det = data.get("detail", "")
        bd_lines.append(f"| {dim.replace('_',' ').title()} | {s}/{mx} | {det} |")
    bd_table = "\n".join(bd_lines)

    reqs = "\n".join(f"- {r}" for r in job.get("requirements", []))
    nth  = "\n".join(f"- {n}" for n in job.get("nice_to_have", []))

    priority_emoji = {"EXCELLENT": "🌟", "HIGH": "✅", "MEDIUM": "🔵"}.get(priority, "")

    return f"""---
job_id: {job.get("id", "")}
score: {score}
priority: {priority}
company: {job.get("company", "")}
location: {job.get("location", "")}
scored_date: {job.get("scored_date", str(date.today()))}
cv_needed: {"yes" if score >= 85 else "no"}
tags: [job, {priority.lower()}, {job.get("source","").replace("apify_","")}]
---

# {job.get("title", "")} @ {job.get("company", "")}

{priority_emoji} **Score: {score}/100** — {priority}
📍 {job.get("location", "")} · {job.get("type", "")}
🔗 [Apply]({job.get("url", "#")})

## Description

{job.get("description", "")[:500]}{"..." if len(job.get("description","")) > 500 else ""}

## Requirements

{reqs if reqs else "- Not specified"}

## Nice to Have

{nth if nth else "- Not specified"}

## Score Breakdown

| Dimension | Score | Detail |
|-----------|-------|--------|
{bd_table}

## Status

- [ ] CV generated
- [ ] Application submitted
- [ ] Follow-up sent

## Notes

_Add personal notes here before applying._
"""


def make_daily_summary(
    scored_jobs: list[dict],
    rejected_count: int,
    clean_stats: Optional[dict] = None,
) -> str:
    """Generate a daily summary note for the Obsidian vault."""
    today = str(date.today())
    excellent = [j for j in scored_jobs if j.get("priority") == "excellent"]
    high      = [j for j in scored_jobs if j.get("priority") == "high"]
    medium    = [j for j in scored_jobs if j.get("priority") == "medium"]

    def job_lines(jobs):
        return "\n".join(
            f"- [[{j.get('id','')}]] {j.get('title','')} @ {j.get('company','')} — {j.get('match_score',0)}/100"
            for j in jobs
        ) or "- None"

    return f"""---
date: {today}
total_scored: {len(scored_jobs)}
excellent: {len(excellent)}
high: {len(high)}
medium: {len(medium)}
rejected: {rejected_count}
tags: [daily-summary, pipeline]
---

# Daily Job Pipeline — {today}

## Results

| Priority | Count |
|----------|-------|
| 🌟 Excellent (90+) | {len(excellent)} |
| ✅ High (85–89) | {len(high)} |
| 🔵 Medium (75–84) | {len(medium)} |
| ❌ Rejected | {rejected_count} |

## Excellent Jobs

{job_lines(excellent)}

## High Priority Jobs

{job_lines(high)}

## Medium Priority Jobs

{job_lines(medium)}

## Pipeline Stats

{f"- Input: {clean_stats.get('total_input', '?')} raw jobs" if clean_stats else ""}
{f"- After cleaning: {clean_stats.get('cleaned', '?')}" if clean_stats else ""}
- Scored and kept: {len(scored_jobs)}
- Rejected (scoring): {rejected_count}

## Action Items

- [ ] Review excellent jobs
- [ ] Generate CVs for score >= 85
- [ ] Check tracker.csv for status updates
"""


def make_tracker_note(tracker_path: str) -> str:
    """Read tracker.csv and generate a formatted Obsidian tracker note."""
    rows = []
    try:
        with open(tracker_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    except FileNotFoundError:
        return "# Application Tracker\n\n_No data yet._\n"

    today = str(date.today())

    # Group by status
    groups = {}
    for row in rows:
        status = row.get("status", "new")
        groups.setdefault(status, []).append(row)

    status_emoji = {
        "new":           "🆕",
        "review":        "👀",
        "cv_ready":      "📄",
        "applied":       "📤",
        "follow_up":     "📬",
        "interview":     "🎯",
        "offer":         "🎉",
        "declined":      "❌",
        "rejected_by_me":"🚫",
    }

    sections = []
    for status, emoji in status_emoji.items():
        if status not in groups:
            continue
        jobs = groups[status]
        lines = []
        for j in sorted(jobs, key=lambda x: int(x.get("score",0)), reverse=True):
            cv = "✓" if j.get("cv_generated") == "yes" else "✗"
            lines.append(
                f"| [[{j['job_id']}\\|{j['title']}]] "
                f"| {j['company']} "
                f"| {j['score']} "
                f"| {cv} "
                f"| {j.get('date_added','')} |"
            )
        section = f"\n## {emoji} {status.replace('_',' ').title()} ({len(jobs)})\n\n"
        section += "| Job | Company | Score | CV | Date Added |\n"
        section += "|-----|---------|-------|----|------------|\n"
        section += "\n".join(lines)
        sections.append(section)

    return f"""---
last_updated: {today}
total_jobs: {len(rows)}
tags: [tracker, applications]
---

# Application Tracker

> Last updated: {today} · Total: {len(rows)} jobs tracked

{"".join(sections)}

---

## Status Guide

| Status | Meaning |
|--------|---------|
| 🆕 new | Scored, not yet reviewed |
| 👀 review | Mina is reviewing |
| 📄 cv_ready | Tailored CV generated |
| 📤 applied | Application submitted |
| 📬 follow_up | Awaiting response |
| 🎯 interview | Interview scheduled |
| 🎉 offer | Offer received |
| ❌ declined | Company declined |
| 🚫 rejected_by_me | Mina decided not to apply |
"""


# ── Main sync function ─────────────────────────────────────────────────────────

def run(config_path: str = "config/config.yaml",
        scored_jobs: Optional[list] = None,
        rejected_count: int = 0,
        clean_stats: Optional[dict] = None) -> dict:
    """
    Sync pipeline results to the Obsidian vault.

    Args:
        scored_jobs:    List of scored job dicts (from job_matcher)
        rejected_count: Number of jobs rejected during scoring
        clean_stats:    Stats dict from job_cleaner

    Returns summary dict.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    vault_path = Path(config.get("obsidian_vault", "../MinaJobAgentVault"))
    if not vault_path.is_absolute():
        vault_path = Path(config_path).parent.parent / vault_path

    logger.info("=" * 60)
    logger.info(f"Obsidian Sync — vault: {vault_path}")

    if not vault_path.exists():
        logger.warning(f"Vault not found at {vault_path} — creating it")
        vault_path.mkdir(parents=True, exist_ok=True)

    today = str(date.today())
    stats = {"job_notes": 0, "daily_summary": False, "tracker_updated": False}

    # 1. Write individual job notes
    scored_dir = vault_path / "02_Jobs" / "Scored_Jobs"
    scored_dir.mkdir(parents=True, exist_ok=True)

    if scored_jobs:
        for job in scored_jobs:
            if job.get("priority") in ("excellent", "high", "medium"):
                note_path = scored_dir / f"{job.get('id', 'unknown')}_{today}.md"
                note_path.write_text(make_job_note(job), encoding="utf-8")
                stats["job_notes"] += 1
                logger.info(f"  ✓ Job note: {note_path.name}")

    # 2. Write daily summary
    summary_dir = vault_path / "02_Jobs"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"Daily_Summary_{today}.md"
    summary_path.write_text(
        make_daily_summary(scored_jobs or [], rejected_count, clean_stats),
        encoding="utf-8",
    )
    stats["daily_summary"] = True
    logger.info(f"  ✓ Daily summary: {summary_path.name}")

    # 3. Update Application Tracker note
    tracker_csv = config["paths"]["tracker"]
    tracker_path = vault_path / "03_Applications" / "Application_Tracker.md"
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    tracker_path.write_text(make_tracker_note(tracker_csv), encoding="utf-8")
    stats["tracker_updated"] = True
    logger.info(f"  ✓ Tracker note updated")

    logger.info(f"Obsidian sync complete: {stats['job_notes']} job notes, tracker updated")
    logger.info("=" * 60)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
