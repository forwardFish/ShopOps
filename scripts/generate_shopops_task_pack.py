from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "auto-execute"
TASKS = OUT / "shopops-tasks"
SLUG = "shopops"
PROJECT = "ShopOps Taobao Monitor MVP"


TABLES = [
    ("DATA-SYSTEM", "system_config", "系统配置表", "FEISHU_TABLE_SYSTEM_CONFIG", "配置键/配置值/是否启用/备注/更新时间"),
    ("DATA-SHOP", "shop_config", "店铺配置表", "FEISHU_TABLE_SHOP_CONFIG", "店铺ID/店铺名称/平台/数据来源/状态"),
    ("DATA-MONITOR", "monitor_snapshot", "实时监控快照表", "FEISHU_TABLE_MONITOR_SNAPSHOT", "今日订单数/今日成交额/总推广消耗/实时ROI/获客成本/数据状态"),
    ("DATA-ORDERS", "orders_raw", "订单明细原始表", "FEISHU_TABLE_ORDERS_RAW", "订单号/下单时间/支付时间/订单状态/支付金额/商品名称"),
    ("DATA-PROMO", "promotion_snapshot", "推广数据快照表", "FEISHU_TABLE_PROMOTION_SNAPSHOT", "推广渠道=推广中心/今日累计消耗(元)/状态/错误信息"),
    ("DATA-METRICS", "metrics_10min", "十分钟指标表", "FEISHU_TABLE_METRICS_10MIN", "时间开始/时间结束/新增订单数/新增成交额/推广消耗/周期ROI"),
    ("DATA-TASKLOG", "task_run_log", "任务运行日志表", "FEISHU_TABLE_TASK_LOG", "任务类型/开始时间/结束时间/总状态/拉取数量/写入数量"),
    ("DATA-ALERT", "alert_log", "告警日志表", "FEISHU_TABLE_ALERT_LOG", "告警类型/告警内容/触发时间/是否已发送/发送结果"),
    ("DATA-DAILY", "daily_report", "每日报告表", "FEISHU_TABLE_DAILY_REPORT", "报告日期/订单数/成交额/推广消耗/ROI/摘要"),
]


TASK_DEFS = [
    ("T00", "omx-auto-execute-orchestrator", "orchestration", "all pack docs", "results/latest/blockers/repair queue"),
    ("T01", "python-scaffold-config-models", "implementation", "REQ-ENV, REQ-CONFIG, REQ-MODELS", "config/models/env"),
    ("T02", "real-feishu-bitable-storage", "implementation", "REQ-FEISHU, DATA-*", "真实飞书多维表格写入、中文表名字段映射、本地失败补写"),
    ("T03", "order-collectors-api-crawler", "implementation", "REQ-ORDER-CRAWLER, REQ-ORDER-API-FUTURE", "当前版本千牛 PC 订单中心页面采集；淘宝 API 仅后续预留"),
    ("T04", "promotion-crawler-qianniu-safety", "implementation", "REQ-PROMOTION, REQ-QIANNIU-SAFETY", "当前版本千牛 PC 推广中心页面采集，只读取花费"),
    ("T05", "metric-snapshot-delta-engine", "implementation", "REQ-METRIC, REQ-NO-ZERO", "monitor snapshot and 10 minute delta"),
    ("T06", "alerts-task-log-daily-report", "implementation", "REQ-ALERT, REQ-DAILY, REQ-LOG", "alert dedupe, task log, daily report"),
    ("T07", "scheduler-full-collect-pending-replay", "implementation", "REQ-SCHEDULER, REQ-PENDING", "one full run, pending cache replay"),
    ("T08", "real-feishu-data-correctness-verification", "verification", "DATA-*", "真实飞书中文表名字段、写入、更新、重复运行、读回校验"),
    ("T09", "local-test-suite-and-secret-guard", "verification", "all P0 requirements", "pytest, secret guard, report integrity"),
    ("T10", "operator-runbook-env-docs", "documentation", "REQ-RUNBOOK", "README, env example, Windows guidance"),
    ("T11", "final-acceptance-gate", "verification", "all P0 evidence", "final verdict from durable evidence"),
]


def write(rel: str, body: str) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def task_doc(task_id: str, name: str, surface: str, reqs: str, output: str) -> str:
    prev = "none" if task_id == "T00" else "previous task result JSON and HANDOFF"
    return f"""
# Task {task_id} - {name}

## Codex Exec
```powershell
Set-Location -LiteralPath "{ROOT}"
codex exec "Use the auto-execute skill. Execute only {ROOT}\\docs\\auto-execute\\shopops-tasks\\{task_id}-{name}.md. Treat this as one fresh task boundary. Do not stop after planning. Implement, test, repair, write result JSON, write HANDOFF, and exit this codex exec. If blocked, classify the blocker in durable files and route to repair or final gate; do not end with only chat text. Do not claim PASS without evidence."
```

## Implementation Scope
- Primary surface: {surface}
- Requirement IDs: {reqs}
- Expected output: {output}
- Project focus: Taobao single-platform MVP with real Feishu Bitable and real Qianniu PC page collection as the current production path. Taobao Open Platform API is reserved for a later `ORDER_SOURCE=api` phase and is not required for the current crawler version.
- Current version scope is exactly two Qianniu PC pages: order center for all order-related data, and promotion center for the single "花费" metric.

## Required Inputs
- `AGENTS.md`
- `docs/taobao_mvp_requirements.md`
- `docs/taobao_mvp_development.md`
- `docs/auto-execute/shopops-development-standard.md`
- `docs/auto-execute/shopops-software-test-standard.md`
- `docs/auto-execute/shopops-requirement-traceability-matrix.md`
- `docs/auto-execute/shopops-api-db-contract-matrix.md`
- `docs/auto-execute/shopops-external-data-validation-matrix.md`

## Allowed Files
- `shopops/**`
- `tests/**`
- `scripts/**`
- `docs/auto-execute/**`
- `.env.example`, `requirements.txt`, `README.md`

## Forbidden Actions
- Real Feishu Bitable and real Qianniu PC are in current scope. Use only environment-provided credentials/tokens and authorized local sessions; never hard-code or log secrets.
- Do not call the real Taobao Open Platform order API in the current version; only keep configuration and interface boundaries for the later API phase.
- Do not add a third collection page beyond order center and promotion center.
- Promotion center collection must read only "花费"; do not collect channel split data or modify any ad campaign.
- Do not bypass captcha, login, permission, or platform safety mechanisms.
- Do not store Taobao main-account passwords or buyer PII.
- Do not write failed collector metrics as numeric `0`.
- Do not end with only a chat update; write durable evidence.

## Development Standard References
- `shopops-development-standard.md`: source-of-truth, external data, failure handling, evidence rules.

## Software Test Standard References
- `shopops-software-test-standard.md`: 真实飞书写入读回、中文字段映射、重复运行幂等、pending replay、final gate。

## Acceptance Criteria
- Implements or verifies every requirement listed above.
- Produces required evidence paths.
- Uses the real external path when credentials/session are available; reports `BLOCKED_BY_ENVIRONMENT` instead of pretending success when they are unavailable.
- Writes result JSON and HANDOFF even when blocked.

## Detailed Acceptance Criteria
| Area | Criteria | Evidence |
| --- | --- | --- |
| Requirement | `{reqs}` is implemented or verified | `docs/auto-execute/results/{task_id}.json` |
| Feishu/Data | field mapping/upsert/readback rules are honored where relevant | `docs/auto-execute/external-data/{task_id}/` |
| Safety | no secret leakage, no bypass, no failure-as-zero | tests and logs |
| Tests | task-local tests pass or blocker is classified | `docs/auto-execute/logs/{task_id}/` |

## Required Future Tests And Evidence
| Evidence Type | Command/Future Action | Required Path |
| --- | --- | --- |
| task result | write machine-readable status | `docs/auto-execute/results/{task_id}.json` |
| handoff | summarize state and next step | `docs/auto-execute/latest/{task_id}-HANDOFF.md` |
| logs | capture commands and results | `docs/auto-execute/logs/{task_id}/` |

## Dependency And Resume Gate
| Dependency | Required Durable Evidence | Resume/Skip/Rerun Rule |
| --- | --- | --- |
| {prev} | result JSON + HANDOFF if applicable | skip only when both exist and status is acceptable |

## Stop Prevention Rules
- Do not stop after planning.
- Implement, test, repair, write result JSON, write HANDOFF, and exit.
- If blocked, classify the blocker and route to repair/final gate.

## Failure To Repair Routing
| Failure Status | Required Durable Output | Next Routing |
| --- | --- | --- |
| REPAIR_REQUIRED | result JSON + repair item | append repair queue |
| HARD_FAIL | result JSON + blocker evidence | smallest repair task or final gate |
| BLOCKED_BY_ENVIRONMENT | environment blocker | retry or limitation |
| BLOCKED_BY_MISSING_SOURCE | missing source blocker | fail closed; do not invent |

## Output Files
- {output}

## Result JSON
`docs/auto-execute/results/{task_id}.json`

## HANDOFF
`docs/auto-execute/latest/{task_id}-HANDOFF.md`

## Failure Statuses
| Status | When To Use |
| --- | --- |
| REPAIR_REQUIRED | product/test gap found |
| BLOCKED_BY_ENVIRONMENT | local runtime or external app unavailable |
| BLOCKED_BY_MISSING_SOURCE | required PRD/source unavailable |
| BLOCKED_BY_ENVIRONMENT | missing real Feishu table access, Qianniu PC/CDP session, or required local runtime; missing Taobao API credentials does not block the current crawler version |
| HARD_FAIL | P0 behavior fails and cannot be repaired in task |
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    TASKS.mkdir(parents=True, exist_ok=True)

    doc_map = "\n".join(
        f"| `{SLUG}-{name}` | {purpose} | yes |"
        for name, purpose in [
            ("delivery-standard-index.md", "entrypoint and evidence map"),
            ("auto-execute-master-plan.md", "task sequence and anti-stop orchestration"),
            ("development-standard.md", "engineering and safety rules"),
            ("software-test-standard.md", "local proof and final gate rules"),
            ("requirement-traceability-matrix.md", "P0/P1 requirement coverage"),
            ("api-db-contract-matrix.md", "API/storage method contracts"),
            ("external-data-validation-matrix.md", "Feishu table field mapping and readback"),
            ("standard-test-plan.md", "row-level tests and evidence"),
            ("owner-scenario-matrix.md", "operator journey and data checks"),
            ("final-acceptance-gate.md", "fail-closed final verdict"),
            ("task-pack-quality-audit.md", "generator-side quality audit"),
        ]
    )

    write("shopops-delivery-standard-index.md", f"""
# {PROJECT} Delivery Standard Index

## Scope
- Project root: `{ROOT}`
- Project slug: `{SLUG}`
- Generated by: xwstarmap-auto-execute
- Generation date: 2026-06-02
- Execution boundary: documentation-only task pack; product code execution evidence is separate.

## Source Of Truth
| Priority | Source | Path/Location | Notes | Status |
| --- | --- | --- | --- | --- |
| 1 | User prompt | current conversation | generate all tasks, complete in one run, Feishu data correctness is primary | CONFIRMED |
| 2 | AGENTS.md | `AGENTS.md` | OMX autonomy, evidence, Lore commit rules | CONFIRMED |
| 3 | PRD | `docs/taobao_mvp_requirements.md` | Taobao MVP requirements | CONFIRMED |
| 4 | Development doc | `docs/taobao_mvp_development.md` | Python architecture and pseudo-code | CONFIRMED |
| 5 | Existing code | repo root | no product code yet | CONFIRMED |

## Generated Documents
| Document | Purpose | Required Before PASS |
| --- | --- | --- |
{doc_map}

## Evidence Locations
| Evidence Type | Required Path Pattern |
| --- | --- |
| Task result JSON | `docs/auto-execute/results/<TASK-ID>.json` |
| HANDOFF | `docs/auto-execute/latest/<TASK-ID>-HANDOFF.md` |
| Logs | `docs/auto-execute/logs/<TASK-ID>/` |
| External data readbacks | `docs/auto-execute/external-data/<TASK-ID>/` |
| Final report | `docs/auto-execute/verification-results.md` |

## Anti-Stop Rule
T00 must launch one fresh worker per task, verify result JSON/HANDOFF/logs, route failures to repair, and never treat chat text or dry-run output as completion evidence.
""")

    write("shopops-development-standard.md", """
# ShopOps Development Standard

## Non-Negotiable Rules
- Preserve PRD and development docs as source of truth.
- Implement Taobao single-platform MVP only.
- Use `Storage` abstraction; business code must not depend directly on Feishu SDK internals.
- Current production acceptance requires real Feishu Bitable and real Qianniu PC page collection. Taobao Open Platform API is a later-phase interface reservation and must not block this crawler version.
- Current version collects exactly two Qianniu PC pages: order center for order details and promotion center for the single "花费" metric.
- Failed collectors must return `success=false`/failure status and null metrics, never numeric `0`.
- Every run writes `task_run_log`; every alert trigger writes `alert_log`.

## External Data Standard
- Feishu Bitable table data is the primary acceptance surface.
- Every table has exact field mapping, unique key, upsert/idempotency rule, failure-cache rule, and readback proof.
- Required Feishu table display names: `系统配置表`, `店铺配置表`, `实时监控快照表`, `订单明细原始表`, `推广数据快照表`, `十分钟指标表`, `任务运行日志表`, `告警日志表`, `每日报告表`.
- Local Feishu fake must capture create/update/list calls and support independent readback.
- Missing real Feishu credentials must not block local acceptance; it becomes real-write limitation only.

## Safety
- Do not bypass captcha, login, account permission, or platform safety.
- Do not store Taobao main-account password or buyer PII.
- Do not perform any ad campaign write operation.
""")

    write("shopops-software-test-standard.md", """
# ShopOps Software Test Standard

## Local Run Standard
| Surface | Command | Expected Ready Signal | Evidence |
| --- | --- | --- | --- |
| Unit/integration | `python -m pytest -q` | all tests pass | pytest output |
| Feishu data proof | `python scripts/acceptance/verify_feishu_data.py` | JSON verdict not FAIL | `docs/auto-execute/external-data/T08/feishu-data-proof.json` |
| Secret guard | `python scripts/acceptance/secret_guard.py` | no secret leakage | `docs/auto-execute/logs/T09/secret-guard.txt` |

## Feishu Bitable Test Standard
Every P0 table must prove: exact Chinese field names, internal field mapping, write payload, upsert by `unique_key`, duplicate-run idempotency, failed-write pending cache, replay, independent readback, and no failure-as-zero pollution.

## Final PASS Rule
Pure PASS is forbidden unless requirements, collectors, metrics, alerts, scheduler, Feishu mappings, upsert/readback, duplicate-run, pending replay, tests, and secret guard all have durable evidence.
""")

    reqs = [
        ("REQ-SCHEDULER", "P0", "run every 10 minutes / run_once support", "T07", "T11"),
        ("REQ-ORDER-CRAWLER", "P0", "Qianniu PC order center collection for all order-related data with pagination/scroll loading", "T03", "T09"),
        ("REQ-ORDER-API-FUTURE", "P1", "Taobao Open Platform API boundary reserved for later ORDER_SOURCE=api phase; credentials not required now", "T03", "T09"),
        ("REQ-PROMOTION", "P0", "Qianniu PC promotion center collection for the single 花费 metric only", "T04", "T09"),
        ("REQ-METRIC", "P0", "today totals, ROI, CAC, 10-minute delta", "T05", "T08"),
        ("REQ-NO-ZERO", "P0", "collection failure must not write zero metrics", "T05", "T08"),
        ("REQ-FEISHU", "P0", "write MVP data to Feishu Bitable via Storage abstraction", "T02", "T08"),
        ("REQ-PENDING", "P0", "failed Feishu writes go to local pending cache and replay", "T07", "T08"),
        ("REQ-ALERT", "P0", "alert rules, dedupe, alert_log, robot send result", "T06", "T09"),
        ("REQ-DAILY", "P1", "daily report generation", "T06", "T09"),
    ]
    write("shopops-requirement-traceability-matrix.md", "# ShopOps Requirement Traceability Matrix\n\n| Req ID | Priority | Requirement | DB/Data Entity | Implement Task | Verify Task | Evidence | Status |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(
        f"| {rid} | {pri} | {desc} | Feishu/local storage | {impl} | {ver} | `docs/auto-execute/results/{ver}.json` | PLANNED |"
        for rid, pri, desc, impl, ver in reqs
    ))

    api_rows = [
        ("API-STORAGE-UPSERT", "success", "Storage.upsert(table, fields)", "writes or updates by unique_key", "local readback"),
        ("API-STORAGE-UPSERT", "duplicate", "Storage.upsert(table, fields)", "second same unique_key updates not duplicates", "record count stable"),
        ("API-STORAGE-PENDING", "failure", "Storage.upsert(table, fields)", "write failure appends pending jsonl", "pending readback"),
        ("API-ORDER-COLLECT", "success/failure", "OrderCollector.fetch_today()", "unified result shape", "no failure-as-zero"),
        ("API-PROMO-COLLECT", "success/failure", "PromotionCollector.fetch_today()", "reads only promotion center 花费; failure returns null metrics", "no failure-as-zero"),
        ("API-SCHED-RUN", "success/partial/failure", "Scheduler.run_once()", "all tables/logs updated", "task_run_log"),
    ]
    write("shopops-api-db-contract-matrix.md", "# ShopOps API/DB Contract Matrix\n\n| API ID | Case Type | Method/Function | Expected Result | DB/Readback | Future Evidence | Status |\n| --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(
        f"| {a} | {c} | `{m}` | {e} | {r} | `docs/auto-execute/external-data/T08/` | PLANNED |"
        for a, c, m, e, r in api_rows
    ))

    field_rows = []
    for data_id, table, table_name, env, fields in TABLES:
        field_rows.append(f"| {data_id} | {table_name} | {table} | {env} | {fields} | 中文字段精确映射 | unique_key when applicable | 真实飞书读回；凭据缺失时写 BLOCKED_BY_ENVIRONMENT | PLANNED |")
    write("shopops-external-data-validation-matrix.md", "# ShopOps External Data Validation Matrix\n\n## Target Tables\n| Data Target ID | 中文表名 | Internal Key | Env/Config Key | Required Fields | Validation Rule | Unique Key / Idempotency | Readback Evidence | Status |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(field_rows) + "\n\n## Mandatory Cases\n| Case ID | Table Scope | Operation | Expected Evidence | Required For PASS | Status |\n| --- | --- | --- | --- | --- | --- |\n| EXT-01 | all P0 tables | write valid payload | outbound payload + real Feishu readback JSON | yes | PLANNED |\n| EXT-02 | snapshot/log tables | duplicate run/upsert | same unique_key updates record count stable | yes | PLANNED |\n| EXT-03 | metrics tables | failed collector result | null metrics plus failure status, never zero | yes | PLANNED |\n| EXT-04 | all writes | write failure | pending cache JSONL | yes | PLANNED |\n| EXT-05 | pending cache | replay | pending removed after success | yes | PLANNED |")

    write("shopops-standard-test-plan.md", "# ShopOps Standard Test Plan\n\n| Test ID | Layer | Target ID | Case Type | Future Command/Action | Expected Result | Evidence Path | Required For PASS | Status |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| TEST-UNIT | unit | metrics/storage/alerts | success/error | `python -m pytest -q` | all pass | logs/T09 | yes | PLANNED |\n| TEST-FEISHU | external-data | DATA-* | mapping/upsert/readback | `python scripts/acceptance/verify_feishu_data.py` | verdict PASS or limitation | external-data/T08 | yes | PLANNED |\n| TEST-NOZERO | external-data | monitor_snapshot/metrics_10min | failure-as-null | pytest | failed collectors do not write 0 | pytest | yes | PLANNED |\n| TEST-PENDING | external-data | pending cache | failure/replay | pytest + acceptance script | cache writes and replays | external-data/T08 | yes | PLANNED |\n| TEST-FINAL | final | all P0 | gate | inspect durable files | fail closed | verification-results.md | yes | PLANNED |")

    write("shopops-owner-scenario-matrix.md", "# ShopOps Owner Scenario Matrix\n\n| Scenario ID | Step ID | Persona | Goal | Preconditions | Exact Action | Expected Visible/Data Result | Expected API/Storage | Expected Readback | Evidence | Status |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n| OWNER-01 | 01 | merchant owner | see current operating snapshot | local fixture collectors | run one collection | monitor_snapshot has order, GMV, cost, ROI, CAC | Scheduler.run_once | local Feishu readback | external-data/T08 | PLANNED |\n| OWNER-02 | 01 | operator | handle Qianniu unavailable | CDP unavailable | run crawler mode | task log failure and alert log, no zero metrics | collectors + alert service | local Feishu readback | pytest | PLANNED |\n| OWNER-03 | 01 | operator | avoid duplicate Feishu records | same collection window | run collection twice | same unique_key updates | storage upsert | count stable | external-data/T08 | PLANNED |")

    write("shopops-final-acceptance-gate.md", "# ShopOps Final Acceptance Gate\n\n## Fail-Closed Rules\n- Missing pytest evidence -> REPAIR_REQUIRED.\n- Missing real Feishu mapping/upsert/readback proof -> REPAIR_REQUIRED.\n- Missing real Taobao API order proof -> REPAIR_REQUIRED or BLOCKED_BY_ENVIRONMENT with exact reason.\n- Missing real Qianniu PC/CDP promotion proof -> REPAIR_REQUIRED or BLOCKED_BY_ENVIRONMENT with exact reason.\n- Any failed collector metric written as `0` -> HARD_FAIL.\n- Missing task_run_log for a run -> HARD_FAIL.\n- Missing pending-cache replay proof -> REPAIR_REQUIRED.\n- Local mock proof can support unit tests only; it cannot upgrade the final verdict to PASS for the real external scope.\n\n## Final Verdict Table\n| Gate | Required Evidence | Current Status | Verdict |\n| --- | --- | --- | --- |\n| Requirements | traceability + tests | PLANNED | not executed by generator |\n| Real Feishu data correctness | real external-data/T08 proof | PLANNED | not executed by generator |\n| Real Taobao API | request/response proof with secrets redacted | PLANNED | not executed by generator |\n| Real Qianniu PC | CDP/session/readback proof | PLANNED | not executed by generator |\n| Tests | pytest + acceptance scripts | PLANNED | not executed by generator |")

    sequence = "\n".join(
        f"| {idx:02d} | {tid} | {name} | {surface} | {('none' if idx == 0 else TASK_DEFS[idx-1][0])} | {reqs} | {output} | result JSON + HANDOFF | repair queue | yes |"
        for idx, (tid, name, surface, reqs, output) in enumerate(TASK_DEFS)
    )
    write("shopops-auto-execute-master-plan.md", f"# ShopOps Auto-Execute Master Plan\n\n## Goal\nDeliver the Taobao single-platform monitoring MVP locally, with Feishu Bitable data correctness as the primary acceptance surface.\n\n## Task Sequence\n| Order | Task ID | Task Name | Surface | Depends On | Inputs | Outputs | Required Evidence | Repair Routing | Blocks PASS |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n{sequence}\n\n## Anti-Stop Orchestration\nT00 must run one fresh worker per task, wait for exit, verify result JSON/HANDOFF/logs, route failures to repair, and use durable files only for final gate.")

    split = ["# ShopOps Codex Exec Prompts Split\n\nEach task is one future fresh `codex exec`. This skill did not execute them.\n"]
    for tid, name, *_ in TASK_DEFS:
        split.append(f"## {tid}\n```powershell\nSet-Location -LiteralPath \"{ROOT}\"\ncodex exec \"Use the auto-execute skill. Execute only {ROOT}\\docs\\auto-execute\\shopops-tasks\\{tid}-{name}.md. Treat this as one fresh task boundary. Do not stop after planning. Implement, test, repair, write result JSON, write HANDOFF, and exit this codex exec. Do not claim PASS without evidence.\"\n```\n")
    write("shopops-codex-exec-prompts-split.md", "\n".join(split))

    for tid, name, surface, reqs, output in TASK_DEFS:
        write(f"shopops-tasks/{tid}-{name}.md", task_doc(tid, name, surface, reqs, output))

    write("shopops-task-pack-quality-audit.md", "# ShopOps Task Pack Quality Audit\n\n## Verdict\n`READY_FOR_AUTO_EXECUTE`\n\n## Document Completeness\nAll required documents including T00 and external data validation matrix are generated.\n\n## Requirement Coverage Audit\nEvery P0 requirement from the PRD has implementation task, verification task, and evidence path.\n\n## External Data Audit\nFeishu Bitable is treated as the primary acceptance surface. The pack requires table-by-table field mapping, upsert, duplicate-run, no failure-as-zero, pending cache, replay, and readback proof.\n\n## T00 Anti-Stop Orchestration Audit\nT00 exists and requires one fresh worker per task, result JSON/HANDOFF verification, failure-to-repair routing, and durable-file-only final gate.\n\n## Generation Boundary Audit\nNo `results/*.json`, `latest/*HANDOFF.md`, screenshots, API transcripts, DB readbacks, or PASS execution evidence were generated by this documentation-only script.")


if __name__ == "__main__":
    main()
