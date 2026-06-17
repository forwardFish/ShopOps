# ShopOps Half-Hour Order And Ad Import

## Decision

Orders should use downloaded Excel/CSV files, then import into Feishu. Order data is multi-row structured data, so Excel import gives better parsing, dedupe, replay, and evidence than screenshot OCR.

Ad spend snapshots can use screenshot OCR because each platform has only one current-day summary row. The importer uses platform plus date as the unique key, so every hourly run overwrites today's ad row. A new row is created only when the stat date changes.

## Main Scheduled Entry

Run one full cycle:

```powershell
python -m data_robot.hourly_shopops_import --once --direct-cdp --wait-login --auto-login
```

Run continuously from 09:00 to 24:00, about every half hour with jitter:

```powershell
python -m data_robot.hourly_shopops_import --direct-cdp --wait-login --auto-login
```

Run the three-cycle acceptance test. This is not a fast simulation: after each
cycle it still sleeps for `--interval-minutes` plus/minus `--jitter-minutes`.

```powershell
python -m data_robot.hourly_shopops_import --cycles 3 --direct-cdp --wait-login --auto-login
```

The default cadence is roughly once per half hour with random jitter:
`--interval-minutes 30 --jitter-minutes 5 --start-hour 9 --end-hour 24`.

Downloaded order files are archived under:

```text
D:\lyh\agent\agent-frame\ShopOps\docs\data\ShopOps_Order
```

Each interval summary row compares the previous collection time with the current
collection time. This is the row that answers: after the latest half-hour of ad
spend, how did orders, sales, refunds, effective sales, costs, and commission
change by platform and in total.

## Browser Session Rule

Prefer an already logged-in local Chrome exposed through CDP. Do not run headless for live platform pages. The program defaults to a visible existing CDP browser path and does not use stealth or fingerprint-bypass code.

Start the visible browser sessions from a normal desktop PowerShell session, then
log in manually if the platforms ask for login, QR code, slider, SMS, or face
verification:

```powershell
.\scripts\start_hourly_shopops_cdp_browsers.ps1
python -m data_robot.check_cdp --platform douyin --platform tmall
```

If Chrome exits with `mojo ... platform_channel ... Access denied (0x5)` when
launched from Codex or another restricted process, start it from the normal
Windows desktop instead:

```powershell
.\scripts\start_hourly_shopops_cdp_browsers.cmd
```

The `.cmd` launcher opens Douyin on `http://127.0.0.1:9224` and Tmall on
`http://127.0.0.1:9225`, waits for both CDP ports, and keeps the console open so
you can see `CDP OK` or `CDP NOT READY`.

The scheduled program can pause while you finish login or verification:

```powershell
python -m data_robot.hourly_shopops_import --cycles 3 --direct-cdp --wait-login
```

Optional local login fill, for a dedicated subaccount only. Keep these values in
`.env.local` on each computer; they are never printed into evidence:

```dotenv
SHOPOPS_TMALL_USERNAME=
SHOPOPS_TMALL_PASSWORD=
SHOPOPS_DOUYIN_USERNAME=
SHOPOPS_DOUYIN_PASSWORD=
```

Then run with `--auto-login --wait-login`. Captcha, slider, SMS, and face
verification still pause for manual handling.

Alternatively, save the login once with Windows DPAPI encryption:

```powershell
.\scripts\save_shopops_login_secret.ps1 -Platform tmall
.\scripts\save_shopops_login_secret.ps1 -Platform douyin
```

Those encrypted files are readable only by the same Windows user on the same
computer. On a new computer, run the same save command once.

## Split Entries

Orders only:

```powershell
python -m data_robot.hourly_order_import --once --direct-cdp
```

Ad OCR only:

```powershell
python -m data_robot.ocr_ads_snapshot --platform tmall --date 2026-06-15 --cdp-url http://127.0.0.1:9225
python -m data_robot.ocr_ads_snapshot --platform douyin --date 2026-06-15 --cdp-url http://127.0.0.1:9224
```

Dry-run ad parsing with OCR text:

```powershell
python -m data_robot.ocr_ads_snapshot --platform douyin --date 2026-06-15 --ocr-text-file .tmp/ocr.txt --dry-run
```
