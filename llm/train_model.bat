@echo off
echo ============================================================
echo MLB Best Ball LLM Fine-tuning
echo QLoRA Training on Mistral-7B
echo Optimized for 4070 Ti Super 16GB
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

REM Check if training data exists
if not exist "training_data\training_data.json" (
    echo ERROR: Training data not found!
    echo Run prepare_data.bat first.
    pause
    exit /b 1
)

REM Check GPU
echo Checking GPU...
python -c "import torch; print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
echo.

REM Confirm
echo WARNING: Training will take 1-3 hours depending on dataset size.
echo Make sure your GPU is not being used by other applications.
echo.
set /p confirm="Continue with training? (y/n): "
if /i not "%confirm%"=="y" (
    echo Training cancelled.
    pause
    exit /b 0
)

REM Run training
echo.
echo Starting fine-tuning...
echo ============================================================
python scripts\finetune.py

echo.
echo ============================================================
echo Training complete!
echo Model saved to: output\final_model
echo.
echo To merge LoRA weights for faster inference:
echo   python scripts\finetune.py --merge
echo.
echo To chat with your model:
echo   Run chat.bat
echo ============================================================
pause
