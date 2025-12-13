@echo off
echo ============================================================
echo MLB Best Ball LLM Setup
echo Optimized for 4070 Ti Super 16GB
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Please install Python 3.10+
    pause
    exit /b 1
)

REM Create virtual environment
echo Creating virtual environment...
if not exist "venv" (
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install PyTorch with CUDA
echo.
echo Installing PyTorch with CUDA support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

REM Install requirements
echo.
echo Installing LLM requirements...
pip install -r requirements.txt

REM Create directories
echo.
echo Creating directories...
if not exist "models" mkdir models
if not exist "training_data" mkdir training_data
if not exist "output" mkdir output

echo.
echo ============================================================
echo Setup complete!
echo.
echo Next steps:
echo 1. Run: prepare_data.bat  (generate training data)
echo 2. Run: train_model.bat   (fine-tune the model)
echo 3. Run: chat.bat          (chat with your model)
echo ============================================================
pause
