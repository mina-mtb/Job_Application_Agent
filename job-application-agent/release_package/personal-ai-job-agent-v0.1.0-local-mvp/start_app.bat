@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" goto ErrorVenv

call .venv\Scripts\activate.bat
echo Starting Streamlit app...
python -m streamlit run app.py

goto :EOF

:ErrorVenv
echo [ERROR] Virtual environment (.venv) not found!
echo Please run setup_project.bat first.
pause
exit /b 1
