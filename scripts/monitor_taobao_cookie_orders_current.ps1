param(
  [int]$CrawlPid = 48124,
  [string]$Repo = 'D:\lyh\agent\agent-frame\ShopOps',
  [string]$SourceFile = 'C:\Users\linyanhui\.codex\attachments\b66a3e22-8b33-42d9-88f3-931aa6d1a433\pasted-text.txt',
  [string]$OutputFile = 'docs\live-evidence\tmall-orders-cookie\all-pages.jsonl'
)
Set-Location -LiteralPath $Repo
$dir = 'docs\live-evidence\tmall-orders-cookie'
$monitorLog = Join-Path $dir 'monitor.log'
$stabilizeLog = Join-Path $dir 'stabilize.log'
$stabilizeErr = Join-Path $dir 'stabilize.err.log'
$uploadLog = Join-Path $dir 'upload.log'
$uploadErr = Join-Path $dir 'upload.err.log'
function Log($msg) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Add-Content -LiteralPath $monitorLog -Encoding UTF8 }
Log "monitor started for pid=$CrawlPid"
while ($true) {
  $proc = Get-Process -Id $CrawlPid -ErrorAction SilentlyContinue
  $pages = 0
  if (Test-Path -LiteralPath $OutputFile) { $pages = (Get-Content -LiteralPath $OutputFile | Measure-Object -Line).Lines }
  if ($proc) {
    Log "crawl still running; jsonl_records=$pages"
    Start-Sleep -Seconds 600
    continue
  }
  Log "crawl process exited; jsonl_records=$pages"
  break
}
$mainErr = 'docs\live-evidence\tmall-orders-cookie\crawl-resume.err.log'
if ((Test-Path -LiteralPath $mainErr) -and ((Get-Item -LiteralPath $mainErr).Length -gt 0)) {
  Log "crawl stderr is non-empty; stop before upload: $mainErr"
  exit 2
}
Log "stabilize started"
python scripts\write_taobao_cookie_orders_to_feishu.py stabilize --source-file $SourceFile --output-file $OutputFile --pages 10 --rounds 3 --delay-min 5 --delay-max 9 *> $stabilizeLog 2> $stabilizeErr
if ($LASTEXITCODE -ne 0) { Log "stabilize failed exit=$LASTEXITCODE"; exit $LASTEXITCODE }
Log "upload started"
python scripts\write_taobao_cookie_orders_to_feishu.py upload --input-file $OutputFile *> $uploadLog 2> $uploadErr
if ($LASTEXITCODE -ne 0) { Log "upload failed exit=$LASTEXITCODE"; exit $LASTEXITCODE }
Log "pipeline complete"
