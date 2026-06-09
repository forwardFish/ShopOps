# ShopOps 每日投流明细同步流程

## 标准方式

天猫投流数据使用千牛推广中心接口 + Cookie：

```text
POST https://1bp.taobao.com/report/query.json
```

请求依赖三项运行时配置。标准保存位置是仓库根目录的 `.env.local`，该文件已被 `.gitignore` 忽略，只用于本机运行，不提交到仓库：

```powershell
$env:TAOBAO_PROMOTION_COOKIE="..."
$env:TAOBAO_PROMOTION_CSRF_ID="..."
$env:TAOBAO_PROMOTION_LOGIN_POINT_ID="..."
```

这些值来自千牛推广中心已登录会话。它们是短期凭据，不应写进仓库。

脚本读取顺序：

1. 先读取 `.env` 中的飞书、表格等稳定配置。
2. 再读取 `.env.local` 中的 `TAOBAO_PROMOTION_COOKIE`、`TAOBAO_PROMOTION_CSRF_ID`、`TAOBAO_PROMOTION_LOGIN_POINT_ID`，并覆盖同名旧值。
3. 只有接口真实返回 `charge` 等字段后才允许写飞书；Cookie 失败时必须停止并记录失败，不能写 0。

如果历史里存在多份 Cookie，只保留刚刚通过 `POST https://1bp.taobao.com/report/query.json` 验证成功的那一份。常见失效表现：

- `2103001`：用于会话的 cookie 异常。
- `5002004`：`loginQueryService#getSession` 返回结果异常。

因此以后天猫投流数据的首选路径固定为：接口 + 当前有效 Cookie；页面/CDP 和官方广告 API 只作为备用路径。

## 飞书表规则

目标表：

```text
https://my.feishu.cn/base/KhbEbksLbauw0fssL6EcKAnlnOe?table=tblXLtZsMTaikCeb
```

固定规则：

- `unique_key = 平台 + 日期`
- 天猫示例：`天猫2026-06-07`
- 当天重复抓取时覆盖同一条记录。
- 新的一天自动新增新记录。
- 只写接口返回的真实 `charge`，不在失败时写 0。

## 日常命令

单次抓取并覆盖今天：

```powershell
python scripts\run_promotion_api_to_feishu.py --daily-unique --platform 天猫 --target-table tblXLtZsMTaikCeb --cycles 1 --evidence-dir docs\live-evidence\promotion-daily-detail-0607
```

约 5 分钟抓取一次，试跑 2 次：

```powershell
python scripts\run_promotion_api_to_feishu.py --daily-unique --platform 天猫 --target-table tblXLtZsMTaikCeb --cycles 2 --interval-seconds 300 --evidence-dir docs\live-evidence\promotion-daily-detail-0607
```

生产上连续抓取可以调大 `--cycles`，但仍然会按同一个 `unique_key` 覆盖当天记录。

## 完成标准

每轮输出和 `latest-run.json` 里必须满足：

- `feishu_unique_key` 等于 `平台+日期`。
- `feishu_action` 第一轮通常是 `created`，同一天后续轮次应为 `updated`。
- `api_cost` 与 `feishu_cost` 相等。
- `matched` 为 `true`。

如果缺少 Cookie/CSRF/loginPointId，脚本必须失败并提示缺少哪个变量；这种情况下不得写入 0。
