# Repair Log

## T02 - Real Feishu Bitable Storage

Status: `BLOCKED_BY_ENVIRONMENT`

Local verification passed with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T02` (`9 passed in 0.29s`).

No code repair was applied because the blocking condition is missing live Feishu credentials/table ids and missing Feishu SDK/API access in the runtime. The next repair worker should rerun T02 only after those external inputs are available.

## T03 - Order Collectors API Crawler

Status: `BLOCKED_BY_ENVIRONMENT`

Code repair was applied for the local T03 implementation:

- Added Qianniu PC CDP text capture with scroll-to-stable support.
- Replaced the order crawler stub with parser-backed Chinese `orders_raw` rows and paid-order aggregation.
- Added regression tests for parser completeness, missing Qianniu session failures without zero metrics, and scheduler writes.

Local verification passed with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T03 tests\test_taobao_order_crawler.py tests\test_storage_and_scheduler.py tests\test_metric_service.py` (`12 passed in 0.30s`).

Remaining blocker is environmental: no usable real Qianniu PC CDP session and no real Feishu credentials/table ids in this runtime. The next repair worker should rerun T03 only after those external inputs are available.

## T04 - Promotion Crawler Qianniu Safety

Status: `BLOCKED_BY_ENVIRONMENT`

Artifact repair was applied for T04:

- Rewrote `docs/auto-execute/results/T04.json` as valid JSON with fresh T04-only evidence.
- Rewrote `docs/auto-execute/latest/T04-HANDOFF.md` with the current blocker classification.
- Refreshed `docs/auto-execute/logs/T04/verification.txt`.

Local verification passed with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T04 tests\test_taobao_promotion_crawler.py tests\test_storage_and_scheduler.py tests\test_metric_service.py` (`13 passed in 0.26s`).

Additional Unicode probe confirmed normal Chinese login/permission detection and normal Chinese `花费` parser cases. Remaining blocker is environmental: no usable real Qianniu PC CDP session and no real Feishu credentials/table ids in this runtime. Missing Taobao Open Platform API credentials are not a blocker for the current crawler scope.
## T05 Relay Worker - 2026-06-02

- Status: `BLOCKED_BY_ENVIRONMENT`
- Added regression coverage in `tests/test_metric_scheduler_delta.py` for the scheduler second-run path that computes a normal 10-minute delta from the previous monitor snapshot.
- Verified local T05 behavior with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T05 tests\test_metric_service.py tests\test_storage_and_scheduler.py tests\test_metric_scheduler_delta.py`: `10 passed in 0.15s`.
- Recorded environment blocker: missing real Feishu credentials/table ids and unavailable Qianniu PC CDP session at `http://127.0.0.1:9222`.

## T07 Relay Worker - 2026-06-03

- Status: `BLOCKED_BY_ENVIRONMENT`
- Updated `shopops/scheduler.py` so pending replay is counted in full-collect saved rows and replay exceptions are recorded as `pending_replay_failed` without aborting the new collection.
- Added regression coverage in `tests/test_storage_and_scheduler.py` for scheduler-level pending replay before collection, `unique_key` duplicate prevention, and replay failure isolation.
- Verified focused T07 behavior with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T07 tests\test_storage_and_scheduler.py tests\test_metric_scheduler_delta.py tests\test_metric_service.py`: `12 passed in 0.34s`.
- Verified full local suite with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T07-full`: `22 passed in 0.51s`.
- Recorded environment blocker: missing real Feishu credentials/table ids and unavailable Qianniu PC CDP session at `http://127.0.0.1:9222`. Missing Taobao Open Platform API credentials do not block the current crawler scope.

## T08 Relay Worker - 2026-06-03

- Status: `BLOCKED_BY_ENVIRONMENT`
- Repaired `scripts/acceptance/verify_feishu_data.py` so local Feishu double evidence cannot produce pure `PASS` for the real external-data gate.
- Aligned the local proof with the current MVP boundary by using the crawler order collector instead of the Taobao API collector.
- Added a secret-safe environment probe for Feishu credential/table-id presence and Qianniu CDP availability.
- Verified focused T08 behavior with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T08 tests\test_storage_and_scheduler.py tests\test_metric_scheduler_delta.py tests\test_taobao_order_crawler.py tests\test_taobao_promotion_crawler.py`: `15 passed in 0.39s`.
- Recorded environment blocker: missing real Feishu credentials/table ids and Qianniu CDP probe returning HTTP 502. Missing Taobao Open Platform API credentials do not block the current crawler scope.

## T05 API Boundary Refresh - 2026-06-03

- Status: `PASS_WITH_LIMITATION`
- Replaced stale T05 metric-task result with a fresh `shopops-goal-2026-06-03` API-boundary result for `REQ-003`.
- Added a page-aware injectable API fetch boundary in `shopops/collectors/taobao_order_api.py`.
- Added `tests/test_taobao_order_api_boundary.py` for `ORDER_SOURCE=api`, crawler default nonblocking credentials, missing-credential fail-closed behavior, pagination, paid-order filtering, normalized `orders_raw` shape, upstream exception handling, and no-zero API failures.
- Verified focused T05 behavior with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T05-api tests\test_taobao_order_api_boundary.py tests\test_storage_and_scheduler.py`: `13 passed in 0.27s`.
- Verified full local suite with `python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\T05-full`: `31 passed in 1.22s`.
- Classified `scripts/acceptance/secret_guard.py` exit code `1` as a pre-existing false positive because it flags prior T01 log lines containing literal `=missing` diagnostic values, not T05 secrets.
