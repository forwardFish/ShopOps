# Task T00 - omx-auto-execute-orchestrator

## 执行命令
```powershell
Set-Location -LiteralPath "D:\lyh\agent\agent-frame\ShopOps"
codex exec "execute D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-tasks\T00-omx-auto-execute-orchestrator.md; write result JSON and HANDOFF; do not stop after planning"
```

## 实现范围
本任务是整个 ShopOps MVP 的一次性总编排任务，不是只完成 `T00` 自己。
执行本任务时，`auto-execute` 必须按下面的任务队列执行、修复、验证并汇总 `T01` 到 `T11`，直到 final gate 给出最终状态。

本项目是中文项目。所有文档、页面显示、飞书表名和字段名都必须使用中文。
飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
当前版本只采集千牛 PC 客户端中的 2 个页面：
1. 订单中心页面：抓取当前筛选范围内所有订单相关数据，必须支持分页或滚动加载，不能只抓首屏。
2. 推广中心页面：只抓取经营概览中的“花费”这个项目，不抓曝光、点击、转化、投入产出比、总成交金额，也不抓直通车/万相台/引力魔方等拆分渠道。

淘宝开放平台 API 仅作为后续阶段能力预留。本版本默认 `ORDER_SOURCE=crawler`，不要求 `TAOBAO_APP_KEY`、`TAOBAO_APP_SECRET`、`TAOBAO_SESSION_KEY`，不得因为缺少这三个 API 凭据阻塞当前版本交付。
当前版本必须把真实飞书多维表格和真实千牛 PC 页面采集纳入任务范围。所有真实调用只能使用环境变量中的凭据和本机已登录授权会话；缺少飞书凭据或千牛 PC 会话时必须写入 `BLOCKED_BY_ENVIRONMENT`，不得冒充 PASS。

## 必须读取的输入
- `AGENTS.md`
- `docs/taobao_mvp_requirements.md`
- `docs/taobao_mvp_development.md`
- `docs/auto-execute/shopops-auto-execute-master-plan.md`
- `docs/auto-execute/shopops-requirement-traceability-matrix.md`
- `docs/auto-execute/shopops-api-db-contract-matrix.md`
- `docs/auto-execute/shopops-standard-test-plan.md`
- `docs/auto-execute/shopops-external-data-validation-matrix.md`

## 一次性执行队列
`auto-execute` 执行本文件时，必须把下面整条队列视为同一个交付目标。不得只写 `T00.json` 后结束。

| 顺序 | Task | 文档 | 目标 | 完成证据 |
| --- | --- | --- | --- | --- |
| 1 | T01 | `docs/auto-execute/shopops-tasks/T01-python-scaffold-config-models.md` | 配置、模型、环境变量骨架 | `docs/auto-execute/results/T01.json` + HANDOFF |
| 2 | T02 | `docs/auto-execute/shopops-tasks/T02-real-feishu-bitable-storage.md` | 真实飞书多维表格/本地失败补写/中文表名字段 | `docs/auto-execute/results/T02.json` + HANDOFF |
| 3 | T03 | `docs/auto-execute/shopops-tasks/T03-order-collectors-api-crawler.md` | 千牛 PC 订单中心页面采集，淘宝 API 后续预留 | `docs/auto-execute/results/T03.json` + HANDOFF |
| 4 | T04 | `docs/auto-execute/shopops-tasks/T04-promotion-crawler-qianniu-safety.md` | 千牛 PC 推广中心页面只抓“花费” | `docs/auto-execute/results/T04.json` + HANDOFF |
| 5 | T05 | `docs/auto-execute/shopops-tasks/T05-metric-snapshot-delta-engine.md` | 今日指标、ROI、获客成本、10 分钟增量、不写 0 | `docs/auto-execute/results/T05.json` + HANDOFF |
| 6 | T06 | `docs/auto-execute/shopops-tasks/T06-alerts-task-log-daily-report.md` | 告警、任务日志、日报 | `docs/auto-execute/results/T06.json` + HANDOFF |
| 7 | T07 | `docs/auto-execute/shopops-tasks/T07-scheduler-full-collect-pending-replay.md` | 调度全链路、pending cache replay | `docs/auto-execute/results/T07.json` + HANDOFF |
| 8 | T08 | `docs/auto-execute/shopops-tasks/T08-real-feishu-data-correctness-verification.md` | 飞书数据正确性验证 | `docs/auto-execute/results/T08.json` + HANDOFF |
| 9 | T09 | `docs/auto-execute/shopops-tasks/T09-local-test-suite-and-secret-guard.md` | 测试、secret guard、报告完整性 | `docs/auto-execute/results/T09.json` + HANDOFF |
| 10 | T10 | `docs/auto-execute/shopops-tasks/T10-operator-runbook-env-docs.md` | 运行手册、环境变量、Windows/千牛/飞书操作说明 | `docs/auto-execute/results/T10.json` + HANDOFF |
| 11 | T11 | `docs/auto-execute/shopops-tasks/T11-final-acceptance-gate.md` | 最终验收门，给出 PASS / REPAIR_REQUIRED / BLOCKED_BY_ENVIRONMENT | `docs/auto-execute/results/T11.json` + HANDOFF |

## 总编排规则
- 一个子任务必须对应一个全新的 `codex exec` 进程；禁止在同一个 `codex exec` 里连续执行多个子任务。
- 每个子任务的 `codex exec` 启动命令必须指向该子任务自己的 markdown 文件，例如 `T03` 只能执行 `docs/auto-execute/shopops-tasks/T03-order-collectors-api-crawler.md`。
- 每个子任务 `codex exec` 完成后必须写入自己的 `docs/auto-execute/results/<TASK>.json`、`docs/auto-execute/latest/<TASK>-HANDOFF.md` 和必要日志，然后退出该 `codex exec`。
- 总编排器必须等待当前子任务 `codex exec` 完全退出，并检查 result JSON + HANDOFF 后，才能启动下一个子任务。
- 禁止复用长时间运行的 worker、旧 `codex exec`、未退出的进程或聊天上下文来执行后续子任务。
- 如果某个子任务失败，必须为修复动作启动新的 `codex exec`，并把修复证据写回同一任务的 result/HANDOFF 或 repair 记录。
- 对每个子任务，先检查对应 `results/<TASK>.json` 和 `latest/<TASK>-HANDOFF.md` 是否都存在且状态可接受。
- 如果子任务缺少结果、状态为 `REPAIR_REQUIRED`、`HARD_FAIL`，或与当前“只抓 2 个页面、淘宝 API 后续预留”的范围冲突，必须重新执行或修复该子任务。
- 如果子任务状态为 `BLOCKED_BY_ENVIRONMENT`，必须保留阻塞证据，并在最终 `T11` 中如实汇总，不能冒充 PASS。
- 子任务执行完成后必须写入自己的 result JSON、HANDOFF、必要日志和外部数据证据。
- 全部子任务完成或阻塞分类后，必须运行 `T11-final-acceptance-gate.md`，并把最终结论写入 `docs/auto-execute/verification-results.md`。
- `T00` 的 result JSON 只能作为总编排摘要，不能替代 `T01` 到 `T11` 的子任务结果。

## 允许改动文件
- `shopops/**`
- `tests/**`
- `scripts/**`
- `docs/auto-execute/**`

## 禁止事项
- 本版本不得实现或调用真实淘宝开放平台订单 API 路径；淘宝 API 只保留后续阶段配置和接口边界。
- 不得硬编码或打印淘宝、飞书、千牛相关凭据。
- 不得绕过验证码、登录、权限或平台安全机制。
- 不得新增除“订单中心”和“推广中心”之外的第三个采集页面。
- 推广中心只能读取“花费”，不得读取或修改任何投放项。
- 采集失败不得写入数字0污柡指标。

## 验收标准
- 飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
- T03 必须实现并验证订单中心页面采集：所有订单相关数据、分页/滚动加载、订单明细写入 `orders_raw`、聚合写入 `monitor_snapshot`。
- T04 必须实现并验证推广中心页面采集：只读取“花费”，写入 `promotion_snapshot` 和 `monitor_snapshot` 的推广消耗字段。
- T00 必须检查后续任务没有把当前版本范围扩大到淘宝 API 真实调用、普通浏览器采集、千牛网页版采集或推广多渠道拆分采集。
- 必须完成或分类处理 `T01` 到 `T11` 全部子任务；不得只完成 `T00` 自己。
- 最终状态必须来自 `T11-final-acceptance-gate.md`，不能只凭聊天记录或局部测试判断。
- 不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。

## 后续测试与证据
| type | command | path |
| --- | --- | --- |
| result | write result | `docs/auto-execute/results/T00.json` |
| handoff | write handoff | `docs/auto-execute/latest/T00-HANDOFF.md` |
| logs | write logs | `docs/auto-execute/logs/T00/` |

## 依赖与续跑门槛
| dependency | evidence | rule |
| --- | --- | --- |
| none | result JSON + HANDOFF | only skip when both exist |

## 防停止规则
- 不能停在计划阶段。
- 不能只完成 `T00` 自己。
- 必须按“一次性执行队列”实施、测试、修复、写入每个子任务结果 JSON 和 HANDOFF。
- 必须坚持一个子任务一个 fresh `codex exec`，每个 `codex exec` 完成对应任务后立即退出。
- 上一个 `codex exec` 未退出、未写 result JSON、未写 HANDOFF，不能启动下一个任务。
- 必须完成 `T11` final gate 后才允许结束。

## 失败修复路由
| status | output | next |
| --- | --- | --- |
| REPAIR_REQUIRED | result JSON + repair item | repair queue |
| BLOCKED_BY_ENVIRONMENT | blocker file | retry or limitation |

## 输出文件
- `docs/auto-execute/results/T00.json`
- `docs/auto-execute/latest/T00-HANDOFF.md`
- `docs/auto-execute/results/T01.json` 到 `docs/auto-execute/results/T11.json`
- `docs/auto-execute/latest/T01-HANDOFF.md` 到 `docs/auto-execute/latest/T11-HANDOFF.md`
- `docs/auto-execute/verification-results.md`

## 结果 JSON
`docs/auto-execute/results/T00.json`

## HANDOFF
`docs/auto-execute/latest/T00-HANDOFF.md`

## 失败状态
| status | meaning |
| --- | --- |
| REPAIR_REQUIRED | gap found |
| BLOCKED_BY_ENVIRONMENT | 缺少真实凭据或千牛 PC 会话时必须写阻塞证据，不得冒充 PASS |
