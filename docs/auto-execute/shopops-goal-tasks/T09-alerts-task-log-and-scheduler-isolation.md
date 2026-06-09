# Task T09 - alerts-task-log-and-scheduler-isolation

## 0. 任务模板选择
| 字段 | 值 |
| --- | --- |
| Task Template ID | `TPL-SCHEDULER-JOB` |
| Task 类型 | 调度任务 |
| 主验收面 | task_run_log、alert_log、告警去重、子任务隔离 |
| 为什么选择这个模板 | 本任务的主要目标是 task_run_log、alert_log、告警去重、子任务隔离，与 `TPL-SCHEDULER-JOB` 的验收面一致。 |
| 覆盖对象 | REQ-011,REQ-012 |
| 辅助模板 | `TPL-REPORT-GUARD` |
| 模板索引 | `C:\Users\linyanhui\.codex\skills\task-auto-execute\references\task-archetype-templates.md` |
| 软件任务模板目录 | `C:\Users\linyanhui\.codex\skills\task-auto-execute\references\software-dev-task-templates.md` |
| 独立任务模板文件 | `C:\Users\linyanhui\.codex\skills\task-auto-execute\references\templates\TPL-SCHEDULER-JOB.md` |

## Codex Exec
```powershell
Set-Location -LiteralPath "D:\lyh\agent\agent-frame\ShopOps"
codex exec "Use auto-execute. Execute only D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-goal-tasks\T09-alerts-task-log-and-scheduler-isolation.md. Treat this as one fresh task boundary. Do not stop after planning. Implement, test, repair, write result JSON, write HANDOFF, and exit. If blocked, classify the blocker in durable files and route to repair; do not end with only chat text."
```

## 实现功能
验证 full_collect 中每轮日志、告警去重、失败隔离、pending replay 前置执行。

## 必须读取的输入
| 输入 | 用途 |
| --- | --- |
| `AGENTS.md` | 仓库执行规则 |
| `docs/taobao_mvp_requirements.md` | 需求源 |
| `docs/taobao_mvp_development.md` | 开发源 |
| `docs/auto-execute/shopops-goal-delivery-standard-index.md` | 本任务包入口 |
| `docs/auto-execute/shopops-goal-implementation-audit.md` | 当前实现差距 |
| `docs/auto-execute/shopops-goal-requirement-traceability-matrix.md` | 需求映射 |
| `docs/auto-execute/shopops-goal-external-data-validation-matrix.md` | 飞书表和字段映射 |

## 允许改动范围
shopops/scheduler.py; shopops/services/alert_service.py; tests/**; docs/auto-execute/**

## 禁止事项
- 不要修改参考文档中的需求含义。
- 不要把本地 mock 结果说成真实飞书或真实千牛证据。
- 不要绕过验证码、登录、权限或平台安全机制。
- 不要保存淘宝主账号密码、买家手机号、地址、姓名等敏感个人信息。
- 不要执行任何投放修改、调价、暂停、创建或编辑广告动作。
- 不要把采集失败值写成数字 `0`。
- 不要在缺 result JSON 和 HANDOFF 时只用聊天文字收尾。

## 验收标准
- 覆盖对象 `REQ-011,REQ-012` 的实现或验证结果必须落到 durable files。
- 本任务结束必须写 `docs/auto-execute/results/T09.json`。
- 本任务结束必须写 `docs/auto-execute/latest/T09-HANDOFF.md`。
- result JSON 必须包含 `task_pack_id: "shopops-goal-2026-06-03"`、`task_id: "T09"`、`status`、`evidence`、`blockers`。
- 续跑时如果已有 result JSON 缺少 `task_pack_id: "shopops-goal-2026-06-03"`，必须判定为历史结果，只能参考，不能跳过本任务。
- 任何环境缺口必须写 `BLOCKED_BY_ENVIRONMENT`，不能伪造 PASS。

## 开发标准引用
- `docs/auto-execute/shopops-goal-development-standard.md`

## 测试标准引用
- `docs/auto-execute/shopops-goal-software-test-standard.md`

## 细化验收标准
| 面 | 标准 | 证据路径 |
| --- | --- | --- |
| 需求 | `REQ-011,REQ-012` 每一项有实现/缺口判定 | `docs/auto-execute/results/T09.json` |
| 数据 | 相关表字段、unique_key、upsert、pending replay、readback 有证据或 blocker | `docs/auto-execute/external-data/T09/` |
| 测试 | 相关命令运行并记录输出，失败则本任务内修复或写 repair | `docs/auto-execute/logs/T09/` |
| 安全 | 不泄露密钥，不触碰真实投放副作用 | `docs/auto-execute/results/T09.json` |

## 测试与证据
```powershell
pytest scheduler/alerts。
```

## Dependency And Resume Gate
| 依赖 | 必须存在 | 不满足时处理 |
| --- | --- | --- |
| T08 | 前置 result JSON 和 HANDOFF，`none` 除外 | 读取 blockers/repair queue；不得猜测前置成功 |

续跑时先检查：
- `docs/auto-execute/results/T09.json`
- `docs/auto-execute/latest/T09-HANDOFF.md`
- `docs/auto-execute/blockers.md`
- `docs/auto-execute/repair-queue.md`

历史结果过滤规则：
- 本任务只接受含有 `task_pack_id: "shopops-goal-2026-06-03"` 的 result JSON。
- 没有 `task_pack_id`、`task_pack_id` 不一致、或缺少本任务 HANDOFF 的结果，均视为 stale evidence。
- stale evidence 可以作为背景诊断输入，但不得作为本轮任务完成依据。

## Stop Prevention Rules
- 不要在计划后停止。
- 本地可逆的实现、测试、修复必须继续执行到本任务退出条件。
- 测试失败先定位并做 task-local 修复，再重跑相关验证。
- 无论成功、失败还是阻塞，都必须写 result JSON 和 HANDOFF。

## Failure To Repair Routing
| 状态 | 何时使用 | 必须动作 |
| --- | --- | --- |
| PASS | 本任务全部证据真实存在 | 写 result JSON/HANDOFF |
| PASS_WITH_LIMITATION | 非 P0 限制或 local-only 限制 | 写清限制 |
| REPAIR_REQUIRED | P0 本地可修复缺口 | 写最小 repair 项 |
| BLOCKED_BY_ENVIRONMENT | 缺真实 Feishu 凭据、表 ID、千牛 CDP 会话或外部环境 | 写环境 blocker |
| BLOCKED_BY_MISSING_SOURCE | 缺 PRD/代码/输入源 | 写缺失源 |
| HARD_FAIL | P0 明确失败且无法修复 | 写失败证据 |

## 输出文件
docs/auto-execute/results/T09.json

## 结果 JSON
`docs/auto-execute/results/T09.json`

最小字段：
```json
{
  "task_pack_id": "shopops-goal-2026-06-03",
  "task_id": "T09",
  "status": "PASS|PASS_WITH_LIMITATION|REPAIR_REQUIRED|BLOCKED_BY_ENVIRONMENT|BLOCKED_BY_MISSING_SOURCE|HARD_FAIL",
  "evidence": [],
  "blockers": []
}
```

## HANDOFF
`docs/auto-execute/latest/T09-HANDOFF.md`

## 失败状态
允许 `PASS`, `PASS_WITH_LIMITATION`, `REPAIR_REQUIRED`, `BLOCKED_BY_ENVIRONMENT`, `BLOCKED_BY_MISSING_SOURCE`, `HARD_FAIL`。
