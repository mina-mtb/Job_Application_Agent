import sqlite3
import os

class DBManager:
    def __init__(self, db_path="database/jobs.db"):
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_db(self):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema file not found at {schema_path}")
            
        with open(schema_path, 'r') as f:
            schema = f.read()

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema)

    def insert_job(self, job_data):
        """
        Inserts a job. If job_link already exists, it ignores to preserve status.
        Uses INSERT OR IGNORE.
        """
        query = '''
            INSERT OR IGNORE INTO jobs 
            (job_id, title, company, location, job_link, description, status) 
            VALUES (?, ?, ?, ?, ?, ?, 'new')
        '''
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (
                job_data.get('job_id'),
                job_data.get('title'),
                job_data.get('company'),
                job_data.get('location'),
                job_data.get('job_link'),
                job_data.get('description')
            ))
            conn.commit()
            return cursor.rowcount > 0  # Returns True if inserted, False if ignored

    def get_job_by_link(self, job_link):
        query = 'SELECT * FROM jobs WHERE job_link = ?'
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, (job_link,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_jobs(self):
        query = 'SELECT * FROM jobs'
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]

    def execute_query(self, query, params=()):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            # If it's a SELECT query, return fetchall
            if query.strip().upper().startswith("SELECT"):
                return [dict(row) for row in cursor.fetchall()]
            return cursor.rowcount
