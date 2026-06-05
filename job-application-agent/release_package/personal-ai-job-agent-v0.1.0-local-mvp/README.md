# Personal AI Job Application Agent

This repository contains a local MVP for an autonomous Personal AI Job Application Agent.

## What the app does
The agent collects job descriptions, evaluates them against your personalized CV and skills profile, and generates heavily grounded, tailored CVs. The human-in-the-loop dashboard allows you to review its decisions, preview the tailored CVs, and ultimately mark jobs as approved or applied. 

## Current MVP features
- **Local Streamlit dashboard**: Human-in-the-loop UI to review matches and manage the pipeline.
- **SQLite job database**: Reliable local storage for all jobs and their states.
- **ChromaDB Knowledge Base**: Vector database for grounding your CV and ensuring factual generation.
- **Manual job entry**: Paste in a job description and link to immediately score and evaluate it.
- **Rule-based + mock AI scoring**: Two-stage pipeline (Rule-based filtering, followed by LLM-based scoring).
- **Grounded CV tailoring**: LLMs rewrite only your Profile and Skills sections based heavily on your verified Knowledge Base.
- **Markdown/HTML/PDF export**: Ready-to-send CV formats.

## Safety design
This agent is built with strict anti-hallucination guardrails:
- **Important rule: only Profile and Skills are tailored.** The AI is forbidden from fabricating facts.
- **Important rule: Experience and Education are copied verbatim.** Your work history and educational timeline are structurally locked and perfectly preserved from your source CV.

## Project structure
```
job-application-agent/
│
├── app.py                     # Streamlit UI dashboard
├── core/                      # Pipeline, Knowledge Base, Job Matcher, and CV Tailor logic
├── database/                  # SQLite DB manager
├── integrations/              # External API clients (e.g., Apify)
├── knowledge_base/            # ChromaDB cache and raw uploaded source files
├── llm/                       # Provider Factory (MockProvider / ClaudeProvider)
├── profile/                   # Your baseline CV files and profile definitions
├── tests/                     # 44 passing pytest modules ensuring total safety
├── utils/                     # Document conversion (Markdown to HTML/PDF)
├── config/                    # Configuration settings
└── setup_project.bat / start_app.bat  # Windows launcher scripts
```

## Requirements
- Python 3.10+
- Windows OS (for the .bat launchers)
- See `requirements.txt` for Python dependencies.

## Windows setup instructions
1. Download the release or clone the repository.
2. Run `setup_project.bat` to automatically build your virtual environment and install all dependencies.
3. Once the setup script succeeds, run `start_app.bat` to launch the dashboard.

## How to run setup_project.bat
Open a command prompt or double-click `setup_project.bat` from your file explorer. It will install packages and run the local test suite to guarantee everything works.

## How to run start_app.bat
Double-click `start_app.bat`. It will boot the Streamlit server and automatically keep the console open if errors occur.

## How to open the app at http://localhost:8501
Once `start_app.bat` runs, your default browser should automatically open `http://localhost:8501`. If it doesn't, manually type the address into your browser.

## How to upload Knowledge Base files
Navigate to the **Knowledge Base** tab in the Streamlit UI. Here, you can upload Markdown or text files describing your skills, projects, and work history. The agent uses this strictly to ground its writing.

## How to prepare profile/mina_base_cv.md
For testing or manual execution:
1. Copy `profile/mina_base_cv_template.md` to `profile/mina_base_cv.md`.
2. Fill it honestly with your real skills and experience. Do not inflate titles.
3. The system will ingest this and use it as your immutable source of truth.

## How to add a manual job
Go to the **Manual Entry** tab. Paste the Job Title, Company, Location, URL, and full text description. The pipeline will immediately process and evaluate it.

## How to score new jobs
From the **Dashboard** tab, you can click "Run Daily Job Matching" or "Score New Jobs" to process anything sitting in the `new` status through Stage 1 and Stage 2 matching.

## How to generate a tailored CV
For any job sitting in `needs_review` or `approved` status, click **Generate CV** from the Dashboard. The AI will output a targeted Markdown, HTML, and PDF file.

## How to preview and approve a CV
Click **Preview CV** on the Dashboard for any generated job to read the tailored outputs. You can click **Approve** to bump its status to `approved`.

## How to mark jobs as applied/rejected/not suitable
Use the corresponding action buttons next to each job on the Dashboard. Marking a job as `rejected` or `not_suitable` ensures the pipeline never re-evaluates it. Marking it as `applied` completes the workflow for that job.

## Explanation of job statuses
- `new`: Job collected, pending evaluation.
- `needs_review`: Passed AI scoring, ready for human evaluation or CV generation.
- `cv_generated`: Tailored CV was created.
- `approved`: Human verified the CV and job.
- `applied`: Application officially submitted.
- `rejected`: Did not pass Rule-based/Stage 1 filtering.
- `not_suitable`: Human explicitly marked it as a bad fit.
- `duplicate`: Already exists in the database.
- `failed`: An error occurred during matching or generation.

## How to run tests manually
Activate your `.venv` and run:
`python -m pytest tests/ -v`

## How to switch from MockProvider to Claude later
Currently, the pipeline uses `MockProvider` to avoid spending API tokens. To switch, set `ANTHROPIC_API_KEY` in your `.env` file, and update `config/config.yaml` to point the `llm_provider` parameter to `claude`.

## How to add Apify later
Fill your `APIFY_TOKEN` inside the `.env` file and use `JobCollector` in production mode to scrape LinkedIn/Indeed listings automatically.

## Known limitations
- PDF export gracefully skips if `pdfkit`/`wkhtmltopdf` are missing on the host OS.
- Only manual job entry is completely verified in this release.

## Troubleshooting
- If the Streamlit UI crashes, verify that `setup_project.bat` created the `.venv` correctly and that `jobs.db` isn't locked.
- If CVs fail to generate, ensure your Knowledge Base contains the `mina_base_cv.md` file.

## Privacy and local-first note
All matching logic, vector databases, and job history are contained strictly inside your local machine. No data is sent to external APIs when running with `MockProvider`.
