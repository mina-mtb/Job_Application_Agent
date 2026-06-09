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
        st.caption("Flow: new ➔ needs_review ➔ cv_generated ➔ applied / rejected / not_suitable")
    with col_b:
        if st.button("Score New Jobs"):
            from core.app_helpers import run_daily_matching
            with st.spinner("Scoring new jobs..."):
                stats = run_daily_matching(db, matcher)
                st.success(f"Processed: {stats['processed']} | Suitable: {stats['suitable']} | Rejected: {stats['rejected']} | Errors: {stats['errors']}")
                # We do not rerun immediately so the user can read the success message.
                # The user can refresh the page or it updates on next action.
                
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
    
    @st.dialog("CV Generation Strategy", width="large")
    def cv_generation_dialog(job, db, km, tailor):
        st.write(f"Evaluating strategy for: **{job['title']}** at **{job['company']}**")
        
        # Calculate scores
        with st.spinner("Analyzing past CVs and your base profile..."):
            best_match = km.get_best_past_cv_match(job['description'])
            predicted_score = km.predict_new_cv_score(job['description'])
            
        st.markdown("### Analysis Results")
        if best_match:
            old_jobs = db.execute_query("SELECT title, company FROM jobs WHERE job_id = ?", (best_match['job_id'],))
            old_job_title = f"{old_jobs[0]['title']} at {old_jobs[0]['company']}" if old_jobs else "an unknown job"
            st.info(f"🔍 **Best Past CV Found:** You previously generated a CV for **{old_job_title}**.\n\n**Match Score:** {best_match['score']}%")
        else:
            st.info("🔍 **No highly relevant past CVs found.**")
            
        st.success(f"✨ **Predicted New CV Score:** {predicted_score}%\n\n(Estimated match if we generate a brand new CV using Claude)")
                   
        st.markdown("---")
        st.write("Would you like to reuse the past CV (Free) or generate a new one (Uses API)?")
        
        col1, col2 = st.columns(2)
        with col1:
            if best_match:
                if st.button("♻️ Reuse Past CV (Free)", use_container_width=True):
                    old_job_data = db.execute_query("SELECT generated_cv_path FROM jobs WHERE job_id = ?", (best_match['job_id'],))
                    if old_job_data and old_job_data[0]['generated_cv_path'] and os.path.exists(old_job_data[0]['generated_cv_path']):
                        old_path = old_job_data[0]['generated_cv_path']
                        from datetime import date
                        import shutil
                        today = date.today().strftime("%Y-%m-%d")
                        safe_company = "".join(x for x in (job.get('company') or "Unknown") if x.isalnum() or x in " _-")
                        safe_title = "".join(x for x in (job.get('title') or "Job") if x.isalnum() or x in " _-")
                        folder_name = f"{safe_company}_{safe_title}".replace(" ", "_")
                        out_dir = os.path.join("outputs", today, folder_name)
                        os.makedirs(out_dir, exist_ok=True)
                        new_path = os.path.join(out_dir, "tailored_cv.md")
                        shutil.copy2(old_path, new_path)
                        # Copy PDF too if exists
                        old_pdf = old_path.replace(".md", ".pdf")
                        if os.path.exists(old_pdf):
                            new_pdf = os.path.join(out_dir, "tailored_cv.pdf")
                            shutil.copy2(old_pdf, new_pdf)
                            
                        db.execute_query("UPDATE jobs SET status = 'cv_generated', generated_cv_path = ? WHERE job_id = ?", (new_path, job['job_id']))
                        st.success("Past CV successfully reused!")
                        st.rerun()
                    else:
                        st.error("Could not find the old CV file.")
            else:
                st.write("*(No past CV to reuse)*")
                    
        with col2:
            if st.button("🚀 Generate New CV (API)", use_container_width=True, type="primary"):
                st.session_state[f"confirm_gen_{job['job_id']}"] = True

        if st.session_state.get(f"confirm_gen_{job['job_id']}", False):
            st.warning("⚠️ **Double Confirmation**: This action will consume API credits. Are you absolutely sure you want to generate a new CV?")
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("✅ Yes, proceed and pay", use_container_width=True):
                    with st.spinner("Generating CV..."):
                        success = tailor.generate_tailored_cv(job['job_id'])
                        if success:
                            st.success("CV Generated!")
                            st.session_state[f"confirm_gen_{job['job_id']}"] = False
                            st.rerun()
                        else:
                            st.error("Failed to generate CV.")
            with c_no:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state[f"confirm_gen_{job['job_id']}"] = False
                    st.rerun()

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
                    if st.button("Prepare CV", key=f"gen_{job['job_id']}"):
                        cv_generation_dialog(job, db, km, tailor)
            with c2:
                if job.get('generated_cv_path') and os.path.exists(job['generated_cv_path']):
                    if st.button("Preview Text CV", key=f"prev_{job['job_id']}"):
                        with open(job['generated_cv_path'], 'r', encoding='utf-8') as f:
                            st.markdown(f.read())
                            
                    pdf_path = job['generated_cv_path'].replace('.md', '.pdf')
                    if os.path.exists(pdf_path):
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                label="📥 Download PDF",
                                data=f,
                                file_name=os.path.basename(pdf_path),
                                mime="application/pdf",
                                key=f"dl_pdf_{job['job_id']}"
                            )
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
    uploaded_file = st.file_uploader("Upload Profile or Experience Document (.md, .txt, .pdf)", type=['md', 'txt', 'pdf'])
    
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
            
    @st.dialog("Viewing/Editing Source", width="large")
    def source_dialog(f, km):
        path = km.processed_dir / f
        if not path.exists():
            st.error("File no longer exists.")
            return

        if f.endswith('.pdf'):
            st.info("PDF files cannot be edited directly. Please delete and upload a new version.")
            try:
                import base64
                with open(path, "rb") as f_obj:
                    base64_pdf = base64.b64encode(f_obj.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not read PDF: {e}")
                
            if st.button("Close Viewer"):
                st.rerun()
        else:
            with open(path, 'r', encoding='utf-8') as file_obj:
                content = file_obj.read()
                
            tab_preview, tab_edit = st.tabs(["👁 Preview", "✏️ Edit Source"])
            
            with tab_preview:
                st.markdown(content)
                if st.button("Close Viewer"):
                    st.rerun()
                    
            with tab_edit:
                new_content = st.text_area("Content", content, height=400)
                
                c1, c2 = st.columns([2, 8])
                with c1:
                    if st.button("💾 Save Changes"):
                        km.delete_source(f)
                        
                        temp_dir = "temp_uploads"
                        os.makedirs(temp_dir, exist_ok=True)
                        original_name = f.split('_')[0] + '.md' if '_' in f else f
                        temp_path = os.path.join(temp_dir, original_name)
                        with open(temp_path, "w", encoding="utf-8") as file_obj:
                            file_obj.write(new_content)
                            
                        from pathlib import Path
                        km.add_source(Path(temp_path))
                        st.rerun()
                with c2:
                    if st.button("❌ Cancel"):
                        st.rerun()

    @st.dialog("Confirm Deletion")
    def confirm_delete_dialog(f, km):
        st.warning(f"Are you sure you want to delete **{f}**?")
        st.write("This will permanently remove the file and its knowledge from the AI database.")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚨 Yes, Delete It", use_container_width=True):
                if km.delete_source(f):
                    st.success(f"Deleted {f}")
                    st.rerun()
                else:
                    st.error(f"Failed to delete {f}")
        with c2:
            if st.button("Cancel", use_container_width=True):
                st.rerun()

    st.subheader("Current Processed Sources")
    processed_dir = km.processed_dir
    if os.path.exists(processed_dir):
        files = os.listdir(processed_dir)
        if files:
            selected_file = st.radio("Select a source file to manage:", files, key="selected_source")
            
            st.markdown("<br>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([2, 2, 6])
            with col1:
                if st.button("👁 View/Edit Selected", use_container_width=True):
                    source_dialog(selected_file, km)
            with col2:
                if st.button("🗑 Delete Selected", use_container_width=True):
                    confirm_delete_dialog(selected_file, km)
            st.markdown("---")
            st.subheader("Default Base CV Template")
            st.write("Choose which file should be used as the main template when generating your CV.")
            
            import json
            from pathlib import Path
            settings_path = Path("knowledge_base") / "settings.json"
            settings = {}
            if settings_path.exists():
                try:
                    with open(settings_path, "r", encoding="utf-8") as sf:
                        settings = json.load(sf)
                except:
                    pass
            
            current_template = settings.get("default_cv_template")
            if current_template not in files:
                current_template = files[0]
                
            selected_template = st.selectbox(
                "Select Default Template:",
                options=files,
                index=files.index(current_template)
            )
            
            if selected_template != settings.get("default_cv_template"):
                settings["default_cv_template"] = selected_template
                with open(settings_path, "w", encoding="utf-8") as sf:
                    json.dump(settings, sf)
                st.success(f"Default template set to: {selected_template}")

            st.markdown("---")
            st.subheader("🤖 AI Template Assistant")
            st.write("Chat with the AI to teach it how to use this template. Any instructions or rules you provide will be permanently saved and applied to all future CVs.")
            
            if "cv_rules" in settings and settings["cv_rules"]:
                with st.expander("📝 Current Learned Rules", expanded=False):
                    for idx, rule in enumerate(settings["cv_rules"]):
                        st.markdown(f"- {rule}")
                    if st.button("Clear All Rules"):
                        settings["cv_rules"] = []
                        with open(settings_path, "w", encoding="utf-8") as sf:
                            json.dump(settings, sf)
                        st.rerun()

            chat_container = st.container(height=350)
            
            with chat_container:
                if "ai_chat" not in st.session_state:
                    st.session_state.ai_chat = [{"role": "assistant", "content": "Hello! I am ready to learn. How should I customize your CVs using this template? (e.g., 'Never change my contact info', 'Keep the Skills section layout exactly the same')"} ]
                    
                for msg in st.session_state.ai_chat:
                    with st.chat_message(msg["role"]):
                        st.markdown(msg["content"])
                    
            if prompt := st.chat_input("Tell the AI how to use the template..."):
                st.session_state.ai_chat.append({"role": "user", "content": prompt})
                
                if "cv_rules" not in settings:
                    settings["cv_rules"] = []
                settings["cv_rules"].append(prompt)
                
                with open(settings_path, "w", encoding="utf-8") as sf:
                    json.dump(settings, sf)
                    
                # Simple conversational reply
                reply = f"✅ Got it! I've noted down: *\"{prompt}\"*.\n\nI will make sure to follow this instruction for all your future CVs. Is there anything else about the formatting or content that I should know?"
                st.session_state.ai_chat.append({"role": "assistant", "content": reply})
                st.rerun()
        else:
            st.write("No sources uploaded yet.")
with tab3:
    st.header("Manual Job Entry")
    
    st.info("Paste the full job description. URL alone is stored as job_link, but matching requires description text unless URL scraping is enabled.")
    
    if "m_link" not in st.session_state:
        st.session_state.m_link = ""
    if "m_title" not in st.session_state:
        st.session_state.m_title = ""
    if "m_company" not in st.session_state:
        st.session_state.m_company = ""
    if "m_location" not in st.session_state:
        st.session_state.m_location = ""
    if "m_desc" not in st.session_state:
        st.session_state.m_desc = ""

    st.text_input("Job URL", key="m_link")
    
    if st.button("Auto-fill from URL (Safe Mode)"):
        from core.public_job_link_importer import fetch_public_job_data
        with st.spinner("Fetching public data (safe mode)..."):
            data = fetch_public_job_data(st.session_state.m_link)
            if data and not data.get("error"):
                st.session_state.m_title = data.get("title", "")
                st.session_state.m_company = data.get("company", "")
                st.session_state.m_location = data.get("location", "")
                st.session_state.m_desc = data.get("description", "")
                if data.get("warning"):
                    st.warning(data["warning"])
                st.success("Extracted public data successfully! Please review before processing.")
            else:
                err_msg = data.get("error") if data else "Unknown error"
                st.error(f"Could not extract data from this public link. Please paste the job description manually. ({err_msg})")
    
    st.text_input("Job Title", key="m_title")
    st.text_input("Company", key="m_company")
    st.text_input("Location", key="m_location")
    st.text_area("Job Description", key="m_desc")
    
    if st.button("Process Manual Job"):
        if st.session_state.m_desc and st.session_state.m_link:
            with st.spinner("Processing job via LLM..."):
                success, msg = process_manual_entry(db, matcher, st.session_state.m_desc, st.session_state.m_link, st.session_state.m_title, st.session_state.m_company, st.session_state.m_location)
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
