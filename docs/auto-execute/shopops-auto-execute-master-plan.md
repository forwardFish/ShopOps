# ShopOps shopops-auto-execute-master-plan.md

本项目是中文项目。所有文档、页面显示、飞书表名和字段名都必须使用中文。
飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。
当前版本只要求真实飞书多维表格和真实千牛 PC 页面采集；淘宝开放平台 API 仅作为后续阶段预留，缺少 TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_SESSION_KEY 不得阻塞当前 crawler 版本。必须仅使用环境变量凭据和已登录授权会话，缺失真实飞书或千牛 PC 会话时写入 BLOCKED_BY_ENVIRONMENT，不得冒充 PASS。

## 总入口

一次性执行入口是：

`docs/auto-execute/shopops-tasks/T00-omx-auto-execute-orchestrator.md`

`T00` 是总编排任务，不是单独功能任务。执行 `T00` 时必须顺序执行并验收 `T01` 到 `T11`。

## 执行队列

| 顺序 | Task | 文档 | 目标 |
| --- | --- | --- | --- |
| 1 | T01 | `docs/auto-execute/shopops-tasks/T01-python-scaffold-config-models.md` | 配置、模型、环境变量骨架 |
| 2 | T02 | `docs/auto-execute/shopops-tasks/T02-real-feishu-bitable-storage.md` | 真实飞书多维表格/中文表名字段/失败补写 |
| 3 | T03 | `docs/auto-execute/shopops-tasks/T03-order-collectors-api-crawler.md` | 千牛 PC 订单中心页面采集；淘宝 API 后续预留 |
| 4 | T04 | `docs/auto-execute/shopops-tasks/T04-promotion-crawler-qianniu-safety.md` | 千牛 PC 推广中心页面只抓“花费” |
| 5 | T05 | `docs/auto-execute/shopops-tasks/T05-metric-snapshot-delta-engine.md` | 指标和增量计算，不写 0 |
| 6 | T06 | `docs/auto-execute/shopops-tasks/T06-alerts-task-log-daily-report.md` | 告警、任务日志、日报 |
| 7 | T07 | `docs/auto-execute/shopops-tasks/T07-scheduler-full-collect-pending-replay.md` | 调度全链路、pending replay |
| 8 | T08 | `docs/auto-execute/shopops-tasks/T08-real-feishu-data-correctness-verification.md` | 飞书数据正确性验证 |
| 9 | T09 | `docs/auto-execute/shopops-tasks/T09-local-test-suite-and-secret-guard.md` | 测试、secret guard、报告完整性 |
| 10 | T10 | `docs/auto-execute/shopops-tasks/T10-operator-runbook-env-docs.md` | 操作手册和环境说明 |
| 11 | T11 | `docs/auto-execute/shopops-tasks/T11-final-acceptance-gate.md` | 最终验收门 |

## 完成规则

- 一个 task 必须对应一个全新的 `codex exec`。
- 每个 `codex exec` 只允许执行一个 task markdown 文件。
- 每个 task 的 `codex exec` 必须在写完 result JSON、HANDOFF 和必要日志后退出。
- 总编排器必须等待当前 task 的 `codex exec` 退出并检查证据，再启动下一个 task。
- 禁止复用长跑 worker 或旧 `codex exec` 继续做下一个 task。
- 每个 task 必须产生 `docs/auto-execute/results/<TASK>.json` 和 `docs/auto-execute/latest/<TASK>-HANDOFF.md`。
- 缺少结果、结果不可接受、或与当前版本范围冲突时必须重新执行或修复。
- 真实飞书或真实千牛 PC 环境缺失时，写 `BLOCKED_BY_ENVIRONMENT`；不能把本地 mock 冒充真实验收。
- `T11` 是最终结论来源。只有 `T11` final gate 通过，才能声称全部需求完成。


