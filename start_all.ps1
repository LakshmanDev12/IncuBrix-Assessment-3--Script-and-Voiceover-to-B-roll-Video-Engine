# Start both servers in separate, persistent PowerShell windows
Set-Location "e:\Incubrix\video-broll-engine"

Write-Host "Starting IncuBrix AI Video Studio..." -ForegroundColor Cyan

# 1. Start FastAPI in its own window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'e:\Incubrix\video-broll-engine'; .\.venv\Scripts\Activate.ps1; python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"

# 2. Start Vite UI in its own window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'e:\Incubrix\video-broll-engine\frontend'; npm run dev"

Write-Host ""
Write-Host "Servers launched in independent terminal windows:" -ForegroundColor Green
Write-Host "  -> Web UI:       http://localhost:8000" -ForegroundColor Cyan
Write-Host "  -> API Backend:  http://localhost:8002" -ForegroundColor Cyan
Write-Host "  -> API Docs:     http://localhost:8002/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "These windows will remain running permanently until you close them." -ForegroundColor Yellow
