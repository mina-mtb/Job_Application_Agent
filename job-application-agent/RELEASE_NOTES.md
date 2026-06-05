# Release Notes

**Version**: v0.1.0-local-mvp
**Date**: 2026-06-05

## What is included
- Local Streamlit dashboard for a complete human-in-the-loop experience.
- SQLite job database ensuring safe storage of state and logic transitions.
- ChromaDB Knowledge Base enabling completely grounded text generation.
- Manual job entry via the web interface.
- Rule-based + mock AI scoring using a highly resilient two-stage filtering pipeline.
- Grounded CV tailoring that statically preserves Experience/Education while targeting Profile/Skills.
- Markdown/HTML/PDF export generation.
- Windows launcher scripts (`setup_project.bat`, `start_app.bat`) for easy installation.
- Local tests (44 passing pytest modules ensuring integrity).

## What is not included yet
- Real Claude production mode validation.
- Real Apify LinkedIn scraping validation.
- PyInstaller `.exe` standalone installer.
- Email/Outlook automation.
- Canva API or headless automation.
