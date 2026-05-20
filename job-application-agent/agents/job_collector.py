"""
agents/job_collector.py
========================
Phase 2 — Job Collector

Responsibility:
  - Collect jobs from one or more sources
  - Currently: Mock data + simulated Apify-format data
  - Future: Real Apify API (LinkedIn, Indeed, Glassdoor scrapers)
  - Save raw jobs to data/raw/

Sources supported:
  - mock       : loads data/raw/mock_jobs.json (Phase 1 data)
  - apify_mock : generates realistic Apify-format jobs for testing
  - apify_live : calls real Apify API (needs APIFY_TOKEN in config)

Design notes:
  - Zero Claude API calls
  - Each source saves its own dated file to data/raw/
  - Apify format is normalized by job_cleaner.py downstream
  - Token cost: zero
"""

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("job_collector")


# ── Mock Apify-format jobs (realistic LinkedIn/Indeed format) ──────────────────

APIFY_MOCK_JOBS = [
    {
        "jobTitle": "Junior Backend Developer",
        "companyName": "Dedicare AB",
        "jobLocation": "Gothenburg, Sweden",
        "jobType": "Hybrid",
        "jobDescription": (
            "We are looking for a Junior Backend Developer to join our healthcare tech team. "
            "You will build REST APIs using Python and FastAPI, work with PostgreSQL, Docker, "
            "and contribute to CI/CD pipelines on Azure. Agile team, friendly environment. "
            "0-3 years experience required."
        ),
        "requirements": ["Python", "FastAPI", "REST APIs", "PostgreSQL", "Docker"],
        "nice_to_have": ["Azure", "GitHub Actions", "Agile"],
        "experienceLevel": "1-3",
        "languages": "Swedish or English",
        "source": "apify_linkedin",
        "applyUrl": "https://dedicare.se/careers/mock/101",
        "publishedAt": "2026-05-18",
        "compensation": "paid",
    },
    {
        "jobTitle": "Data Engineer / ML Engineer",
        "companyName": "Hexagon AB",
        "jobLocation": "Gothenburg, Sweden",
        "jobType": "On-site",
        "jobDescription": (
            "Hexagon is hiring a Data/ML Engineer to support our industrial AI division. "
            "Build data pipelines with Python and SQL, deploy ML models with MLflow and Docker, "
            "work on Azure cloud infrastructure. Experience with PyTorch or TensorFlow is a plus."
        ),
        "requirements": ["Python", "SQL", "Machine Learning", "Azure", "Docker"],
        "nice_to_have": ["PyTorch", "MLflow", "MLOps", "Kubernetes"],
        "experienceLevel": "2-4",
        "languages": "English",
        "source": "apify_linkedin",
        "applyUrl": "https://hexagon.com/careers/mock/102",
        "publishedAt": "2026-05-17",
        "compensation": "paid",
    },
    {
        "jobTitle": ".NET Developer",
        "companyName": "Knowit AB",
        "jobLocation": "Göteborg",
        "jobType": "hybrid",
        "jobDescription": (
            "Knowit is growing and looking for a .NET Developer. You will work on customer projects "
            "in the public sector, building backend services with C#, ASP.NET Core, and SQL Server. "
            "Azure DevOps is used for CI/CD. Consulting role with great team culture."
        ),
        "requirements": ["C#", ".NET", "ASP.NET Core", "SQL Server", "Azure DevOps"],
        "nice_to_have": ["Docker", "REST APIs", "Entity Framework", "Agile"],
        "experienceLevel": "1-4",
        "languages": "Swedish",
        "source": "apify_indeed",
        "applyUrl": "https://knowit.se/careers/mock/103",
        "publishedAt": "2026-05-16",
        "compensation": "paid",
    },
    {
        "jobTitle": "Junior .NET Developer",       # Near-duplicate of mock job_001
        "companyName": "Volvo Cars",               # Same company → should be caught as near-duplicate
        "jobLocation": "Gothenburg, Sweden",
        "jobType": "Hybrid",
        "jobDescription": "Duplicate listing from a different source.",
        "requirements": ["C#", ".NET", "SQL Server"],
        "nice_to_have": [],
        "experienceLevel": "1-3",
        "languages": "English",
        "source": "apify_linkedin",
        "applyUrl": "https://careers.volvocars.com/mock/001b",
        "publishedAt": "2026-05-18",
        "compensation": "paid",
    },
    {
        "jobTitle": "AI Research Engineer",
        "companyName": "Zenseact",
        "jobLocation": "Gothenburg, Sweden",
        "jobType": "Hybrid",
        "jobDescription": (
            "Zenseact (Volvo Cars spin-off) is hiring an AI Research Engineer for autonomous driving. "
            "You will work on deep learning models for perception and prediction using PyTorch. "
            "Experience with CNNs, transformers, and Python is required. MLOps experience is a plus. "
            "Master's or PhD in relevant field preferred. 1-3 years experience."
        ),
        "requirements": ["Python", "PyTorch", "Deep Learning", "CNNs", "Machine Learning"],
        "nice_to_have": ["MLOps", "Docker", "Azure", "Transformers", "LLM"],
        "experienceLevel": "1-3",
        "languages": "English",
        "source": "apify_linkedin",
        "applyUrl": "https://zenseact.com/careers/mock/104",
        "publishedAt": "2026-05-15",
        "compensation": "paid",
    },
    {
        "jobTitle": "Barista",                     # Irrelevant — should be filtered
        "companyName": "Espresso House",
        "jobLocation": "Gothenburg, Sweden",
        "jobType": "Part-time",
        "jobDescription": "Make coffee and serve customers. Customer service required.",
        "requirements": ["Customer service", "Swedish"],
        "nice_to_have": [],
        "experienceLevel": "0-1",
        "languages": "Swedish",
        "source": "apify_indeed",
        "applyUrl": "https://espressohouse.se/mock/999",
        "publishedAt": "2026-05-14",
        "compensation": "paid",
    },
    {
        "jobTitle": "Cloud & DevOps Engineer",
        "companyName": "Consid AB",
        "jobLocation": "Göteborg",
        "jobType": "Hybrid",
        "jobDescription": (
            "Consid is a Swedish IT consulting firm looking for a Cloud & DevOps Engineer. "
            "Work with Azure infrastructure, Kubernetes, Docker, Helm, and CI/CD pipelines. "
            "Python or C# scripting skills needed. You will serve multiple clients in different industries."
        ),
        "requirements": ["Azure", "Kubernetes", "Docker", "CI/CD", "Helm"],
        "nice_to_have": ["Python", "C#", "Terraform", "GitHub Actions"],
        "experienceLevel": "2-5",
        "languages": "Swedish or English",
        "source": "apify_linkedin",
        "applyUrl": "https://consid.se/careers/mock/105",
        "publishedAt": "2026-05-14",
        "compensation": "paid",
    },
    {
        "jobTitle": "Junior AI Developer",
        "companyName": "Peltarion",
        "jobLocation": "Stockholm, Sweden",
        "jobType": "Remote",
        "jobDescription": (
            "Peltarion is an AI platform company looking for a Junior AI Developer. "
            "Build LLM-powered applications, work with RAG architectures, LangChain, and Python. "
            "Help customers integrate AI into their products. "
            "Strong Python skills and understanding of ML fundamentals required."
        ),
        "requirements": ["Python", "LLM", "LangChain", "RAG", "Machine Learning"],
        "nice_to_have": ["Azure", "Docker", "FastAPI", "ChromaDB", "MLOps"],
        "experienceLevel": "0-2",
        "languages": "English",
        "source": "apify_linkedin",
        "applyUrl": "https://peltarion.com/careers/mock/106",
        "publishedAt": "2026-05-13",
        "compensation": "paid",
    },
]


# ── Collector functions ────────────────────────────────────────────────────────

def collect_mock(raw_dir: Path) -> dict:
    """Load existing Phase 1 mock data."""
    mock_file = raw_dir / "mock_jobs.json"
    if not mock_file.exists():
        logger.warning("mock_jobs.json not found — skipping mock source")
        return {"source": "mock", "count": 0}
    jobs = json.loads(mock_file.read_text(encoding="utf-8"))
    logger.info(f"  Mock source: {len(jobs)} jobs already in {mock_file.name}")
    return {"source": "mock", "count": len(jobs), "file": str(mock_file)}


def collect_apify_mock(raw_dir: Path) -> dict:
    """
    Save mock Apify-format jobs as if they came from a real Apify scraper.
    This tests the full normalization pipeline without real API calls.
    """
    today = str(date.today())
    out_file = raw_dir / f"apify_jobs_{today}.json"
    out_file.write_text(
        json.dumps(APIFY_MOCK_JOBS, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    logger.info(f"  Apify mock source: {len(APIFY_MOCK_JOBS)} jobs → {out_file.name}")
    return {"source": "apify_mock", "count": len(APIFY_MOCK_JOBS), "file": str(out_file)}


def collect_apify_live(raw_dir: Path, config: dict) -> dict:
    """
    FUTURE: Call real Apify API to scrape LinkedIn/Indeed.

    To activate:
      1. Set apify_token in config/config.yaml
      2. Set use_mock_data: false
      3. Choose actor_id (e.g. "bebity/linkedin-jobs-scraper")

    This function is a placeholder — safe to call, does nothing without token.
    """
    token = config.get("apify", {}).get("token", "")
    if not token or token == "YOUR_APIFY_TOKEN_HERE":
        logger.info("  Apify live: no token configured — skipping (set apify.token in config.yaml)")
        return {"source": "apify_live", "count": 0, "skipped": True}

    try:
        import requests  # only needed for live mode
        actor_id = config.get("apify", {}).get("actor_id", "bebity/linkedin-jobs-scraper")
        search_terms = config.get("apify", {}).get("search_terms", ["Software Developer Gothenburg"])
        location = config.get("apify", {}).get("location", "Gothenburg, Sweden")

        logger.info(f"  Apify live: calling actor '{actor_id}'...")

        # This is the Apify REST API call structure
        # Uncomment and fill in when you have a real token:
        #
        # run_url = f"https://api.apify.com/v2/acts/{actor_id}/runs"
        # payload = {
        #     "searchTerms": search_terms,
        #     "location": location,
        #     "maxResults": 50,
        # }
        # headers = {"Authorization": f"Bearer {token}"}
        # response = requests.post(run_url, json=payload, headers=headers)
        # run_id = response.json()["data"]["id"]
        # ... poll for results, save to raw_dir

        logger.warning("  Apify live: placeholder only — implement when token is available")
        return {"source": "apify_live", "count": 0, "placeholder": True}

    except Exception as e:
        logger.error(f"  Apify live error: {e}")
        return {"source": "apify_live", "count": 0, "error": str(e)}


# ── Main entry point ───────────────────────────────────────────────────────────

def run(config_path: str = "config/config.yaml") -> dict:
    """
    Run the job collector.
    Returns summary of what was collected.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info("=" * 60)
    logger.info("Job Collector — Phase 2 starting")

    raw_dir = Path(config["paths"]["raw_jobs"])
    raw_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Always load mock Phase 1 data
    results["mock"] = collect_mock(raw_dir)

    # Add Apify-format mock data (tests normalization pipeline)
    results["apify_mock"] = collect_apify_mock(raw_dir)

    # Attempt live Apify (skipped unless token configured)
    results["apify_live"] = collect_apify_live(raw_dir, config)

    total = sum(r.get("count", 0) for r in results.values())
    logger.info(f"Total collected: {total} jobs across {len(results)} sources")
    logger.info("=" * 60)

    return {"total": total, "sources": results}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
