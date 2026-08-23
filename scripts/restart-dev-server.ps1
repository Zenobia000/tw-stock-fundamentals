<#
.SYNOPSIS
  Cleanly restart the local FastAPI dev server on a given port.

.DESCRIPTION
  `uvicorn --reload` on Windows spawns its actual worker via
  multiprocessing.spawn as a separate process. Killing only the
  reloader PID (Stop-Process, Ctrl+C mid-restart, closing the
  terminal) leaves that worker running as an orphan, still bound
  to the port. Do this enough times across sessions and several
  stale workers pile up on the same port; Windows then serves
  requests from whichever one happens to answer, so some routes
  work and others 404 depending on which stale build answered.

  This script always kills the FULL process tree (taskkill /T) of
  whatever currently owns the port, confirms the port is empty,
  then starts exactly one fresh instance and smoke-tests it.

.PARAMETER Port
  Port to bind. Defaults to 8000.

.EXAMPLE
  ./scripts/restart-dev-server.ps1
  ./scripts/restart-dev-server.ps1 -Port 8001
#>
param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Get-PortOwnerPids {
    param([int]$Port)
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
}

Write-Host "Checking port $Port ..."
$owners = Get-PortOwnerPids -Port $Port
if ($owners) {
    foreach ($ownerPid in $owners) {
        Write-Host "Killing process tree for PID $ownerPid (and its spawned workers)"
        # /T kills the whole process tree; plain Stop-Process only kills the
        # named PID and leaves multiprocessing-spawned children orphaned.
        taskkill /F /T /PID $ownerPid | Out-Null
    }
    Start-Sleep -Seconds 1
}

$stillThere = Get-PortOwnerPids -Port $Port
if ($stillThere) {
    throw "Port $Port still has a listener (PID $stillThere) after taskkill /T. Investigate manually before retrying."
}
Write-Host "Port $Port is clear."

Push-Location $repoRoot
try {
    Write-Host "Starting uv run uvicorn app.main:app --reload --port $Port ..."
    Start-Process -FilePath "uv" -ArgumentList "run", "uvicorn", "app.main:app", "--reload", "--port", $Port `
        -WorkingDirectory $repoRoot -WindowStyle Hidden `
        -RedirectStandardOutput "$repoRoot\.dev-server.log" -RedirectStandardError "$repoRoot\.dev-server.err.log"
} finally {
    Pop-Location
}

Write-Host "Waiting for startup..."
$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
}

if (-not $ok) {
    throw "Server did not come up on port $Port within 15s. Check .dev-server.err.log."
}

Write-Host "Smoke-testing a couple of routes..."
$overview = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/market/overview" -TimeoutSec 5
Write-Host "  /api/market/overview -> $($overview.StatusCode)"
if ($overview.StatusCode -ne 200) {
    throw "/api/market/overview returned $($overview.StatusCode) on a freshly restarted server -- that's a real code bug now, not a stale-process issue. Investigate app/api/routes.py."
}

Write-Host "Dev server is up and healthy on port $Port."
