import streamlit as st
import os
import uuid
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
from core.cv_vault import CVVault, SLOTS
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
    vault = CVVault(db, km)
    # One-time import of any CVs that already exist on jobs into the vault.
    try:
        vault.backfill_from_jobs()
    except Exception as e:
        print(f"Vault backfill skipped: {e}")

    return db, km, matcher, tailor, vault, config

db, km, matcher, tailor, vault, config = init_system()

st.title("Job Application Agent Dashboard")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Dashboard", "🧠 Knowledge Base", "📝 CV Templates", 
    "➕ Manual Entry", "⚙️ Settings", "📋 Tracker"
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
        "not_suitable": "❌",
        "cv_generated": "🟣",
        "approved": "🟢",
    }

    # ====================================================================
    # CV Vault redesign — helpers & dialogs
    # ====================================================================
    SLOT_LABEL = {
        "vault": "From Vault (reuse best CV)",
        "template": "Generate with Template",
        "free_form": "Generate Free-form",
    }

    def _render_cv_pdf(markdown_text, out_dir, base_name="tailored_cv"):
        """Render markdown -> styled HTML -> PDF. Returns final path (pdf or html)."""
        os.makedirs(out_dir, exist_ok=True)
        html_path = os.path.join(out_dir, f"{base_name}.html")
        tailor._markdown_to_styled_html(markdown_text, html_path)
        from utils.exporter import export_pdf as _exp_pdf
        pdf_path = os.path.join(out_dir, f"{base_name}.pdf")
        ok = False
        try:
            ok = _exp_pdf(html_path, pdf_path)
        except Exception:
            ok = False
        return pdf_path if (ok and os.path.exists(pdf_path)) else html_path

    def _do_find_vault(job):
        best, score, expl = vault.find_best_match(job)
        if not best:
            st.warning(expl)
            return
        vault.set_candidate(job['job_id'], 'vault', cv_id=best['cv_id'],
                            match_score=score, match_explanation=expl)

    def _do_generate(job, mode):
        slot = 'template' if mode == 'template' else 'free_form'
        ok = tailor.generate_tailored_cv(job['job_id'], mode=mode)
        if not ok:
            st.error("Generation failed.")
            return
        rows = db.execute_query(
            "SELECT generated_cv_path, template_used FROM jobs WHERE job_id = ?",
            (job['job_id'],))
        path = rows[0]['generated_cv_path'] if rows else None
        md = tailor.get_cv_markdown(job['job_id'])
        cv_id = vault.register_cv(
            markdown_content=md, file_path=path, generation_method=mode,
            origin_job_id=job['job_id'],
            template_used=rows[0].get('template_used') if rows else None)
        score = vault.score_text(vault._job_text(job), md or "")
        vault.set_candidate(job['job_id'], slot, cv_id=cv_id, match_score=score,
                            match_explanation=f"Freshly generated ({mode}).")

    def _do_delete_slot(job, slot, cand):
        cv_id = cand.get('cv_id') if cand else None
        if not cv_id:
            return
        # On the 'vault' row the CV is a reused, shared record — remove it from
        # the vault but keep the underlying file (it may belong to another job).
        # On generated rows, delete the file too.
        vault.delete_cv(cv_id, remove_file=(slot != 'vault'))
        vault.clear_candidate(job['job_id'], slot)

    @st.dialog("View / Edit CV", width="large")
    def view_edit_dialog(job, slot, cv_id):
        cv = vault.get_cv(cv_id)
        if not cv:
            st.error("CV not found in vault.")
            return
        st.caption(f"{SLOT_LABEL.get(slot, slot)} — {cv.get('label', '')}")
        md = cv.get('markdown_content') or ""
        file_path = cv.get('file_path')

        tab_prev, tab_edit = st.tabs(["👁 Preview", "✏️ Edit"])
        with tab_prev:
            if file_path and file_path.endswith('.pdf') and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode('utf-8')
                st.markdown(
                    f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="560" type="application/pdf"></iframe>',
                    unsafe_allow_html=True)
            elif md:
                st.markdown(md)
            else:
                st.info("No preview available for this CV.")
        with tab_edit:
            if not md:
                st.info("This CV has no editable markdown content.")
            else:
                edited = st.text_area("Edit CV (Markdown)", value=md, height=460,
                                      key=f"ve_txt_{job['job_id']}_{slot}")
                st.caption("Saving creates a NEW CV in the vault — the original is kept.")
                if st.button("💾 Save as new vault CV", type="primary",
                             key=f"ve_save_{job['job_id']}_{slot}"):
                    out_dir = os.path.join("outputs", "vault_edits",
                                           f"{job['job_id']}_{slot}_{uuid.uuid4().hex[:6]}")
                    final = _render_cv_pdf(edited, out_dir)
                    with open(os.path.join(out_dir, "tailored_cv_editable.md"), "w", encoding="utf-8") as f:
                        f.write(edited)
                    new_id = vault.register_cv(
                        markdown_content=edited, file_path=final, generation_method='edited',
                        origin_job_id=job['job_id'], parent_cv_id=cv_id,
                        template_used=cv.get('template_used'))
                    vault.set_candidate(
                        job['job_id'], slot, cv_id=new_id,
                        match_score=vault.score_text(vault._job_text(job), edited),
                        match_explanation="Edited copy saved to vault.")
                    db.execute_query("UPDATE jobs SET generated_cv_path = ? WHERE job_id = ?",
                                     (final, job['job_id']))
                    st.success("Saved as a new CV in the vault.")
                    st.rerun()

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
            
            # ----------------------------------------------------------------
            # CV options — three rows (Vault / Template / Free-form)
            # ----------------------------------------------------------------
            st.markdown("---")
            st.markdown("##### CV options for this job")
            cands = vault.ensure_candidates(job['job_id'])

            # Header row
            h = st.columns([2.4, 1, 1, 1, 1.2, 0.8])
            for col, lbl in zip(h, ["Action", "View/Edit", "Delete", "Match", "Download", "Use"]):
                col.caption(lbl)

            for slot in SLOTS:
                cand = cands.get(slot, {})
                cv_id = cand.get('cv_id')
                has_cv = bool(cv_id)
                cv = vault.get_cv(cv_id) if has_cv else None
                file_path = cv.get('file_path') if cv else None

                rc = st.columns([2.4, 1, 1, 1, 1.2, 0.8])

                # col 0 — primary action (Choose / Generate). Disabled once filled.
                with rc[0]:
                    if slot == 'vault':
                        if st.button("🔎 Find Best CV", key=f"find_{job['job_id']}",
                                     disabled=has_cv, use_container_width=True):
                            with st.spinner("Searching your CV vault..."):
                                _do_find_vault(job)
                            st.rerun()
                    elif slot == 'template':
                        if st.button("📄 Generate (Template)", key=f"gent_{job['job_id']}",
                                     disabled=has_cv, use_container_width=True):
                            with st.spinner("Generating CV with template (uses AI)..."):
                                _do_generate(job, 'template')
                            st.rerun()
                    else:
                        if st.button("✨ Generate (Free)", key=f"genf_{job['job_id']}",
                                     disabled=has_cv, use_container_width=True):
                            with st.spinner("Generating free-form CV (uses AI)..."):
                                _do_generate(job, 'free_form')
                            st.rerun()
                    st.caption(SLOT_LABEL[slot])

                # col 1 — View / Edit (enabled only when a CV exists)
                with rc[1]:
                    if st.button("👁 View/Edit", key=f"vebtn_{job['job_id']}_{slot}",
                                 disabled=not has_cv, use_container_width=True):
                        view_edit_dialog(job, slot, cv_id)

                # col 2 — Delete (inverse of the action button)
                with rc[2]:
                    if st.button("🗑 Delete", key=f"del_{job['job_id']}_{slot}",
                                 disabled=not has_cv, use_container_width=True):
                        _do_delete_slot(job, slot, cand)
                        st.rerun()

                # col 3 — match %
                with rc[3]:
                    ms = cand.get('match_score')
                    ai = cand.get('ai_acceptance_score')
                    if ms is not None:
                        st.metric("Match", f"{ms}%", label_visibility="collapsed")
                        if ai is not None:
                            st.caption(f"AI: {ai}%")
                    else:
                        st.write("—")

                # col 4 — download PDF
                with rc[4]:
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            st.download_button(
                                "📥 PDF", f, file_name=os.path.basename(file_path),
                                key=f"dl_{job['job_id']}_{slot}", use_container_width=True)
                    else:
                        st.write("")

                # col 5 — per-row select marker (acts as the radio)
                with rc[5]:
                    is_sel = bool(cand.get('is_selected'))
                    if st.button("🔵" if is_sel else "⚪",
                                 key=f"sel_{job['job_id']}_{slot}", disabled=not has_cv,
                                 help="Select this CV to apply with"):
                        vault.select_candidate(job['job_id'], slot)
                        st.rerun()

            # Skill match panel
            with st.expander("📊 Skill match & suggestions"):
                from core.match_analyzer import MatchAnalyzer
                from core.skills_store import load_candidate_skills
                _ma = MatchAnalyzer(embed_fn=km.embedding_function)
                _report = _ma.analyze(job.get('description', '') or '', load_candidate_skills())
                st.metric("Skill match", f"{_report['score']}%")
                _have = [r['job_skill'] for r in _report['matched']] + [r['job_skill'] for r in _report['related']]
                _miss = [r['job_skill'] for r in _report['missing']]
                if _have:
                    st.markdown("**Matched:** " + ", ".join(_have))
                if _miss:
                    st.markdown("**Missing:** " + ", ".join(_miss))
                for _s in _report['suggestions']:
                    st.write("• " + _s)

            # Optional paid deep analysis
            with st.expander("🤖 Deep AI fit analysis (optional — uses API)"):
                st.caption("Predicts acceptance chance for the best vault CV, a template CV, and a free-form CV.")
                if st.button("Run AI analysis", key=f"ai_{job['job_id']}"):
                    with st.spinner("Asking the AI..."):
                        try:
                            scores = tailor.predict_acceptance_scores(job['job_id'])
                            if scores:
                                if scores.get('best_existing_cv'):
                                    vault.set_candidate(job['job_id'], 'vault',
                                        ai_acceptance_score=scores['best_existing_cv'].get('score'))
                                vault.set_candidate(job['job_id'], 'template',
                                    ai_acceptance_score=scores.get('template_predicted_score'))
                                vault.set_candidate(job['job_id'], 'free_form',
                                    ai_acceptance_score=scores.get('free_form_predicted_score'))
                                if scores.get('analysis'):
                                    st.info(scores['analysis'])
                        except Exception as e:
                            st.error(f"AI analysis failed: {e}")
                    st.rerun()

            # ----------------------------------------------------------------
            # Decision row
            # ----------------------------------------------------------------
            st.markdown("---")
            selected = vault.get_selected(job['job_id'])
            if selected and selected.get('cv_id'):
                st.write(f"**Selected to apply with:** {SLOT_LABEL.get(selected['slot'], selected['slot'])}")
            else:
                st.caption("Pick one CV above (Use column) before approving.")

            d1, d2, d3, d4 = st.columns(4)
            with d1:
                if st.button("✅ Approve", key=f"appr_{job['job_id']}",
                             disabled=not (selected and selected.get('cv_id')),
                             use_container_width=True):
                    sel_cv = vault.get_cv(selected['cv_id']) or {}
                    db.execute_query(
                        "UPDATE jobs SET status = 'approved', selected_cv_id = ?, generated_cv_path = ? WHERE job_id = ?",
                        (selected['cv_id'], sel_cv.get('file_path'), job['job_id']))
                    st.rerun()
            with d2:
                approved_cv = job.get('selected_cv_id')
                if st.button("📤 Mark Applied", key=f"ma_{job['job_id']}",
                             disabled=not approved_cv, use_container_width=True):
                    cvrow = vault.get_cv(approved_cv) or {}
                    db.execute_query(
                        "UPDATE jobs SET status = 'applied', date_applied = CURRENT_TIMESTAMP, "
                        "applied_cv_id = ?, applied_cv_path = ? WHERE job_id = ?",
                        (approved_cv, cvrow.get('file_path'), job['job_id']))
                    st.rerun()
            with d3:
                if st.button("🔴 Reject", key=f"rej_{job['job_id']}",
                             disabled=job.get('status') in ['applied', 'rejected', 'not_suitable'],
                             use_container_width=True):
                    update_job_status(db, job['job_id'], "rejected")
                    st.rerun()
            with d4:
                if st.button("❌ Not Suitable", key=f"ns_{job['job_id']}",
                             disabled=job.get('status') in ['applied', 'rejected', 'not_suitable'],
                             use_container_width=True):
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
# TAB 5: SETTINGS
# ============================================================
with tab5:
    st.header("Settings")
    
    st.write("Edit configuration values here. Secrets are loaded from environment variables.")
    
    # --------------------------------------------------------
    # Personal Info Section
    # --------------------------------------------------------
    st.subheader("Personal Information")
    st.write("This information is used to build your CV header.")
    personal_info_path = "profile/personal_info.yaml"
    
    try:
        if os.path.exists(personal_info_path):
            with open(personal_info_path, "r", encoding="utf-8") as f:
                personal_info = yaml.safe_load(f) or {}
        else:
            personal_info = {}
    except Exception:
        personal_info = {}

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        pi_name = st.text_input("Full Name", value=personal_info.get("full_name", ""))
        pi_email = st.text_input("Email", value=personal_info.get("email", ""))
        pi_phone = st.text_input("Phone", value=personal_info.get("phone", ""))
    with col_p2:
        pi_location = st.text_input("Location", value=personal_info.get("location", ""))
        pi_linkedin = st.text_input("LinkedIn", value=personal_info.get("linkedin", ""))
        pi_github = st.text_input("GitHub", value=personal_info.get("github", ""))

    pi_website = st.text_input("Website (Optional)", value=personal_info.get("website", ""))

    if st.button("Save Personal Info"):
        new_pi = {
            "full_name": pi_name.strip(),
            "location": pi_location.strip(),
            "email": pi_email.strip(),
            "phone": pi_phone.strip(),
            "linkedin": pi_linkedin.strip(),
            "github": pi_github.strip(),
            "website": pi_website.strip(),
        }
        os.makedirs("profile", exist_ok=True)
        with open(personal_info_path, "w", encoding="utf-8") as f:
            yaml.dump(new_pi, f, sort_keys=False)
        st.success("Personal information saved!")

    st.markdown("---")
    
    # --------------------------------------------------------
    # App Settings Section
    # --------------------------------------------------------
    st.subheader("App Configuration")
    locs = st.text_area("Preferred Locations (comma separated)", value=", ".join(config.get('preferred_locations', [])))
    allow_rem = st.checkbox("Allow Remote", value=config.get('allow_remote', True))
    allow_hyb = st.checkbox("Allow Hybrid", value=config.get('allow_hybrid', True))
    rej_reloc = st.checkbox("Reject Relocation Required", value=config.get('reject_relocation_required', True))
    provider = st.selectbox("Active Provider", ["gemini", "mock", "claude", "openai"], 
                           index=["gemini", "mock", "claude", "openai"].index(config.get('active_provider', 'gemini')) if config.get('active_provider', 'gemini') in ["gemini", "mock", "claude", "openai"] else 0)
    
    if st.button("Save App Settings"):
        config['preferred_locations'] = [l.strip() for l in locs.split(",") if l.strip()]
        config['allow_remote'] = allow_rem
        config['allow_hybrid'] = allow_hyb
        config['reject_relocation_required'] = rej_reloc
        config['active_provider'] = provider
        
        with open("config/config.yaml", 'w', encoding="utf-8") as f:
            yaml.dump(config, f)
        st.success("Settings saved! Restart app to fully apply provider changes.")

# ============================================================
# TAB 6: APPLICATION HISTORY (was incorrectly in tab5 before!)
# ============================================================
with tab6:
    st.header("Application Tracker")
    st.write("Master table of every job. Filter, sort, and export.")

    import pandas as pd

    RESPONSE_OPTIONS = ["pending", "no_response", "acknowledged", "interview", "offer", "rejected_by_company"]

    all_jobs = db.get_all_jobs()

    # ---- Filters ----
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        f_status = st.multiselect(
            "Status",
            ["new", "needs_review", "cv_pending_approval", "cv_generated",
             "approved", "applied", "rejected", "not_suitable"],
            key="trk_status")
    with fc2:
        f_applied = st.selectbox("Applied?", ["All", "Applied", "Not applied"], key="trk_applied")
    with fc3:
        f_response = st.multiselect("Response", RESPONSE_OPTIONS, key="trk_resp")
    with fc4:
        f_min_score = st.slider("Min suitability", 0, 100, 0, key="trk_score")
    f_kw = st.text_input("Search (title / company)", key="trk_kw")

    # Build a CV-id -> label map for the "Selected CV" column.
    cv_labels = {c['cv_id']: c.get('label', '') for c in vault.list_vault(include_archived=True)}

    def _row(j):
        sel = j.get('selected_cv_id') or j.get('applied_cv_id')
        # Best match % across this job's candidate slots.
        cands = vault.get_candidates(j['job_id'])
        scores = [c.get('match_score') for c in cands.values() if c.get('match_score') is not None]
        best_match = max(scores) if scores else None
        return {
            "Title": j.get('title', ''),
            "Company": j.get('company', ''),
            "Apply Link": j.get('job_link', ''),
            "Suitable CV": cv_labels.get(sel, '') if sel else '',
            "Match %": best_match,
            "Suitability": j.get('suitability_score'),
            "Applied": "Yes" if j.get('status') == 'applied' else "No",
            "Date Applied": (j.get('date_applied') or '')[:16],
            "Response": j.get('response_status') or 'pending',
            "Response Date": (j.get('response_date') or '')[:16],
            "Status": j.get('status', ''),
            "CV Method": j.get('cv_generation_method', ''),
            "_job_id": j['job_id'],
        }

    rows = [_row(j) for j in all_jobs]

    # Apply filters
    def _keep(r, j):
        if f_status and r["Status"] not in f_status:
            return False
        if f_applied == "Applied" and r["Applied"] != "Yes":
            return False
        if f_applied == "Not applied" and r["Applied"] == "Yes":
            return False
        if f_response and r["Response"] not in f_response:
            return False
        if f_min_score and (r["Suitability"] or 0) < f_min_score:
            return False
        if f_kw:
            kw = f_kw.lower()
            if kw not in r["Title"].lower() and kw not in r["Company"].lower():
                return False
        return True

    rows = [r for r, j in zip(rows, all_jobs) if _keep(r, j)]

    st.write(f"Showing {len(rows)} of {len(all_jobs)} jobs")

    if rows:
        df = pd.DataFrame(rows).drop(columns=["_job_id"])
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Apply Link": st.column_config.LinkColumn("Apply Link", display_text="Open"),
                "Match %": st.column_config.NumberColumn("Match %", format="%d%%"),
                "Suitability": st.column_config.NumberColumn("Suitability", format="%d"),
            },
        )

        st.download_button(
            "⬇️ Export CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="application_tracker.csv",
            mime="text/csv",
        )

        # ---- Update employer response per job ----
        st.markdown("---")
        st.subheader("Update employer response")
        job_choices = {f"{r['Company']} — {r['Title']}": r["_job_id"]
                       for r in [_row(j) for j in all_jobs]}
        sel_key = st.selectbox("Job", list(job_choices.keys()), key="resp_job")
        rc1, rc2 = st.columns([1, 2])
        with rc1:
            new_resp = st.selectbox("Response status", RESPONSE_OPTIONS, key="resp_val")
        with rc2:
            resp_note = st.text_input("Note (optional)", key="resp_note")
        if st.button("Save response"):
            jid = job_choices[sel_key]
            db.execute_query(
                "UPDATE jobs SET response_status = ?, response_date = CURRENT_TIMESTAMP, "
                "response_notes = ? WHERE job_id = ?",
                (new_resp, resp_note, jid))
            st.success("Response updated.")
            st.rerun()
    else:
        st.info("No jobs match the current filters.")
