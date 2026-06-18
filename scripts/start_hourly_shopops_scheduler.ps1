param(
    [switch]$RestartExisting,
    [string]$Python = "python",
    [string]$ProfileRoot = "$env:LOCALAPPDATA\ShopOpsCdpProfiles",
    [string]$HourlyIntervalTableId = "tblb7aBTN2dZ9ZSF",
    [int]$StartHour = 9,
    [int]$EndHour = 24,
    [int]$IntervalMinutes = 30,
    [int]$JitterMinutes = 6
)

$ErrorActionPreference = "Stop"

$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
$logDir = Join-Path $repo "docs\live-evidence\data-robot\scheduler"
$pidFile = Join-Path $logDir "hourly-shopops-scheduler.pid"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -Raw).Trim()
    if ($existingPid) {
        $existing = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
        if ($existing) {
            if (-not $RestartExisting) {
                [pscustomobject]@{
                    status = "already_running"
                    pid = $existing.Id
                    pid_file = $pidFile
                } | ConvertTo-Json -Depth 3
                exit 0
            }
            Stop-Process -Id $existing.Id -Force
        }
    }
}

& (Join-Path $PSScriptRoot "start_hourly_shopops_cdp_browsers.ps1") -ProfileRoot $ProfileRoot

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stdout = Join-Path $logDir "hourly-shopops-scheduler-$stamp.out.log"
$stderr = Join-Path $logDir "hourly-shopops-scheduler-$stamp.err.log"
$archiveRoot = Join-Path $repo "docs\data\ShopOps_Order"
$evidenceRoot = Join-Path $repo "docs\live-evidence\data-robot"
$args = @(
    "-m",
    "data_robot.hourly_shopops_import",
    "--archive-root",
    $archiveRoot,
    "--evidence-root",
    $evidenceRoot,
    "--browser-profile-root",
    $ProfileRoot,
    "--direct-cdp",
    "--restart-stale-cdp",
    "--wait-login",
    "--auto-login",
    "--allow-new-browser",
    "--auto-actions",
    "--ensure-missing-ad-fields",
    "--douyin-ad-cdp-url",
    "http://127.0.0.1:9224",
    "--tmall-ad-cdp-url",
    "http://127.0.0.1:9225",
    "--hourly-interval-table-id",
    $HourlyIntervalTableId,
    "--start-hour",
    "$StartHour",
    "--end-hour",
    "$EndHour",
    "--interval-minutes",
    "$IntervalMinutes",
    "--jitter-minutes",
    "$JitterMinutes",
    "--order-lookback-days",
    "0",
    "--wait-preflight",
    "--preflight-retry-seconds",
    "300"
)

$process = Start-Process `
    -FilePath $Python `
    -ArgumentList $args `
    -WorkingDirectory $repo `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $pidFile -Value $process.Id -Encoding ASCII

[pscustomobject]@{
    status = "started"
    pid = $process.Id
    pid_file = $pidFile
    stdout = $stdout
    stderr = $stderr
    args = ($args -join " ")
} | ConvertTo-Json -Depth 3
