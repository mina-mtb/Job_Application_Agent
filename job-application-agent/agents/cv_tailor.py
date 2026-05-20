"""
agents/cv_tailor.py
====================
Phase 3 — CV Tailor

Responsibility:
  - Load a scored job (score >= 85)
  - Load Mina's base CV + rules from Obsidian vault
  - Call Claude API with a tight, token-efficient prompt
  - Generate a tailored, ATS-optimized CV in markdown
  - Save to cvs/tailored/
  - Update tracker: cv_generated = yes

Token optimization strategy:
  - Prompt is built from small reusable chunks
  - Only loads 3 files: base_cv.md, job description, rules summary
  - Never loads full vault
  - Claude output is ~600-900 tokens (markdown CV)
  - Total per CV: ~1500-2000 tokens

Design rules (from Do_Not_Invent_Rules.md):
  - NEVER fabricate experience, companies, skills
  - ONLY rephrase, reorder, keyword-optimize
  - Every claim must exist in base_cv.md
"""

import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("cv_tailor")

# ── Claude API call ────────────────────────────────────────────────────────────

def call_claude(prompt: str, system: str, max_tokens: int = 1500) -> str:
    """
    Call Claude API (claude-sonnet-4-20250514).
    Returns the text response.
    Raises on failure.
    """
    try:
        import anthropic
        client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
    except ImportError:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )
    except Exception as e:
        raise RuntimeError(f"Claude API error: {e}")


# ── Prompt builder ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional CV writer helping Mina Tahmasebi tailor her CV for a specific job.

CRITICAL RULES — you must follow these without exception:
1. NEVER invent experience, companies, dates, or skills
2. NEVER add skills not present in the base CV
3. NEVER claim certifications not in the base CV
4. NEVER use vague inflated language ("decade of experience", "industry leader")
5. You MAY reorder bullet points, use stronger action verbs, and place job keywords naturally
6. You MAY rewrite the profile summary to match the role
7. You MAY reorder skills sections to highlight the most relevant skills first
8. Output ONLY the tailored CV in clean markdown — no preamble, no explanation
9. Keep ATS formatting: no tables, no columns, standard section headers
10. File must be complete — all sections: Profile, Skills, Experience, Education, Languages"""

def build_prompt(base_cv: str, job: dict) -> str:
    """
    Build a tight, token-efficient prompt.
    We pass only what Claude needs — not the full vault.
    """
    requirements = "\n".join(f"- {r}" for r in job.get("requirements", []))
    nice_to_have = "\n".join(f"- {n}" for n in job.get("nice_to_have", []))

    return f"""Tailor Mina's CV for the following job. Follow all rules strictly.

## TARGET JOB
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')} ({job.get('type')})
Match Score: {job.get('match_score')}/100

## JOB DESCRIPTION
{job.get('description', '')}

## REQUIRED SKILLS (mirror these exact keywords where truthful)
{requirements}

## NICE TO HAVE
{nice_to_have}

## MINA'S BASE CV (this is the ONLY source of truth — do not add anything not here)
{base_cv}

## YOUR TASK
Produce a tailored CV that:
1. Rewrites the Profile summary (3-4 lines) to match this specific role
2. Reorders Skills to put the most job-relevant skills first
3. Reorders experience bullet points to highlight most relevant work
4. Places exact keywords from the job description naturally in existing bullets
5. Keeps ALL experience entries — do not remove any jobs
6. Preserves exact dates, company names, and role titles

Output the complete tailored CV now in markdown format:"""


# ── Match optimizer ────────────────────────────────────────────────────────────

OPTIMIZER_SYSTEM = """You are an ATS optimization specialist. 
Analyze a tailored CV against a job description and suggest ONLY truthful improvements.
Never suggest adding skills or experience that don't exist in the CV.
Output a short JSON list of suggestions only."""

def optimize_match(tailored_cv: str, job: dict) -> list[str]:
    """
    Phase 3b: Compare tailored CV with job description.
    Returns list of truthful keyword suggestions.
    Token cost: ~500-700 tokens (small targeted call).
    """
    job_keywords = job.get("requirements", []) + job.get("nice_to_have", [])
    keywords_str = ", ".join(job_keywords)

    prompt = f"""Job keywords to check: {keywords_str}

Tailored CV (excerpt — skills and profile only):
{tailored_cv[:1500]}

Task: Which job keywords are MISSING from this CV but ARE plausibly present in Mina's background?
Return ONLY a JSON array of strings like: ["keyword1", "keyword2"]
If nothing is missing, return: []
Do not suggest skills Mina clearly does not have."""

    try:
        raw = call_claude(prompt, OPTIMIZER_SYSTEM, max_tokens=300)
        # Extract JSON array from response
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return []
    except Exception as e:
        logger.warning(f"Optimizer failed (non-critical): {e}")
        return []


# ── File helpers ───────────────────────────────────────────────────────────────

def make_cv_filename(job: dict) -> str:
    company = re.sub(r"[^a-zA-Z0-9]", "_", job.get("company", "Company"))[:20]
    title   = re.sub(r"[^a-zA-Z0-9]", "_", job.get("title", "Role"))[:25]
    today   = str(date.today())
    return f"CV_Mina_Tahmasebi_{company}_{title}_{today}.md"


def update_tracker_cv_status(tracker_path: str, job_id: str, cv_filename: str) -> None:
    """Mark cv_generated = yes in tracker.csv for this job."""
    import csv
    rows = []
    with open(tracker_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["job_id"] == job_id:
                row["cv_generated"] = "yes"
                row["status"] = "cv_ready"
                row["notes"] = f"CV: {cv_filename}"
            rows.append(row)

    with open(tracker_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Main tailor function ───────────────────────────────────────────────────────

def tailor_one_cv(job: dict, base_cv: str, output_dir: Path,
                  tracker_path: str, run_optimizer: bool = True) -> dict:
    """
    Generate a tailored CV for one job.
    Returns a result dict with status and file path.
    """
    job_id   = job.get("id", "unknown")
    title    = job.get("title", "?")
    company  = job.get("company", "?")
    score    = job.get("match_score", 0)

    logger.info(f"  Tailoring CV for [{job_id}] {title} @ {company} (score: {score})")

    # Build prompt and call Claude
    prompt = build_prompt(base_cv, job)

    try:
        tailored_cv = call_claude(prompt, SYSTEM_PROMPT, max_tokens=1500)
    except Exception as e:
        logger.error(f"  ✗ Claude API failed for {job_id}: {e}")
        return {"job_id": job_id, "status": "error", "error": str(e)}

    # Run match optimizer (small follow-up call)
    suggestions = []
    if run_optimizer:
        logger.info(f"    Running match optimizer...")
        suggestions = optimize_match(tailored_cv, job)
        if suggestions:
            logger.info(f"    Optimizer suggestions: {suggestions}")
            # Append suggestions as a note at the bottom of the CV
            note = "\n\n---\n## ⚡ ATS Optimizer Notes\n"
            note += "_The following keywords from the job description could be added "
            note += "if truthfully applicable — verify before including:_\n\n"
            note += "\n".join(f"- `{s}`" for s in suggestions)
            tailored_cv += note

    # Save CV file
    filename = make_cv_filename(job)
    out_path = output_dir / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Add header metadata
    header = f"""---
job_id: {job_id}
title: {title}
company: {company}
score: {score}
generated: {date.today()}
---

"""
    out_path.write_text(header + tailored_cv, encoding="utf-8")
    logger.info(f"  ✓ Saved: {filename}")

    # Update tracker
    update_tracker_cv_status(tracker_path, job_id, filename)

    return {
        "job_id": job_id,
        "status": "success",
        "file": str(out_path),
        "filename": filename,
        "optimizer_suggestions": suggestions,
    }


# ── Main entry point ───────────────────────────────────────────────────────────

def run(config_path: str = "config/config.yaml",
        min_score: int = 85,
        max_cvs: Optional[int] = None) -> dict:
    """
    Run CV tailor for all scored jobs above min_score.

    Args:
        min_score: Only tailor CVs for jobs with score >= this value
        max_cvs:   Limit how many CVs to generate (None = all qualifying)

    Returns summary dict.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info("=" * 60)
    logger.info("CV Tailor — Phase 3 starting")

    # Load base CV
    base_cv_path = Path(config["paths"]["base_cv"])
    base_cv = base_cv_path.read_text(encoding="utf-8")
    logger.info(f"Base CV loaded: {base_cv_path}")

    # Load scored jobs
    scored_dir = Path(config["paths"]["scored_jobs"])
    today = str(date.today())
    scored_file = scored_dir / f"scored_jobs_{today}.json"

    if not scored_file.exists():
        # Try most recent file
        scored_files = sorted(scored_dir.glob("scored_jobs_*.json"))
        if not scored_files:
            logger.error("No scored jobs found. Run job_matcher first.")
            return {"error": "No scored jobs found"}
        scored_file = scored_files[-1]
        logger.info(f"Using most recent: {scored_file.name}")

    jobs = json.loads(scored_file.read_text(encoding="utf-8"))
    logger.info(f"Loaded {len(jobs)} scored jobs")

    # Filter to qualifying jobs
    qualifying = [j for j in jobs if j.get("match_score", 0) >= min_score]
    qualifying.sort(key=lambda j: j.get("match_score", 0), reverse=True)

    if max_cvs:
        qualifying = qualifying[:max_cvs]

    logger.info(f"Qualifying jobs (score >= {min_score}): {len(qualifying)}")

    # Output directory
    output_dir = Path(config["paths"]["tailored_cvs"])
    tracker_path = config["paths"]["tracker"]

    # Generate CVs
    results = []
    for i, job in enumerate(qualifying):
        logger.info(f"\n[{i+1}/{len(qualifying)}]")
        result = tailor_one_cv(
            job=job,
            base_cv=base_cv,
            output_dir=output_dir,
            tracker_path=tracker_path,
            run_optimizer=True,
        )
        results.append(result)
        # Small delay to avoid rate limiting
        if i < len(qualifying) - 1:
            time.sleep(1)

    # Summary
    success = [r for r in results if r.get("status") == "success"]
    errors  = [r for r in results if r.get("status") == "error"]

    summary = {
        "total_qualifying": len(qualifying),
        "generated": len(success),
        "errors": len(errors),
        "files": [r.get("filename") for r in success],
    }

    logger.info("\n" + "=" * 60)
    logger.info(f"CV Tailor complete: {len(success)} generated, {len(errors)} errors")
    if errors:
        for e in errors:
            logger.error(f"  ✗ {e['job_id']}: {e.get('error')}")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
