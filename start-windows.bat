@echo off
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
call npm --prefix frontend install
start "Knee API" /min cmd /c ".venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
start "Knee UI" /min cmd /c "npm --prefix frontend run dev"
echo Open http://127.0.0.1:5173
pause
