import os
import json
from datetime import date
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from utils.exporter import export_markdown, export_html, export_pdf

class CVTailor:
    def __init__(self, db_manager: DBManager, km: KnowledgeManager, llm_provider, config: dict):
        self.db = db_manager
        self.km = km
        self.llm = llm_provider
        self.config = config

    def build_cv_context(self, job: dict, retrieved_chunks: list) -> str:
        context = f"Job Title: {job.get('title', '')}\n"
        context += f"Job Description: {job.get('description', '')}\n\n"
        context += "Evidence from Candidate Knowledge Base:\n"
        for i, chunk in enumerate(retrieved_chunks):
            context += f"[{i+1}] Source: {chunk['metadata'].get('source', 'Unknown')} - {chunk['text']}\n"
        return context

    def generate_profile_and_skills(self, job: dict, evidence_chunks: list) -> dict:
        context = self.build_cv_context(job, evidence_chunks)
        prompt = f"""
You are an expert resume writer. Generate ONLY the 'Profile' and 'Skills' sections of a CV tailored to this job.
Rules:
1. Base your writing strictly on the provided Evidence. Do not hallucinate.
2. Provide your output as JSON with keys "profile" (string) and "skills" (list of strings).
3. If evidence is missing for a requirement, write a weaker but honest sentence, or exclude it.

Context:
{context}
"""
        response = self.llm.generate_completion(prompt)
        try:
            import re
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                res = json.loads(match.group(0))
            else:
                res = json.loads(response)
                
            return {
                "profile": res.get("profile", "Professional candidate tailored to the role."),
                "skills": res.get("skills", ["Relevant Skill"])
            }
        except Exception:
            return {"profile": "Experienced professional tailored to the role.", "skills": ["Relevant Skill"]}

    def assemble_cv(self, profile: str, skills: list, static_experience: str, static_education: str, evidence_sources: list) -> str:
        cv_md = f"# Tailored CV\n\n"
        cv_md += f"## Profile\n{profile}\n\n"
        cv_md += f"## Skills\n"
        for skill in skills:
            cv_md += f"- {skill}\n"
        cv_md += f"\n## Experience\n{static_experience}\n\n"
        cv_md += f"## Education\n{static_education}\n\n"
        
        cv_md += f"## Evidence Sources\n"
        for src in evidence_sources:
            cv_md += f"- {src}\n"
            
        return cv_md

    def generate_tailored_cv(self, job_id: str):
        jobs = self.db.execute_query("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if not jobs:
            print(f"Job {job_id} not found.")
            return False
            
        job = jobs[0]
        if job['status'] not in ['needs_review', 'approved']:
            print(f"Job {job_id} is in status {job['status']}, not generating CV.")
            return False

        # Query RAG
        query = f"Job title: {job.get('title', '')}. Description: {job.get('description', '')}"
        rag_results = self.km.query_knowledge_base(query, top_k=5)
        
        # Generate Profile & Skills
        generated_parts = self.generate_profile_and_skills(job, rag_results)
        
        # Static sections (Read from base_cv.md)
        base_cv_path = self.config.get('base_cv_path', 'profile/base_cv.md')
        static_experience = "### Senior Backend Engineer | Tech Solutions Inc.\\n- Architected and deployed microservices.\\n- Copied verbatim from source."
        static_education = "### B.S. Computer Science\\n- University of Technology, 2016"
        
        if os.path.exists(base_cv_path):
            with open(base_cv_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            import re
            exp_match = re.search(r"##\s+(?:Work )?Experience\s*(.*?)(?=\n## |\Z)", content, re.DOTALL | re.IGNORECASE)
            if exp_match:
                static_experience = exp_match.group(1).strip()
                
            edu_match = re.search(r"##\s+Education\s*(.*?)(?=\n## |\Z)", content, re.DOTALL | re.IGNORECASE)
            if edu_match:
                static_education = edu_match.group(1).strip()
        
        # Evidence sources mapping
        sources_set = set()
        for chunk in rag_results:
            src = chunk['metadata'].get('source', 'Unknown')
            if not src.endswith('_template.md'):
                sources_set.add(src)
        
        evidence_sources = list(sources_set)
        if not evidence_sources:
            evidence_sources = ["No direct evidence found, used generic profile."]
            
        cv_md = self.assemble_cv(
            generated_parts.get('profile', ''),
            generated_parts.get('skills', []),
            static_experience,
            static_education,
            evidence_sources
        )
        
        # Outputs directory structure
        today = date.today().strftime("%Y-%m-%d")
        safe_company = "".join(x for x in (job.get('company') or "Unknown") if x.isalnum() or x in " _-")
        safe_title = "".join(x for x in (job.get('title') or "Job") if x.isalnum() or x in " _-")
        folder_name = f"{safe_company}_{safe_title}".replace(" ", "_")
        if not folder_name:
            folder_name = "Unknown_Job"
            
        out_dir = os.path.join("outputs", today, folder_name)
        os.makedirs(out_dir, exist_ok=True)
        
        md_path = os.path.join(out_dir, "tailored_cv.md")
        html_path = os.path.join(out_dir, "tailored_cv.html")
        pdf_path = os.path.join(out_dir, "tailored_cv.pdf")
        
        # Export
        export_markdown(cv_md, md_path)
        export_html(md_path, html_path)
        export_pdf(html_path, pdf_path)
        
        # Update DB
        self.db.execute_query(
            "UPDATE jobs SET status = 'cv_generated', generated_cv_path = ? WHERE job_id = ?",
            (md_path, job_id)
        )
        
        # Add to knowledge manager for future reuse
        self.km.add_generated_cv(cv_md, job_id)
        
        return True
