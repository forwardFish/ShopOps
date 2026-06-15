@echo off
setlocal

set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  echo Chrome executable was not found.
  exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "STAMP=%%I"
set "PROFILE_ROOT=%LOCALAPPDATA%\ShopOpsCdpProfiles\run-%STAMP%"
set "DOUYIN_PROFILE=%PROFILE_ROOT%\douyin-9224"
set "TMALL_PROFILE=%PROFILE_ROOT%\tmall-9225"

echo Profile root: %PROFILE_ROOT%
start "ShopOps Douyin CDP" "%CHROME%" --new-window --remote-debugging-address=127.0.0.1 --remote-debugging-port=9224 --remote-allow-origins=* --user-data-dir="%DOUYIN_PROFILE%" --no-first-run --no-default-browser-check "https://qianchuan.jinritemai.com/home?aavid=1860240208332803"
start "ShopOps Tmall CDP" "%CHROME%" --new-window --remote-debugging-address=127.0.0.1 --remote-debugging-port=9225 --remote-allow-origins=* --user-data-dir="%TMALL_PROFILE%" --no-first-run --no-default-browser-check "https://myseller.taobao.com/home.htm/tuiguangcenter_new/"

echo Opened ShopOps Chrome windows.
echo Waiting for Chrome remote debugging ports...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = 9224,9225; foreach ($port in $ports) { $ok = $false; for ($i=0; $i -lt 20; $i++) { try { $r = Invoke-RestMethod ('http://127.0.0.1:' + $port + '/json/version') -TimeoutSec 2; Write-Host ('CDP OK ' + $port + ' ' + $r.Browser); $ok = $true; break } catch { Start-Sleep -Seconds 2 } }; if (-not $ok) { Write-Host ('CDP NOT READY ' + $port) } }"
echo Keep both windows open, then run:
echo python -m data_robot.check_cdp --platform douyin --platform tmall
echo python -m data_robot.hourly_shopops_import --cycles 3 --direct-cdp --wait-login --auto-login
pause
