# T00 HANDOFF - omx-auto-execute-orchestrator

## Status
`PASS_WITH_LIMITATION`

T00 is implemented and verified inside the allowed scope `docs/auto-execute/**`. The limitation is intentional: this run executed only T00, so the relay runner was validated with `-DryRun` and did not spawn downstream `codex exec` workers.

## Evidence
| Evidence | Path | Result |
| --- | --- | --- |
| Relay runner implementation | `docs/auto-execute/T00-run-goal-task-relay.ps1` | Present |
| Dry-run machine log | `docs/auto-execute/logs/T00/orchestrator-20260603-120938.json` | PASS |
| Repair queue | `docs/auto-execute/repair-queue.md` | Written |
| Result JSON | `docs/auto-execute/results/T00.json` | Written |

## What T00 Enforces
- Task pack id: `shopops-goal-2026-06-03`.
- Task directory: `docs/auto-execute/shopops-goal-tasks`.
- One-at-a-time downstream selection.
- Required downstream artifacts: `docs/auto-execute/results/Txx.json` plus `docs/auto-execute/latest/Txx-HANDOFF.md`.
- Existing result JSON without matching `task_pack_id` is `STALE_RESULT` and cannot skip the task.
- Missing result or handoff is `MISSING_ARTIFACT` and goes to `docs/auto-execute/repair-queue.md`.

## Current Queue Finding
The dry-run checked T01-T13 and selected `T01` as the next task. Existing T01-T09/T11 outputs are stale for this task pack because their JSON files do not contain `task_pack_id: "shopops-goal-2026-06-03"`. T10, T12, and T13 are missing required result/handoff artifacts.

## Blockers
No T00-local blocker remains.

Downstream environment blockers from prior evidence remain documented in `docs/auto-execute/blockers.md` for live Feishu credentials/table ids and Qianniu PC CDP session availability. Those are not upgraded to PASS by T00.

## Resume Instruction
To continue beyond this T00-only boundary, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\docs\auto-execute\T00-run-goal-task-relay.ps1 -ProjectRoot "D:\lyh\agent\agent-frame\ShopOps"
```

The runner will launch only the first open downstream task, wait for it to exit, and write a T00 log. Re-run after each downstream task until the queue advances to T13.
