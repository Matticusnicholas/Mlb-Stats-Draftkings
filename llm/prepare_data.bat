@echo off
echo ============================================================
echo Preparing Training Data for MLB Best Ball LLM
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

REM Run data preparation
echo Running training data preparation...
python scripts\prepare_training_data.py

echo.
echo ============================================================
echo Training data prepared!
echo Check training_data\ folder for output files.
echo.
echo Next: Run train_model.bat to fine-tune the model.
echo ============================================================
pause
