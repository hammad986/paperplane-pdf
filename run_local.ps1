# ======================================================================
# Paperplane PDF — Local Launch Script (Windows)
# ======================================================================
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   Starting Paperplane PDF Platform (Local Windows Mode)  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Set LibreOffice path if available in Downloads\pdf
$loExe = "C:\Users\mdham\Downloads\pdf\LibreOffice\program\soffice.exe"
if (Test-Path $loExe) {
    $env:LIBREOFFICE_EXECUTABLE = $loExe
    Write-Host "[OK] LibreOffice detected: $loExe" -ForegroundColor Green
} else {
    Write-Host "[WARN] Local LibreOffice not found at $loExe (Using pure Python fallback)" -ForegroundColor Yellow
}

# Run live application
Write-Host "[INFO] Starting server on http://127.0.0.1:8501..." -ForegroundColor White
python app.py
