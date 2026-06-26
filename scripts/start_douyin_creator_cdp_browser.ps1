param(
    [string]$Chrome = "chrome",
    [int]$Port = 9224,
    [string]$ProfileRoot = "",
    [string]$Keyword = "$([char]0x6d17)$([char]0x9762)$([char]0x5976)",
    [switch]$FreshProfile,
    [switch]$SingleProcess
)

$ErrorActionPreference = "Stop"

if (-not $ProfileRoot) {
    $ProfileRoot = Join-Path (Split-Path -Parent $PSScriptRoot) ".tmp\ShopOpsCdpProfiles"
}

function Resolve-ChromePath {
    param([string]$Name)
    if ($Name -and (Test-Path $Name)) {
        $leaf = [System.IO.Path]::GetFileName($Name).ToLowerInvariant()
        if (-not $leaf.Contains("chrome")) { throw "This workflow is Chrome-only; got $Name." }
        return $Name
    }
    if ($Name -and ($Name.ToLowerInvariant().Contains("edge") -or $Name.ToLowerInvariant().Contains("msedge"))) {
        throw "This workflow is Chrome-only; start Google Chrome, not Edge."
    }
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $leaf = [System.IO.Path]::GetFileName($cmd.Source).ToLowerInvariant()
        if (-not $leaf.Contains("chrome")) { throw "This workflow is Chrome-only; got $($cmd.Source)." }
        return $cmd.Source
    }
    $candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "Google Chrome executable not found for $Name."
}

function Test-CdpReady {
    param([int]$Port)
    try {
        $version = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/version" -TimeoutSec 2
        Write-Host "CDP ready on $($Port): $($version.Browser)"
        return $true
    } catch {
        return $false
    }
}

function Wait-CdpReady {
    param([int]$Port, [int]$Seconds = 45)
    for ($i = 0; $i -lt $Seconds; $i++) {
        if (Test-CdpReady -Port $Port) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

$browserPath = Resolve-ChromePath $Chrome
if ($FreshProfile) {
    $ProfileRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("shopops-creator-cdp-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$profilePath = Join-Path $ProfileRoot "douyin-creator-$Port"
New-Item -ItemType Directory -Force -Path $profilePath | Out-Null
$stdoutLog = Join-Path $profilePath "chrome-cdp-launch.stdout.log"
$stderrLog = Join-Path $profilePath "chrome-cdp-launch.stderr.log"
$encodedKeyword = [System.Uri]::EscapeDataString($Keyword)
$startUrl = "https://so.douyin.com/s?keyword=$encodedKeyword&pd=user&source=normal_search&traffic_source=ZY1112"

if (-not (Test-CdpReady -Port $Port)) {
    $argsList = @(
        "--new-window",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=$Port",
        "--remote-allow-origins=*",
        "--user-data-dir=$profilePath",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-crashpad",
        "--disable-breakpad",
        "--disable-crash-reporter",
        "--disable-gpu",
        "--disable-gpu-sandbox",
        "--in-process-gpu",
        "--disable-extensions",
        "--disable-component-update",
        "--disable-sync",
        "--disable-background-mode",
        "--disable-default-apps",
        "--disable-site-isolation-trials",
        "--no-sandbox",
        "--disable-features=RendererCodeIntegrity,NetworkServiceSandbox,CalculateNativeWinOcclusion,MojoIpcz,IsolateOrigins,site-per-process",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-ipc-flooding-protection",
        "--metrics-recording-only",
        "--disk-cache-size=1"
    )
    if ($SingleProcess) { $argsList += "--single-process" }
    $argsList += $startUrl
    Write-Host "Starting Chrome: $browserPath"
    Write-Host "Profile: $profilePath"
    Write-Host "stderr: $stderrLog"
    Start-Process -FilePath $browserPath -ArgumentList $argsList -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -WindowStyle Normal
}

if (-not (Wait-CdpReady -Port $Port -Seconds 45)) {
    Write-Host "Chrome stderr log: $stderrLog"
    if (Test-Path $stderrLog) { Get-Content -Path $stderrLog -Tail 20 }
    throw "Chrome CDP did not become ready on port $Port. Keep the browser open and rerun this script."
}

Write-Host "Keep this Chrome window open."
Write-Host "Run creator pipeline:"
Write-Host "python scripts\run_douyin_creator_roi_pipeline.py --target 50 --keywords $Keyword --collection-mode profile --comments-per-creator 50 --profile-video-limit 30 --direct-cdp --cdp-url http://127.0.0.1:$Port"
