@echo off
echo Starting ANPR Command Center (GPU Mode)
echo =======================================

IF NOT EXIST ".venv\Scripts\python.exe" (
    echo Error: .venv not found. Please create the virtual environment first.
    pause
    exit /b 1
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Starting server...
python run_server.py

pause
