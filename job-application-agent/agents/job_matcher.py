"""
agents/job_matcher.py
=====================
Phase 1 — Job Matcher

Responsibility:
  - Load cleaned (or raw) job listings
  - Score each job against Mina's profile (0–100)
  - Produce a brief explanation for each score
  - Output scored jobs to data/scored/
  - Reject jobs below threshold

Scoring dimensions:
  1. skill_match      (35 pts) — overlap between job requirements and Mina's skills
  2. experience_fit   (20 pts) — is seniority level appropriate for Mina?
  3. location_fit     (20 pts) — Gothenburg / Sweden / Remote / Hybrid
  4. language_fit     (10 pts) — Swedish/English, no native-only barrier
  5. ai_cloud_bonus   (10 pts) — extra weight for AI/ML/Cloud roles
  6. career_value     (5 pts)  — company quality / growth potential

Design notes:
  - NO Claude API calls in this module (pure Python scoring)
  - Token cost: zero
  - Fast, deterministic, debuggable
  - All weights configurable via config.yaml
"""

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

# ── Logging setup ──────────────────────────────────────────────────────────────

def setup_logging(log_file: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger("job_matcher")
    if logger.handlers:
        return logger  # already configured
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


# ── Profile & config loading ───────────────────────────────────────────────────

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_skill_set(profile: dict) -> set:
    """Flatten all skills from profile into a lowercase set for matching."""
    skills = set()
    for category, items in profile.get("skills", {}).items():
        for skill in items:
            skills.add(skill.lower().strip())
    # Also add aliases for common abbreviations
    aliases = {
        "c#": {"csharp", "c sharp"},
        ".net": {"dotnet", "asp.net", "asp.net core"},
        "azure": {"azure devops", "azure service bus", "azure entra"},
        "sql": {"sql server", "mssql", "t-sql"},
        "ml": {"machine learning"},
        "llm": {"large language model", "llm-powered"},
        "ci/cd": {"cicd", "ci cd", "github actions"},
    }
    expanded = set(skills)
    for canonical, alts in aliases.items():
        if canonical in skills:
            expanded.update(alts)
    return expanded


# ── Hard rejection filters ─────────────────────────────────────────────────────

def is_hard_rejected(job: dict, config: dict, logger: logging.Logger) -> tuple[bool, str]:
    """
    Returns (True, reason) if the job should be rejected before scoring.
    These are absolute disqualifiers that save scoring time.
    """
    filters = config.get("rejection_filters", {})
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    combined_text = title + " " + description

    # 1. Unpaid positions
    if filters.get("unpaid") and job.get("compensation") == "unpaid":
        return True, "Unpaid position"

    # 2. Over-senior roles (experience years check)
    exp = job.get("experience_years", "")
    senior_flags = filters.get("required_experience_flags", [])
    for flag in senior_flags:
        if flag.lower() in combined_text:
            return True, f"Over-senior: found '{flag}' in description"

    # 3. Irrelevant role keywords
    irrelevant = filters.get("irrelevant_keywords", [])
    for keyword in irrelevant:
        if keyword.lower() in combined_text:
            return True, f"Irrelevant role: matched keyword '{keyword}'"

    # 4. Native Swedish only (Mina speaks Swedish fluently but not as native)
    lang_req = job.get("language_requirement", "").lower()
    if "native" in lang_req and "swedish" in lang_req and "english" not in lang_req:
        return True, "Requires native Swedish; Mina is fluent but not native"

    return False, ""


# ── Scoring functions ──────────────────────────────────────────────────────────

def score_skill_match(job: dict, mina_skills: set) -> tuple[int, str]:
    """
    Score: 0–35
    Logic: Count how many required skills match Mina's skills.
    """
    requirements = [r.lower().strip() for r in job.get("requirements", [])]
    nice_to_have = [n.lower().strip() for n in job.get("nice_to_have", [])]

    if not requirements:
        return 15, "No requirements listed (partial credit)"

    # Check required skills
    matched_req = []
    missed_req = []
    for req in requirements:
        # Fuzzy: check if any of Mina's skills is a substring or vice versa
        matched = any(
            req in skill or skill in req or req == skill
            for skill in mina_skills
        )
        if matched:
            matched_req.append(req)
        else:
            missed_req.append(req)

    # Check nice-to-have (half weight)
    matched_nth = [n for n in nice_to_have if any(
        n in skill or skill in n for skill in mina_skills
    )]

    req_ratio = len(matched_req) / len(requirements) if requirements else 0
    nth_bonus = min(5, len(matched_nth) * 1)  # max 5 bonus pts from nice-to-have

    base_score = round(req_ratio * 30) + nth_bonus
    base_score = min(35, base_score)

    detail = f"Matched {len(matched_req)}/{len(requirements)} required skills"
    if missed_req:
        detail += f"; missing: {', '.join(missed_req[:3])}"
    if matched_nth:
        detail += f"; nice-to-have matches: {', '.join(matched_nth[:3])}"

    return base_score, detail


def score_experience_fit(job: dict) -> tuple[int, str]:
    """
    Score: 0–20
    Logic: Mina has ~4 years total experience + current M.Sc.
    Junior/mid-level roles (0–5 years) score high.
    Senior 6+ score low.
    """
    exp_str = str(job.get("experience_years", "")).lower()

    if any(x in exp_str for x in ["0-1", "0-2", "student", "intern", "trainee"]):
        return 20, "Junior/intern level — perfect fit"
    elif any(x in exp_str for x in ["1-3", "1-4", "2-4"]):
        return 20, "Junior to mid-level — strong fit"
    elif any(x in exp_str for x in ["2-5", "3-5", "1-5"]):
        return 16, "Mid-level — good fit with Mina's background"
    elif any(x in exp_str for x in ["4-6", "3-6", "5"]):
        return 10, "Mid-senior — slight stretch but possible"
    elif any(x in exp_str for x in ["6+", "7+", "8+", "10+"]):
        return 2, "Over-senior — significant mismatch"
    else:
        return 12, f"Experience unclear ('{exp_str}') — partial credit"


def score_location_fit(job: dict) -> tuple[int, str]:
    """
    Score: 0–20
    Priority: Gothenburg > Sweden-wide > Remote > Other
    """
    location = job.get("location", "").lower()
    job_type = job.get("type", "").lower()

    if "gothenburg" in location or "göteborg" in location:
        return 20, "Gothenburg — ideal location"
    elif "remote" in job_type or "remote" in location:
        if "sweden" in location or "stockholm" in location:
            return 18, "Remote within Sweden — great option"
        return 16, "Remote (location flexible)"
    elif "hybrid" in job_type:
        if "sweden" in location:
            return 17, "Hybrid in Sweden — good fit"
        return 14, "Hybrid (location TBD)"
    elif "sweden" in location:
        return 15, "Sweden (non-Gothenburg) — relocation possible"
    else:
        return 5, f"Location mismatch: {job.get('location', 'unknown')}"


def score_language_fit(job: dict) -> tuple[int, str]:
    """
    Score: 0–10
    Mina: Swedish (Fluent), English (Intermediate), Persian (Native)
    """
    lang = job.get("language_requirement", "").lower()

    if not lang or lang == "english":
        return 10, "English only — Mina qualifies"
    elif "swedish or english" in lang or ("swedish" in lang and "english" in lang):
        return 10, "Swedish or English — Mina qualifies (Swedish fluent)"
    elif lang == "swedish":
        return 8, "Swedish required — Mina is fluent"
    elif "native" in lang and "swedish" in lang:
        return 3, "Native Swedish required — Mina is fluent but not native"
    else:
        return 6, f"Language unclear: '{lang}'"


def score_ai_cloud_bonus(job: dict) -> tuple[int, str]:
    """
    Score: 0–10
    Bonus for AI, ML, Cloud, LLM roles — aligned with Mina's career direction.
    """
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    combined = title + " " + description

    ai_keywords = ["ai", "ml", "machine learning", "llm", "langchain", "rag",
                   "generative", "deep learning", "neural", "llmops", "mlops",
                   "nlp", "data science", "pytorch", "tensorflow"]
    cloud_keywords = ["azure", "aws", "gcp", "cloud", "kubernetes", "docker",
                      "devops", "mlops", "infrastructure"]

    ai_hits = sum(1 for kw in ai_keywords if kw in combined)
    cloud_hits = sum(1 for kw in cloud_keywords if kw in combined)

    if ai_hits >= 3:
        return 10, f"Strong AI/ML alignment ({ai_hits} AI keywords matched)"
    elif ai_hits >= 1 and cloud_hits >= 2:
        return 9, f"AI + Cloud role ({ai_hits} AI, {cloud_hits} cloud keywords)"
    elif cloud_hits >= 3:
        return 8, f"Strong cloud alignment ({cloud_hits} cloud keywords)"
    elif ai_hits >= 1 or cloud_hits >= 1:
        return 5, "Some AI/cloud relevance"
    else:
        return 2, "Low AI/cloud relevance"


def score_career_value(job: dict) -> tuple[int, str]:
    """
    Score: 0–5
    Heuristic based on company type and role growth potential.
    """
    company = job.get("company", "").lower()
    title = job.get("title", "").lower()

    # Known high-value companies (tech, research, scale-ups)
    top_tier = ["volvo", "ericsson", "spotify", "klarna", "king",
                "chalmers", "astrazeneca", "microsoft", "google", "meta"]

    if any(t in company for t in top_tier):
        return 5, f"Top-tier company ({job.get('company')})"
    elif any(kw in title for kw in ["ai", "ml", "cloud", "architect", "platform"]):
        return 4, "High growth-potential role title"
    else:
        return 3, "Standard career value"


# ── Main scoring orchestrator ──────────────────────────────────────────────────

def score_job(job: dict, mina_skills: set) -> dict:
    """
    Score a single job and return an enriched dict with score + breakdown.
    """
    s1, d1 = score_skill_match(job, mina_skills)
    s2, d2 = score_experience_fit(job)
    s3, d3 = score_location_fit(job)
    s4, d4 = score_language_fit(job)
    s5, d5 = score_ai_cloud_bonus(job)
    s6, d6 = score_career_value(job)

    total = s1 + s2 + s3 + s4 + s5 + s6

    breakdown = {
        "skill_match":    {"score": s1, "max": 35, "detail": d1},
        "experience_fit": {"score": s2, "max": 20, "detail": d2},
        "location_fit":   {"score": s3, "max": 20, "detail": d3},
        "language_fit":   {"score": s4, "max": 10, "detail": d4},
        "ai_cloud_bonus": {"score": s5, "max": 10, "detail": d5},
        "career_value":   {"score": s6, "max": 5,  "detail": d6},
    }

    return {
        **job,
        "match_score": total,
        "score_breakdown": breakdown,
        "scored_date": str(date.today()),
    }


def assign_priority(score: int, thresholds: dict) -> str:
    if score >= thresholds.get("excellent", 85):
        return "excellent"
    elif score >= thresholds.get("high_priority", 75):
        return "high"
    elif score >= thresholds.get("medium_priority", 60):
        return "medium"
    else:
        return "reject"


# ── File I/O ───────────────────────────────────────────────────────────────────

def load_jobs(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_jobs(jobs: list[dict], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)


# ── Main entry point ───────────────────────────────────────────────────────────

def run(config_path: str = "config/config.yaml") -> dict:
    """
    Run the job matcher pipeline.
    Returns a summary dict with counts per priority tier.
    """
    config = load_yaml(config_path)
    logger = setup_logging(config["paths"]["logs"] + "pipeline.log")
    logger.info("=" * 60)
    logger.info("Job Matcher — Phase 1 starting")

    # Load profile
    profile = load_yaml(config["paths"]["profile"])
    mina_skills = build_skill_set(profile)
    thresholds = config["score_thresholds"]
    logger.info(f"Profile loaded. Skill set: {len(mina_skills)} skills")

    # Load jobs
    jobs_file = config.get("mock_jobs_file", config["paths"]["raw_jobs"] + "mock_jobs.json")
    jobs = load_jobs(jobs_file)
    logger.info(f"Loaded {len(jobs)} jobs from {jobs_file}")

    # Process
    results = {"excellent": [], "high": [], "medium": [], "rejected": []}
    rejection_log = []

    for job in jobs:
        job_id = job.get("id", "unknown")
        title = job.get("title", "?")
        company = job.get("company", "?")

        # Step 1: Hard rejection
        rejected, reason = is_hard_rejected(job, config, logger)
        if rejected:
            logger.info(f"  REJECTED [{job_id}] {title} @ {company} — {reason}")
            rejection_log.append({**job, "rejection_reason": reason, "match_score": 0, "priority": "reject"})
            results["rejected"].append({**job, "rejection_reason": reason})
            continue

        # Step 2: Score
        scored = score_job(job, mina_skills)
        priority = assign_priority(scored["match_score"], thresholds)
        scored["priority"] = priority

        logger.info(
            f"  {'✓' if priority != 'reject' else '✗'} [{job_id}] "
            f"{title} @ {company} — Score: {scored['match_score']}/100 ({priority.upper()})"
        )

        if priority == "reject":
            scored["rejection_reason"] = f"Score {scored['match_score']} below threshold {thresholds['medium_priority']}"
            results["rejected"].append(scored)
        else:
            results[priority].append(scored)

    # Save outputs
    today = str(date.today())
    all_kept = results["excellent"] + results["high"] + results["medium"]

    save_jobs(all_kept, f"{config['paths']['scored_jobs']}scored_jobs_{today}.json")
    save_jobs(results["rejected"], f"{config['paths']['scored_jobs']}rejected_jobs_{today}.json")

    # Summary
    summary = {
        "total_input": len(jobs),
        "excellent": len(results["excellent"]),
        "high": len(results["high"]),
        "medium": len(results["medium"]),
        "rejected": len(results["rejected"]),
        "output_file": f"{config['paths']['scored_jobs']}scored_jobs_{today}.json",
    }

    logger.info("-" * 60)
    logger.info(f"SUMMARY: {summary['total_input']} jobs processed")
    logger.info(f"  Excellent : {summary['excellent']}")
    logger.info(f"  High      : {summary['high']}")
    logger.info(f"  Medium    : {summary['medium']}")
    logger.info(f"  Rejected  : {summary['rejected']}")
    logger.info(f"  Saved to  : {summary['output_file']}")
    logger.info("=" * 60)

    return summary, results


if __name__ == "__main__":
    summary, results = run()
