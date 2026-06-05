import json
from database.db_manager import DBManager
from core.job_collector import JobCollector
from core.knowledge_manager import KnowledgeManager
from core.job_matcher import JobMatcher

class DailyRunner:
    def __init__(self, db_manager: DBManager, job_collector: JobCollector, knowledge_manager: KnowledgeManager, llm_provider, config: dict):
        self.db = db_manager
        self.collector = job_collector
        self.km = knowledge_manager
        self.matcher = JobMatcher(config, knowledge_manager, llm_provider)

    def run(self):
        # 1. Collect jobs and deduplicate (insert_job handles deduplication)
        self.collector.collect_jobs()

        # 2. Get all new jobs from DB
        jobs = self.db.execute_query("SELECT * FROM jobs WHERE status = 'new'")

        for job in jobs:
            # Check if job is still 'new' or if it somehow got protected
            # Actually we already selected 'new', but we can check just to be safe
            if job['status'] in ['applied', 'rejected', 'not_suitable']:
                continue

            # Stage 1: Rule-based filtering
            stage1_result = self.matcher.evaluate_stage1(job)
            
            if stage1_result['status'] == 'not_suitable':
                self._update_job(job['job_link'], stage1_result)
                continue

            # Stage 2: AI scoring
            stage2_result = self.matcher.evaluate_stage2(job)
            self._update_job(job['job_link'], stage2_result)

    def _update_job(self, job_link: str, result: dict):
        # Protection check: never overwrite applied/rejected/not_suitable jobs
        current_job = self.db.get_job_by_link(job_link)
        if current_job and current_job.get('status') in ['applied', 'rejected', 'not_suitable']:
            return

        reasons = json.dumps(result.get('reasons_for_match', []))
        weaknesses = json.dumps(result.get('weaknesses_or_risks', []))

        query = '''
            UPDATE jobs 
            SET suitability_score = ?,
                suitability_category = ?,
                reasons_for_match = ?,
                weaknesses_or_risks = ?,
                status = ?
            WHERE job_link = ?
        '''
        self.db.execute_query(query, (
            result.get('suitability_score'),
            result.get('suitability_category'),
            reasons,
            weaknesses,
            result.get('status'),
            job_link
        ))
