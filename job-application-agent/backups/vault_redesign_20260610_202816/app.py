import streamlit as st
import os
import yaml
import json
import base64
from datetime import date, datetime
from dotenv import load_dotenv
load_dotenv()
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
        config = {'active_provider': 'gemini'}
        
    if 'preferred_locations' not in config or not config['preferred_locations']:
        config['preferred_locations'] = ["Göteborg", "Gothenburg", "Västra Götaland"]

        
    provider = get_provider()
    matcher = JobMatcher(config, km, provider)
    tailor = CVTailor(db, km, provider, config)
    
    return db, km, matcher, tailor, config

db, km, matcher, tailor, config = init_system()

st.title("Job Application Agent Dashboard")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Dashboard", "🧠 Knowledge Base", "📝 CV Templates", 
    "➕ Manual Entry", "⚙️ Settings", "📋 Application History"
])

# ============================================================
# TAB 1: DASHBOARD
# ============================================================
with tab1:
    st.header("Jobs Dashboard")
    
    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.write("Manage your job pipeline below.")
        st.caption("Flow: new ➔ needs_review ➔ cv_generated ➔ approved ➔ applied / rejected / not_suitable")
    with col_b:
        if st.button("Score New Jobs"):
            from core.app_helpers import run_daily_matching
            with st.spinner("Scoring new jobs..."):
                stats = run_daily_matching(db, matcher)
                st.success(f"Processed: {stats['processed']} | Suitable: {stats['suitable']} | Rejected: {stats['rejected']} | Errors: {stats['errors']}")
                
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
    
    # ---- CV Generation Strategy Dialog ----
    @st.dialog("CV Generation Strategy", width="large")
    def cv_generation_dialog(job, db, km, tailor):
        st.write(f"Evaluating strategy for: **{job['title']}** at **{job['company']}**")
        
        # Step 1: Analyze and show scores
        with st.spinner("Analyzing your CVs and predicting acceptance chances..."):
            try:
                scores = tailor.predict_acceptance_scores(job['job_id'])
            except Exception as e:
                st.error(f"Error predicting scores: {e}")
                scores = None
        
        if scores:
            st.markdown("### 📊 Acceptance Chance Analysis")
            
            col_a, col_b, col_c = st.columns(3)
            
            # Best existing CV
            with col_a:
                best = scores.get('best_existing_cv')
                if best and best.get('score', 0) > 0:
                    st.metric("Best Existing CV", f"{best['score']}%")
                    old_jobs = db.execute_query("SELECT title, company FROM jobs WHERE job_id = ?", (best.get('job_id', ''),))
                    if old_jobs:
                        st.caption(f"From: {old_jobs[0]['title']} @ {old_jobs[0]['company']}")
                else:
                    st.metric("Best Existing CV", "N/A")
                    st.caption("No past CVs found")
            
            # Template CV prediction
            with col_b:
                template_score = scores.get('template_predicted_score', 0)
                st.metric("New CV (Template)", f"{template_score}%")
                st.caption("Uses your PDF template")
            
            # Free-form CV prediction  
            with col_c:
                free_score = scores.get('free_form_predicted_score', 0)
                st.metric("New CV (Free-form)", f"{free_score}%")
                st.caption("AI designs optimal layout")
            
            if scores.get('analysis'):
                with st.expander("🔍 Detailed Analysis"):
                    st.write(scores['analysis'])
        
        st.markdown("---")
        st.markdown("### Choose Generation Method")
        
        col1, col2, col3 = st.columns(3)
        
        # Option 1: Reuse existing CV
        with col1:
            best_cv = scores.get('best_existing_cv') if scores else None
            if best_cv and best_cv.get('path') and os.path.exists(best_cv.get('path', '')):
                if st.button("♻️ Reuse Best CV\n(Free)", use_container_width=True):
                    import shutil
                    old_path = best_cv['path']
                    today = date.today().strftime("%Y-%m-%d")
                    safe_company = "".join(x for x in (job.get('company') or "Unknown") if x.isalnum() or x in " _-")
                    safe_title = "".join(x for x in (job.get('title') or "Job") if x.isalnum() or x in " _-")
                    folder_name = f"{safe_company}_{safe_title}".replace(" ", "_")
                    out_dir = os.path.join("outputs", today, folder_name)
                    os.makedirs(out_dir, exist_ok=True)
                    
                    ext = os.path.splitext(old_path)[1]
                    new_path = os.path.join(out_dir, f"tailored_cv{ext}")
                    shutil.copy2(old_path, new_path)
                    
                    # Copy editable markdown too if exists
                    old_md = os.path.join(os.path.dirname(old_path), "tailored_cv_editable.md")
                    if os.path.exists(old_md):
                        new_md = os.path.join(out_dir, "tailored_cv_editable.md")
                        shutil.copy2(old_md, new_md)
                    
                    db.execute_query(
                        "UPDATE jobs SET status = 'cv_generated', generated_cv_path = ?, cv_generation_method = ? WHERE job_id = ?",
                        (new_path, 'reused', job['job_id'])
                    )
                    st.success("Past CV reused successfully!")
                    st.rerun()
            else:
                st.button("♻️ Reuse Best CV\n(No past CV)", use_container_width=True, disabled=True)
        
        # Option 2: Generate with template
        with col2:
            if st.button("📄 Generate with Template\n(API Call)", use_container_width=True, type="primary"):
                st.session_state[f"gen_mode_{job['job_id']}"] = "template"
                st.session_state[f"confirm_gen_{job['job_id']}"] = True
        
        # Option 3: Generate free-form
        with col3:
            if st.button("✨ Generate Free-form\n(API Call)", use_container_width=True):
                st.session_state[f"gen_mode_{job['job_id']}"] = "free_form"
                st.session_state[f"confirm_gen_{job['job_id']}"] = True
        
        # Confirmation and generation
        if st.session_state.get(f"confirm_gen_{job['job_id']}", False):
            mode = st.session_state.get(f"gen_mode_{job['job_id']}", "template")
            mode_label = "Template-based" if mode == "template" else "Free-form"
            st.warning(f"⚠️ **Confirm**: Generate a **{mode_label}** CV? This uses the Gemini API.")
            
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("✅ Yes, Generate", use_container_width=True):
                    with st.spinner(f"Generating {mode_label} CV..."):
                        try:
                            success = tailor.generate_tailored_cv(job['job_id'], mode=mode)
                            if success:
                                st.session_state[f"gen_success_{job['job_id']}"] = True
                                st.session_state[f"confirm_gen_{job['job_id']}"] = False
                                st.rerun()
                            else:
                                st.error("Failed to generate CV.")
                        except Exception as e:
                            st.error(f"Error generating CV: {e}")
            with c_no:
                if st.button("❌ Cancel", use_container_width=True):
                    st.session_state[f"confirm_gen_{job['job_id']}"] = False
                    st.rerun()
        
        # Show generated CV for review/edit
        if st.session_state.get(f"gen_success_{job['job_id']}", False):
            _show_cv_review(job, db, tailor)

    def _show_cv_review(job, db, tailor):
        """Show the CV review/edit interface."""
        updated_jobs = db.execute_query("SELECT generated_cv_path, status FROM jobs WHERE job_id = ?", (job['job_id'],))
        if not updated_jobs or not updated_jobs[0].get('generated_cv_path'):
            return
            
        cv_path = updated_jobs[0]['generated_cv_path']
        status = updated_jobs[0].get('status', '')
        
        if not os.path.exists(cv_path):
            st.error(f"CV file not found: {cv_path}")
            return
        
        st.markdown("---")
        st.markdown("### 📝 Review & Edit Your CV")
        
        # Get the editable markdown
        md_content = tailor.get_cv_markdown(job['job_id'])
        
        if md_content:
            tab_preview, tab_edit = st.tabs(["👁️ Preview (PDF)", "✏️ Edit Content"])
            
            with tab_preview:
                if cv_path.endswith('.pdf') and os.path.exists(cv_path):
                    with open(cv_path, "rb") as f:
                        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
                elif cv_path.endswith('.docx'):
                    from core.app_helpers import render_docx_preview
                    render_docx_preview(cv_path)
                else:
                    st.markdown(md_content)
                
                with open(cv_path, 'rb') as f:
                    st.download_button("📥 Download CV", f, file_name=os.path.basename(cv_path))
            
            with tab_edit:
                edited = st.text_area(
                    "Edit your CV content (Markdown)", 
                    value=md_content, 
                    height=500,
                    key=f"cv_edit_{job['job_id']}"
                )
                
                if st.button("💾 Save Changes & Re-render PDF", use_container_width=True, type="primary", key=f"save_edit_{job['job_id']}"):
                    with st.spinner("Saving and re-rendering..."):
                        try:
                            mode = 'template' if 'template' in (updated_jobs[0].get('cv_generation_method') or 'free_form') else 'free_form'
                            tailor.save_edited_cv(job['job_id'], edited, mode)
                            st.success("Changes saved and PDF re-rendered!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving: {e}")
        else:
            # No markdown, just show PDF/file preview
            if cv_path.endswith('.pdf'):
                with open(cv_path, "rb") as f:
                    base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
                st.markdown(pdf_display, unsafe_allow_html=True)
                with open(cv_path, 'rb') as f:
                    st.download_button("📥 Download PDF", f, file_name=os.path.basename(cv_path))
        
        # Approval / Rejection buttons
        if status == 'cv_pending_approval':
            st.markdown("---")
            st.info("⚠️ This CV is pending your approval.")
            c_app, c_rej = st.columns(2)
            with c_app:
                if st.button("✅ Approve CV", use_container_width=True, type="primary", key=f"approve_cv_{job['job_id']}"):
                    with st.spinner("Finalizing..."):
                        tailor.approve_and_finalize_cv(job['job_id'])
                    st.success("CV Approved and Finalized!")
                    st.session_state[f"gen_success_{job['job_id']}"] = False
                    st.rerun()
            with c_rej:
                if st.button("❌ Reject & Delete", use_container_width=True, key=f"reject_cv_{job['job_id']}"):
                    db.execute_query("UPDATE jobs SET status = 'needs_review', generated_cv_path = NULL WHERE job_id = ?", (job['job_id'],))
                    st.session_state[f"gen_success_{job['job_id']}"] = False
                    st.rerun()
        else:
            if st.button("✅ Close & Return to Dashboard", key=f"close_dialog_{job['job_id']}"):
                st.session_state[f"gen_success_{job['job_id']}"] = False
                st.rerun()

    # ---- CV Edit Dialog (for already-generated CVs) ----
    @st.dialog("Edit CV", width="large")
    def cv_edit_dialog(job, db, tailor):
        """Popup to edit an already-generated CV."""
        cv_path = job.get('generated_cv_path', '')
        if not cv_path or not os.path.exists(cv_path):
            st.error("CV file not found.")
            return
        
        md_content = tailor.get_cv_markdown(job['job_id'])
        
        st.markdown(f"### Editing CV for: {job['title']} at {job['company']}")
        
        if md_content:
            tab_preview, tab_edit = st.tabs(["👁️ Preview", "✏️ Edit"])
            
            with tab_preview:
                if cv_path.endswith('.pdf') and os.path.exists(cv_path):
                    with open(cv_path, "rb") as f:
                        base64_pdf = base64.b64encode(f.read()).decode('utf-8')
                    st.markdown(f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>', unsafe_allow_html=True)
                else:
                    st.markdown(md_content)
            
            with tab_edit:
                edited = st.text_area("Edit CV (Markdown)", value=md_content, height=500, key=f"edit_existing_{job['job_id']}")
                if st.button("💾 Save & Re-render PDF", use_container_width=True, type="primary"):
                    with st.spinner("Saving..."):
                        try:
                            mode = job.get('cv_generation_method', 'free_form')
                            if mode not in ('template', 'free_form'):
                                mode = 'free_form'
                            tailor.save_edited_cv(job['job_id'], edited, mode)
                            st.success("Saved!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
        else:
            st.warning("No editable markdown found for this CV. It may have been generated with an older version.")
            if cv_path.endswith('.pdf'):
                with open(cv_path, "rb") as f:
                    st.download_button("📥 Download PDF", f, file_name=os.path.basename(cv_path))

    # ---- Job Cards ----
    status_emojis = {
        "new": "🔵",
        "needs_review": "🟡",
        "cv_pending_approval": "⏳",
        "cv_generated": "🟣",
        "approved": "🟢",
        "applied": "✅",
        "rejected": "🔴",
        "not_suitable": "❌"
    }
    
    for job in jobs:
        emoji = status_emojis.get(job.get('status'), "⚪")
        score_display = job.get('suitability_score') if job.get('suitability_score') is not None else "?"
        with st.expander(f"{emoji} {job.get('title')} at {job.get('company')} ({job.get('status')}) - Score: {score_display}"):
            col_info_1, col_info_2 = st.columns(2)
            with col_info_1:
                st.write(f"**Location:** {job.get('location')}")
                st.write(f"**Category:** {job.get('suitability_category')}")
                if job.get('job_link'):
                    st.write(f"**Link:** [Job Post]({job.get('job_link')})")
            with col_info_2:
                st.write(f"**Reasons for match:** {job.get('reasons_for_match')}")
                st.write(f"**Weaknesses:** {job.get('weaknesses_or_risks')}")
            
            if job.get('user_notes'):
                st.write(f"**Notes:** {job.get('user_notes')}")
            if job.get('generated_cv_path'):
                st.write(f"**CV Path:** `{job.get('generated_cv_path')}`")
            
            # Action buttons
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                if can_generate_cv(job.get('status')):
                    if st.button("🎯 Prepare CV", key=f"gen_{job['job_id']}"):
                        cv_generation_dialog(job, db, km, tailor)
                        
            with c2:
                if job.get('generated_cv_path') and os.path.exists(job['generated_cv_path']):
                    # Edit button
                    if st.button("✏️ Edit CV", key=f"edit_{job['job_id']}"):
                        cv_edit_dialog(job, db, tailor)
                    
                    # Download buttons
                    if job['generated_cv_path'].endswith('.pdf'):
                        with open(job['generated_cv_path'], "rb") as f:
                            st.download_button(
                                label="📥 Download PDF",
                                data=f,
                                file_name=os.path.basename(job['generated_cv_path']),
                                mime="application/pdf",
                                key=f"dl_pdf_{job['job_id']}"
                            )
                    elif job['generated_cv_path'].endswith('.docx'):
                        with open(job['generated_cv_path'], "rb") as f:
                            st.download_button(
                                label="📝 Download DOCX",
                                data=f,
                                file_name=os.path.basename(job['generated_cv_path']),
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"dl_docx_{job['job_id']}"
                            )
                    
                    # Delete CV button
                    if st.button("🗑️ Delete CV", key=f"del_cv_{job['job_id']}"):
                        try:
                            if os.path.exists(job['generated_cv_path']):
                                os.remove(job['generated_cv_path'])
                            # Also delete associated files
                            cv_dir = os.path.dirname(job['generated_cv_path'])
                            for ext_file in ['tailored_cv_editable.md', 'tailored_cv.html']:
                                fpath = os.path.join(cv_dir, ext_file)
                                if os.path.exists(fpath):
                                    os.remove(fpath)
                        except Exception:
                            pass
                        db.execute_query("UPDATE jobs SET status = 'needs_review', generated_cv_path = NULL WHERE job_id = ?", (job['job_id'],))
                        st.rerun()
                        
            with c3:
                if can_approve(job.get('status')):
                    if st.button("👍 Approve", key=f"appr_{job['job_id']}"):
                        update_job_status(db, job['job_id'], "approved")
                        st.rerun()
                        
            with c4:
                if can_mark_applied(job.get('generated_cv_path')):
                    if st.button("📤 Mark Applied", key=f"ma_{job['job_id']}"):
                        # Save the CV path used for application
                        db.execute_query(
                            "UPDATE jobs SET status = 'applied', date_applied = CURRENT_TIMESTAMP, applied_cv_path = ? WHERE job_id = ?",
                            (job.get('generated_cv_path', ''), job['job_id'])
                        )
                        st.rerun()
                        
            with c5:
                if job.get('status') not in ['applied', 'rejected', 'not_suitable']:
                    if st.button("🔴 Reject", key=f"rej_{job['job_id']}"):
                        update_job_status(db, job['job_id'], "rejected")
                        st.rerun()
                    if st.button("❌ Not Suitable", key=f"ns_{job['job_id']}"):
                        update_job_status(db, job['job_id'], "not_suitable")
                        st.rerun()
                        
            # Notes
            note = st.text_input("Add Note", key=f"note_in_{job['job_id']}")
            if st.button("Save Note", key=f"save_note_{job['job_id']}"):
                if note:
                    add_user_note(db, job['job_id'], note)
                    st.rerun()

# ============================================================
# TAB 2: KNOWLEDGE BASE
# ============================================================
with tab2:
    st.header("Knowledge Base Management")
    uploaded_file = st.file_uploader("Upload Profile or Experience (.md, .txt, .pdf, .docx)", type=['md', 'txt', 'pdf', 'docx'])
    
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

        if f.endswith('.pdf') or f.endswith('.docx'):
            st.info("This file type cannot be edited directly in the browser.")
            try:
                with open(path, "rb") as f_obj:
                    file_data = f_obj.read()
                    base64_data = base64.b64encode(file_data).decode('utf-8')
                
                st.download_button(
                    label=f"⬇️ Download {f}",
                    data=file_data,
                    file_name=f,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document" if f.endswith('.docx') else "application/pdf"
                )
                
                if f.endswith('.pdf'):
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_data}" width="100%" height="600" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Could not read file: {e}")
                
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
                        success, final_name = km.add_source(Path(temp_path))
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
        else:
            st.info("No sources uploaded yet.")

# ============================================================
# TAB 3: CV TEMPLATES
# ============================================================
with tab3:
    st.header("CV Templates Management")
    st.write("Upload your PDF templates here. The app will use these to overlay your profile and skills.")
    
    template_dir = "templates/cv"
    os.makedirs(template_dir, exist_ok=True)
    
    uploaded_template = st.file_uploader("Upload PDF CV Template", type=['pdf'])
    if st.button("Save Template") and uploaded_template is not None:
        temp_path = os.path.join(template_dir, uploaded_template.name)
        with open(temp_path, "wb") as f:
            f.write(uploaded_template.getbuffer())
        st.success(f"Template saved: {uploaded_template.name}")
        st.rerun()

    st.subheader("Available Templates")
    template_files = os.listdir(template_dir) if os.path.exists(template_dir) else []
    
    if template_files:
        from pathlib import Path
        settings_path = Path("knowledge_base") / "settings.json"
        settings = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as sf:
                    settings = json.load(sf)
            except Exception:
                pass
        
        current_template = settings.get("default_cv_template")
        if current_template not in template_files:
            current_template = template_files[0]
            
        selected_template = st.selectbox(
            "Select Default Template:",
            options=template_files,
            index=template_files.index(current_template) if current_template in template_files else 0
        )
        
        if selected_template and selected_template != settings.get("default_cv_template"):
            settings["default_cv_template"] = selected_template
            with open(settings_path, "w", encoding="utf-8") as sf:
                json.dump(settings, sf)
            st.success(f"Default template set to: {selected_template}")
            import time
            time.sleep(1.5)
            st.rerun()
            
        if st.button("Delete Selected Template"):
            try:
                os.remove(os.path.join(template_dir, selected_template))
                st.success("Deleted template.")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to delete: {e}")
                
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
            st.session_state.ai_chat.append({"role": "assistant", "content": f"Got it! I've saved the rule: '{prompt}'"})
            st.rerun()
    else:
        st.info("No templates found. Please upload a PDF template.")

# ============================================================
# TAB 4: MANUAL ENTRY
# ============================================================
with tab4:
    st.header("Manual Job Entry")
    
    st.info("Paste the job URL and let the AI extract details, or fill in manually.")
    
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
                    import time
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.error("Job URL and Description are required.")

# ============================================================
# TAB 5: SETTINGS (was incorrectly in tab4 before!)
# ============================================================
with tab5:
    st.header("Settings")
    
    st.write("Edit configuration values here. Secrets are loaded from environment variables.")
    
    locs = st.text_area("Preferred Locations (comma separated)", value=", ".join(config.get('preferred_locations', [])))
    allow_rem = st.checkbox("Allow Remote", value=config.get('allow_remote', True))
    allow_hyb = st.checkbox("Allow Hybrid", value=config.get('allow_hybrid', True))
    rej_reloc = st.checkbox("Reject Relocation Required", value=config.get('reject_relocation_required', True))
    provider = st.selectbox("Active Provider", ["gemini", "mock", "claude", "openai"], 
                           index=["gemini", "mock", "claude", "openai"].index(config.get('active_provider', 'gemini')) if config.get('active_provider', 'gemini') in ["gemini", "mock", "claude", "openai"] else 0)
    
    if st.button("Save Settings"):
        config['preferred_locations'] = [l.strip() for l in locs.split(",") if l.strip()]
        config['allow_remote'] = allow_rem
        config['allow_hybrid'] = allow_hyb
        config['reject_relocation_required'] = rej_reloc
        config['active_provider'] = provider
        
        with open("config/config.yaml", 'w') as f:
            yaml.dump(config, f)
        st.success("Settings saved! Restart app to fully apply provider changes.")

# ============================================================
# TAB 6: APPLICATION HISTORY (was incorrectly in tab5 before!)
# ============================================================
with tab6:
    st.header("Application History")
    st.write("Complete history of jobs you have applied for.")
    
    import pandas as pd
    all_jobs = db.get_all_jobs()
    applied_jobs = [j for j in all_jobs if j.get('status') == 'applied']
    
    if applied_jobs:
        df = pd.DataFrame([{
            "Date Applied": j.get('date_applied', 'Unknown'),
            "Company": j.get('company', ''),
            "Title": j.get('title', ''),
            "Score": j.get('suitability_score', ''),
            "Predicted %": j.get('acceptance_score_predicted', ''),
            "CV Method": j.get('cv_generation_method', ''),
            "Link": j.get('job_link', ''),
            "CV Path": j.get('applied_cv_path') or j.get('generated_cv_path', ''),
        } for j in applied_jobs])
        st.dataframe(df, use_container_width=True)
        
        # Download CVs from history
        st.subheader("Download CVs")
        for j in applied_jobs:
            cv_p = j.get('applied_cv_path') or j.get('generated_cv_path', '')
            if cv_p and os.path.exists(cv_p):
                with open(cv_p, 'rb') as f:
                    st.download_button(
                        f"📥 {j.get('company', '')} - {j.get('title', '')}",
                        f,
                        file_name=os.path.basename(cv_p),
                        key=f"hist_dl_{j['job_id']}"
                    )
    else:
        st.info("No applications yet. Your applied jobs will appear here.")
