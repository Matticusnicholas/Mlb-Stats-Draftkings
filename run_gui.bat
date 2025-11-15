@echo off
REM MLB Best Ball Analyzer - Desktop GUI Runner
REM Checks dependencies and launches the GUI

echo ========================================
echo MLB Best Ball Analyzer - Desktop GUI
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH!
    echo Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

echo [OK] Python found
echo.

REM Check if database exists
if not exist "data\mlb_stats.db" (
    echo WARNING: Database not found at data\mlb_stats.db
    echo.
    echo You need to either:
    echo   1. Run: python fetch_data.py
    echo   2. Or add your existing database to the data\ folder
    echo.
    set /p continue="Continue anyway? (y/n): "
    if /i not "%continue%"=="y" exit /b 0
)

echo [OK] Database check passed
echo.

REM Check if required packages are installed
echo Checking dependencies...
python -c "import tkinter, numpy, pandas, sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Some dependencies are missing. Installing...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

echo [OK] All dependencies installed
echo.

REM Launch the GUI
echo Starting GUI...
echo.
python run_gui.py

if errorlevel 1 (
    echo.
    echo ERROR: GUI crashed or failed to start
    pause
    exit /b 1
)
