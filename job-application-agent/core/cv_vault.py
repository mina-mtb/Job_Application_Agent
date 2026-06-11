"""
core/cv_vault.py — CV Vault & per-job CV candidate management.

The vault stores every CV that is ever produced (template-based, free-form,
imported, or an edited copy). When a new job arrives, the vault can be searched
to find the best previously-built CV and estimate how well it fits — entirely
offline and free (local embeddings, with a keyword fallback). Paid AI calls are
only used elsewhere when the user explicitly asks to generate or deep-analyze.

Design notes
------------
* All SQL goes through DBManager.execute_query (which commits and returns dict
  rows for SELECT, rowcount otherwise).
* Matching uses the KnowledgeManager's local embedding function when available
  (all-MiniLM-L6-v2, free). If embeddings are unavailable for any reason it
  silently falls back to a keyword/Jaccard overlap score, so the dashboard never
  breaks.
* A job has at most one candidate per slot: 'vault', 'template', 'free_form'.
"""

import os
import re
import uuid
import math
import logging

logger = logging.getLogger(__name__)

SLOTS = ("vault", "template", "free_form")

_STOPWORDS = {
    "the", "and", "for", "you", "your", "with", "our", "are", "will", "have",
    "this", "that", "from", "but", "not", "can", "all", "who", "has", "was",
    "their", "they", "them", "out", "use", "etc", "a", "an", "of", "to", "in",
    "on", "at", "is", "as", "be", "or", "we", "by", "it", "if", "us", "do",
    "job", "role", "work", "team", "experience", "skills", "ability", "years",
}


# ----------------------------------------------------------------------------
# Pure helpers (no DB) — easy to unit test
# ----------------------------------------------------------------------------
def _tokens(text: str) -> set:
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\+\#\.]{1,}", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def keyword_score(job_text: str, cv_text: str) -> int:
    """Offline overlap score (0-100) between a job and a CV. Always works."""
    jt, ct = _tokens(job_text), _tokens(cv_text)
    if not jt or not ct:
        return 0
    overlap = jt & ct
    # Fraction of the job's meaningful terms that the CV covers, lightly
    # rewarded so a strong CV lands in a believable 40-95 band.
    coverage = len(overlap) / len(jt)
    score = int(round(40 + coverage * 60))
    return max(0, min(98, score))


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ----------------------------------------------------------------------------
# CVVault
# ----------------------------------------------------------------------------
class CVVault:
    def __init__(self, db, km=None):
        self.db = db
        self.km = km  # KnowledgeManager (optional, for embedding matching)

    # ---- low-level CV records ---------------------------------------------
    def register_cv(self, *, markdown_content="", file_path=None,
                    generation_method="free_form", origin_job_id=None,
                    label=None, parent_cv_id=None, template_used=None,
                    role_tags=None) -> str:
        """Insert a new CV into the vault and return its cv_id."""
        cv_id = f"cv_{uuid.uuid4().hex[:12]}"
        if not label:
            label = self._auto_label(origin_job_id, generation_method)
        self.db.execute_query(
            """INSERT INTO cvs
               (cv_id, label, origin_job_id, generation_method, parent_cv_id,
                markdown_content, file_path, template_used, role_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cv_id, label, origin_job_id, generation_method, parent_cv_id,
             markdown_content, file_path, template_used, role_tags),
        )
        return cv_id

    def _auto_label(self, origin_job_id, method):
        title, company = "CV", ""
        if origin_job_id:
            rows = self.db.execute_query(
                "SELECT title, company FROM jobs WHERE job_id = ?", (origin_job_id,))
            if rows:
                title = rows[0].get("title") or "CV"
                company = rows[0].get("company") or ""
        pretty = {"template": "template", "free_form": "free-form",
                  "vault_reuse": "reused", "imported": "imported", "edited": "edited"}
        m = pretty.get(method, method)
        return f"{company} — {title} ({m})".strip(" —")

    def get_cv(self, cv_id):
        rows = self.db.execute_query("SELECT * FROM cvs WHERE cv_id = ?", (cv_id,))
        return rows[0] if rows else None

    def list_vault(self, include_archived=False):
        q = "SELECT * FROM cvs"
        if not include_archived:
            q += " WHERE is_archived = 0"
        q += " ORDER BY created_at DESC"
        return self.db.execute_query(q)

    def update_cv_content(self, cv_id, markdown_content, file_path=None):
        if file_path is not None:
            self.db.execute_query(
                "UPDATE cvs SET markdown_content = ?, file_path = ?, updated_at = CURRENT_TIMESTAMP WHERE cv_id = ?",
                (markdown_content, file_path, cv_id))
        else:
            self.db.execute_query(
                "UPDATE cvs SET markdown_content = ?, updated_at = CURRENT_TIMESTAMP WHERE cv_id = ?",
                (markdown_content, cv_id))

    def delete_cv(self, cv_id, remove_file=False):
        """Remove a CV from the vault. Detaches it from any candidate slots."""
        cv = self.get_cv(cv_id)
        if not cv:
            return False
        if remove_file and cv.get("file_path") and os.path.exists(cv["file_path"]):
            try:
                os.remove(cv["file_path"])
            except OSError:
                pass
        # Detach from candidates and any job selections.
        self.db.execute_query(
            "UPDATE job_cv_candidates SET cv_id = NULL, match_score = NULL, "
            "ai_acceptance_score = NULL, is_selected = 0 WHERE cv_id = ?", (cv_id,))
        self.db.execute_query(
            "UPDATE jobs SET selected_cv_id = NULL WHERE selected_cv_id = ?", (cv_id,))
        self.db.execute_query("DELETE FROM cvs WHERE cv_id = ?", (cv_id,))
        return True

    # ---- matching (offline / free) ----------------------------------------
    def _embed(self, texts):
        """Return embeddings for a list of texts, or None if unavailable."""
        if not self.km or not getattr(self.km, "embedding_function", None):
            return None
        try:
            return list(self.km.embedding_function(texts))
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Embedding failed, falling back to keywords: %s", e)
            return None

    def score_text(self, job_text: str, cv_text: str) -> int:
        """Score how well a CV matches a job (0-100). Embeddings then keywords."""
        embs = self._embed([job_text or "", cv_text or ""])
        if embs and len(embs) == 2:
            sim = _cosine(embs[0], embs[1])          # roughly 0..1 for MiniLM
            score = int(round(max(0.0, min(1.0, sim)) * 100))
            # Blend a little keyword signal so near-empty CVs don't over-score.
            kw = keyword_score(job_text, cv_text)
            return max(0, min(99, int(round(0.7 * score + 0.3 * kw))))
        return keyword_score(job_text, cv_text)

    @staticmethod
    def _job_text(job: dict) -> str:
        return f"{job.get('title','')} {job.get('company','')} {job.get('description','')}"

    def find_best_match(self, job: dict):
        """Find the best vault CV for a job.

        Returns (cv_row, score, explanation) or (None, 0, msg).
        """
        vault = self.list_vault()
        if not vault:
            return None, 0, "Vault is empty — no past CVs to reuse yet."
        job_text = self._job_text(job)
        best, best_score = None, -1
        for cv in vault:
            text = cv.get("markdown_content") or cv.get("label") or ""
            s = self.score_text(job_text, text)
            if s > best_score:
                best, best_score = cv, s
        method = "semantic similarity" if (self.km and getattr(self.km, "embedding_function", None)) else "keyword overlap"
        expl = f"Best of {len(vault)} vault CV(s) by {method}: '{best.get('label')}'."
        return best, max(0, best_score), expl

    # ---- candidates (the 3 rows per job) ----------------------------------
    def get_candidates(self, job_id: str) -> dict:
        rows = self.db.execute_query(
            "SELECT * FROM job_cv_candidates WHERE job_id = ?", (job_id,))
        return {r["slot"]: r for r in rows}

    def ensure_candidates(self, job_id: str):
        existing = self.get_candidates(job_id)
        for slot in SLOTS:
            if slot not in existing:
                self.db.execute_query(
                    "INSERT OR IGNORE INTO job_cv_candidates (job_id, slot) VALUES (?, ?)",
                    (job_id, slot))
        return self.get_candidates(job_id)

    def set_candidate(self, job_id, slot, *, cv_id=None, match_score=None,
                      ai_acceptance_score=None, match_explanation=None):
        """Upsert a candidate slot's CV + scores."""
        self.ensure_candidates(job_id)
        sets, params = [], []
        if cv_id is not None:
            sets.append("cv_id = ?"); params.append(cv_id)
        if match_score is not None:
            sets.append("match_score = ?"); params.append(int(match_score))
        if ai_acceptance_score is not None:
            sets.append("ai_acceptance_score = ?"); params.append(int(ai_acceptance_score))
        if match_explanation is not None:
            sets.append("match_explanation = ?"); params.append(match_explanation)
        if not sets:
            return
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.extend([job_id, slot])
        self.db.execute_query(
            f"UPDATE job_cv_candidates SET {', '.join(sets)} WHERE job_id = ? AND slot = ?",
            tuple(params))

    def clear_candidate(self, job_id, slot):
        """Detach the CV from a slot (does NOT delete the CV from the vault)."""
        self.db.execute_query(
            "UPDATE job_cv_candidates SET cv_id = NULL, match_score = NULL, "
            "ai_acceptance_score = NULL, match_explanation = NULL, is_selected = 0 "
            "WHERE job_id = ? AND slot = ?", (job_id, slot))

    def select_candidate(self, job_id, slot):
        """Mark one slot as the chosen CV (radio). Clears the others."""
        self.db.execute_query(
            "UPDATE job_cv_candidates SET is_selected = 0 WHERE job_id = ?", (job_id,))
        self.db.execute_query(
            "UPDATE job_cv_candidates SET is_selected = 1 WHERE job_id = ? AND slot = ?",
            (job_id, slot))

    def get_selected(self, job_id):
        rows = self.db.execute_query(
            "SELECT * FROM job_cv_candidates WHERE job_id = ? AND is_selected = 1",
            (job_id,))
        return rows[0] if rows else None

    # ---- backfill ----------------------------------------------------------
    def backfill_from_jobs(self):
        """Import CVs that already exist on jobs (generated_cv_path) into the
        vault, once. Idempotent: skips files already registered."""
        jobs = self.db.execute_query(
            "SELECT * FROM jobs WHERE generated_cv_path IS NOT NULL AND generated_cv_path != ''")
        known = {c.get("file_path") for c in self.list_vault(include_archived=True)}
        created = 0
        for job in jobs:
            path = job.get("generated_cv_path")
            if not path or path in known:
                continue
            md = self._read_editable_md(path)
            cv_id = self.register_cv(
                markdown_content=md,
                file_path=path,
                generation_method=job.get("cv_generation_method") or "free_form",
                origin_job_id=job.get("job_id"),
                template_used=job.get("template_used"),
            )
            known.add(path)
            created += 1
            # Attach to the matching candidate slot for its origin job.
            slot = "template" if (job.get("cv_generation_method") == "template") else "free_form"
            self.set_candidate(job["job_id"], slot, cv_id=cv_id,
                               match_score=job.get("suitability_score"))
            # Keep jobs.selected_cv_id sensible if it was already applied/approved.
            if job.get("status") in ("approved", "applied") and not job.get("selected_cv_id"):
                self.db.execute_query(
                    "UPDATE jobs SET selected_cv_id = ? WHERE job_id = ?",
                    (cv_id, job["job_id"]))
        return created

    @staticmethod
    def _read_editable_md(cv_path: str) -> str:
        if not cv_path:
            return ""
        cv_dir = os.path.dirname(cv_path)
        md_path = os.path.join(cv_dir, "tailored_cv_editable.md")
        for p in (md_path, cv_path if cv_path.endswith(".md") else None):
            if p and os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        return f.read()
                except OSError:
                    pass
        return ""
