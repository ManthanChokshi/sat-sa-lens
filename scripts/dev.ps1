# Start the backend and the frontend together for local development (Windows).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BackendPort = if ($env:SATSA_BACKEND_PORT) { $env:SATSA_BACKEND_PORT } else { "8000" }
$FrontendPort = if ($env:SATSA_FRONTEND_PORT) { $env:SATSA_FRONTEND_PORT } else { "5173" }

if (-not (Test-Path "backend\.venv")) {
    Write-Host "Creating the Python virtual environment..."
    python -m venv backend\.venv
    & backend\.venv\Scripts\python.exe -m pip install --upgrade pip
    & backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
}

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    Push-Location frontend; npm install; Pop-Location
}

if (-not (Test-Path "data\raw\alerts.csv")) {
    Write-Host "Generating the sample corpus (seed 42)..."
    & backend\.venv\Scripts\python.exe -m generator.generate --seed 42 --entities 12 --days 90
}

if (-not (Test-Path "data\satsa.duckdb")) {
    Write-Host "Loading the sample corpus and running the first analysis..."
    Push-Location backend
    & .venv\Scripts\python.exe -m app.ingest.load_sample
    & .venv\Scripts\python.exe -m app.runner
    Pop-Location
}

Write-Host "Backend  -> http://127.0.0.1:$BackendPort  (docs at /docs)"
Write-Host "Frontend -> http://localhost:$FrontendPort"

Start-Process -FilePath "backend\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--reload","--port",$BackendPort `
    -WorkingDirectory "$Root\backend"

$env:SATSA_API = "http://127.0.0.1:$BackendPort"
Push-Location frontend
npm run dev -- --port $FrontendPort
Pop-Location
