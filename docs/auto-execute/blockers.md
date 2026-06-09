# Auto-Execute Blockers

## T03 - Feishu Bitable Storage Real And Local Proof

Status: `BLOCKED_BY_ENVIRONMENT`

Fresh task pack: `shopops-goal-2026-06-03`

Local storage proof passed for `DATA-001..DATA-009`: Chinese-field payloads/readback, `unique_key` upsert without duplicate rows, pending cache write, and replay clearing are recorded under `docs/auto-execute/external-data/T03/`.

Live Feishu Bitable write/upsert/readback remains blocked because the runtime does not provide:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_APP_TOKEN`
- required `FEISHU_TABLE_*` real table IDs
- installed `lark_oapi` SDK module

No live Feishu PASS is claimed by T03.

## T02 - Real Feishu Bitable Storage

Status: `BLOCKED_BY_ENVIRONMENT`

Live Feishu Bitable write/readback is blocked because the runtime does not provide:

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_APP_TOKEN`
- required `FEISHU_TABLE_*` table ids
- installed `lark_oapi` SDK module

Local storage tests passed, but local double evidence cannot upgrade T02 to real Feishu `PASS`.

## T03 - Order Collectors API Crawler

Status: `BLOCKED_BY_ENVIRONMENT`

Local T03 implementation and tests passed, but live crawler acceptance is blocked because the runtime does not provide:

- a usable Qianniu PC CDP session at `http://127.0.0.1:9222` (`无法连接到远程服务器`);
- real Feishu credentials and table ids for `orders_raw` and `monitor_snapshot` write/readback.

Missing Taobao Open Platform API credentials are not a blocker for the current `ORDER_SOURCE=crawler` scope.

## T08 - Real Feishu Data Correctness Verification

Status: `BLOCKED_BY_ENVIRONMENT`

Local T08 data correctness checks passed, but live external-data acceptance is blocked because the runtime does not provide:

- real Feishu credentials and table ids for `orders_raw`, `promotion_snapshot`, `monitor_snapshot`, `metrics_10min`, and `task_run_log` write/upsert/readback;
- a usable Qianniu PC CDP session at `http://127.0.0.1:9222` (`CDP HTTP 状态异常：502`).

Missing Taobao Open Platform API credentials are not a blocker for the current `ORDER_SOURCE=crawler` scope.
## T04 - Promotion Crawler Qianniu Safety

Status: `BLOCKED_BY_ENVIRONMENT`

Local T04 implementation and tests passed, but live crawler acceptance is blocked because the runtime does not provide:

- a usable Qianniu PC CDP session at `http://127.0.0.1:9222` (`无法连接到远程服务器`);
- real Feishu credentials and table ids for `promotion_snapshot` and `monitor_snapshot` write/readback.

Missing Taobao Open Platform API credentials are not a blocker for the current crawler promotion-center scope.

### T04 repair worker refresh

Status remains `BLOCKED_BY_ENVIRONMENT`.

Fresh probe evidence:

- `http://127.0.0.1:9222/json/version` failed with `无法连接到远程服务器`.
- `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_APP_TOKEN`, `FEISHU_TABLE_PROMOTION_SNAPSHOT`, and `FEISHU_TABLE_MONITOR_SNAPSHOT` were missing.
- `TAOBAO_APP_KEY`, `TAOBAO_APP_SECRET`, and `TAOBAO_SESSION_KEY` were missing but do not block the current crawler-only promotion-center scope.

## T05 - Metric Snapshot Delta Engine

Status: `BLOCKED_BY_ENVIRONMENT`

Local T05 implementation and tests passed, but live metric acceptance is blocked because the runtime does not provide:

- a usable Qianniu PC CDP session at `http://127.0.0.1:9222` (`无法连接到远程服务器`);
- real Feishu credentials and table ids for `monitor_snapshot` and `metrics_10min` write/readback.

Missing Taobao Open Platform API credentials are not a blocker for the current crawler scope.

## T07 - Scheduler Full Collect Pending Replay

Status: `BLOCKED_BY_ENVIRONMENT`

Local T07 implementation and tests passed, but live scheduler acceptance is blocked because the runtime does not provide:

- a usable Qianniu PC CDP session at `http://127.0.0.1:9222` (`无法连接到远程服务器`);
- real Feishu credentials and table ids for `orders_raw`, `promotion_snapshot`, `monitor_snapshot`, `metrics_10min`, and `task_run_log` write/upsert/readback.

Missing Taobao Open Platform API credentials are not a blocker for the current `ORDER_SOURCE=crawler` scope.

## T04 - Qianniu Order Center Live Crawler

Status: `BLOCKED_BY_ENVIRONMENT`

Fresh task pack: `shopops-goal-2026-06-03`

Local T04 evidence passed for `REQ-001`, `REQ-002`, and `REQ-010`: the crawler parser normalized order rows, preserved scroll/pagination evidence shape, wrote local `orders_raw`, wrote local `monitor_snapshot`, wrote a task log, and kept failed collection metrics as `null` instead of numeric `0`.

Evidence:

- `docs/auto-execute/external-data/T04/order-crawler-local-proof.json`
- `docs/auto-execute/logs/T04/pytest-order-crawler.txt`
- `docs/auto-execute/logs/T04/pytest-full.txt`
- `docs/auto-execute/logs/T04/qianniu-cdp-probe.json`

Live Qianniu order-center proof remains blocked because `http://127.0.0.1:9222/json/version` returned HTTP 502. No live Qianniu PASS is claimed by T04.
