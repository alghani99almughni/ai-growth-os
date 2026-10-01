@echo off
echo Starting AI Growth OS development environment...

start "AI Growth OS - API" cmd /k "cd /d %~dp0apps\api && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 2 >nul
start "AI Growth OS - Web" cmd /k "cd /d %~dp0apps\web && npm run dev"

echo Both servers are starting in separate windows.
echo   API:  http://localhost:8000
echo   Web:  http://localhost:3000
echo Close the two spawned windows when you're done for the day.