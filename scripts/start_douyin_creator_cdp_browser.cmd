@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_douyin_creator_cdp_browser.ps1" %*
pause
