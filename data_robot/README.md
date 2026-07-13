# ShopOps Data Robot

Playwright scripts for collecting daily Excel/CSV exports, normalizing filenames, extracting zip files, and copying the usable files into:

```powershell
D:\lyh\agent\agent-frame\ShopOps\docs\data\ShopOps_Order\<MMDD>\<平台>
```

The standard archive layout is the date folder `docs\data\ShopOps_Order\<MMDD>\<平台>` so the stability archive remains separate from the formal import folder.
Use `--hourly-batch --batch-hour 23` when repeated same-day runs must be isolated under
`docs\data\ShopOps_Order\<MMDD>\23点下载\<平台>`.

## First-time setup

```powershell
cd D:\lyh\agent\agent-frame\ShopOps
python -m pip install -r requirements.txt
python -m playwright install chromium
```

For a new Windows computer, use the repository setup and browser scripts. They
use stable profiles, reuse an already-running CDP port, and never close the
operator's existing browser windows:

```powershell
.\scripts\setup_shopops_data_robot.ps1
.\scripts\start_shopops_cdp_browsers.ps1
python -m data_robot.check_cdp
```

Log in once in each of the four visible browser windows. Leave those windows
open for later runs. The profiles are stored in `data_robot\profiles` unless
`-ProfileRoot` is supplied. The standard one-command flow is:

```powershell
.\scripts\run_standard_shopops_flow.ps1 -DateToken 0711
```

The command downloads all seven configured files, verifies
`docs\data\ShopOps_Order\0711`, and only then invokes the existing standard
importer. A batch is never imported when any configured task is missing. Each
attempt is separated by the platform floor (2 minutes for non-Tmall tasks, 5
minutes for Tmall tasks), so the default five attempts do not create a
high-frequency click loop. Use `-MaxTaskAttempts 1` for a single-pass smoke
test, or rerun after the platform floor when a portal is still generating a
report.

The downloader records the difference between a browser click and a real
platform result. `task_not_created` means the portal did not create a report
task, `task_pending` means the report is still asynchronous, and
`download_started` means a file or partial download was observed. A hung CDP
target is detached from the automation session and replaced with a new tab;
the old tab remains open so its login state and manual inspection are not
destroyed.

## Login/profile warm-up

Each platform uses a persistent browser profile under `data_robot\profiles\<platform>`, so login cookies can be reused.

```powershell
python -m data_robot.pinduoduo --task pinduoduo_orders
python -m data_robot.wechat_channels
python -m data_robot.douyin --task douyin_ads
python -m data_robot.tmall --task tmall_orders
```

When the browser opens, log in, set the date range, click export/download, and let the script capture the download.
By default the robot tries to click common export/download buttons automatically after the page is available. Use `--manual` only when you want to click by hand.
Some portals use a two-step export flow. For example, WeChat Channels orders open an "订单导出" confirmation dialog after the first export click; the robot handles that second dialog button as part of the normal automatic flow.

Current smart-click flows include the platform-specific paths that do not expose a plain text export button:

- Pinduoduo orders: `批量导出` and then the generated report's `下载报表`.
- WeChat Channels orders: `全部导出` and then the confirmation `导出`.
- Douyin ads: the Qianchuan report table's icon-only `.qc-report-download-btn.download-btn`, then the popover `下载`.
- Douyin influencer commission: `导出数据`, confirmation `导出`, then `下载列表`.
- Tmall orders: `批量导出`, report generation, then the export-list `下载订单报表`.
- Tmall ads: `下载报表`, confirmation, `下载任务管理`, then the generated task `下载`.

## Run all collectors

```powershell
python -m data_robot.run_all --date-token 0612
```

## One-command download and import

After the four Chrome debug sessions are logged in, run the complete production flow:

```powershell
python -m data_robot.full_flow --date-token 0613
```

This runs `daily_download`, verifies the archived batch, then calls:

```powershell
python scripts\import_daily_files_to_feishu.py --batch-dir D:\lyh\agent\agent-frame\ShopOps\docs\data\ShopOps_Order\0613
```

With the default date layout, the actual batch directory is
`D:\lyh\agent\agent-frame\ShopOps\docs\data\ShopOps_Order\0613`.

By default the command is strict: if the fresh download run has errors, it does not import just because older files already exist. When a portal is temporarily blocked but the archive folder is already complete and you intentionally want to import the existing batch, use:

```powershell
python -m data_robot.full_flow --date-token 0613 --allow-existing-archive
```

Use `--dry-run-import` to parse and validate without writing to Feishu.

If `full_flow` exits with `failed_browser_runtime`, the script stopped before
clicking any platform export button. This means the local Python/Playwright
runtime could not start its helper subprocess, commonly shown on Windows as
`PermissionError: [WinError 5]`. In that state, run the command again from a
normal PowerShell session or restart the blocked Codex/terminal environment;
do not keep retrying exports, because no platform download attempt has actually
started yet.

If the CDP browser profile itself is locked or broken, start a clean login
profile suffix and reuse that suffix in the full flow:

```powershell
python -m data_robot.daily_download --prepare-login --browser-profile-suffix cdp-test
python -m data_robot.full_flow --date-token 0614 --browser-profile-suffix cdp-test --auto-actions
```

The first command opens one browser per platform. Log in once in those windows.
The second command uses the stability archive, for example
`docs\data\ShopOps_Order\0614`, and then downloads, verifies, and imports that
fresh batch only.

When the Python Playwright driver is blocked but a Chrome/Edge CDP port is
stable, add `--direct-cdp` to avoid the Playwright helper process entirely:

```powershell
python -m data_robot.full_flow --date-token 0614 --browser-profile-suffix cdp-test --direct-cdp --auto-actions
```

`--direct-cdp` uses the built-in smart export clicks and ignores action JSON
files. If it exits with `failed_browser_connection`, the browser debug port did
not stay available long enough for automation; rerun from a normal desktop
PowerShell session and keep the login browser windows open.

## Daily Download Flow

Open normal Chrome sessions for login:

```powershell
python -m data_robot.daily_download --prepare-login
```

Check whether the Chrome debug sessions are reachable before collecting:

```powershell
python -m data_robot.check_cdp
python -m data_robot.check_cdp --platform pinduoduo
```

Run a read-only preflight before collecting. This checks the archive folder, cooldown state, and optionally Chrome CDP ports. It does not open pages or click export buttons.

```powershell
python -m data_robot.status --date-token 0613
python -m data_robot.status --date-token 0613 --skip-cdp
```

After each platform is logged in and usable, run the seven configured downloads:

```powershell
python -m data_robot.daily_download --date-token 0611
```

This uses four fixed Chrome debug ports: Pinduoduo `9222`, WeChat Channels `9223`, Douyin `9224`, and Tmall `9225`. It watches your default Downloads folder and archives new Excel/CSV/zip files into `docs\data\ShopOps_Order\<MMDD>\<平台>`.

The standard command reuses those existing Chrome windows and logged-in pages; it does not close or restart them during a normal run. If a platform's Playwright/CDP attachment is temporarily blocked, the runner retries the task through the lightweight direct-CDP path without restarting Chrome. For Tmall order reports this path can click the visible existing `下载订单报表` control by the live CSS viewport and then archive the newly created file from the Downloads folder. Use `--restart-stale-cdp` only when an explicitly requested browser restart is acceptable.

Useful flags:

- `--platform pinduoduo` runs one platform.
- `--task pinduoduo_orders` runs one task.
- `--hourly-batch --batch-hour 23` writes into `23点下载` under the date folder.
- `--flat-date-folder` is the explicit date-folder layout and is the default.
- `--auto-actions` reads click/fill/wait steps from `data_robot\actions\<task>.json`.
- `--manual` disables smart export clicks and only waits for your manual download.
- The default anti-risk cooldown is platform-aware: Tmall waits at least 300 seconds; Pinduoduo, WeChat Channels, and Douyin wait at least 120 seconds. `--min-task-interval-seconds` may only increase that floor.
- The default retry interval uses the same platform-aware floor. `--retry-interval-seconds` may only increase it.
- `--max-task-attempts 5` tries each task at most five times, then skips to the next task/platform.
- `--force` bypasses the cooldown. Use it sparingly because frequent exports may trigger platform risk control.
- `--run-import-check` optionally runs `scripts\import_daily_files_to_feishu.py --dry-run` after archiving. It is off by default because the robot's main job is only downloading source files.

## Scheduled run

Default interval is 120 minutes. The scheduler clamps the interval to 60..1440 minutes.

```powershell
python -m data_robot.scheduler --interval-minutes 120
```

For a one-time smoke:

```powershell
python -m data_robot.scheduler --once --platform pinduoduo --task pinduoduo_orders
```

## Record selectors

Use codegen to record a task after login works:

```powershell
python -m data_robot.record_task pinduoduo_orders
```

Then convert the stable clicks/fills into `data_robot\actions\<task>.json`, for example:

```json
[
  {"type": "click", "selector": "text=导出"},
  {"type": "click", "selector": "text=确认导出"},
  {"type": "wait", "seconds": 2}
]
```

Run it with:

```powershell
python -m data_robot.pinduoduo --task pinduoduo_orders --auto-actions
```

## Pinduoduo Loading Or Risk-Control Workaround

If Pinduoduo shows "操作太过频繁，请稍后再试" or keeps loading in the Playwright-launched browser, use a normal Chrome remote-debugging session:

```powershell
python -m data_robot.start_chrome pinduoduo_orders --port 9222
```

Log in and wait until the page loads normally in that Chrome window. Then run:

```powershell
python -m data_robot.pinduoduo --task pinduoduo_orders --date-token 0611 --cdp-url http://127.0.0.1:9222
```

The script attaches to that existing Chrome tab, waits for your export/download click, and copies the downloaded file into `docs\data\ShopOps_Order\<MMDD>\拼多多`.

If the browser downloads into Chrome's default Downloads folder without emitting a Playwright download event, add a watch folder:

```powershell
python -m data_robot.pinduoduo --task pinduoduo_orders --date-token 0611 --cdp-url http://127.0.0.1:9222 --watch-dir C:\Users\linyanhui\Downloads
```

## Archive Files Downloaded Manually

If a platform blocks automated download capture, download the Excel/CSV/zip manually, then archive it with the same naming and unzip rules:

```powershell
python -m data_robot.archive_files pinduoduo_orders C:\Users\linyanhui\Downloads --date-token 0611
```

You can pass one file or a folder. Only `.csv`, `.xls`, `.xlsx`, and `.zip` files are archived. By default this uses the date archive folder; add `--hourly-batch --batch-hour 23` to isolate a repeated same-day archive.

## Verify A Daily Folder

After collecting a batch, check which of the seven configured downloads are present:

```powershell
python -m data_robot.verify_batch --date-token 0611
```

The command writes a JSON report under `docs\live-evidence\data-robot` and returns non-zero when any configured task is missing.
Daily download evidence also includes a per-task `diagnostics` object with the page URL, page title, local capture directory, and watched download folder. Use that field first when a platform was clicked but produced `no_download`; it is intentionally lightweight and does not record order-table text.

For hourly batches, pass the relative batch folder:

```powershell
python -m data_robot.verify_batch --date-token 0611\23点下载
```

To verify that the collected batch can be parsed by the existing importer without writing to Feishu:

```powershell
python scripts\import_daily_files_to_feishu.py --batch-dir D:\lyh\agent\agent-frame\ShopOps\docs\data\ShopOps_Order\0611 --dry-run
```
