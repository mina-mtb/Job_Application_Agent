import streamlit as st
import os
import yaml
from database.db_manager import DBManager
from core.knowledge_manager import KnowledgeManager
from core.job_matcher import JobMatcher
from core.cv_tailor import CVTailor
from llm.provider_factory import get_provider
from core.app_helpers import (
    can_generate_cv, can_approve, can_mark_applied,
    update_job_status, mark_as_applied, add_user_note,
    process_manual_entry, handle_knowledge_upload
)

st.set_page_config(page_title="Job Application Agent", layout="wide")

@st.cache_resource
def init_system():
    db = DBManager()
    km = KnowledgeManager()
    
    config_path = "config/config.yaml"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {'active_provider': 'mock'}
        
    if 'preferred_locations' not in config or not config['preferred_locations']:
        config['preferred_locations'] = ["Göteborg", "Gothenburg", "Västra Götaland"]

        
    provider = get_provider()
    matcher = JobMatcher(config, km, provider)
    tailor = CVTailor(db, km, provider, config)
    
    return db, km, matcher, tailor, config

db, km, matcher, tailor, config = init_system()

st.title("Job Application Agent Dashboard")

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Knowledge Base", "Manual Entry", "Settings"])

with tab1:
    st.header("Jobs Dashboard")
    
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.write("Manage your job pipeline below.")
    with col_b:
        if st.button("Score New Jobs"):
            from core.app_helpers import run_daily_matching
            with st.spinner("Scoring new jobs..."):
                count = run_daily_matching(db, matcher)
                st.success(f"Scored {count} new jobs!")
                st.rerun()
                
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox("Status", ["All", "new", "needs_review", "cv_generated", "approved", "applied", "rejected", "not_suitable", "failed"])
    with col2:
        min_score = st.slider("Minimum Suitability Score", 0, 100, 0)
    with col3:
        search_kw = st.text_input("Search Keyword (Title/Company)")
        
    jobs = db.get_all_jobs()
    
    # Apply filters
    if status_filter != "All":
        jobs = [j for j in jobs if j.get('status') == status_filter]
    if min_score > 0:
        jobs = [j for j in jobs if j.get('suitability_score') is not None and j.get('suitability_score') >= min_score]
    if search_kw:
        kw = search_kw.lower()
        jobs = [j for j in jobs if kw in (j.get('title') or "").lower() or kw in (j.get('company') or "").lower()]
        
    st.write(f"Showing {len(jobs)} jobs")
    
    for job in jobs:
        with st.expander(f"{job.get('title')} at {job.get('company')} ({job.get('status')}) - Score: {job.get('suitability_score')}"):
            st.write(f"**Location:** {job.get('location')}")
            st.write(f"**Link:** [Job Post]({job.get('job_link')})")
            st.write(f"**Category:** {job.get('suitability_category')}")
            st.write(f"**Reasons for match:** {job.get('reasons_for_match')}")
            st.write(f"**Weaknesses:** {job.get('weaknesses_or_risks')}")
            if job.get('user_notes'):
                st.write(f"**Notes:** {job.get('user_notes')}")
            if job.get('generated_cv_path'):
                st.write(f"**CV Path:** `{job.get('generated_cv_path')}`")
            
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                if can_generate_cv(job.get('status')):
                    if st.button("Generate CV", key=f"gen_{job['job_id']}"):
                        with st.spinner("Generating CV..."):
                            success = tailor.generate_tailored_cv(job['job_id'])
                            if success:
                                st.success("CV Generated!")
                                st.rerun()
                            else:
                                st.error("Failed to generate CV.")
            with c2:
                if job.get('generated_cv_path') and os.path.exists(job['generated_cv_path']):
                    if st.button("Preview CV", key=f"prev_{job['job_id']}"):
                        with open(job['generated_cv_path'], 'r', encoding='utf-8') as f:
                            st.markdown(f.read())
            with c3:
                if can_approve(job.get('status')):
                    if st.button("Approve", key=f"appr_{job['job_id']}"):
                        update_job_status(db, job['job_id'], "approved")
                        st.rerun()
            with c4:
                if can_mark_applied(job.get('generated_cv_path')):
                    if st.button("Mark Applied", key=f"ma_{job['job_id']}"):
                        mark_as_applied(db, job['job_id'])
                        st.rerun()
            with c5:
                if job.get('status') not in ['applied', 'rejected', 'not_suitable']:
                    if st.button("Reject", key=f"rej_{job['job_id']}"):
                        update_job_status(db, job['job_id'], "rejected")
                        st.rerun()
                    if st.button("Not Suitable", key=f"ns_{job['job_id']}"):
                        update_job_status(db, job['job_id'], "not_suitable")
                        st.rerun()
                        
            note = st.text_input("Add Note", key=f"note_in_{job['job_id']}")
            if st.button("Save Note", key=f"save_note_{job['job_id']}"):
                if note:
                    add_user_note(db, job['job_id'], note)
                    st.rerun()

with tab2:
    st.header("Knowledge Base Management")
    uploaded_file = st.file_uploader("Upload Profile or Experience Document (.md, .txt)", type=['md', 'txt'])
    
    if st.button("Add to Knowledge Base") and uploaded_file is not None:
        temp_dir = "temp_uploads"
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, uploaded_file.name)
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
            
        success, msg = handle_knowledge_upload(km, temp_path)
        if success:
            st.success(msg)
        else:
            st.error(msg)
            
    st.subheader("Current Processed Sources")
    processed_dir = km.processed_dir
    if os.path.exists(processed_dir):
        files = os.listdir(processed_dir)
        if files:
            for f in files:
                st.write(f"- {f}")
        else:
            st.write("No sources uploaded yet.")

with tab3:
    st.header("Manual Job Entry")
    
    st.info("Paste the full job description. URL alone is stored as job_link, but matching requires description text unless URL scraping is enabled.")
    
    m_title = st.text_input("Job Title")
    m_company = st.text_input("Company")
    m_location = st.text_input("Location")
    m_link = st.text_input("Job URL")
    m_desc = st.text_area("Job Description")
    
    if st.button("Process Manual Job"):
        if m_desc and m_link:
            with st.spinner("Processing job via LLM..."):
                success, msg = process_manual_entry(db, matcher, m_desc, m_link, m_title, m_company, m_location)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)
        else:
            st.error("Job URL and Description are required.")

with tab4:
    st.header("Settings")
    
    st.write("Edit configuration values here. Secrets are generally loaded from environment variables to avoid plaintext exposure.")
    
    locs = st.text_area("Preferred Locations (comma separated)", value=", ".join(config.get('preferred_locations', [])))
    allow_rem = st.checkbox("Allow Remote", value=config.get('allow_remote', True))
    allow_hyb = st.checkbox("Allow Hybrid", value=config.get('allow_hybrid', True))
    rej_reloc = st.checkbox("Reject Relocation Required", value=config.get('reject_relocation_required', True))
    provider = st.selectbox("Active Provider", ["mock", "claude", "openai"], index=["mock", "claude", "openai"].index(config.get('active_provider', 'mock')) if config.get('active_provider', 'mock') in ["mock", "claude", "openai"] else 0)
    
    if st.button("Save Settings"):
        config['preferred_locations'] = [l.strip() for l in locs.split(",") if l.strip()]
        config['allow_remote'] = allow_rem
        config['allow_hybrid'] = allow_hyb
        config['reject_relocation_required'] = rej_reloc
        config['active_provider'] = provider
        
        with open("config/config.yaml", 'w') as f:
            yaml.dump(config, f)
        st.success("Settings saved! Restart app to fully apply provider changes.")
