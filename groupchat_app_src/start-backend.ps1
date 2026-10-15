$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot 'backend')
try {
    & .\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
