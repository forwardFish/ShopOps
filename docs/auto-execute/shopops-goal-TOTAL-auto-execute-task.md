# ShopOps 淘宝单平台监控 MVP 总任务 - 交给 auto-execute 一次性执行
> 生成日期：2026-06-03
> 项目根目录：`D:\lyh\agent\agent-frame\ShopOps`
> task_pack_id：`shopops-goal-2026-06-03`
> 分任务目录：`docs/auto-execute/shopops-goal-tasks`

## 总目标
使用 `auto-execute` 按 `docs/auto-execute/shopops-goal-auto-execute-master-plan.md` 串行执行 T00-T13，完成需求文档功能实现审计、缺口修复、本地验证、外部环境探针和最终 fail-closed 验收。

## 必须读取
- `AGENTS.md`
- `docs/auto-execute/shopops-goal-delivery-standard-index.md`
- `docs/auto-execute/shopops-goal-auto-execute-master-plan.md`
- `docs/auto-execute/shopops-goal-task-pack-quality-audit.md`
- `docs/auto-execute/shopops-goal-tasks/T00-omx-auto-execute-orchestrator.md`

## 模板约束
- 每个分任务都已选择 `Task Template ID`。
- 每个分任务都引用独立模板文件：`C:\Users\linyanhui\.codex\skills\task-auto-execute\references\templates\TPL-*.md`。
- 后续执行不得把任何分任务改成无模板的泛化任务。

## 执行方式
从 T00 开始。T00 是唯一总编排入口，必须：
- 读取本总任务和 master plan。
- 一次只启动一个 fresh `codex exec` 执行下一个分任务。
- 等待当前 `codex exec` 完全退出。
- 校验当前任务写出 result JSON、HANDOFF 和必要日志。
- 校验 result JSON 含有 `task_pack_id: "shopops-goal-2026-06-03"`。
- 如果遇到 `REPAIR_REQUIRED` 或 `HARD_FAIL`，写入 repair queue 并执行最小修复任务。
- 如果遇到真实 Feishu/Qianniu/外部环境不可用，写 `BLOCKED_BY_ENVIRONMENT`，不得伪造 PASS。

## 首个命令
```powershell
Set-Location -LiteralPath "D:\lyh\agent\agent-frame\ShopOps"
codex exec "Use auto-execute. Execute the total task pack at D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-goal-TOTAL-auto-execute-task.md. Start from D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-goal-tasks\T00-omx-auto-execute-orchestrator.md. Execute one fresh codex exec per subtask, wait for exit, verify task_pack_id shopops-goal-2026-06-03, result JSON, HANDOFF, logs, repair routing, and final gate. Do not stop after planning. Implement, test, repair, write durable result files, and exit only after T13 reaches PASS, PASS_WITH_LIMITATION, REPAIR_REQUIRED, BLOCKED_BY_ENVIRONMENT, BLOCKED_BY_MISSING_SOURCE, or HARD_FAIL."
```

## 终态规则
总任务完成不等于 pure PASS。只有 T13 final gate 可判定最终状态。缺真实飞书写入/读回或真实千牛 PC CDP 页面证据时，必须保留 `BLOCKED_BY_ENVIRONMENT` 或限制态。
