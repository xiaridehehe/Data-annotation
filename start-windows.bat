@echo off
cd /d "%~dp0"
.venv\Scripts\python -m pip install -r backend\requirements.txt
start "Knee API" /min cmd /c ".venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"
call npm --prefix frontend install
start "Knee UI" /min cmd /c "npm --prefix frontend run dev"
echo Open http://127.0.0.1:5173
pause
