param(
    [string]$Browser = "chrome",
    [string]$ProfileRoot = "$env:LOCALAPPDATA\ShopOpsCdpProfiles",
    [int]$DouyinPort = 9224,
    [int]$TmallPort = 9225,
    [switch]$FreshProfile
)

$ErrorActionPreference = "Stop"

function Resolve-BrowserPath {
    param([string]$Name)
    if ($Name -eq "edge") {
        $candidates = @(
            "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
            "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
            "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
        )
    } else {
        $candidates = @(
            "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
        )
    }
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }
    throw "Browser executable not found for '$Name'."
}

function Start-CdpBrowser {
    param(
        [string]$BrowserPath,
        [string]$ProfilePath,
        [int]$Port,
        [string]$Url
    )
    New-Item -ItemType Directory -Force -Path $ProfilePath | Out-Null
    $argsList = @(
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=$Port",
        "--remote-allow-origins=*",
        "--user-data-dir=$ProfilePath",
        "--no-first-run",
        "--no-default-browser-check",
        $Url
    )
    Start-Process -FilePath $BrowserPath -ArgumentList $argsList
}

function Wait-CdpReady {
    param([int]$Port)
    $url = "http://127.0.0.1:$Port/json/version"
    for ($i = 0; $i -lt 15; $i++) {
        try {
            $version = Invoke-RestMethod -Uri $url -TimeoutSec 2
            Write-Host "CDP ready on ${Port}: $($version.Browser)"
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    Write-Warning "CDP port $Port is not ready yet. Keep the browser open and rerun: python -m data_robot.check_cdp --platform douyin --platform tmall"
}

$browserPath = Resolve-BrowserPath $Browser
if ($FreshProfile) {
    $ProfileRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("shopops-cdp-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$douyinProfile = Join-Path $ProfileRoot "douyin-$DouyinPort"
$tmallProfile = Join-Path $ProfileRoot "tmall-$TmallPort"
$douyinUrl = "https://qianchuan.jinritemai.com/home?aavid=1860240208332803"
$tmallUrl = "https://myseller.taobao.com/home.htm/tuiguangcenter_new/"

Write-Host "Opening Douyin CDP browser on port $DouyinPort..."
Start-CdpBrowser -BrowserPath $browserPath -ProfilePath $douyinProfile -Port $DouyinPort -Url $douyinUrl

Write-Host "Opening Tmall CDP browser on port $TmallPort..."
Start-CdpBrowser -BrowserPath $browserPath -ProfilePath $tmallProfile -Port $TmallPort -Url $tmallUrl

Wait-CdpReady -Port $DouyinPort
Wait-CdpReady -Port $TmallPort

Write-Host "If login or verification appears, complete it in these visible browser windows and keep them open."
Write-Host "Then run: python -m data_robot.hourly_shopops_import --cycles 3 --direct-cdp --wait-login --auto-login"
