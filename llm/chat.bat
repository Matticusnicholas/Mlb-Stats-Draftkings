@echo off
echo ============================================================
echo MLB Best Ball Assistant - Interactive Chat
echo ============================================================
echo.

REM Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found!
    echo Run setup_llm.bat first.
    pause
    exit /b 1
)

REM Run chat
python scripts\inference.py

pause
