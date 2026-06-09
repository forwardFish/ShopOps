# ShopOps

ShopOps is a Taobao single-shop monitoring MVP for orders, promotion cost, alerts, task logs, and daily reports.

The current local implementation defaults to mock collectors plus a local Feishu Bitable double. It does not call real Taobao, Qianniu, or Feishu services unless you provide the required environment and run in an authorized Windows desktop session.

## Local Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

## Local Verification

```powershell
python -m pytest -q
python scripts\acceptance\verify_feishu_data.py
python scripts\acceptance\secret_guard.py
```

## Platform Order API Mode

Order API connectors are available for Taobao/Tmall, Pinduoduo, Doudian, and WeChat Channels/WeChat Store. Fill the relevant credentials in `.env`, set `ORDER_SOURCE=api`, set `SHOP_PLATFORM` to one of `taobao`, `pinduoduo`, `doudian`, or `wechat_channels`, then run:

```powershell
python scripts\run_platform_orders.py
```

Detailed credential names, default endpoints, and verification notes are in `docs/platform-order-api-integration.md`.

To pull all platform orders through Jushuitan instead, keep the direct API variables above in place for later use, set `ORDER_SOURCE=jushuitan`, fill `JUSHUITAN_PARTNER_ID`, `JUSHUITAN_PARTNER_KEY`, and `JUSHUITAN_TOKEN`, then run the same `python scripts\run_platform_orders.py` command. Details are in `docs/jushuitan-order-api-integration.md`.

Daily-report focused verification:

```powershell
python -m pytest -q -p no:cacheprovider tests\test_alerts_task_log_daily_report.py tests\test_storage_and_scheduler.py
```

Local Feishu data evidence is written under `cache/` by default, including:

```text
cache/local_feishu.json
cache/pending_records.jsonl
```

Auto-execute evidence for task runs is written under:

```text
docs/auto-execute/results/
docs/auto-execute/latest/
docs/auto-execute/logs/
```

## Daily Report

The scheduler sends the daily report at `DAILY_REPORT_TIME`, default `23:50`. The report is saved to the `daily_report` table with:

- `unique_key`: `<SHOP_ID>_<YYYYMMDD>`
- `日期`
- `店铺ID`
- `店铺名称`
- `日报内容`
- `生成时间`
- send status fields

`unique_key` upsert prevents duplicate daily report rows when the same shop/date is generated repeatedly.

The report text summarizes:

- today's order count;
- today's GMV;
- promotion center cost;
- total promotion cost;
- ROI;
- customer acquisition cost;
- alert statistics;
- data-status disclaimer.

If a metric is unavailable because collection failed, the report must show an unavailable value rather than writing numeric `0`.

## Windows Operator Runbook

1. Start the Windows machine that has Qianniu PC installed.
2. Log in with an authorized Taobao sub-account. Do not bypass captcha, login, or permission checks.
3. Expose or confirm the Qianniu Chromium CDP endpoint configured by `QIANNIU_CDP_URL`, default `http://127.0.0.1:9222`.
4. Create or confirm the Feishu app, Bitable app token, table IDs, and optional robot webhook.
5. Copy `.env.example` to `.env` and fill only environment variables. Do not store Taobao account passwords or buyer personal data.
6. Run local verification first.
7. Run `python main.py` from an activated virtual environment.
8. Inspect `task_run_log`, `alert_log`, `monitor_snapshot`, and `daily_report` for write/readback evidence.
9. If Feishu write fails, inspect `PENDING_RECORDS_PATH`; replay should be handled after credentials/connectivity recover.

## Environment Boundaries

- `ORDER_SOURCE=crawler` is the current Taobao order source.
- `PROMOTION_SOURCE=qianniu_pc` is the only supported promotion source for this MVP.
- Taobao Open Platform keys are reserved for the future API boundary and are not required for the current crawler path.
- Missing real Feishu credentials/table IDs blocks live Feishu write/readback verification.
- Missing a live logged-in Qianniu PC CDP session blocks live order/promotion page verification.
- Local mock or local Feishu double evidence must not be described as real Feishu or real Qianniu evidence.

## Safety Rules

- Do not store Taobao main-account passwords.
- Do not store buyer phone numbers, addresses, names, or other sensitive personal data in repo files.
- Do not bypass captcha, login validation, permission checks, or platform safety mechanisms.
- Do not create, edit, pause, bid-change, or otherwise modify advertisements.
- Do not write real Feishu Bitable data unless the operator has explicitly provided authorized credentials and table IDs for that environment.
