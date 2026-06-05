@echo off
cd /d "%~dp0"

IF NOT EXIST ".venv" (
    echo [ERROR] Virtual environment (.venv) not found!
    echo Please run setup_project.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
echo Starting Streamlit app...
python -m streamlit run app.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Application crashed or failed to start.
    pause
)
