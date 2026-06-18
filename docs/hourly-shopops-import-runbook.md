# ShopOps Order And Ad Import

## Decision

Orders should use downloaded Excel/CSV files for Tmall and Jushuitan for Douyin, then import into Feishu. Order data is multi-row structured data, so table/API import gives better parsing, dedupe, replay, and evidence than screenshot OCR.

Tmall ad spend snapshots can use screenshot OCR because the platform has one current-day summary row. Douyin order/sales data comes from Jushuitan in this workflow; do not treat a Tmall-only ad snapshot as a complete total.

The business-facing incremental result is the Feishu table `tblb7aBTN2dZ9ZSF`
(`投流小时段归因汇总`). It stores rows for each collection window and exposes
the newly added order/ad values with fields such as `窗口开始`, `窗口结束`,
`新增订单数`, `新增有效销售额`, `新增投流消耗`, and `新增投流成交金额`.
Historical order backfill belongs to the separate historical import program; the
hourly program passes `--order-lookback-days 0` so it imports only the requested
date before calculating the interval rows. When Douyin falls back to Jushuitan
for an hourly run, the Jushuitan API query is also narrowed to the requested
date instead of scanning the historical 90-day window. A complete hourly cycle
requires Tmall orders plus Douyin Jushuitan orders before the interval summary
can be trusted.

## Main Scheduled Entry

Run one full cycle:

```powershell
python -m data_robot.hourly_shopops_import --once --direct-cdp --wait-login --auto-login
```

Acceptance test on a new computer. A failed cycle does not count; the command
exits only after five successful order plus ad plus interval-summary cycles:

```powershell
python -m data_robot.hourly_shopops_import --success-cycles 5 --direct-cdp --wait-login --auto-login --interval-minutes 30 --jitter-minutes 0 --min-task-interval-seconds 900
```

Production schedule after acceptance succeeds. It runs from 08:00 through the
last run before 23:00, then sleeps overnight and resumes at 08:00 the next day.
The cadence is roughly one hour, with up to 12 minutes of random jitter. These
are the program defaults, so the timing flags below are only shown to make the
schedule explicit:

```powershell
python -m data_robot.hourly_shopops_import --direct-cdp --wait-login --auto-login --interval-minutes 60 --jitter-minutes 12 --start-hour 8 --end-hour 23 --min-task-interval-seconds 900
```

The hourly command defaults to both order platforms:

```text
--order-platform 天猫 --order-platform 抖音
```

Douyin requires Jushuitan credentials on the machine:

```dotenv
JUSHUITAN_PARTNER_ID=
JUSHUITAN_PARTNER_KEY=
JUSHUITAN_TOKEN=
JUSHUITAN_SHOP_ID_DOUYIN=
```

If any of those are missing, preflight must fail and the program must not write
an incomplete Tmall-only interval total.

Downloaded order files are archived under:

```text
C:\LYH\Code\ShopOps\docs\data\ShopOps_Order
```

Each interval summary row compares the previous collection time with the current
collection time inside the configured collection window. This is the row that answers: after the latest interval of ad
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
