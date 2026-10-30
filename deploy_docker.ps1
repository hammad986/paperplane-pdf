# ======================================================================
# Paperplane PDF — Production Docker Deployment Script
# ======================================================================
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Deploying Paperplane PDF Platform (Docker Container)   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Docker Daemon
try {
    docker info | Out-Null
    Write-Host "[OK] Docker daemon is running." -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker Desktop is not running! Please start Docker Desktop and run this script again." -ForegroundColor Red
    exit 1
}

# 2. Build Container Image
Write-Host "[INFO] Building Docker container image..." -ForegroundColor White
docker compose build

# 3. Start Containers
Write-Host "[INFO] Launching Paperplane PDF & Nginx services..." -ForegroundColor White
docker compose up -d

# 4. Verify Health
Write-Host "[INFO] Checking container status..." -ForegroundColor White
Start-Sleep -Seconds 3
docker compose ps

Write-Host ""
Write-Host "Paperplane PDF is deployed and running on http://localhost:8501 (or via reverse proxy on port 80/443)" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
