# ShopOps Goal Requirement Traceability Matrix

Generated: 2026-06-03

Task pack: `shopops-goal-2026-06-03`

Task: `T02-requirements-traceability-refresh`

## Verdict

`PASS_WITH_LIMITATION`

The matrix now covers every in-scope requirement `REQ-001` through `REQ-014` and maps each requirement to the owning implementation task, verification task, durable evidence path, and known blocker or limitation. This is not a pure `PASS` because several P0 requirements still depend on live Feishu Bitable credentials/table IDs or a live Qianniu PC CDP session, which are environment-bound and must remain fail-closed in later tasks.

## Source And Freshness Rules

| Source | Path | Use |
| --- | --- | --- |
| Repository rules | `AGENTS.md` | Execution, scope, stale-result, and verification rules |
| PRD | `docs/taobao_mvp_requirements.md` | Source requirement semantics |
| Development doc | `docs/taobao_mvp_development.md` | Intended architecture and implementation contracts |
| Delivery index | `docs/auto-execute/shopops-goal-delivery-standard-index.md` | Task-pack entry and task_pack_id |
| Current audit | `docs/auto-execute/shopops-goal-implementation-audit.md` | Fresh T01 implementation status for `shopops-goal-2026-06-03` |
| External data matrix | `docs/auto-execute/shopops-goal-external-data-validation-matrix.md` | Feishu table, field, upsert, pending replay, and readback expectations |
| Upstream handoffs | `docs/auto-execute/latest/T00-HANDOFF.md`, `docs/auto-execute/latest/T01-HANDOFF.md` | Fresh upstream status and blockers |

Prior `docs/auto-execute/results/T02.json` was treated as stale because it did not contain `task_pack_id: "shopops-goal-2026-06-03"` and described an older real-Feishu-storage task instead of this requirements-traceability refresh.

## Requirement Matrix

| Req ID | Priority | Requirement Summary | Current Status | Implement Task | Verify Task | Evidence Path | Blocker / Limitation | Trace Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | P0 | Default `ORDER_SOURCE=crawler`; order collection must use Qianniu PC order center, not ordinary browser or Taobao web entry. | Local implementation present; live proof missing | T04 | T11, T13 | `shopops/collectors/__init__.py`; `shopops/collectors/taobao_order_crawler.py`; `tests/test_taobao_order_crawler.py`; `docs/auto-execute/logs/T01/verification.txt` | `BLOCKED_BY_ENVIRONMENT`: no live Qianniu PC CDP session evidence in this task boundary | MAPPED |
| REQ-002 | P0 | Order center collection must cover all visible/current-scope orders through pagination or scrolling and persist raw order detail when available. | Local parser and local storage path present; live full-page proof missing | T04 | T11, T13 | `shopops/collectors/taobao_order_crawler.py`; `shopops/storage/local_feishu.py`; `tests/test_taobao_order_crawler.py`; `tests/test_storage_and_scheduler.py` | `BLOCKED_BY_ENVIRONMENT`: no real Qianniu order-center pagination/scroll evidence and no real Feishu `orders_raw` readback | MAPPED |
| REQ-003 | P1 | Preserve `ORDER_SOURCE=api` and Taobao Open Platform future-switch boundary without requiring real Taobao API credentials for the crawler-first MVP. | API boundary present; future-stage only | T05 | T11, T13 | `shopops/collectors/taobao_order_api.py`; `shopops/config.py`; `tests/test_storage_and_scheduler.py` | `DEFERRED`: Taobao API credentials absent but not a current MVP blocker while crawler remains default | MAPPED |
| REQ-004 | P0 | Promotion spend must be read only from Qianniu PC promotion center cost, with no ad modification or channel-management side effects. | Local parser and safety boundary present; live proof missing | T06 | T11, T13 | `shopops/collectors/taobao_promotion_crawler.py`; `tests/test_taobao_promotion_crawler.py`; `docs/auto-execute/logs/T01/verification.txt` | `BLOCKED_BY_ENVIRONMENT`: no live Qianniu promotion-center page evidence | MAPPED |
| REQ-005 | P0 | Compute today cumulative order count, paid amount, promotion cost, real-time ROI, and customer acquisition cost. | Local implementation present | T07 | T11, T13 | `shopops/services/metric_service.py`; `tests/test_metric_service.py`; `tests/test_storage_and_scheduler.py`; `docs/auto-execute/logs/T01/verification.txt` | Needs final full-suite evidence and real upstream data proof for pure acceptance | MAPPED |
| REQ-006 | P0 | Compute latest 10-minute deltas and handle missing previous snapshot, rollback, timeout, and invalid windows. | Local implementation present | T07 | T11, T13 | `shopops/services/metric_service.py`; `tests/test_metric_scheduler_delta.py`; `docs/auto-execute/logs/T01/verification.txt` | Needs final full-suite evidence for pure acceptance | MAPPED |
| REQ-007 | P0 | Feishu Bitable must use Chinese-visible table and field mapping for config, snapshots, raw orders, promotion, metrics, task logs, alerts, and daily reports. | Local field mapping and local storage present; live Feishu proof missing | T03 | T11, T13 | `shopops/config.py`; `shopops/storage/field_mapping.py`; `shopops/storage/local_feishu.py`; `docs/auto-execute/shopops-goal-external-data-validation-matrix.md` | `BLOCKED_BY_ENVIRONMENT`: no real Feishu Bitable SDK write/update/readback evidence | MAPPED |
| REQ-008 | P0 | Storage writes must be idempotent by `unique_key`; repeated runs must update instead of duplicating snapshots/logs. | Local upsert present | T03 | T11, T13 | `shopops/storage/local_feishu.py`; `tests/test_storage_and_scheduler.py`; `docs/auto-execute/shopops-goal-external-data-validation-matrix.md` | `BLOCKED_BY_ENVIRONMENT` for real Feishu upsert/readback; local double evidence is available only as local proof | MAPPED |
| REQ-009 | P0 | Feishu write failures must be stored in a local pending cache and replayed before the next run. | Local pending replay present | T03 | T11, T13 | `shopops/storage/local_feishu.py`; `shopops/scheduler.py`; `tests/test_storage_and_scheduler.py`; `docs/auto-execute/shopops-goal-external-data-validation-matrix.md` | Needs real Feishu failure/replay proof for pure acceptance | MAPPED |
| REQ-010 | P0 | Collection failure must not be converted to numeric `0`; it must carry failure status, error code, and error message. | Local implementation present | T08 | T11, T13 | `shopops/services/metric_service.py`; `shopops/collectors/taobao_promotion_crawler.py`; `tests/test_metric_service.py`; `tests/test_storage_and_scheduler.py` | Needs final full-suite evidence and live-source failure proof for pure acceptance | MAPPED |
| REQ-011 | P0 | Every run must write `task_run_log`; subtask failures must remain isolated while the main flow records total status. | Local implementation present | T09 | T11, T13 | `shopops/models.py`; `shopops/scheduler.py`; `shopops/storage/field_mapping.py`; `tests/test_alerts_task_log_daily_report.py` | Needs final full-suite evidence and real storage proof for pure acceptance | MAPPED |
| REQ-012 | P0 | Business/system alerts must trigger, deduplicate for 30 minutes, write `alert_log`, and record Feishu webhook send result. | Local alert/dedup/logging present; live webhook proof missing | T09 | T11, T13 | `shopops/services/alert_service.py`; `tests/test_alerts_task_log_daily_report.py`; `docs/auto-execute/logs/T01/verification.txt` | `BLOCKED_BY_ENVIRONMENT`: no live Feishu webhook send evidence | MAPPED |
| REQ-013 | P1 | Daily report must generate at fixed configured time, send through Feishu, and upsert `daily_report`. | Local report generation present; live delivery proof missing | T10 | T11, T13 | `shopops/services/daily_report_service.py`; `shopops/scheduler.py`; `tests/test_alerts_task_log_daily_report.py` | Live webhook/report delivery remains environment-dependent | MAPPED |
| REQ-014 | P0 | Safety boundary: do not bypass login/captcha/permission checks, do not store master-account password or buyer PII, and do not perform ad mutation. | Local safety posture present; final guard pending | T12 | T13 | `shopops/services/browser_service.py`; collector failure handling; `scripts/acceptance/secret_guard.py`; `docs/auto-execute/shopops-goal-final-acceptance-gate.md` | Needs T12 report-integrity, secret-guard, and code-review evidence for final acceptance | MAPPED |

## External Data Mapping Summary

| Coverage Area | Requirement IDs | Data IDs | Required evidence route |
| --- | --- | --- |
| Feishu field coverage | REQ-007 | DATA-001..DATA-009 | T03 must prove local mapping/upsert behavior and classify real Feishu proof as environment-blocked when credentials/table IDs are absent. |
| Upsert idempotency | REQ-008 | DATA-003, DATA-005, DATA-006, DATA-007, DATA-008, DATA-009 | T03/T11 must prove `unique_key` upsert/readback or fail closed for real Feishu. |
| Pending replay | REQ-009 | DATA-003..DATA-009 | T03/T11 must prove pending cache and replay locally, then preserve live Feishu replay as environment-blocked when unavailable. |
| No-zero failure | REQ-010 | DATA-003, DATA-005, DATA-006, DATA-007 | T08/T11 must prove failure status/null metrics instead of `0`. |
| Task run log | REQ-011 | DATA-007 | T09/T11 must prove task log status isolation. |
| Alert log | REQ-012 | DATA-008 | T09/T11 must prove alert log and webhook-result handling or classify live webhook proof as environment-blocked. |
| Daily report | REQ-013 | DATA-009 | T10/T11 must prove daily report upsert and delivery handling or classify live webhook proof as environment-blocked. |

## Coverage Check

All required IDs are present exactly once in the matrix:

`REQ-001`, `REQ-002`, `REQ-003`, `REQ-004`, `REQ-005`, `REQ-006`, `REQ-007`, `REQ-008`, `REQ-009`, `REQ-010`, `REQ-011`, `REQ-012`, `REQ-013`, `REQ-014`.

Durable machine-readable coverage evidence is written to `docs/auto-execute/external-data/T02/traceability-coverage.json`.
