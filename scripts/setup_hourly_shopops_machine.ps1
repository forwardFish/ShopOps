param(
    [switch]$InstallTools,
    [switch]$InstallPythonPackages,
    [string]$Browser = "chrome",
    [string]$ProfileRoot = "$env:LOCALAPPDATA\ShopOpsCdpProfiles"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

function Test-CommandAvailable {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Write-Check {
    param([string]$Name, [bool]$Ok, [string]$Hint = "")
    if ($Ok) {
        Write-Host "[OK] $Name"
    } else {
        Write-Warning "[MISS] $Name $Hint"
    }
}

Write-Host "ShopOps hourly machine setup check"
Write-Host "Repo: $RepoRoot"

$pythonOk = Test-CommandAvailable "python"
$chromeOk = Test-CommandAvailable "chrome"
$tesseractOk = Test-CommandAvailable "tesseract"
$wingetOk = Test-CommandAvailable "winget"
$chocoOk = Test-CommandAvailable "choco"

Write-Check "python" $pythonOk "Install Python 3.11+ and add it to PATH."
Write-Check "chrome command" $chromeOk "Chrome can still be found by the CDP launcher through Program Files."
Write-Check "tesseract OCR" $tesseractOk "Run this script with -InstallTools, or install Tesseract and add it to PATH."

if ($InstallTools -and -not $tesseractOk) {
    if ($wingetOk) {
        Write-Host "Installing Tesseract OCR through winget..."
        winget install --id UB-Mannheim.TesseractOCR --source winget --accept-source-agreements --accept-package-agreements
    } elseif ($chocoOk) {
        Write-Host "Installing Tesseract OCR through Chocolatey..."
        choco install tesseract -y
    } else {
        throw "Neither winget nor choco is available. Install Tesseract OCR manually."
    }
}

if ($InstallPythonPackages) {
    Write-Host "Installing Python requirements..."
    python -m pip install -r requirements.txt
    python -m playwright install chromium
}

if (-not (Test-Path ".env")) {
    Write-Warning ".env is missing. Copy .env.example to .env and fill Feishu/Jushuitan values before live import."
}

New-Item -ItemType Directory -Force -Path $ProfileRoot | Out-Null
Write-Host "Profile root ready: $ProfileRoot"

Write-Host "Checking ShopOps live prerequisites without printing secrets..."
python -B -m data_robot.hourly_shopops_import --preflight-only --skip-ads --ocr-command "tesseract {image} stdout -l chi_sim"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Environment preflight found missing order/import settings. See the JSON output above."
}

Write-Host ""
Write-Host "Next commands:"
Write-Host ".\scripts\start_hourly_shopops_cdp_browsers.ps1 -Browser $Browser -ProfileRoot `"$ProfileRoot`""
Write-Host ".\scripts\save_shopops_login_secret.ps1 -Platform tmall"
Write-Host ".\scripts\save_shopops_login_secret.ps1 -Platform douyin"
Write-Host "python -m data_robot.check_cdp --platform douyin --platform tmall"
Write-Host "python -m data_robot.hourly_shopops_import --cycles 3 --direct-cdp --wait-login --auto-login"
