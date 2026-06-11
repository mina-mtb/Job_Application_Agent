import os
import json
import re
import logging
from datetime import date
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from utils.exporter import export_markdown, export_html, export_pdf

logger = logging.getLogger(__name__)

# Professional CSS for free-form CV PDF generation
CV_PDF_CSS = """
<style>
    @page { margin: 1.5cm; size: A4; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; font-size: 10pt; line-height: 1.5; color: #1f2937; }
    
    .header { text-align: center; margin-bottom: 16px; border-bottom: 2px solid #2563eb; padding-bottom: 12px; }
    .header h1 { font-size: 24pt; color: #111827; margin: 0; letter-spacing: 0.5px; font-weight: 700; border-bottom: none; }
    .contact-info { margin-top: 6px; font-size: 9.5pt; color: #4b5563; }
    .contact-info a { color: #2563eb; text-decoration: none; margin: 0 6px; }
    .contact-separator { margin: 0 4px; color: #9ca3af; }
    
    h2 { font-size: 12.5pt; color: #1e3a8a; margin-top: 18px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }
    h3 { font-size: 11pt; color: #111827; margin-top: 10px; margin-bottom: 2px; font-weight: 600; display: inline-block; }
    
    .date-location { float: right; font-size: 9.5pt; color: #6b7280; font-weight: 500; margin-top: 10px; }
    .subtitle { font-size: 10pt; color: #4b5563; font-style: italic; margin-bottom: 4px; }
    
    p { margin: 3px 0; text-align: justify; }
    ul { margin: 4px 0 10px 18px; padding: 0; }
    li { margin-bottom: 3px; text-align: justify; }
    
    .skills-grid { margin-bottom: 10px; }
    .skill-category { font-weight: 600; color: #111827; }
</style>
"""


class CVTailor:
    def __init__(self, db_manager: DBManager, km: KnowledgeManager, llm_provider, config: dict):
        self.db = db_manager
        self.km = km
        self.llm = llm_provider
        self.config = config
        self._base_cv_content = None

    def _get_base_cv(self) -> str:
        """Load the user's base CV from profile/mina_base_cv.md."""
        if self._base_cv_content:
            return self._base_cv_content
        
        base_path = "profile/mina_base_cv.md"
        if os.path.exists(base_path):
            with open(base_path, 'r', encoding='utf-8') as f:
                self._base_cv_content = f.read()
        else:
            self._base_cv_content = ""
        return self._base_cv_content

    def _get_settings(self) -> dict:
        """Load user settings from knowledge_base/settings.json."""
        settings_path = "knowledge_base/settings.json"
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _get_output_dir(self, job: dict, mode: str = "default") -> str:
        """Create and return the output directory for a job's CV."""
        today = date.today().strftime("%Y-%m-%d")
        safe_company = "".join(x for x in (job.get('company') or "Unknown") if x.isalnum() or x in " _-")
        safe_title = "".join(x for x in (job.get('title') or "Job") if x.isalnum() or x in " _-")
        folder_name = f"{safe_company}_{safe_title}".replace(" ", "_")
        if not folder_name:
            folder_name = "Unknown_Job"
        out_dir = os.path.join("outputs", today, folder_name, mode)
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def build_cv_context(self, job: dict, retrieved_chunks: list) -> str:
        context = f"Job Title: {job.get('title', '')}\n"
        context += f"Company: {job.get('company', '')}\n"
        context += f"Location: {job.get('location', '')}\n"
        context += f"Job Description: {job.get('description', '')}\n\n"
        context += "Evidence from Candidate Knowledge Base:\n"
        for i, chunk in enumerate(retrieved_chunks):
            source = chunk.get('metadata', {}).get('source', 'Unknown') if chunk.get('metadata') else 'Unknown'
            context += f"[{i+1}] Source: {source} - {chunk['text']}\n"
        return context

    def predict_acceptance_scores(self, job_id: str) -> dict:
        """Predict acceptance chances for existing CV, template CV, and free-form CV."""
        jobs = self.db.execute_query("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if not jobs:
            return {}
        
        job = jobs[0]
        base_cv = self._get_base_cv()
        
        # Get best existing CV match from knowledge base
        best_match = self.km.get_best_past_cv_match(job.get('description', ''))
        best_existing = None
        if best_match:
            old_jobs = self.db.execute_query("SELECT generated_cv_path FROM jobs WHERE job_id = ?", (best_match['job_id'],))
            if old_jobs and old_jobs[0].get('generated_cv_path'):
                best_existing = {
                    'job_id': best_match['job_id'],
                    'score': best_match.get('score', 0),
                    'path': old_jobs[0]['generated_cv_path']
                }

        # Get RAG context
        query = f"Job title: {job.get('title', '')}. Description: {job.get('description', '')}"
        rag_results = self.km.query_knowledge_base(query, top_k=5)
        evidence = "\n".join([r['text'] for r in rag_results])

        # Ask LLM to predict scores
        prompt = f"""You are an expert career advisor. Analyze this job posting against the candidate's profile and predict acceptance chances.

### Job Posting:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description: {job.get('description', '')}

### Candidate's Base Profile:
{base_cv}

### Additional Evidence from Knowledge Base:
{evidence}

### Task:
Predict the candidate's acceptance chance (0-100%) for three scenarios:
1. **best_existing_score**: If using the best previously generated CV (which was for a different job), how well would it match THIS job? If no info available, use 0.
2. **template_score**: If we generate a NEW CV that only customizes Profile and Skills sections (keeping Experience/Education fixed), what's the predicted match?
3. **free_form_score**: If we generate a completely NEW, fully customized CV (ATS-optimized, with all sections tailored), what's the predicted match?

Also provide a brief analysis explaining why.

Return ONLY valid JSON:
{{
    "best_existing_score": <int>,
    "template_score": <int>,
    "free_form_score": <int>,
    "analysis": "<brief explanation of strengths, gaps, and recommendation>"
}}"""

        try:
            response = self.llm.generate_completion(prompt)
            response_clean = re.sub(r'^```(?:json)?\s*', '', response.strip())
            response_clean = re.sub(r'\s*```$', '', response_clean)
            scores = json.loads(response_clean)
        except Exception as e:
            logger.warning(f"Failed to predict scores: {e}")
            # Fallback to embedding-based estimation
            scores = {
                "best_existing_score": best_match.get('score', 0) if best_match else 0,
                "template_score": self.km.predict_new_cv_score(job.get('description', '')),
                "free_form_score": min(self.km.predict_new_cv_score(job.get('description', '')) + 15, 95),
                "analysis": "Score prediction used fallback method. Real AI analysis was unavailable."
            }

        result = {
            'best_existing_cv': best_existing,
            'template_predicted_score': scores.get('template_score', 0),
            'free_form_predicted_score': scores.get('free_form_score', 0),
            'analysis': scores.get('analysis', '')
        }
        
        # Update best_existing score with LLM prediction if available
        if best_existing:
            best_existing['score'] = scores.get('best_existing_score', best_existing.get('score', 0))

        return result

    def generate_tailored_cv(self, job_id: str, mode: str = 'template') -> bool:
        """Generate a tailored CV for a job. 
        
        mode='template': Overlay Profile+Skills on PDF template
        mode='free_form': Generate complete CV as markdown → PDF
        """
        jobs = self.db.execute_query("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if not jobs:
            logger.error(f"Job {job_id} not found.")
            return False
            
        job = jobs[0]
        if job['status'] not in ['needs_review', 'approved', 'cv_pending_approval']:
            logger.warning(f"Job {job_id} is in status {job['status']}, not generating CV.")
            return False

        base_cv = self._get_base_cv()
        settings = self._get_settings()
        cv_rules = settings.get("cv_rules", [])
        rules_text = "\n".join([f"- {r}" for r in cv_rules]) if cv_rules else "- No special rules."

        # Query RAG for evidence
        query = f"Job title: {job.get('title', '')}. Description: {job.get('description', '')}"
        rag_results = self.km.query_knowledge_base(query, top_k=5)
        evidence = "\n".join([f"[{i+1}] {r['text']}" for i, r in enumerate(rag_results)])

        out_dir = self._get_output_dir(job, mode)

        if mode == 'template':
            return self._generate_template_cv(job, base_cv, evidence, rules_text, out_dir, settings)
        else:
            return self._generate_free_form_cv(job, base_cv, evidence, rules_text, out_dir)

    def _generate_template_cv(self, job, base_cv, evidence, rules_text, out_dir, settings) -> bool:
        """Generate CV by overlaying Profile+Skills on the PDF template."""
        # Find the template PDF
        template_name = settings.get("default_cv_template")
        base_cv_path = None
        if template_name:
            if template_name.lower().endswith('.docx'):
                template_name = template_name[:-5] + '.pdf'
            base_cv_path = os.path.join("knowledge_base", "processed_sources", template_name)
            if not os.path.exists(base_cv_path):
                # Try templates/cv/ directory
                base_cv_path = os.path.join("templates", "cv", template_name)

        if not base_cv_path or not os.path.exists(base_cv_path):
            # Fallback: find any PDF in templates/cv/
            template_dir = "templates/cv"
            if os.path.exists(template_dir):
                pdfs = [f for f in os.listdir(template_dir) if f.endswith('.pdf')]
                if pdfs:
                    base_cv_path = os.path.join(template_dir, pdfs[0])
                    template_name = pdfs[0]
            
            if not base_cv_path or not os.path.exists(base_cv_path):
                raise FileNotFoundError(f"No PDF template found. Please upload one in CV Templates tab.")

        prompt = f"""You are an expert resume writer. Generate ONLY the 'Profile' and 'Skills' sections tailored specifically to this job.

### Job Details:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description:
{job.get('description', '')}

### Candidate's Full Profile (source of truth — DO NOT fabricate beyond this):
{base_cv}

### Additional Evidence:
{evidence}

### User Rules:
{rules_text}

### CRITICAL INSTRUCTIONS:
1. The Profile MUST be specifically written for THIS job at THIS company. Reference key skills and requirements from the job description.
2. The Skills section MUST prioritize skills that match THIS job's requirements. Put the most relevant skills first.
3. NEVER fabricate experience, certifications, or skills not found in the candidate's profile.
4. Keep it concise — Profile should be 3-5 sentences, Skills should be a categorized list.
5. Write in professional English.

Return ONLY valid JSON:
{{
    "profile": "The tailored profile paragraph...",
    "skills": "Categorized skills text..."
}}"""

        response = self.llm.generate_completion(prompt)
        response_clean = re.sub(r'^```(?:json)?\s*', '', response.strip())
        response_clean = re.sub(r'\s*```$', '', response_clean)
        
        try:
            cv_data = json.loads(response_clean)
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            cv_data = {"profile": "Error generating profile.", "skills": "Error generating skills."}

        profile_val = cv_data.get('profile', '')
        skills_val = cv_data.get('skills', '')
        
        if isinstance(skills_val, list):
            skills_val = '\n'.join([f"• {item}" for item in skills_val])
        if isinstance(profile_val, list):
            profile_val = ' '.join([str(item) for item in profile_val])

        # Render PDF using template overlay
        from core.pdf_template_renderer import render_pdf_cv_template
        final_path = os.path.join(out_dir, "tailored_cv.pdf")
        render_result = render_pdf_cv_template(base_cv_path, final_path, str(profile_val), str(skills_val))
        
        if not render_result["success"]:
            logger.warning(f"PDF render failed: {render_result['warnings']}")
            import shutil
            shutil.copy2(base_cv_path, final_path)

        # Save editable markdown version
        editable_md = f"""# Tailored CV — {job.get('title', '')} at {job.get('company', '')}

## Profile
{profile_val}

## Skills
{skills_val}

---
*Template mode: Only Profile and Skills are customized. Experience and Education remain as in the original template.*
"""
        md_path = os.path.join(out_dir, "tailored_cv_editable.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(editable_md)

        # Update DB
        self.db.execute_query(
            "UPDATE jobs SET status = 'cv_pending_approval', generated_cv_path = ?, cv_generation_method = ?, template_used = ? WHERE job_id = ?",
            (final_path, 'template', template_name, job['job_id'])
        )
        
        # Store in knowledge base for future matching
        self.km.add_generated_cv(editable_md, job['job_id'])
        
        return True

    def _generate_free_form_cv(self, job, base_cv, evidence, rules_text, out_dir) -> bool:
        """Generate a complete free-form CV optimized for ATS and the specific job."""
        import yaml
        personal_info = {}
        if os.path.exists("profile/personal_info.yaml"):
            try:
                with open("profile/personal_info.yaml", "r", encoding="utf-8") as f:
                    personal_info = yaml.safe_load(f) or {}
            except Exception:
                pass
                
        # Use city-level location by default if possible
        full_loc = personal_info.get("location", "")
        city_loc = full_loc
        if "," in full_loc:
            parts = [p.strip() for p in full_loc.split(",")]
            if len(parts) >= 2:
                city_loc = f"{parts[-2]}, {parts[-1]}"

        # Read the raw text from the template PDF as an additional source of truth
        template_text = ""
        try:
            import fitz
            template_path = os.path.join("knowledge_base", "processed_sources", "Mina TAhmasebi Cv Template (2).pdf")
            if os.path.exists(template_path):
                with fitz.open(template_path) as doc:
                    for page in doc:
                        template_text += page.get_text() + "\n"
        except Exception as e:
            logger.warning(f"Could not extract text from template PDF: {e}")

        prompt = f"""You are an expert resume writer and ATS optimization specialist. Create a COMPLETE, professional CV tailored specifically for this job.

### Job Details:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Description:
{job.get('description', '')}

### Candidate's Full Profile (source of truth — DO NOT fabricate beyond this):
{base_cv}

### Text from Candidate's Previous PDF CV (for accurate Experience/Education):
{template_text}

### Additional Evidence:
{evidence}

### User Rules:
{rules_text}

### CRITICAL INSTRUCTIONS:
1. Create a structured CV in JSON format.
2. The Profile Summary MUST specifically target this job and company.
3. Skills MUST be ordered by relevance to THIS job's requirements. Group them logically (e.g. "Languages & Frameworks", "Tools", etc).
4. Experience descriptions should emphasize achievements relevant to THIS role.
5. NEVER fabricate experience, dates, company names, or certifications.
6. NEVER invent skills not in the candidate's profile or previous CV.
7. Experience and Education facts must remain truthful — you may rephrase and reorder bullet points to emphasize relevance.
8. Include languages (the candidate knows English, Swedish, and Persian) and any projects/certifications found in the sources.
9. Keep the CV concise (1-2 pages when rendered).

Return ONLY valid JSON matching this structure:
{{
  "profile": "A tailored 3-4 sentence professional summary",
  "skills": [
    {{"category": "Programming Languages", "items": ["Python", "JavaScript"]}},
    {{"category": "Tools", "items": ["Git", "Docker"]}}
  ],
  "experience": [
    {{
      "title": "Job Title",
      "company": "Company Name",
      "location": "City, Country",
      "dates": "Start - End",
      "bullets": ["Achievement 1", "Achievement 2"]
    }}
  ],
  "education": [
    {{
      "degree": "Degree Name",
      "institution": "University Name",
      "dates": "Start - End",
      "details": "Optional details or honors"
    }}
  ],
  "languages": [
    {{"language": "English", "proficiency": "Fluent"}}
  ],
  "projects": [
    {{"name": "Project Name", "description": "Short description of project and technologies used"}}
  ],
  "certifications": [
    "Certification Name 1", "Certification Name 2"
  ]
}}"""

        response = self.llm.generate_completion(prompt)
        
        # Parse JSON
        response_clean = re.sub(r'^```(?:json)?\s*', '', response.strip())
        response_clean = re.sub(r'\s*```$', '', response_clean)
        try:
            cv_data = json.loads(response_clean)
        except Exception as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}\nRaw Response: {response_clean}")
            return False

        # Build Markdown
        md_lines = []
        
        # 1. HTML Header
        name = personal_info.get("full_name", "Mina Tahmasebi Berjouei")
        email = personal_info.get("email", "")
        phone = personal_info.get("phone", "")
        linkedin = personal_info.get("linkedin", "")
        github = personal_info.get("github", "")
        
        contact_parts = []
        if city_loc: contact_parts.append(city_loc)
        if email: contact_parts.append(f'<a href="mailto:{email}">{email}</a>')
        if phone: contact_parts.append(phone)
        if linkedin: contact_parts.append(f'<a href="{linkedin}">LinkedIn</a>')
        if github: contact_parts.append(f'<a href="{github}">GitHub</a>')
        
        contact_html = ' <span class="contact-separator">|</span> '.join(contact_parts)
        
        header_html = f"""<div class="header">
<h1>{name}</h1>
<div class="contact-info">
{contact_html}
</div>
</div>
"""
        md_lines.append(header_html)
        
        # 2. Profile
        if cv_data.get("profile"):
            md_lines.append("## Professional Summary\n")
            md_lines.append(f"{cv_data['profile']}\n")
            
        # 3. Skills
        if cv_data.get("skills"):
            md_lines.append("## Skills\n")
            md_lines.append('<div class="skills-grid">')
            for skill_group in cv_data["skills"]:
                cat = skill_group.get("category", "")
                items = ", ".join(skill_group.get("items", []))
                md_lines.append(f"<p><span class=\"skill-category\">{cat}:</span> {items}</p>")
            md_lines.append('</div>\n')
            
        # 4. Experience
        if cv_data.get("experience"):
            md_lines.append("## Experience\n")
            for exp in cv_data["experience"]:
                title = exp.get("title", "")
                company = exp.get("company", "")
                dates = exp.get("dates", "")
                loc = exp.get("location", "")
                
                date_loc = []
                if dates: date_loc.append(dates)
                if loc: date_loc.append(loc)
                date_loc_str = " | ".join(date_loc)
                
                md_lines.append(f"### {title} <span class=\"date-location\">{date_loc_str}</span>")
                md_lines.append(f"<div class=\"subtitle\">{company}</div>\n")
                
                for bullet in exp.get("bullets", []):
                    md_lines.append(f"- {bullet}")
                md_lines.append("")
                
        # 5. Education
        if cv_data.get("education"):
            md_lines.append("## Education\n")
            for edu in cv_data["education"]:
                degree = edu.get("degree", "")
                inst = edu.get("institution", "")
                dates = edu.get("dates", "")
                details = edu.get("details", "")
                
                md_lines.append(f"### {degree} <span class=\"date-location\">{dates}</span>")
                md_lines.append(f"<div class=\"subtitle\">{inst}</div>\n")
                if details:
                    md_lines.append(f"<p>{details}</p>\n")
                    
        # 6. Projects (Optional)
        if cv_data.get("projects"):
            md_lines.append("## Projects\n")
            for proj in cv_data["projects"]:
                name = proj.get("name", "")
                desc = proj.get("description", "")
                md_lines.append(f"- **{name}:** {desc}")
            md_lines.append("")
            
        # 7. Certifications & Languages
        has_certs = bool(cv_data.get("certifications"))
        has_langs = bool(cv_data.get("languages"))
        
        if has_certs or has_langs:
            md_lines.append("## Certifications & Languages\n")
            if has_certs:
                certs = ", ".join(cv_data["certifications"])
                md_lines.append(f"- **Certifications:** {certs}")
            if has_langs:
                langs = ", ".join([f"{l.get('language', '')} ({l.get('proficiency', '')})" for l in cv_data["languages"]])
                md_lines.append(f"- **Languages:** {langs}")

        cv_md = "\n".join(md_lines)

        # Save editable markdown
        md_path = os.path.join(out_dir, "tailored_cv_editable.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(cv_md)

        # Convert to HTML with professional styling
        html_path = os.path.join(out_dir, "tailored_cv.html")
        self._markdown_to_styled_html(cv_md, html_path)

        # Convert HTML to PDF using exporter
        pdf_path = os.path.join(out_dir, "tailored_cv.pdf")
        pdf_success = export_pdf(html_path, pdf_path)
        
        final_path = pdf_path if os.path.exists(pdf_path) and pdf_success else html_path

        # Update DB
        self.db.execute_query(
            "UPDATE jobs SET status = 'cv_pending_approval', generated_cv_path = ?, cv_generation_method = ? WHERE job_id = ?",
            (final_path, 'free_form', job['job_id'])
        )
        
        # Store in knowledge base for future matching
        self.km.add_generated_cv(cv_md, job['job_id'])
        
        return True

    def _markdown_to_styled_html(self, md_text: str, html_path: str):
        """Convert markdown to a professionally styled HTML document."""
        try:
            import markdown
            body_html = markdown.markdown(md_text, extensions=['tables', 'sane_lists'])
        except ImportError:
            # Minimal manual conversion
            body_html = md_text.replace('\n', '<br>')
        
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CV</title>
    {CV_PDF_CSS}
</head>
<body>
{body_html}
</body>
</html>"""
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(full_html)

    def get_cv_markdown(self, job_id: str) -> str:
        """Get the editable markdown content of a generated CV."""
        jobs = self.db.execute_query("SELECT generated_cv_path FROM jobs WHERE job_id = ?", (job_id,))
        if not jobs or not jobs[0].get('generated_cv_path'):
            return ""
        
        cv_path = jobs[0]['generated_cv_path']
        cv_dir = os.path.dirname(cv_path)
        md_path = os.path.join(cv_dir, "tailored_cv_editable.md")
        
        if os.path.exists(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        # Fallback: if the CV itself is markdown
        if cv_path.endswith('.md') and os.path.exists(cv_path):
            with open(cv_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        return ""

    def save_edited_cv(self, job_id: str, edited_markdown: str, mode: str = 'free_form'):
        """Save edited markdown and re-render to PDF."""
        jobs = self.db.execute_query("SELECT generated_cv_path, template_used FROM jobs WHERE job_id = ?", (job_id,))
        if not jobs:
            raise ValueError(f"Job {job_id} not found.")
        
        cv_path = jobs[0]['generated_cv_path']
        cv_dir = os.path.dirname(cv_path)
        
        # Save the edited markdown
        md_path = os.path.join(cv_dir, "tailored_cv_editable.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(edited_markdown)
        
        if mode == 'template':
            # Re-extract profile and skills from edited markdown and re-overlay
            profile, skills = self._extract_profile_skills_from_md(edited_markdown)
            
            settings = self._get_settings()
            template_name = jobs[0].get('template_used') or settings.get("default_cv_template")
            base_cv_path = None
            if template_name:
                base_cv_path = os.path.join("knowledge_base", "processed_sources", template_name)
                if not os.path.exists(base_cv_path):
                    base_cv_path = os.path.join("templates", "cv", template_name)
            
            if base_cv_path and os.path.exists(base_cv_path):
                from core.pdf_template_renderer import render_pdf_cv_template
                pdf_path = os.path.join(cv_dir, "tailored_cv.pdf")
                render_pdf_cv_template(base_cv_path, pdf_path, profile, skills)
        else:
            # Free-form: re-render markdown → HTML → PDF
            html_path = os.path.join(cv_dir, "tailored_cv.html")
            self._markdown_to_styled_html(edited_markdown, html_path)
            
            pdf_path = os.path.join(cv_dir, "tailored_cv.pdf")
            pdf_success = export_pdf(html_path, pdf_path)
            
            if not pdf_success:
                try:
                    from weasyprint import HTML
                    HTML(filename=html_path).write_pdf(pdf_path)
                except ImportError:
                    logger.warning("PDF re-render failed. HTML file updated.")
        
        # Update knowledge base
        self.km.add_generated_cv(edited_markdown, job_id)

    def _extract_profile_skills_from_md(self, md_text: str) -> tuple:
        """Extract Profile and Skills sections from markdown text."""
        profile = ""
        skills = ""
        
        current_section = None
        lines = md_text.split('\n')
        
        for line in lines:
            lower = line.strip().lower()
            if lower.startswith('## profile'):
                current_section = 'profile'
                continue
            elif lower.startswith('## skills'):
                current_section = 'skills'
                continue
            elif lower.startswith('## ') or lower.startswith('---'):
                current_section = None
                continue
            
            if current_section == 'profile':
                profile += line + '\n'
            elif current_section == 'skills':
                skills += line + '\n'
        
        return profile.strip(), skills.strip()

    def approve_and_finalize_cv(self, job_id: str):
        """Finalize a pending CV — update status to cv_generated."""
        jobs = self.db.execute_query("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if not jobs:
            return False
            
        job = jobs[0]
        final_path = job.get('generated_cv_path')
        if not final_path or not os.path.exists(final_path):
            return False

        # For DOCX, convert to PDF
        if final_path.endswith('.docx'):
            try:
                from docx2pdf import convert as docx2pdf_convert
                pdf_path = final_path.replace('.docx', '.pdf')
                docx2pdf_convert(final_path, pdf_path)
            except Exception as e:
                logger.warning(f"Failed to convert DOCX to PDF: {e}")

        # Update DB to final status
        self.db.execute_query(
            "UPDATE jobs SET status = 'cv_generated' WHERE job_id = ?",
            (job_id,)
        )
        return True

    # Legacy methods kept for compatibility
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
