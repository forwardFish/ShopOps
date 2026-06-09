# T07 HANDOFF - metric-snapshot-delta-engine-refresh

Task pack: `shopops-goal-2026-06-03`
Task id: `T07`
Status: `BLOCKED_BY_ENVIRONMENT`

This run executed only T07. It did not execute or update any other Txx task.

## What Changed

- Replaced stale invalid `docs/auto-execute/results/T07.json` with valid UTF-8 JSON containing `task_pack_id`, `task_id`, `status`, `evidence`, and `blockers`.
- Refreshed T07-only handoff and logs under `docs/auto-execute/latest/` and `docs/auto-execute/logs/T07/`.
- No product code or tests were changed in this speed-mode repair.

## Local Evidence

Command:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T07-current tests\test_metric_service.py tests\test_metric_scheduler_delta.py
```

Result:

```text
5 passed in 0.13s
```

Local coverage:

- `REQ-005`: failed order collection keeps `order_count`, `total_amount`, `roi`, and `cac` as `None`, not `0`.
- `REQ-006`: normal 10-minute delta, ROI/CAC delta, missing previous snapshot, late previous snapshot, and cumulative decrease invalidation are covered by focused tests.
- `REQ-010`: local abnormal status logic is present, but live external validation is blocked by environment.

## Environment Blockers

- Feishu Bitable live verification is blocked because required app credentials and table ids were absent.
- Qianniu PC live verification is blocked because `QIANNIU_CDP_URL` was absent and `http://127.0.0.1:9222/json/version` was unreachable.

Evidence paths:

- `docs/auto-execute/results/T07.json`
- `docs/auto-execute/logs/T07/verification.txt`
- `docs/auto-execute/logs/T07/environment-probe.json`

## Stop Condition

T07 durable files are current and JSON validation is required next. Stop after validating `docs/auto-execute/results/T07.json` parses; do not continue to T08 or any other Txx task.
