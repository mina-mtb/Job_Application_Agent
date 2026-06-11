import os
from dotenv import load_dotenv
load_dotenv()
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from llm.provider_factory import get_provider
from core.cv_tailor import CVTailor
import fitz

def generate_test_cvs():
    db = DBManager()
    km = KnowledgeManager()
    llm = get_provider()
    
    jobs = db.get_all_jobs()
    if not jobs:
        print("No jobs in DB to test with.")
        return
        
    job = jobs[0]
    print(f"Testing CV generation for Job: {job['title']} at {job['company']}")
    
    tailor = CVTailor(db, km, llm, {})
    
    print("Generating Template CV...")
    success_t = tailor.generate_tailored_cv(job['job_id'], mode='template')
    updated_jobs = db.execute_query("SELECT generated_cv_path FROM jobs WHERE job_id = ?", (job['job_id'],))
    pdf_path_t = updated_jobs[0]['generated_cv_path']
    print(f"Template success: {success_t}, path: {pdf_path_t}")

    print("Generating Free-form CV...")
    success_f = tailor.generate_tailored_cv(job['job_id'], mode='free_form')
    updated_jobs = db.execute_query("SELECT generated_cv_path FROM jobs WHERE job_id = ?", (job['job_id'],))
    pdf_path_f = updated_jobs[0]['generated_cv_path']
    print(f"Free-form success: {success_f}, path: {pdf_path_f}")
    
    # Save a PNG of the new free-form to verify
    artifact_dir = r"C:\Users\mina_\.gemini\antigravity\brain\a7bed0b4-9c16-450a-a936-506a269cbf36"
    if os.path.exists(pdf_path_f) and pdf_path_f.endswith('.pdf'):
        doc = fitz.open(pdf_path_f)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=150)
            png_path = os.path.join(artifact_dir, f"bugA_free_form_page{i+1}.png")
            pix.save(png_path)
            print(f"Saved PNG: {png_path}")

if __name__ == "__main__":
    generate_test_cvs()
