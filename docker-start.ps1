# DukaanAI 1-Click Container Launcher (Windows PowerShell)
$ErrorActionPreference = "Continue"

Write-Host "=================================================" -ForegroundColor Green
Write-Host " 🏪 DukaanAI - Docker Deployment & Phone Access " -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green

Set-Location -Path $PSScriptRoot

$composeCmd = "docker-compose"
if (Get-Command "docker" -ErrorAction SilentlyContinue) {
    $composeCmd = "docker compose"
}
if (Test-Path "C:\Users\$env:USERNAME\.docker\cli-plugins\docker-compose.exe") {
    $composeCmd = "& 'C:\Users\$env:USERNAME\.docker\cli-plugins\docker-compose.exe'"
}

Write-Host "1. Building and launching DukaanAI containers..." -ForegroundColor Cyan
Invoke-Expression "$composeCmd up --build -d"

Write-Host ""
Write-Host "2. Checking running containers..." -ForegroundColor Cyan
Invoke-Expression "$composeCmd ps"

# Detect host LAN IP address for phone connection
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.InterfaceAlias -notlike "*vEthernet*" -and $_.IPAddress -notlike "169.254*" } | Select-Object -ExpandProperty IPAddress -First 1)

Write-Host ""
Write-Host "=================================================" -ForegroundColor Green
Write-Host " 🎉 DukaanAI is Running in Docker!" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green
Write-Host "💻 Local Browser:     http://localhost (or http://localhost:4000)"
Write-Host "📱 Phone Browser/PWA: http://$($lanIp) (on same Wi-Fi)"
Write-Host "⚙️ Backend API:       http://$($lanIp):8000"
Write-Host "🐘 PostgreSQL DB:     localhost:5432"
Write-Host ""
Write-Host "To view real-time logs: $composeCmd logs -f" -ForegroundColor Yellow
Write-Host "To stop containers:    $composeCmd down" -ForegroundColor Yellow
Write-Host "=================================================" -ForegroundColor Green
