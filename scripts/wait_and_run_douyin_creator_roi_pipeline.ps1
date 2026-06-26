param(
    [string]$Keyword = "$([char]0x6d17)$([char]0x9762)$([char]0x5976)",
    [int]$Target = 50,
    [int]$Port = 9224,
    [int]$CommentsPerCreator = 50,
    [int]$ProfileVideoLimit = 30,
    [int]$WaitMinutes = 30,
    [string]$OutDir = "docs/live-evidence"
)

$ErrorActionPreference = "Stop"
$deadline = (Get-Date).AddMinutes($WaitMinutes)
$cdpUrl = "http://127.0.0.1:$Port"
$ready = $false

while ((Get-Date) -lt $deadline) {
    python scripts\check_douyin_creator_chrome_cdp.py --cdp-url $cdpUrl | Out-Host
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 10
}

if (-not $ready) {
    throw "Chrome CDP was not ready at $cdpUrl within $WaitMinutes minutes."
}

$env:PYTHONIOENCODING = "utf-8"
python scripts\run_douyin_creator_roi_pipeline.py --target $Target --keywords $Keyword --collection-mode profile --comments-per-creator $CommentsPerCreator --profile-video-limit $ProfileVideoLimit --direct-cdp --cdp-url $cdpUrl --round-timeout-seconds 7200 --max-rounds 3 --out-dir $OutDir
exit $LASTEXITCODE
