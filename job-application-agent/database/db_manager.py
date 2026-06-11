import sqlite3
import os

class DBManager:
    def __init__(self, db_path="database/jobs.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._migrate_schema()

    def _init_schema(self):
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                self.conn.executescript(f.read())
        self.conn.commit()

    def _migrate_schema(self):
        """Add new columns if they don't exist (safe for existing databases)."""
        new_columns = [
            ("applied_cv_path", "TEXT"),
            ("cv_generation_method", "TEXT"),
            ("acceptance_score_predicted", "INTEGER"),
            ("template_used", "TEXT"),
            # CV-vault redesign columns
            ("selected_cv_id", "TEXT"),
            ("applied_cv_id", "TEXT"),
            ("response_status", "TEXT DEFAULT 'pending'"),
            ("response_date", "DATETIME"),
            ("response_notes", "TEXT"),
        ]
        for col_name, col_type in new_columns:
            try:
                self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                # Column already exists
                pass
        # Backfill response_status for older rows that came in as NULL.
        try:
            self.conn.execute(
                "UPDATE jobs SET response_status = 'pending' WHERE response_status IS NULL"
            )
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def insert_job(self, job_data: dict) -> bool:
        try:
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (job_id, title, company, location, job_link, description, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'new')""",
                (
                    job_data.get('job_id'),
                    job_data.get('title'),
                    job_data.get('company'),
                    job_data.get('location'),
                    job_data.get('job_link'),
                    job_data.get('description')
                )
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Insert error: {e}")
            return False

    def get_job_by_link(self, job_link: str):
        cursor = self.conn.execute("SELECT * FROM jobs WHERE job_link = ?", (job_link,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_jobs(self):
        cursor = self.conn.execute("SELECT * FROM jobs ORDER BY date_seen DESC")
        return [dict(row) for row in cursor.fetchall()]

    def execute_query(self, query: str, params: tuple = ()):
        try:
            cursor = self.conn.execute(query, params)
            self.conn.commit()
            if query.strip().upper().startswith("SELECT"):
                return [dict(row) for row in cursor.fetchall()]
            return cursor.rowcount
        except Exception as e:
            print(f"Query error: {e}")
            return [] if query.strip().upper().startswith("SELECT") else 0
