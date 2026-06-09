# Personal AI Job Application Agent

## What this app does
The Personal AI Job Application Agent helps you locally collect jobs, evaluate them against your real personalized CV and skills profile, and generate highly tailored CVs for the ones you approve. The human-in-the-loop dashboard ensures you maintain total control over your applications.

## Current MVP features
- Streamlit dashboard for managing jobs visually
- Manual job entry with instant AI scoring
- SQLite job database for safe, resilient state storage
- ChromaDB knowledge base to securely hold your CV facts
- Local MockProvider for token-free offline testing
- Rule-based filtering to instantly discard unsuitable roles
- RAG-based scoring and reasoning tailored to your profile
- Grounded CV generation that preserves your baseline truth
- Markdown/HTML/PDF CV export capabilities
- Windows setup and launcher scripts (`setup_project.bat`, `start_app.bat`)

## Important safety rules
- **The app only tailors Profile and Skills.**
- **Experience and Education are copied verbatim.**
- The app must not invent work history, education, dates, employers, or skills.
- The real personal CV file `profile/mina_base_cv.md` is intentionally not committed to GitHub.

## First-time setup on Windows
1. Download the ZIP from GitHub Release.
2. Extract the ZIP.
3. Open the extracted folder.
4. Double-click `setup_project.bat`.
5. Wait until dependencies install and tests finish.
6. Double-click `start_app.bat`.
7. Open `http://localhost:8501` in the browser if it does not open automatically.

## How to prepare your real profile file
1. Go to the `profile` folder.
2. Copy `mina_base_cv_template.md`.
3. Rename the copy to `mina_base_cv.md`.
4. Fill it with real professional data.
5. Do not upload private medical/family/sensitive data.
6. Keep Experience and Education accurate because they are copied verbatim.
7. Upload the file in the Knowledge Base tab or place it locally.

## How to use the Dashboard
- **View jobs**: See all imported jobs sorted in a card/table view.
- **Filter**: Filter by status, score, location, or keyword.
- **Score New Jobs**: Click the "Run Daily Job Matching" or "Score New Jobs" button to run the pipeline on `new` jobs.
- **Review**: Review the calculated score, reasons for match, and weaknesses/risks.
- **Generate CV**: Generate your tailored CV files for `needs_review` jobs.
- **Preview CV**: Read the generated CV directly in the app.
- **Approve**: Mark the tailored CV as verified.
- **Mark Applied**: Log the application as complete.
- **Reject / Not Suitable**: Discard jobs you do not want to pursue.
- **Add Notes**: Attach personal notes to any job.

## How to add a manual job
1. Open the **Manual Entry** tab.
2. Fill the title, company, location, and URL if available.
3. Paste the full job description.
4. URL alone is not enough unless scraping is enabled.
5. Click **Process Manual Job**.
6. Generate a CV if the job passes the filters and becomes `needs_review`.

## How to upload Knowledge Base files
- Use `.md` or `.txt` files first.
- Upload your CV/profile source files here to ground the AI.
- Template files should not be used as evidence.
- Do not upload private sensitive data unless it is absolutely necessary and safe for your CV generation.

## Job status meanings
- `new`: Recently imported, pending matching score.
- `needs_review`: Passed matching, ready for CV generation or review.
- `cv_generated`: Tailored CV was created.
- `approved`: You approved the CV visually.
- `applied`: You submitted the application.
- `rejected`: The AI discarded the job during matching.
- `not_suitable`: You manually marked it as a bad fit.
- `duplicate`: Ignored because it already existed.
- `failed`: An error occurred during matching or generation.

## How to run tests
Open a terminal in the project folder and run:
`.\.venv\Scripts\python.exe -m pytest tests/ -v`

## How to switch to Claude later
- Create `.env` from `.env.example`.
- Add `ANTHROPIC_API_KEY` locally only.
- Change `active_provider` (or `llm_provider`) from `mock` to `claude` in `config/config.yaml`.
- Never commit the `.env` file.

## How to add Apify later
- Add `APIFY_TOKEN` to `.env` locally.
- Keep the token out of GitHub.
- Real Apify scraping is not fully validated in this MVP release yet.

## Known limitations
- Not a one-click EXE installer yet.
- Claude production mode not fully validated yet.
- Apify LinkedIn scraping not fully validated yet.
- Canva automation not included yet.
- Outlook/email automation not included yet.
- Human review is still required before applying.

## Troubleshooting
- If `setup_project.bat` fails, check your Python installation.
- If `start_app.bat` says `.venv` is missing, run `setup_project.bat` first.
- If the browser does not open, manually go to `http://localhost:8501`.
- If the CV does not generate, check that `profile/mina_base_cv.md` exists and the Knowledge Base has been uploaded.
- If no jobs have scores, click **Score New Jobs**.
