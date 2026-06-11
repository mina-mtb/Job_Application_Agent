-- ============================================================
-- Job Application Agent — Database Schema
-- Extensible design: jobs + CV vault + per-job CV candidates
-- ============================================================

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    job_link TEXT UNIQUE NOT NULL,
    description TEXT,
    suitability_score INTEGER,
    suitability_category TEXT,
    reasons_for_match TEXT,
    weaknesses_or_risks TEXT,
    status TEXT DEFAULT 'new',
    date_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    date_applied DATETIME,
    generated_cv_path TEXT,
    user_notes TEXT,
    applied_cv_path TEXT,
    cv_generation_method TEXT,
    acceptance_score_predicted INTEGER,
    template_used TEXT,
    selected_cv_id TEXT,
    applied_cv_id TEXT,
    response_status TEXT DEFAULT 'pending',
    response_date DATETIME,
    response_notes TEXT
);

CREATE TABLE IF NOT EXISTS cvs (
    cv_id TEXT PRIMARY KEY,
    label TEXT,
    origin_job_id TEXT,
    generation_method TEXT,
    parent_cv_id TEXT,
    markdown_content TEXT,
    file_path TEXT,
    template_used TEXT,
    role_tags TEXT,
    is_archived INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_cv_candidates (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    slot TEXT NOT NULL,
    cv_id TEXT,
    match_score INTEGER,
    ai_acceptance_score INTEGER,
    match_explanation TEXT,
    is_selected INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, slot)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_candidates_job ON job_cv_candidates(job_id);
CREATE INDEX IF NOT EXISTS idx_cvs_origin ON cvs(origin_job_id);
