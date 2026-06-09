# Task T03 - order-collectors-api-crawler

## 执行命令
```powershell
Set-Location -LiteralPath "D:\lyh\agent\agent-frame\ShopOps"
codex exec "execute D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-tasks\T03-order-collectors-api-crawler.md; write result JSON and HANDOFF; do not stop after planning"
```

## 实现范围
本项目是中文项目。所有文档、页面显示、飞书表名和字段名都必须使用中文。
飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
当前版本必须实现千牛 PC 订单中心页面采集。淘宝开放平台订单 API 只保留后续阶段配置和接口边界；缺少淘宝 API 凭据不得阻塞当前 crawler 版本。

本任务必须实现的当前版本范围：
- 默认 `ORDER_SOURCE=crawler`。
- 订单中心页面必须抓取当前筛选范围内所有订单相关数据。
- 订单中心页面必须支持分页或滚动加载，不能只抓首屏。
- 单条订单至少覆盖：订单号、创建时间、宝贝名称、单价、数量、履约/售后状态、交易状态、实收款、操作区可见文本或链接状态。
- 成功时订单明细写入 `orders_raw`，并基于明细聚合今日订单数、今日成交额到 `monitor_snapshot`。
- 登录失效、验证码、权限不足、千牛未运行时返回失败状态和错误信息，不得写 0 污染指标。

后续 API 切换条件只写入配置和接口边界：后续改为 `ORDER_SOURCE=api` 时才需要 `TAOBAO_APP_KEY`、`TAOBAO_APP_SECRET`、`TAOBAO_SESSION_KEY`。

## 必须读取的输入
- `AGENTS.md`
- `docs/taobao_mvp_requirements.md`
- `docs/taobao_mvp_development.md`
- `docs/auto-execute/shopops-external-data-validation-matrix.md`

## 允许改动文件
- `shopops/**`
- `tests/**`
- `scripts/**`
- `docs/auto-execute/**`

## 禁止事项
- 不得硬编码、打印或提交淘宝开放平台凭据；不得绕过登录、验证码、权限或平台安全机制。
- 不得使用普通浏览器、淘宝网页版或千牛网页版替代千牛 PC 客户端订单中心。
- 不得新增除订单中心之外的订单采集页面。
- 采集失败不得写入数字0污柡指标。

## 验收标准
- 飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
- 订单中心页面采集必须证明：分页/滚动加载覆盖全部订单、订单明细字段完整、`orders_raw` 写入中文字段、`monitor_snapshot` 聚合值来自订单明细。
- API 模式在当前版本只验收为“后续预留”：缺少 `TAOBAO_APP_KEY`、`TAOBAO_APP_SECRET`、`TAOBAO_SESSION_KEY` 不得导致 crawler 版本失败。
- 不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。

## 后续测试与证据
| type | command | path |
| --- | --- | --- |
| result | write result | `docs/auto-execute/results/T03.json` |
| handoff | write handoff | `docs/auto-execute/latest/T03-HANDOFF.md` |
| logs | write logs | `docs/auto-execute/logs/T03/` |

## 依赖与续跑门槛
| dependency | evidence | rule |
| --- | --- | --- |
| previous result JSON and HANDOFF | result JSON + HANDOFF | only skip when both exist |

## 防停止规则
- 不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。

## 失败修复路由
| status | output | next |
| --- | --- | --- |
| REPAIR_REQUIRED | result JSON + repair item | repair queue |
| BLOCKED_BY_ENVIRONMENT | blocker file | retry or limitation |

## 输出文件
- `order-collectors-api-crawler`

## 结果 JSON
`docs/auto-execute/results/T03.json`

## HANDOFF
`docs/auto-execute/latest/T03-HANDOFF.md`

## 失败状态
| status | meaning |
| --- | --- |
| REPAIR_REQUIRED | gap found |
| BLOCKED_BY_ENVIRONMENT | 缺少真实千牛 PC 会话、真实飞书授权或必要本地运行环境时必须写阻塞证据；缺少淘宝 API 凭据不阻塞当前 crawler 版本 |
