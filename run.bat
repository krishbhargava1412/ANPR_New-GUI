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

echo Ensure PostgreSQL is running on localhost:5432
echo If you use Docker for DB only, run: docker compose up -d postgres

echo Starting server...
python run_server.py

pause
