# Testing Clean Cycle

This document explains how to perform a controlled reset of the Job Application Agent state for clean testing.

## 1. How to Reset the Local Test State
To clear the application state and start fresh:
1. Ensure the Streamlit server is stopped.
2. Run the reset script from the root directory:
   ```bash
   python scripts/reset_local_test_state.py --confirm
   ```

## 2. What gets backed up
Before clearing any data, the script automatically creates a timestamped folder in `backups/clean_reset_YYYYMMDD_HHMMSS/`. It backs up:
- The `database/` folder (SQLite DB)
- The `outputs/` folder (all generated PDF and DOCX CVs)
- The `knowledge_base/` folder (raw sources, processed sources, CV templates, and ChromaDB vector database)

## 3. What gets cleared
The reset script wipes the working state without deleting any source code or removing table schemas.
- **Outputs**: All contents inside `outputs/` are deleted.
- **Knowledge Base**: `raw_sources/`, `processed_sources/`, `chroma_db/`, and `agent.db` are cleared.
- **Database**: All job entries and CV tracking rows in the `jobs` table are deleted via a `DELETE FROM` query. The schema is fully preserved.

## 4. Re-uploading Knowledge Base Files
After a reset, your RAG system is completely empty. To restore your knowledge:
1. Start the app: `python -m streamlit run app.py`
2. Navigate to the Knowledge Base or Upload area.
3. Upload your background documents (`.pdf`, `.docx`, `.txt`, `.md`).
4. These files will be processed, chunked, and stored in the vector database to guide the AI's CV generation.

## 5. Re-adding the Approved PDF CV Template
The PDF template uses exact coordinates to overlay your dynamic Profile and Skills.
1. Make sure your approved design is named `Mina TAhmasebi Cv Template (1).pdf` or similar.
2. Upload this file as your CV template in the UI.
3. The app will save it to the templates directory (e.g., `templates/cv/`) and register its path in the database or config.
4. The system will use the PDF renderer for this file. It will *not* convert it to DOCX.

## 6. Running the First Clean Test
1. Re-add a sample job link (via the Job Dashboard "Add Manual Entry" or through the job importer).
2. Click "Tailor CV".
3. Verify that the app generates a tailored CV matching the job description using your clean Knowledge Base.
4. Verify the preview PDF overlays the new text successfully onto Page 1 while leaving Page 2 untouched.
