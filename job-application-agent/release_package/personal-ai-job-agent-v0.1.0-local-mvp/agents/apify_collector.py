"""
agents/apify_collector.py
==========================
Phase 4 — Apify Live Collector

Responsibility:
  - Connect to real Apify API
  - Scrape LinkedIn and Indeed job listings for Mina's target roles
  - Save raw results to data/raw/apify_live_YYYY-MM-DD.json
  - Designed to be called daily by the scheduler

Apify actors used:
  - LinkedIn: "bebity/linkedin-jobs-scraper"
  - Indeed:   "misceres/indeed-scraper"

Setup instructions:
  1. Create account at https://apify.com
  2. Get your API token from https://console.apify.com/account/integrations
  3. Set it in config.yaml under apify.token
  4. Run: python agents/apify_collector.py

Token optimization:
  - Only fetches fields we need (title, company, description, url)
  - Limits results per search to avoid bloat
  - Caches results per day — won't re-fetch if today's file exists
"""

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.error
import urllib.parse

import yaml

logger = logging.getLogger("apify_collector")


def get_dynamic_searches(config: dict) -> list[dict]:
    search_cfg = config.get("search", {})
    keywords = search_cfg.get("keywords", [])
    locations = search_cfg.get("locations", [])
    searches = []
    for kw in keywords:
        for loc in locations:
            searches.append({"keywords": kw, "query": kw, "location": loc})
    return searches


# ── Apify API client ───────────────────────────────────────────────────────────

class ApifyClient:
    """Minimal Apify REST client using only stdlib (no extra packages needed)."""

    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, token: str):
        self.token = token

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{self.BASE_URL}{path}?token={self.token}"
        data = json.dumps(body).encode("utf-8") if body else None
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Apify API error {e.code}: {e.read().decode()}")

    def run_actor(self, actor_id: str, input_data: dict) -> str:
        """Start an actor run and return the run ID."""
        actor_id_safe = actor_id.replace("/", "~")
        result = self._request("POST", f"/acts/{actor_id_safe}/runs", input_data)
        return result["data"]["id"]

    def wait_for_run(self, run_id: str, max_wait: int = 120, poll_interval: int = 5) -> str:
        """Poll until run finishes. Returns dataset ID."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            result = self._request("GET", f"/actor-runs/{run_id}")
            status = result["data"]["status"]
            if status == "SUCCEEDED":
                return result["data"]["defaultDatasetId"]
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Actor run {run_id} ended with status: {status}")
            logger.info(f"    Run {run_id[:8]}... status: {status} — waiting {poll_interval}s")
            time.sleep(poll_interval)
        raise TimeoutError(f"Actor run {run_id} did not finish within {max_wait}s")

    def get_dataset_items(self, dataset_id: str, limit: int = 50) -> list[dict]:
        """Fetch items from a dataset."""
        result = self._request("GET", f"/datasets/{dataset_id}/items?limit={limit}")
        return result if isinstance(result, list) else result.get("items", [])


# ── Field normalization for Apify outputs ─────────────────────────────────────

def normalize_linkedin_item(item: dict, search: dict) -> dict:
    """Convert LinkedIn scraper output to our standard job format."""
    return {
        "id": "",  # will be assigned by job_cleaner
        "title":                item.get("title") or item.get("jobTitle", ""),
        "company":              item.get("companyName") or item.get("company", ""),
        "location":             item.get("location") or item.get("jobLocation", ""),
        "type":                 item.get("workType") or item.get("employmentType", ""),
        "description":          item.get("description") or item.get("jobDescription", "")[:2000],
        "requirements":         [],  # extracted by job_cleaner from description
        "nice_to_have":         [],
        "experience_years":     item.get("experienceLevel", ""),
        "language_requirement": "English",
        "source":               "apify_linkedin",
        "url":                  item.get("applyUrl") or item.get("jobUrl", ""),
        "posted_date":          item.get("postedAt") or item.get("publishedAt", str(date.today())),
        "compensation":         "paid",
        "search_query":         search.get("keywords", ""),
    }


def normalize_indeed_item(item: dict, search: dict) -> dict:
    """Convert Indeed scraper output to our standard job format."""
    return {
        "id": "",
        "title":                item.get("positionName") or item.get("title", ""),
        "company":              item.get("company", ""),
        "location":             item.get("location", ""),
        "type":                 item.get("jobType", ""),
        "description":          item.get("description") or item.get("jobDescription", "")[:2000],
        "requirements":         [],
        "nice_to_have":         [],
        "experience_years":     item.get("experienceLevel", ""),
        "language_requirement": "English",
        "source":               "apify_indeed",
        "url":                  item.get("url") or item.get("jobUrl", ""),
        "posted_date":          item.get("postingDateParsed") or str(date.today()),
        "compensation":         "paid",
        "search_query":         search.get("query", ""),
    }


# ── Main collection functions ──────────────────────────────────────────────────

def collect_linkedin(client: ApifyClient, config: dict, max_per_search: int = 15) -> list[dict]:
    """Run LinkedIn scraper for all of Mina's target searches."""
    actor_id = config.get("apify", {}).get(
        "linkedin_actor", "bebity/linkedin-jobs-scraper"
    )
    all_jobs = []

    searches = get_dynamic_searches(config)
    for search in searches:
        logger.info(f"  LinkedIn: '{search['keywords']}' in {search['location']}")
        try:
            input_data = {
                "searchTerms":  [search["keywords"]],
                "location":     search["location"],
                "maxResults":   max_per_search,
                "proxy":        {"useApifyProxy": True},
            }
            run_id     = client.run_actor(actor_id, input_data)
            dataset_id = client.wait_for_run(run_id, max_wait=180)
            items      = client.get_dataset_items(dataset_id, limit=max_per_search)
            normalized = [normalize_linkedin_item(i, search) for i in items]
            all_jobs.extend(normalized)
            logger.info(f"    → {len(normalized)} jobs collected")
            time.sleep(2)  # polite delay between searches
        except Exception as e:
            logger.error(f"    LinkedIn search failed: {e}")
            continue

    return all_jobs


def collect_indeed(client: ApifyClient, config: dict, max_per_search: int = 15) -> list[dict]:
    """Run Indeed scraper for all of Mina's target searches."""
    actor_id = config.get("apify", {}).get(
        "indeed_actor", "misceres/indeed-scraper"
    )
    all_jobs = []

    searches = get_dynamic_searches(config)
    for search in searches:
        logger.info(f"  Indeed: '{search['query']}' in {search['location']}")
        try:
            input_data = {
                "query":        search["query"],
                "location":     search["location"],
                "country":      "SE",
                "maxItems":     max_per_search,
                "proxy":        {"useApifyProxy": True},
            }
            run_id     = client.run_actor(actor_id, input_data)
            dataset_id = client.wait_for_run(run_id, max_wait=180)
            items      = client.get_dataset_items(dataset_id, limit=max_per_search)
            normalized = [normalize_indeed_item(i, search) for i in items]
            all_jobs.extend(normalized)
            logger.info(f"    → {len(normalized)} jobs collected")
            time.sleep(2)
        except Exception as e:
            logger.error(f"    Indeed search failed: {e}")
            continue

    return all_jobs


def run(config_path: str = "config/config.yaml",
        force_refresh: bool = False) -> dict:
    """
    Run the live Apify collector.

    Args:
        force_refresh: Re-fetch even if today's file already exists

    Returns summary dict.
    """
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    logger.info("=" * 60)
    logger.info("Apify Live Collector — Phase 4 starting")

    token = config.get("apify", {}).get("token", "")
    if not token or token == "YOUR_APIFY_TOKEN_HERE":
        logger.warning("No Apify token configured.")
        logger.warning("Set apify.token in config/config.yaml to enable live collection.")
        logger.warning("Get your token at: https://console.apify.com/account/integrations")
        return {"status": "skipped", "reason": "no_token", "total": 0}

    raw_dir = Path(config["paths"]["raw_jobs"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = str(date.today())
    output_file = raw_dir / f"apify_live_{today}.json"

    # Cache check — don't re-fetch if already done today
    if output_file.exists() and not force_refresh:
        existing = json.loads(output_file.read_text())
        logger.info(f"Today's Apify data already exists ({len(existing)} jobs). Use --force to refresh.")
        return {"status": "cached", "total": len(existing), "file": str(output_file)}

    client = ApifyClient(token)
    all_jobs = []
    
    max_per_kw = config.get("search", {}).get("max_jobs_per_keyword", 100)
    max_total = config.get("search", {}).get("max_total_jobs_per_day", 500)

    # LinkedIn
    logger.info("Collecting from LinkedIn...")
    linkedin_jobs = collect_linkedin(client, config, max_per_search=max_per_kw)
    all_jobs.extend(linkedin_jobs)
    logger.info(f"LinkedIn total: {len(linkedin_jobs)} jobs")

    # Indeed
    logger.info("Collecting from Indeed...")
    indeed_jobs = collect_indeed(client, config, max_per_search=max_per_kw)
    all_jobs.extend(indeed_jobs)
    logger.info(f"Indeed total: {len(indeed_jobs)} jobs")

    # Apply max_total_jobs_per_day limit if exceeded
    if len(all_jobs) > max_total:
        logger.info(f"Capping total jobs at {max_total} (was {len(all_jobs)})")
        all_jobs = all_jobs[:max_total]

    # Save
    output_file.write_text(
        json.dumps(all_jobs, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "status": "success",
        "total": len(all_jobs),
        "linkedin": len(linkedin_jobs),
        "indeed": len(indeed_jobs),
        "file": str(output_file),
        "date": today,
    }

    logger.info(f"Total collected: {len(all_jobs)} jobs → {output_file.name}")
    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
