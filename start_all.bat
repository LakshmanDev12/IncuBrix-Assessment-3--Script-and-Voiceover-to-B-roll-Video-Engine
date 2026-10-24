@echo off
echo ========================================================
echo   Starting IncuBrix AI Video Studio Servers
echo ========================================================
echo.
echo Launching Backend API on port 8002...
start "IncuBrix Backend (FastAPI :8002)" cmd /k "cd /d e:\Incubrix\video-broll-engine && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"

echo Launching Frontend UI on port 8000...
start "IncuBrix Frontend (Vite :8000)" cmd /k "cd /d e:\Incubrix\video-broll-engine\frontend && npm run dev"

echo.
echo Both servers launched in separate windows!
echo - Web UI:       http://localhost:8000
echo - API Backend:  http://localhost:8002
echo - API Docs:     http://localhost:8002/docs
echo ========================================================
pause
