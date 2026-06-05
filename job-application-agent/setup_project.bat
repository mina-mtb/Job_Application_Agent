@echo off
cd /d "%~dp0"

echo [1/4] Checking/Creating virtual environment (.venv)...
IF NOT EXIST ".venv" (
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [2/4] Upgrading pip...
python -m pip install --upgrade pip

echo [3/4] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt

echo [4/4] Running tests to verify setup...
python -m pytest tests/ -v

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================================
    echo [SUCCESS] Setup complete and all tests passed!
    echo You can now launch the app using start_app.bat.
    echo ====================================================
) else (
    echo.
    echo ====================================================
    echo [ERROR] Tests failed during setup. Please check the logs above.
    echo ====================================================
)
pause
