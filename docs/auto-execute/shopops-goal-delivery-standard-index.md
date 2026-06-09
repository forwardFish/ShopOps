# ShopOps 淘宝单平台监控 MVP Goal Delivery Standard Index
> 生成日期：2026-06-03
> 项目根目录：`D:\lyh\agent\agent-frame\ShopOps`
> 项目 slug：`shopops-goal`
> task_pack_id：`shopops-goal-2026-06-03`
> 语言：zh-CN

## Goal
使用 `task-auto-execute` 生成一套新的、可交给后续 `auto-execute` 一次性串行执行的完整任务包，并把需求文档功能是否已实现写成可恢复审计。

## Source Inventory
| Source ID | 类型 | 路径/位置 | 用途 | 状态 | Blocker |
| --- | --- | --- | --- | --- | --- |
| SRC-AGENTS | 规则 | `AGENTS.md` | 仓库执行约束 | PLANNED | |
| SRC-PRD | 需求 | `docs/taobao_mvp_requirements.md` | P0/P1 需求源 | PLANNED | |
| SRC-DEV | 开发文档 | `docs/taobao_mvp_development.md` | 架构与伪代码源 | PLANNED | |
| SRC-CODE | 代码 | `shopops/**`, `tests/**`, `scripts/**` | 当前实现审计 | PLANNED | |
| SRC-OLD | 历史执行证据 | `docs/auto-execute/results/**`, `latest/**` | 只能作为旧状态参考，不能当本轮新鲜 PASS | PLANNED | STALE_EVIDENCE_GUARD |

## 文档地图
| 文档 | 作用 |
| --- | --- |
| `shopops-goal-delivery-standard-index.md` | 入口、证据地图、执行边界 |
| `shopops-goal-implementation-audit.md` | 需求是否已实现的逐项审计 |
| `shopops-goal-TOTAL-auto-execute-task.md` | 给后续 auto-execute 的总任务入口 |
| `shopops-goal-auto-execute-master-plan.md` | 完整任务队列和依赖 |
| `shopops-goal-development-standard.md` | 后续 worker 开发规则 |
| `shopops-goal-software-test-standard.md` | 测试和 final gate 规则 |
| `shopops-goal-requirement-traceability-matrix.md` | 需求到任务/证据映射 |
| `shopops-goal-api-db-contract-matrix.md` | API/服务/DB/存储契约 |
| `shopops-goal-external-data-validation-matrix.md` | 飞书表字段、upsert、readback 矩阵 |
| `shopops-goal-standard-test-plan.md` | 行级测试计划 |
| `shopops-goal-codex-exec-prompts.md` | 母执行提示词 |
| `shopops-goal-codex-exec-prompts-split.md` | 一任务一 fresh codex exec 队列 |
| `shopops-goal-owner-scenario-matrix.md` | 老板/运营验收场景 |
| `shopops-goal-final-acceptance-gate.md` | 只读 durable evidence 的最终门禁 |
| `shopops-goal-task-pack-quality-audit.md` | 本任务包质量自检 |

## 执行边界
本轮使用的是 `task-auto-execute`，只能生成任务包和未来执行提示词；本轮不会运行产品实现、不会调用 `codex exec` 队列、不会创建新的 `results/*.json` 或 `latest/*HANDOFF.md` 执行证据。

## 一次性执行规则
后续真实执行时，从 `T00` 开始。T00 必须一次只启动一个 fresh `codex exec`，等待旧进程退出并确认 result JSON、HANDOFF、日志存在后，才能启动下一任务。

## 状态词
`READY_FOR_AUTO_EXECUTE` 表示任务包可执行，不表示产品已完成。产品最终状态只能由后续 final gate 根据 durable evidence 判定。
