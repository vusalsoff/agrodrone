<#
.SYNOPSIS
    AgroDrone Windows PowerShell development helper.
.DESCRIPTION
    Provides convenient commands for migrating, testing, linting, and running the
    FastAPI backend and Next.js frontend locally without requiring Make or Docker.
.EXAMPLE
    .\scripts\dev.ps1 -Action validate
    .\scripts\dev.ps1 -Action api
    .\scripts\dev.ps1 -Action web
    .\scripts\dev.ps1 -Action arduino
#>
param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("api", "web", "arduino", "migrate", "test", "validate", "contracts")]
    [string]$Action = "validate"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ApiDir = Join-Path $RepoRoot "apps\api"
$WebDir = Join-Path $RepoRoot "apps\web"

function Invoke-ApiMigrate {
    Write-Host "==> Running Alembic migrations..." -ForegroundColor Green
    Push-Location $ApiDir
    try {
        & uv run alembic upgrade head
    } finally {
        Pop-Location
    }
}

switch ($Action) {
    "migrate" {
        Invoke-ApiMigrate
    }
    "api" {
        Invoke-ApiMigrate
        Write-Host "==> Starting FastAPI API on http://127.0.0.1:8000 ..." -ForegroundColor Green
        Push-Location $ApiDir
        try {
            & uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
        } finally {
            Pop-Location
        }
    }
    "web" {
        Write-Host "==> Starting Next.js Web on http://127.0.0.1:3000 ..." -ForegroundColor Green
        Push-Location $WebDir
        try {
            & npm run dev
        } finally {
            Pop-Location
        }
    }
    "arduino" {
        Write-Host "==> Starting AgroDrone ESP32-CAM -> AI -> Arduino UNO Serial Bridge (COM15, 9600 baud)..." -ForegroundColor Green
        $TokenFile = Join-Path $ApiDir "data\arduino_gateway.token"
        if (-not $env:AGRODRONE_GATEWAY_TOKEN -and (Test-Path $TokenFile)) {
            $env:AGRODRONE_GATEWAY_TOKEN = (Get-Content $TokenFile -Raw).Trim()
        }
        Push-Location $ApiDir
        try {
            & .\.venv\Scripts\python.exe -m agrodrone_gateway.arduino_cli
        } finally {
            Pop-Location
        }
    }
    "contracts" {
        Write-Host "==> Exporting OpenAPI schema to packages/contracts/openapi.json ..." -ForegroundColor Green
        Push-Location $ApiDir
        try {
            & uv run python scripts/export_openapi.py
        } finally {
            Pop-Location
        }
    }
    "test" {
        Write-Host "==> Running backend tests..." -ForegroundColor Green
        Push-Location $ApiDir
        try {
            & uv run pytest -v
        } finally {
            Pop-Location
        }
        Write-Host "==> Running frontend tests..." -ForegroundColor Green
        Push-Location $WebDir
        try {
            & npm test
        } finally {
            Pop-Location
        }
    }
    "validate" {
        Write-Host "==> Validating backend (ruff + alembic + pytest)..." -ForegroundColor Green
        Push-Location $ApiDir
        try {
            & uv run ruff check app tests alembic scripts
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & uv run alembic upgrade head
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & uv run pytest -v
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & uv run python scripts/export_openapi.py
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally {
            Pop-Location
        }
        Write-Host "==> Validating frontend (typecheck + lint + test + build)..." -ForegroundColor Green
        Push-Location $WebDir
        try {
            & npm run typecheck
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & npm run lint
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & npm test
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & npm run build
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        } finally {
            Pop-Location
        }
        Write-Host "==> All validation checks passed." -ForegroundColor Green
    }
}
