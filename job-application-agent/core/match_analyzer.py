"""
core/match_analyzer.py — CV <-> Job match analysis with semantic understanding.

What it does (no custom model training required):
  * extracts the skills/keywords a job posting is asking for,
  * checks each against the candidate's known skills using THREE layers:
        1) exact / normalized match
        2) alias map  (CI/CD <-> DevOps, C# <-> .NET, ...)  — high precision
        3) semantic similarity via an embedding function (optional)  — catches
           wording differences the alias map doesn't know about,
  * returns a 0-100 score PLUS an explainable gap report (matched / related /
    missing) and concrete, truthful suggestions,
  * ranks the candidate's skills by relevance to THIS job so the most important
    ones can be placed first in the CV,
  * surfaces "high-impact missing" keywords for interactive learning (the app can
    ask the user "do you know X?" and, on yes, add it to confirmed skills).

The embedding function is optional and injected (e.g. the app's ChromaDB
all-MiniLM embedder). Without it, layers 1-2 still work; with it, layer 3 adds
the "vector distance" understanding.
"""

import re
import math


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[–—]", "-", s)          # en/em dash -> hyphen
    s = re.sub(r"[^a-z0-9\+\#\./\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Seed alias groups (extensible). Each inner list = synonyms / closely-equivalent.
# The FIRST item of each group is used as the canonical display label.
DEFAULT_ALIAS_GROUPS = [
    ["c#", "c sharp", "csharp", ".net", "dotnet", "asp.net", "asp.net core", ".net core"],
    ["ci/cd", "cicd", "continuous integration", "continuous delivery", "devops",
     "build pipelines", "release pipelines", "github actions", "azure devops", "gitlab ci"],
    ["rest apis", "rest api", "rest", "restful", "web api", "web services"],
    ["microservices", "micro services", "distributed systems", "service oriented"],
    ["sql", "sql server", "t-sql", "mssql", "relational databases", "rdbms"],
    ["entity framework", "ef core", "orm"],
    ["docker", "containers", "containerization"],
    ["kubernetes", "k8s", "container orchestration", "helm"],
    ["azure", "microsoft azure"],
    ["aws", "amazon web services"],
    ["gcp", "google cloud", "google cloud platform"],
    ["machine learning", "ml"],
    ["deep learning", "neural networks", "cnn", "cnns"],
    ["llm", "large language models", "generative ai", "genai", "gpt"],
    ["rag", "retrieval augmented generation"],
    ["python", "py"],
    ["agile", "scrum", "kanban"],
    ["message queue", "messaging", "rabbitmq", "service bus", "kafka"],
    ["power platform", "power apps", "power automate", "power bi", "dataverse"],
]

# A small lexicon of single/multi-word skill phrases used to spot skills inside a
# job posting. Extend freely. (Lowercase.)
BASE_LEXICON = set()
for _g in DEFAULT_ALIAS_GROUPS:
    for _t in _g:
        BASE_LEXICON.add(_norm(_t))
BASE_LEXICON |= {
    "java", "javascript", "typescript", "react", "node", "node.js", "git",
    "clean architecture", "ddd", "tdd", "unit testing", "linux",
    "terraform", "graphql", "soap", "ado.net", "fastapi", "pytorch", "tensorflow",
    "mlops", "llmops", "xai", "data engineering", "etl", "english", "swedish",
}


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class MatchAnalyzer:
    def __init__(self, embed_fn=None, alias_groups=None, lexicon=None,
                 sem_threshold=0.60):
        self.embed_fn = embed_fn
        self.sem_threshold = sem_threshold
        groups = alias_groups or DEFAULT_ALIAS_GROUPS
        # term -> group id, plus canonical label per group
        self._group_of = {}
        self.group_canonical = []
        for i, g in enumerate(groups):
            self.group_canonical.append(_norm(g[0]))
            for t in g:
                self._group_of[_norm(t)] = i
        self.lexicon = set(_norm(x) for x in (lexicon or BASE_LEXICON))
        self._emb_cache = {}

    # ---- matching primitives ------------------------------------------------
    def _alias_equal(self, a, b):
        a, b = _norm(a), _norm(b)
        if a == b:
            return True
        ga, gb = self._group_of.get(a), self._group_of.get(b)
        return ga is not None and ga == gb

    def _embed(self, text):
        if not self.embed_fn:
            return None
        key = _norm(text)
        if key in self._emb_cache:
            return self._emb_cache[key]
        try:
            v = list(self.embed_fn([text])[0])
        except Exception:
            v = None
        self._emb_cache[key] = v
        return v

    def _semantic_sim(self, a, b):
        va, vb = self._embed(a), self._embed(b)
        if va is None or vb is None:
            return 0.0
        return _cos(va, vb)

    def classify(self, job_skill, candidate_skills):
        """Return (status, evidence, score) where status in
        exact | alias | semantic | missing."""
        js = _norm(job_skill)
        # 1) exact / normalized
        for c in candidate_skills:
            if _norm(c) == js:
                return ("exact", c, 1.0)
        # 2) alias
        for c in candidate_skills:
            if self._alias_equal(js, c):
                return ("alias", c, 0.95)
        # 3) semantic
        if self.embed_fn:
            best_c, best_s = None, 0.0
            for c in candidate_skills:
                s = self._semantic_sim(js, c)
                if s > best_s:
                    best_c, best_s = c, s
            if best_s >= self.sem_threshold:
                return ("semantic", best_c, round(best_s, 3))
        return ("missing", None, 0.0)

    # ---- job parsing --------------------------------------------------------
    def extract_job_skills(self, job_text):
        """Find skill phrases from the lexicon that appear in the job text.
        Longer phrases first so 'asp.net core' wins over 'asp.net'."""
        norm_text = _norm(job_text)
        found = []
        for term in sorted(self.lexicon, key=len, reverse=True):
            pat = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
            if re.search(pat, norm_text):
                found.append(term)
        # collapse to one canonical representative per alias group
        seen_groups, result = set(), []
        for t in found:
            g = self._group_of.get(t)
            if g is not None:
                if g in seen_groups:
                    continue
                seen_groups.add(g)
                result.append(self.group_canonical[g])
            else:
                result.append(t)
        return result

    # ---- main analysis ------------------------------------------------------
    def analyze(self, job_text, candidate_skills, must_haves=None):
        job_skills = self.extract_job_skills(job_text)
        must = set(_norm(x) for x in (must_haves or []))
        matched, related, missing = [], [], []
        for js in job_skills:
            status, ev, sc = self.classify(js, candidate_skills)
            row = {"job_skill": js, "status": status, "evidence": ev,
                   "similarity": sc, "must_have": js in must}
            if status in ("exact", "alias"):
                matched.append(row)
            elif status == "semantic":
                related.append(row)
            else:
                missing.append(row)

        # weighted score: must-haves count double; related (semantic) counts 0.7
        def w(row):
            return 2.0 if row["must_have"] else 1.0
        total = sum(w(r) for r in (matched + related + missing)) or 1.0
        got = sum(w(r) for r in matched) + sum(0.7 * w(r) for r in related)
        score = int(round(100 * got / total))

        suggestions = self._suggestions(matched, related, missing)
        return {
            "score": score,
            "matched": matched,         # you clearly have these
            "related": related,         # you have something close - name it the job's way
            "missing": missing,         # not found - confirm or it's a real gap
            "suggestions": suggestions,
            "job_skills": job_skills,
        }

    def _suggestions(self, matched, related, missing):
        s = []
        for r in related:
            s.append(f"You list '{r['evidence']}', but this job says "
                     f"'{r['job_skill']}'. Use the job's exact wording "
                     f"'{r['job_skill']}' in your CV so ATS scores it.")
        must_missing = [r["job_skill"] for r in missing if r["must_have"]]
        if must_missing:
            s.append("Required keywords not found in your CV: "
                     + ", ".join(must_missing)
                     + ". If you actually have these, add them; otherwise this is a real gap.")
        opt_missing = [r["job_skill"] for r in missing if not r["must_have"]]
        if opt_missing:
            s.append("Nice-to-have keywords missing: " + ", ".join(opt_missing) + ".")
        return s

    def prioritize_skills(self, job_text, candidate_skills):
        """Rank the candidate's own skills by relevance to THIS job (for ordering
        the CV's Skills section)."""
        job_skills = self.extract_job_skills(job_text)
        jset = set(job_skills)
        scored = []
        for c in candidate_skills:
            cn = _norm(c)
            rel = 0.0
            if cn in jset:
                rel = 1.0
            elif any(self._alias_equal(cn, j) for j in job_skills):
                rel = 0.9
            elif self.embed_fn and job_skills:
                rel = max(self._semantic_sim(cn, j) for j in job_skills)
            scored.append((c, round(rel, 3)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def high_impact_missing(self, report, top=8):
        """Missing keywords most worth asking the user about (must-haves first)."""
        miss = sorted(report["missing"], key=lambda r: (not r["must_have"]))
        return [r["job_skill"] for r in miss][:top]
