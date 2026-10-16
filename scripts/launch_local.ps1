#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Launch WorkbenchIQ locally (backend + frontend).

.DESCRIPTION
    Starts the FastAPI backend on port 8000 and Next.js frontend on port 3000.
    Uses local file storage (JSON) and Azure OpenAI for AI features.

.PARAMETER BackendOnly
    Start only the backend (skip frontend).

.PARAMETER FrontendOnly
    Start only the frontend (skip backend).

.PARAMETER Port
    Backend port (default: 8000).

.EXAMPLE
    .\scripts\launch_local.ps1              # Both
    .\scripts\launch_local.ps1 -BackendOnly # Backend only
#>
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host " WorkbenchIQ — Local Development" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

# ── Environment ──
$env:STORAGE_BACKEND        = "local"
$env:DATABASE_BACKEND       = "json"
$env:UW_APP_STORAGE_ROOT    = "data"
$env:AZURE_OPENAI_ENDPOINT          = "https://ai-horiquiz-dev.cognitiveservices.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME   = "gpt-5.4-mini"
$env:AZURE_OPENAI_MODEL_NAME        = "gpt-5.4-mini"
$env:AZURE_OPENAI_NANO_DEPLOYMENT_NAME = "gpt-5.4-nano"
$env:AZURE_OPENAI_NANO_MODEL_NAME     = "gpt-5.4-nano"

# ── Backend ──
if (-not $FrontendOnly) {
    Write-Host ""
    Write-Host ">>> Starting backend on port $Port..." -ForegroundColor Cyan

    # Kill existing backend if running
    Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
        try { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "uvicorn.*api_server" } catch { $false }
    } | ForEach-Object {
        Write-Host "    Stopping existing backend (PID $($_.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force
    }

    $backendJob = Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
        -ArgumentList "-m", "uvicorn", "api_server:app", "--port", $Port, "--host", "0.0.0.0" `
        -WorkingDirectory $root `
        -PassThru -NoNewWindow

    # Wait for backend to start
    $retries = 0
    do {
        Start-Sleep -Milliseconds 500
        $retries++
        try {
            $null = Invoke-RestMethod -Uri "http://localhost:$Port/" -TimeoutSec 2 -ErrorAction Stop
            $backendOk = $true
        } catch {
            $backendOk = $false
        }
    } while (-not $backendOk -and $retries -lt 20)

    if ($backendOk) {
        Write-Host "    Backend ready: http://localhost:$Port" -ForegroundColor Green
    } else {
        Write-Host "    Backend may still be starting..." -ForegroundColor Yellow
    }
}

# ── Frontend ──
if (-not $BackendOnly) {
    Write-Host ""
    Write-Host ">>> Starting frontend..." -ForegroundColor Cyan

    # Kill existing frontend if running
    Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object {
        try { (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine -match "next" } catch { $false }
    } | ForEach-Object {
        Write-Host "    Stopping existing frontend (PID $($_.Id))..." -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force
    }

    $frontendJob = Start-Process -FilePath "npm" `
        -ArgumentList "run", "dev" `
        -WorkingDirectory "$root\frontend" `
        -PassThru -NoNewWindow

    # Wait for frontend
    $retries = 0
    do {
        Start-Sleep -Seconds 1
        $retries++
        try {
            $null = Invoke-WebRequest -Uri "http://localhost:3000" -Method HEAD -TimeoutSec 2 -ErrorAction Stop
            $frontendOk = $true
        } catch {
            $frontendOk = $false
        }
    } while (-not $frontendOk -and $retries -lt 30)

    if ($frontendOk) {
        Write-Host "    Frontend ready: http://localhost:3000" -ForegroundColor Green
    } else {
        Write-Host "    Frontend may still be starting (check port 3000/3001)..." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host " WorkbenchIQ running locally!" -ForegroundColor Green
if (-not $FrontendOnly) { Write-Host "   API      : http://localhost:$Port" -ForegroundColor White }
if (-not $BackendOnly)  { Write-Host "   Frontend : http://localhost:3000" -ForegroundColor White }
Write-Host "   Press Ctrl+C to stop" -ForegroundColor DarkGray
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""

# Keep script alive (Ctrl+C to exit)
try {
    while ($true) {
        Start-Sleep -Seconds 60
    }
} finally {
    Write-Host "`n>>> Shutting down..." -ForegroundColor Yellow
    if ($backendJob -and !$backendJob.HasExited) { Stop-Process -Id $backendJob.Id -Force -ErrorAction SilentlyContinue }
    if ($frontendJob -and !$frontendJob.HasExited) { Stop-Process -Id $frontendJob.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "    Done." -ForegroundColor Green
}
