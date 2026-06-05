import uuid
from database.db_manager import DBManager
from integrations.apify_client import ApifyClient

class JobCollector:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        # Using mock client for Phase 1
        self.client = ApifyClient()

    def collect_jobs(self):
        raw_jobs = self.client.fetch_linkedin_jobs()
        new_jobs_count = 0
        duplicate_jobs_count = 0

        for raw_job in raw_jobs:
            normalized_job = {
                "job_id": raw_job.get("id", str(uuid.uuid4())),
                "title": raw_job.get("title", ""),
                "company": raw_job.get("companyName", ""),
                "location": raw_job.get("location", ""),
                "job_link": raw_job.get("url", ""),
                "description": raw_job.get("description", "")
            }
            
            if not normalized_job["job_link"]:
                continue

            inserted = self.db.insert_job(normalized_job)
            if inserted:
                new_jobs_count += 1
            else:
                duplicate_jobs_count += 1

        return {
            "fetched": len(raw_jobs),
            "new_inserted": new_jobs_count,
            "duplicates_ignored": duplicate_jobs_count
        }
