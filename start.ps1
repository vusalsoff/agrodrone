<#
.SYNOPSIS
    1-Click AgroDrone Launcher (Backend + Frontend + Arduino COM15 Bridge).
#>
$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  AgroDrone 1-Click Launcher (API + Web + COM15)  " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot\apps\api'; .\.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot\apps\web'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot'; .\scripts\dev.ps1 -Action arduino"

Write-Host "Launched 3 windows: API (8000), Web (3000), Arduino Bridge (COM15)." -ForegroundColor Green
