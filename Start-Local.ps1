$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendDirectory = Join-Path $projectRoot 'backend'
$frontendDirectory = Join-Path $projectRoot 'frontend'
$pythonExecutable = Join-Path $backendDirectory '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    throw 'Backend environment is missing. Follow the installation commands in README.md.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory 'node_modules'))) {
    throw 'Frontend packages are missing. Run npm ci in the frontend directory.'
}

function Test-LocalUrl([string]$Address) {
    try {
        $response = Invoke-WebRequest -Uri $Address -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-LocalUrl 'http://localhost:8000/api/health')) {
    if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8000 is already occupied by another service.'
    }
    Start-Process -FilePath $pythonExecutable -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $backendDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $backendDirectory 'runtime.log') -RedirectStandardError (Join-Path $backendDirectory 'runtime-error.log')
}
if (-not (Test-LocalUrl 'http://localhost:5173')) {
    if (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 5173 is already occupied by another service.'
    }
    $npmExecutable = (Get-Command npm.cmd -ErrorAction Stop).Source
    Start-Process -FilePath $npmExecutable -ArgumentList 'run','dev','--','--host','127.0.0.1','--port','5173','--strictPort' -WorkingDirectory $frontendDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $frontendDirectory 'runtime.log') -RedirectStandardError (Join-Path $frontendDirectory 'runtime-error.log')
}

$backendReady = $false
$frontendReady = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $backendReady = Test-LocalUrl 'http://localhost:8000/api/ready'
    $frontendReady = Test-LocalUrl 'http://localhost:5173'
    if ($backendReady -and $frontendReady) { break }
    Start-Sleep -Milliseconds 500
}
if (-not ($backendReady -and $frontendReady)) {
    throw 'A service did not become ready. Check backend/runtime-error.log or frontend/runtime-error.log.'
}
Write-Host 'ADEM LMS: http://localhost:5173'
Write-Host 'API documentation: http://localhost:8000/docs'
