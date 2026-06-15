param(
    [string]$DateToken = (Get-Date -Format "MMdd"),
    [string]$BatchHour = (Get-Date -Format "HH"),
    [string]$BrowserProfileSuffix = "cdp",
    [string]$BrowserProfileRoot = "D:\tmp\ShopOps\data_robot\profiles",
    [switch]$DirectCdp,
    [switch]$SkipDoctorCheck,
    [switch]$DryRunImport
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

$python = "python"
$downloadLabel = ([string][char]0x70B9) + ([string][char]0x4E0B) + ([string][char]0x8F7D)
$batchLabel = "$DateToken\$BatchHour$downloadLabel"
Write-Host "ShopOps data robot batch: $batchLabel"

if (-not $SkipDoctorCheck) {
    Write-Host "Running runtime doctor..."
    & $python -B -m data_robot.doctor --date-token $DateToken --batch-hour $BatchHour --browser-profile-suffix "doctor" --browser-profile-root $BrowserProfileRoot
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Runtime doctor failed. Check docs\live-evidence\data-robot\doctor-*.json before downloading."
        exit $LASTEXITCODE
    }
}

$argsList = @(
    "-B", "-m", "data_robot.full_flow",
    "--date-token", $DateToken,
    "--batch-hour", $BatchHour,
    "--browser-profile-suffix", $BrowserProfileSuffix,
    "--browser-profile-root", $BrowserProfileRoot,
    "--auto-actions",
    "--skip-doctor-check"
)

if ($DirectCdp) {
    $argsList += "--direct-cdp"
}
if ($DryRunImport) {
    $argsList += "--dry-run-import"
}

Write-Host "Running full download/import flow..."
& $python @argsList
exit $LASTEXITCODE
