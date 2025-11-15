@echo off
REM MLB Best Ball Analyzer - Web App Runner
REM Checks dependencies and launches the Flask web server

echo ========================================
echo MLB Best Ball Analyzer - Web Version
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
    echo ERROR: Database not found at data\mlb_stats.db
    echo.
    echo You need to either:
    echo   1. Run: python fetch_data.py
    echo   2. Or add your existing database to the data\ folder
    echo.
    pause
    exit /b 1
)

echo [OK] Database found
echo.

REM Check if required packages are installed
echo Checking dependencies...
python -c "import flask, numpy, pandas, sqlalchemy" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Installing main dependencies...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install main dependencies
        pause
        exit /b 1
    )

    echo Installing Flask...
    python -m pip install Flask flask-cors
    if errorlevel 1 (
        echo ERROR: Failed to install Flask
        pause
        exit /b 1
    )
)

echo [OK] All dependencies installed
echo.

REM Ask about pre-calculation
echo Have you pre-calculated the Best Ball metrics?
echo (This is required for the web app to work properly)
echo.
set /p precalc="Run pre-calculation now? (y/n, recommended if first time): "
if /i "%precalc%"=="y" (
    echo.
    echo Running pre-calculation... This may take 10-15 minutes.
    python web\precalculate_data.py
    if errorlevel 1 (
        echo.
        echo WARNING: Pre-calculation had errors
        set /p continue="Continue anyway? (y/n): "
        if /i not "%continue%"=="y" exit /b 0
    )
    echo.
    echo [OK] Pre-calculation complete
    echo.
)

REM Launch the web app
echo Starting Flask web server...
echo.
echo The app will be available at: http://localhost:5000
echo Press Ctrl+C to stop the server
echo.
echo ========================================
echo.

cd web
python app.py

if errorlevel 1 (
    echo.
    echo ERROR: Web server crashed or failed to start
    cd..
    pause
    exit /b 1
)

cd..
