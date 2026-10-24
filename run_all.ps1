# --------------------------------------------------------------
# run_all.ps1 – start FastAPI (8002) and Vite UI (8000) together
# --------------------------------------------------------------

Set-Location "e:\Incubrix\video-broll-engine"

# Activate the Python venv if it exists
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

# --- 1. FastAPI on port 8002 ------------------------------------
$PYTHON_BIN = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PYTHON_BIN)) {
    $PYTHON_BIN = "python"
}

Start-Process -FilePath $PYTHON_BIN `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload" `
    -NoNewWindow

# --- 2. Vite UI on port 8000 ------------------------------------
Push-Location "frontend"

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing node dependencies..." -ForegroundColor Yellow
    & npm.cmd ci
}

# Use npm.cmd (not npm) so Start-Process finds a real executable
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -NoNewWindow

Pop-Location

# -----------------------------------------------------------------
Write-Host ""
Write-Host "UI (Vite)   -> http://localhost:8000"   -ForegroundColor Cyan
Write-Host "FastAPI     -> http://localhost:8002"   -ForegroundColor Cyan
Write-Host "API docs    -> http://localhost:8002/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C in this window to stop both services." -ForegroundColor DarkGray
