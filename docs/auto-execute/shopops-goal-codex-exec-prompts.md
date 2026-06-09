# ShopOps 淘宝单平台监控 MVP auto-execute Codex Exec 执行提示词
> 生成日期：2026-06-03
> 项目根目录：`D:\lyh\agent\agent-frame\ShopOps`
> 项目 slug：`shopops-goal`
> task_pack_id：`shopops-goal-2026-06-03`
> 需求文档：`docs/taobao_mvp_requirements.md`, `docs/taobao_mvp_development.md`

本文件是未来执行包，不是完成报告。本轮 `task-auto-execute` 没有执行产品代码、没有调用 API、没有创建执行证据。


## Task Queue

| T00 | omx-auto-execute-orchestrator | TPL-ORCH-T00 | 串行 fresh codex exec 编排与续跑 | ALL | none | `docs/auto-execute/results/T00.json` | `docs/auto-execute/latest/T00-HANDOFF.md` | repair queue/final gate |
| T01 | source-intake-and-current-implementation-audit | TPL-INTAKE | 需求文档与现有实现差距审计 | REQ-001..REQ-014 | T00 | `docs/auto-execute/results/T01.json` | `docs/auto-execute/latest/T01-HANDOFF.md` | repair queue/final gate |
| T02 | requirements-traceability-refresh | TPL-REQ-MATRIX | P0/P1 需求追踪矩阵刷新 | REQ-001..REQ-014 | T01 | `docs/auto-execute/results/T02.json` | `docs/auto-execute/latest/T02-HANDOFF.md` | repair queue/final gate |
| T03 | feishu-bitable-storage-real-and-local-proof | TPL-EXTERNAL-DATA | 飞书多维表格中文字段、upsert、pending replay、读回 | REQ-007,REQ-008,REQ-009,DATA-001..DATA-009 | T02 | `docs/auto-execute/results/T03.json` | `docs/auto-execute/latest/T03-HANDOFF.md` | repair queue/final gate |
| T04 | qianniu-order-center-live-crawler | TPL-CRAWLER-PIPELINE | 千牛 PC 订单中心采集与 orders_raw/monitor_snapshot | REQ-001,REQ-002,REQ-010 | T03 | `docs/auto-execute/results/T04.json` | `docs/auto-execute/latest/T04-HANDOFF.md` | repair queue/final gate |
| T05 | taobao-api-boundary-and-nonblocking-config | TPL-API-DOMAIN | 淘宝官方 API 后续切换边界，不阻塞当前 crawler MVP | REQ-003 | T04 | `docs/auto-execute/results/T05.json` | `docs/auto-execute/latest/T05-HANDOFF.md` | repair queue/final gate |
| T06 | qianniu-promotion-center-cost-crawler | TPL-CRAWLER-PIPELINE | 千牛 PC 推广中心只读花费采集 | REQ-004,REQ-010 | T05 | `docs/auto-execute/results/T06.json` | `docs/auto-execute/latest/T06-HANDOFF.md` | repair queue/final gate |
| T07 | metric-snapshot-delta-engine-refresh | TPL-BUSINESS-ENGINE | 今日累计和 10 分钟增量指标 | REQ-005,REQ-006,REQ-010 | T06 | `docs/auto-execute/results/T07.json` | `docs/auto-execute/latest/T07-HANDOFF.md` | repair queue/final gate |
| T08 | no-zero-failure-and-data-status-regression | TPL-TEST-INTEGRATION | 失败不写 0 和数据状态传播 | REQ-010,REQ-011 | T07 | `docs/auto-execute/results/T08.json` | `docs/auto-execute/latest/T08-HANDOFF.md` | repair queue/final gate |
| T09 | alerts-task-log-and-scheduler-isolation | TPL-SCHEDULER-JOB | task_run_log、alert_log、告警去重、子任务隔离 | REQ-011,REQ-012 | T08 | `docs/auto-execute/results/T09.json` | `docs/auto-execute/latest/T09-HANDOFF.md` | repair queue/final gate |
| T10 | daily-report-and-operator-runbook | TPL-DOCS-HANDOFF | 日报生成、Windows 运行手册、环境变量说明 | REQ-013,REQ-014 | T09 | `docs/auto-execute/results/T10.json` | `docs/auto-execute/latest/T10-HANDOFF.md` | repair queue/final gate |
| T11 | full-local-test-suite-and-acceptance-scripts | TPL-TEST-E2E | 全 P0 本地测试、acceptance scripts、历史证据新鲜度 | REQ-001..REQ-014 | T10 | `docs/auto-execute/results/T11.json` | `docs/auto-execute/latest/T11-HANDOFF.md` | repair queue/final gate |
| T12 | report-integrity-secret-guard-code-review | TPL-REPORT-GUARD | secret guard、证据一致性、代码审查 | REQ-014 | T11 | `docs/auto-execute/results/T12.json` | `docs/auto-execute/latest/T12-HANDOFF.md` | repair queue/final gate |
| T13 | final-acceptance-gate-fail-closed | TPL-FINAL-GATE | 只读 durable evidence 判定最终验收 | ALL | T12 | `docs/auto-execute/results/T13.json` | `docs/auto-execute/latest/T13-HANDOFF.md` | repair queue/final gate |
