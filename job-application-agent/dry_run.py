import os
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from llm.mock_provider import MockProvider
from core.cv_tailor import CVTailor

def run_dry_run():
    print("Starting End-to-End Dry Run...")
    
    # Ensure profile directory exists
    os.makedirs("profile", exist_ok=True)
    
    # 1. Create a realistic profile
    realistic_profile_path = "profile/base_cv.md"
    realistic_profile = """# Jane Doe
**Backend & AI Engineer**
Gothenburg, Sweden

## Profile Source Facts
Jane has 5 years of experience building highly scalable microservices using Python, C#, and AWS.
She specializes in integrating machine learning models into production systems and optimizing RAG pipelines.
She has a passion for building robust cloud architectures and maintaining high security standards.

## Skills
**Cloud & Backend:** Python, C#, .NET, AWS, Azure, Microservices, Docker, Kubernetes
**AI/ML:** RAG, LangChain, PyTorch, LLMs, NLP
**Databases:** PostgreSQL, MongoDB, Redis, SQLite

## Experience
### Senior Backend Engineer | TechNova Solutions
*Jan 2021 - Present | Gothenburg, Sweden*
- Designed and deployed a distributed RAG pipeline reducing query latency by 40%.
- Migrated monolith legacy systems to Dockerized microservices on AWS.

### Software Engineer | CodeForge
*Aug 2018 - Dec 2020 | Remote*
- Built RESTful APIs using ASP.NET Core and Entity Framework.

## Education
### M.Sc. Data Science and AI
Chalmers University of Technology (2018)

### B.S. Computer Science
University of Gothenburg (2016)

## Projects
- **AI Agent Builder:** Open-source framework for orchestrating LLM tool calling.
"""
    with open(realistic_profile_path, 'w', encoding='utf-8') as f:
        f.write(realistic_profile)
        
    print(f"Created realistic profile at {realistic_profile_path}")

    # 2. Add realistic profile to ChromaDB
    km = KnowledgeManager()
    km.add_source(realistic_profile_path)
    print("Added profile to Knowledge Base.")

    # 3. Insert realistic job into SQLite
    db = DBManager()
    job_data = {
        "job_id": "dry_run_job_001",
        "title": "Senior AI & Cloud Engineer",
        "company": "Gothenburg AI Labs",
        "location": "Gothenburg, Sweden",
        "job_link": "https://example.com/jobs/ai-cloud-engineer",
        "description": "We are looking for a Senior AI & Cloud Engineer to join our team in Gothenburg. You should have strong experience in Python, AWS, and integrating LLMs/RAG pipelines into scalable backend services. Experience with microservices and Docker is required."
    }
    
    db.insert_job(job_data)
    # Force status to needs_review
    db.execute_query("UPDATE jobs SET status = 'needs_review' WHERE job_id = 'dry_run_job_001'")
    print("Inserted job into database and set to needs_review.")

    # 4. Generate CV
    provider = MockProvider()
    config = {'base_cv_path': realistic_profile_path}
    
    tailor = CVTailor(db, km, provider, config)
    success = tailor.generate_tailored_cv("dry_run_job_001")
    
    print(f"CV Generation Success: {success}")
    
    # Verify outputs
    job = db.get_job_by_link("https://example.com/jobs/ai-cloud-engineer")
    print(f"Job Status: {job['status']}")
    print(f"Generated CV Path: {job['generated_cv_path']}")
    
    # Read the markdown
    if job['generated_cv_path'] and os.path.exists(job['generated_cv_path']):
        with open(job['generated_cv_path'], 'r', encoding='utf-8') as f:
            print("\n--- GENERATED MARKDOWN CV ---")
            print(f.read())
            print("-----------------------------\n")
            
if __name__ == "__main__":
    run_dry_run()
