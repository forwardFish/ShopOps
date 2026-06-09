# ShopOps Daily Folder Import

Use this importer for the date-first source folder layout:

```powershell
python scripts\import_daily_files_to_feishu.py --batch-dir D:\lyh\ShopOps\0608
```

For a local parse check without writing Feishu:

```powershell
python scripts\import_daily_files_to_feishu.py --batch-dir D:\lyh\ShopOps\0608 --dry-run
```

Rules:

- The importer never creates, updates, or deletes Feishu Bitable fields.
- It reads existing fields first, then writes only fields that already exist.
- Orders are idempotent by platform order number: `tmall_<order_no>`, `douyin_<order_no>`, `pdd_<order_no>`, `wechat_channels_<order_no>`.
- Ad rows are idempotent by platform and date: `ads_<platform_code>_<yyyy-mm-dd>`.
- Influencer rows are idempotent by platform plus order number.
- Evidence is written to `docs/live-evidence/daily-import-<date-dir>.json`.

2026-06-08 import command:

```powershell
python scripts\import_daily_files_to_feishu.py --batch-dir D:\lyh\ShopOps\0608 --evidence docs\live-evidence\daily-import-0608.json
```
