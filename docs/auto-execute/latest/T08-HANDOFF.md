# T08 HANDOFF - no-zero-failure-and-data-status-regression

Task pack: `shopops-goal-2026-06-03`
Task: `T08`
Verdict: `BLOCKED_BY_ENVIRONMENT`
Updated: `2026-06-03T18:06:19+08:00`

This run executed only T08. It did not execute any other Txx task.

## Evidence

- Result JSON: `docs/auto-execute/results/T08.json`
- Focused pytest pass: `docs/auto-execute/logs/T08/focused-pytest-20260603-refresh-workspace-basetemp.txt`
- Fresh environment probe: `docs/auto-execute/logs/T08/environment-probe-refresh-20260603.json`
- Prior local external-data proof used as background/local-only evidence: `docs/auto-execute/external-data/T08/feishu-data-proof.json`
- Initial temp-path failures retained for traceability:
  - `docs/auto-execute/logs/T08/focused-pytest-20260603-refresh.txt`
  - `docs/auto-execute/logs/T08/focused-pytest-20260603-refresh-basetemp.txt`

## Local Verification

Focused command:

```powershell
python -m pytest -q --basetemp .\docs\auto-execute\logs\T08\pytest-basetemp tests/test_metric_service.py tests/test_metric_scheduler_delta.py tests/test_storage_and_scheduler.py::test_pending_cache_and_replay tests/test_storage_and_scheduler.py::test_scheduler_replays_pending_cache_before_full_collect tests/test_storage_and_scheduler.py::test_scheduler_records_pending_replay_failure_without_aborting_collect tests/test_storage_and_scheduler.py::test_promotion_center_failure_does_not_write_zero tests/test_feishu_storage_contract.py
```

Observed result: `12 passed in 0.19s`.

Covered local behavior:

- Collector failure does not write numeric zero metrics.
- `data_status` propagates `order_failed`, `promotion_failed`, `missing_previous`, `invalid`, and `normal`.
- Pending cache write and replay behavior is covered locally.
- Local Feishu double covers required tables, upsert, and readback.
- Feishu storage fails closed when real environment values are missing.

## Blockers

- `BLOCKED_BY_ENVIRONMENT`: real Feishu Bitable credentials/table IDs are absent. Missing values include `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_APP_TOKEN`, `FEISHU_TABLE_MONITOR_SNAPSHOT`, `FEISHU_TABLE_ORDERS_RAW`, `FEISHU_TABLE_PROMOTION_SNAPSHOT`, `FEISHU_TABLE_METRICS_10MIN`, and `FEISHU_TABLE_TASK_LOG`.
- `BLOCKED_BY_ENVIRONMENT`: real Qianniu PC CDP session is unavailable. Probe target was `http://127.0.0.1:9222/json/version`; current result is not reachable from this surface.
- Missing Taobao Open Platform credentials do not block current T08 because the current MVP scope uses crawler mode, not API mode.

## Stop Condition

T08 result JSON, T08 handoff, and focused logs are written. JSON parse validation passed. This worker must exit and must not continue into T09 or any other task.
