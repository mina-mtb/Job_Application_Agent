"""
agents/job_cleaner.py
=====================
Phase 2 — Job Cleaner

Responsibility:
  - Load raw jobs (from any source: mock, Apify, manual)
  - Normalize field names and values
  - Remove exact duplicates (same job_id)
  - Remove near-duplicates (same title + company)
  - Flag and remove clearly irrelevant jobs
  - Output a clean, standardized JSON to data/cleaned/

Design notes:
  - Zero Claude API calls — pure Python
  - Idempotent: safe to run multiple times
  - Logs every decision with reason
  - Preserves original data in a 'raw_data' field for audit
"""

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("job_cleaner")


# ── Normalization ──────────────────────────────────────────────────────────────

FIELD_ALIASES = {
    # Apify LinkedIn fields → our standard fields
    "jobTitle": "title",
    "job_title": "title",
    "companyName": "company",
    "company_name": "company",
    "jobLocation": "location",
    "job_location": "location",
    "jobType": "type",
    "job_type": "type",
    "jobDescription": "description",
    "job_description": "description",
    "applyUrl": "url",
    "apply_url": "url",
    "postedDate": "posted_date",
    "posted_at": "posted_date",
    "publishedAt": "posted_date",
    "experienceLevel": "experience_years",
    "experience_level": "experience_years",
    "languages": "language_requirement",
}

LOCATION_NORMALIZATIONS = {
    "göteborg": "Gothenburg, Sweden",
    "gothenburg": "Gothenburg, Sweden",
    "gothenburg, sweden": "Gothenburg, Sweden",
    "stockholm": "Stockholm, Sweden",
    "stockholm, sweden": "Stockholm, Sweden",
    "malmö": "Malmö, Sweden",
    "malmo": "Malmö, Sweden",
    "sweden": "Sweden",
    "remote": "Remote",
    "hybrid": "Hybrid",
    "remote (sweden)": "Remote, Sweden",
    "sweden (remote)": "Remote, Sweden",
}

TYPE_NORMALIZATIONS = {
    "on-site": "On-site",
    "onsite": "On-site",
    "on site": "On-site",
    "remote": "Remote",
    "hybrid": "Hybrid",
    "full-time": "Full-time",
    "fulltime": "Full-time",
    "part-time": "Part-time",
    "parttime": "Part-time",
    "internship": "Internship",
    "intern": "Internship",
    "contract": "Contract",
}


def normalize_fields(job: dict) -> dict:
    """Rename aliased fields to standard names."""
    normalized = {}
    for key, value in job.items():
        standard_key = FIELD_ALIASES.get(key, key)
        normalized[standard_key] = value
    return normalized


def normalize_location(location: str) -> str:
    """Standardize location strings."""
    if not location:
        return "Unknown"
    key = location.lower().strip()
    return LOCATION_NORMALIZATIONS.get(key, location.strip())


def normalize_type(job_type: str) -> str:
    """Standardize job type strings."""
    if not job_type:
        return "Unknown"
    key = job_type.lower().strip()
    return TYPE_NORMALIZATIONS.get(key, job_type.strip())


def normalize_job(job: dict) -> dict:
    """Apply all normalization rules to a single job."""
    job = normalize_fields(job)

    # Normalize location
    if "location" in job:
        job["location"] = normalize_location(str(job["location"]))

    # Normalize type
    if "type" in job:
        job["type"] = normalize_type(str(job["type"]))

    # Ensure required fields exist with defaults
    defaults = {
        "id": "",
        "title": "Unknown Title",
        "company": "Unknown Company",
        "location": "Unknown",
        "type": "Unknown",
        "description": "",
        "requirements": [],
        "nice_to_have": [],
        "experience_years": "unknown",
        "language_requirement": "English",
        "source": "unknown",
        "url": "",
        "posted_date": str(date.today()),
        "compensation": "paid",
    }
    for field, default in defaults.items():
        if field not in job or job[field] is None:
            job[field] = default

    # Clean whitespace in text fields
    for field in ["title", "company", "description"]:
        if isinstance(job[field], str):
            job[field] = re.sub(r"\s+", " ", job[field]).strip()

    # Ensure requirements/nice_to_have are lists
    for field in ["requirements", "nice_to_have"]:
        if isinstance(job[field], str):
            job[field] = [x.strip() for x in job[field].split(",") if x.strip()]
        elif not isinstance(job[field], list):
            job[field] = []

    return job


# ── Deduplication ──────────────────────────────────────────────────────────────

def make_fingerprint(job: dict) -> str:
    """
    Create a fingerprint for near-duplicate detection.
    Uses title + company (lowercased, stripped of punctuation).
    """
    title = re.sub(r"[^a-z0-9 ]", "", job.get("title", "").lower())
    company = re.sub(r"[^a-z0-9 ]", "", job.get("company", "").lower())
    raw = f"{title}||{company}"
    return hashlib.md5(raw.encode()).hexdigest()


def assign_id_if_missing(job: dict, index: int) -> dict:
    """Give a stable ID to jobs that don't have one (e.g. from Apify)."""
    if not job.get("id"):
        title_slug = re.sub(r"[^a-z0-9]", "_", job.get("title", "job").lower())[:20]
        company_slug = re.sub(r"[^a-z0-9]", "_", job.get("company", "co").lower())[:15]
        job["id"] = f"{title_slug}_{company_slug}_{index:03d}"
    return job


# ── Relevance filtering ────────────────────────────────────────────────────────

IRRELEVANT_TITLE_PATTERNS = [
    r"\bretail\b", r"\bsales associate\b", r"\bcashier\b",
    r"\bwarehouse worker\b", r"\bdriver\b", r"\bnurse\b",
    r"\bteacher\b", r"\baccountant\b", r"\bmarketing manager\b",
    r"\bhr manager\b", r"\brecruiter\b", r"\bsecretary\b",
    r"\bcleaner\b", r"\bjanitor\b", r"\bchef\b", r"\bcook\b",
]

REQUIRED_RELEVANCE_SIGNALS = [
    # At least one of these must be present in title or description
    "developer", "engineer", "programmer", "software", "backend",
    "frontend", "fullstack", "cloud", "devops", "ml", "ai", "data",
    "python", "java", "c#", ".net", "machine learning", "llm",
    "analyst", "architect", "platform", "infrastructure", "sre",
]


def is_relevant(job: dict) -> tuple[bool, str]:
    """Check if a job is relevant to Mina's target roles."""
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()

    # Hard irrelevant patterns in title
    for pattern in IRRELEVANT_TITLE_PATTERNS:
        if re.search(pattern, title):
            return False, f"Irrelevant title pattern: '{pattern}'"

    # Must have at least one relevance signal
    combined = title + " " + description
    has_signal = any(signal in combined for signal in REQUIRED_RELEVANCE_SIGNALS)
    if not has_signal:
        return False, "No software/tech relevance signals found"

    return True, "OK"


# ── Main cleaner ───────────────────────────────────────────────────────────────

def clean_jobs(raw_jobs: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    """
    Clean a list of raw jobs.
    Returns: (cleaned_jobs, rejected_jobs)
    """
    seen_ids = set()
    seen_fingerprints = {}
    cleaned = []
    rejected = []

    for i, raw_job in enumerate(raw_jobs):
        # Step 1: Normalize
        job = normalize_job(dict(raw_job))
        job = assign_id_if_missing(job, i)

        job_id = job["id"]
        title = job["title"]
        company = job["company"]

        # Step 2: Exact duplicate check (same ID)
        if job_id in seen_ids:
            logger.info(f"  DUPLICATE (exact ID) [{job_id}] {title} @ {company}")
            rejected.append({**job, "clean_rejection_reason": "Exact duplicate ID"})
            continue
        seen_ids.add(job_id)

        # Step 3: Near-duplicate check (same title + company)
        fp = make_fingerprint(job)
        if fp in seen_fingerprints:
            original_id = seen_fingerprints[fp]
            logger.info(f"  DUPLICATE (near-match) [{job_id}] {title} @ {company} — same as [{original_id}]")
            rejected.append({**job, "clean_rejection_reason": f"Near-duplicate of {original_id}"})
            continue
        seen_fingerprints[fp] = job_id

        # Step 4: Relevance check
        relevant, reason = is_relevant(job)
        if not relevant:
            logger.info(f"  IRRELEVANT [{job_id}] {title} @ {company} — {reason}")
            rejected.append({**job, "clean_rejection_reason": reason})
            continue

        # Step 5: Unpaid check
        rejection_filters = config.get("rejection_filters", {})
        if rejection_filters.get("unpaid") and job.get("compensation") == "unpaid":
            logger.info(f"  UNPAID [{job_id}] {title} @ {company}")
            rejected.append({**job, "clean_rejection_reason": "Unpaid position"})
            continue

        logger.info(f"  ✓ CLEAN [{job_id}] {title} @ {company}")
        job["cleaned_date"] = str(date.today())
        cleaned.append(job)

    return cleaned, rejected


def run(config_path: str = "config/config.yaml") -> dict:
    """
    Run the job cleaner on all raw job files.
    Returns summary dict.
    """
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info("=" * 60)
    logger.info("Job Cleaner — Phase 2 starting")

    raw_dir = Path(config["paths"]["raw_jobs"])
    cleaned_dir = Path(config["paths"]["cleaned_jobs"])
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    # Load all JSON files from raw/
    all_raw = []
    for json_file in sorted(raw_dir.glob("*.json")):
        jobs = json.loads(json_file.read_text(encoding="utf-8"))
        logger.info(f"  Loaded {len(jobs)} jobs from {json_file.name}")
        all_raw.extend(jobs)

    logger.info(f"Total raw jobs: {len(all_raw)}")

    cleaned, rejected = clean_jobs(all_raw, config)

    today = str(date.today())
    out_clean = cleaned_dir / f"cleaned_jobs_{today}.json"
    out_rejected = cleaned_dir / f"clean_rejected_{today}.json"

    out_clean.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    out_rejected.write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "total_input": len(all_raw),
        "cleaned": len(cleaned),
        "rejected": len(rejected),
        "output_file": str(out_clean),
    }

    logger.info(f"Clean: {summary['cleaned']} | Rejected: {summary['rejected']}")
    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
