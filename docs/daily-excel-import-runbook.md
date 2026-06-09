# ShopOps 每日 Excel/CSV 导入流程

## 输入目录

默认数据根目录：

```powershell
D:\lyh\ShopOps
```

每日目录按平台分开，例如：

```powershell
D:\lyh\ShopOps\抖音\0607
D:\lyh\ShopOps\视频号\0607
```

## 订单数据

订单数据继续使用统一订单分表脚本。该脚本以本地导出为主，写入四个平台订单明细表，并刷新汇总公式：

```powershell
python scripts\split_platform_order_tables.py --data-root D:\lyh\ShopOps
```

完成标准：

- 写入或更新对应平台订单明细表。
- 生成 `docs/live-evidence/platform-order-split/platform-order-split-result.json`。
- 结果中的 `status` 为 `success`，并包含表计数、字段校验和重复订单审计。

## 达人佣金数据

达人佣金数据使用每日固定脚本：

```powershell
python scripts\sync_daily_influencer_commissions.py --data-root D:\lyh\ShopOps --date-dir 0607
```

默认目标表：

```text
https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe?table=tblhBsehmQbzWEVm
```

也可以显式指定：

```powershell
python scripts\sync_daily_influencer_commissions.py --data-root D:\lyh\ShopOps --date-dir 0607 --target-table tblhBsehmQbzWEVm
```

固定规则：

- `unique_key = 平台 + 订单编号`，例如 `抖音6953489890610190242`、`视频号1234567890`。
- 只写源文件中实际存在达人或带货费用信息的行。
- 不用 0 或空达人字段伪造佣金数据。
- 写入后按本次 `unique_key` 读回校验。

完成标准：

- 生成 `docs/live-evidence/influencer-commission-<date-dir>.json`。
- `upsert.saved == readback_count == source_row_count`。
- `missing_unique_keys` 和 `mismatched_unique_keys` 为空。
- 如果 `source_row_count` 为 0，表示当天导出没有可识别达人/带货费用行；脚本不会写假数据。
