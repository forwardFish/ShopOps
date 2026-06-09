from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shopops.config import Settings
from shopops.models import Metric10Min, MonitorSnapshot, TaskRunLog
from shopops.storage.feishu_bitable import FeishuBitableStorage
from shopops.storage.local_feishu import LocalFeishuBitableStorage


TASK_PACK_ID = "shopops-goal-2026-06-03"
TASK_ID = "T03"
OUT = ROOT / "docs" / "auto-execute" / "external-data" / TASK_ID
RESULTS = ROOT / "docs" / "auto-execute" / "results"
LATEST = ROOT / "docs" / "auto-execute" / "latest"
LOGS = ROOT / "docs" / "auto-execute" / "logs" / TASK_ID

TABLES = [
    "system_config",
    "shop_config",
    "monitor_snapshot",
    "orders_raw",
    "promotion_snapshot",
    "metrics_10min",
    "task_run_log",
    "alert_log",
    "daily_report",
]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def sample_payloads(now: datetime) -> dict[str, dict[str, Any]]:
    return {
        "system_config": {
            "unique_key": "ORDER_SOURCE",
            "config_key": "ORDER_SOURCE",
            "config_value": "crawler",
            "enabled": True,
            "remark": "T03 local proof",
            "updated_at": "2026-06-03 12:00:00",
        },
        "shop_config": {
            "unique_key": "taobao_shop_001",
            "shop_id": "taobao_shop_001",
            "shop_name": "淘宝店铺A",
            "platform": "taobao",
            "qianniu_cdp_url": "http://127.0.0.1:9222",
            "order_source": "crawler",
            "promotion_source": "qianniu_pc",
            "status": "active",
            "remark": "T03 local proof",
        },
        "orders_raw": {
            "unique_key": "taobao_taobao_shop_001_T03_ORDER_001",
            "数据来源": "crawler",
            "店铺ID": "taobao_shop_001",
            "店铺名称": "淘宝店铺A",
            "订单号": "T03_ORDER_001",
            "下单时间": "2026-06-03 11:50:00",
            "支付时间": "2026-06-03 11:51:00",
            "订单状态": "TRADE_FINISHED",
            "支付金额": 99.9,
            "商品名称": "T03 local proof item",
            "采集时间": "2026-06-03 12:00:00",
            "原始数据": "{\"source\":\"local-proof\"}",
        },
        "promotion_snapshot": {
            "unique_key": "taobao_shop_001_tuiguangcenter_202606031200",
            "采集时间": "2026-06-03 12:00:00",
            "店铺ID": "taobao_shop_001",
            "店铺名称": "淘宝店铺A",
            "推广渠道": "推广中心",
            "今日累计消耗(元)": 12.34,
            "曝光": None,
            "点击": None,
            "转化": None,
            "状态": "success",
            "错误信息": None,
            "原始数据": {"source": "local-proof"},
        },
        "alert_log": {
            "unique_key": "T03_ALERT_001",
            "alert_id": "T03_ALERT_001",
            "触发时间": "2026-06-03 12:00:00",
            "店铺ID": "taobao_shop_001",
            "告警类型": "feishu_failed",
            "告警级别": "critical",
            "告警内容": "T03 local proof alert",
            "当前值": None,
            "阈值": None,
            "是否已发送": False,
            "发送结果": "pending",
        },
        "daily_report": {
            "unique_key": "taobao_shop_001_2026-06-03",
            "report_date": "2026-06-03",
            "店铺ID": "taobao_shop_001",
            "店铺名称": "淘宝店铺A",
            "今日订单数": 1,
            "今日成交额(元)": 99.9,
            "推广中心花费(元)": 12.34,
            "总推广消耗(元)": 12.34,
            "今日ROI": 8.1,
            "获客成本(元)": 12.34,
            "异常统计": "{}",
            "数据状态": "normal",
        },
    }


def write_model_rows(storage: LocalFeishuBitableStorage, now: datetime) -> None:
    snapshot = MonitorSnapshot(
        unique_key="taobao_shop_001_202606031200",
        fetched_at=now,
        shop_id="taobao_shop_001",
        shop_name="淘宝店铺A",
        order_source="crawler",
        promotion_source="qianniu_pc",
        data_status="normal",
        promotion_center_cost=12.34,
        total_cost=12.34,
        order_count=1,
        paid_order_count=1,
        total_amount=99.9,
        roi=8.1,
        cac=12.34,
        error_message=None,
        alert_flag=False,
    )
    metric = Metric10Min(
        unique_key="taobao_shop_001_202606031150_202606031200",
        window_start=datetime(2026, 6, 3, 11, 50, 0),
        window_end=now,
        shop_id="taobao_shop_001",
        shop_name="淘宝店铺A",
        delta_order_count=1,
        delta_total_amount=99.9,
        delta_cost=12.34,
        delta_roi=8.1,
        delta_cac=12.34,
        data_status="normal",
        abnormal_reason=None,
    )
    log = TaskRunLog(
        task_id="T03_TASK_LOG_001",
        task_type="full_collect",
        started_at=datetime(2026, 6, 3, 12, 0, 0),
        ended_at=datetime(2026, 6, 3, 12, 0, 1),
        duration_seconds=1.0,
        shop_id="taobao_shop_001",
        order_status="success",
        promotion_status="success",
        storage_status="success",
        total_status="success",
        fetched_count=2,
        saved_count=5,
        error_code=None,
        error_message=None,
        alerted=False,
    )
    storage.save_monitor_snapshot(snapshot)
    storage.save_metric_10min(metric)
    storage.save_task_log(log)


def prove_local_storage() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = Settings(local_feishu_path=str(OUT / "local_feishu.json"), pending_records_path=str(OUT / "pending_records.jsonl"))
    for generated in [
        OUT / "local_feishu.json",
        OUT / "local_feishu_fail.json",
        OUT / "pending_records.jsonl",
        OUT / "pending_records_fail.jsonl",
    ]:
        if generated.exists():
            generated.unlink()

    storage = LocalFeishuBitableStorage(settings)
    now = datetime(2026, 6, 3, 12, 0, 0)
    payloads = sample_payloads(now)
    for table in ["system_config", "shop_config", "orders_raw", "promotion_snapshot", "alert_log", "daily_report"]:
        storage.upsert(table, payloads[table])
    write_model_rows(storage, now)

    counts_after_first = {table: storage.count(table) for table in TABLES}
    updated_monitor = dict(storage.read_table("monitor_snapshot")[0]["fields"])
    updated_monitor["今日订单数"] = 2
    storage.upsert("monitor_snapshot", updated_monitor)
    counts_after_second = {table: storage.count(table) for table in TABLES}

    failing_storage = LocalFeishuBitableStorage(
        settings,
        path=OUT / "local_feishu_fail.json",
        pending_path=OUT / "pending_records_fail.jsonl",
        fail_tables={"monitor_snapshot"},
    )
    write_model_rows(failing_storage, now)
    pending_before = failing_storage.pending_records()
    failing_storage.fail_tables.clear()
    replayed = failing_storage.replay_pending()
    pending_after = failing_storage.pending_records()

    readback = {table: [record["fields"] for record in storage.read_table(table)] for table in TABLES}
    field_coverage = {table: sorted(readback[table][0].keys()) if readback[table] else [] for table in TABLES}
    required_checks = {
        "all_tables_written": all(counts_after_first[table] >= 1 for table in TABLES),
        "readback_all_tables": all(bool(readback[table]) for table in TABLES),
        "unique_key_upsert_no_duplicate": counts_after_second["monitor_snapshot"] == counts_after_first["monitor_snapshot"],
        "upsert_updated_existing_row": storage.read_table("monitor_snapshot")[0]["fields"].get("今日订单数") == 2,
        "pending_cache_written": len(pending_before) == 1,
        "pending_replay_cleared": replayed == 1 and pending_after == [],
    }
    local_ok = all(required_checks.values())
    proof = {
        "status": "PASS" if local_ok else "FAIL",
        "required_checks": required_checks,
        "counts_after_first": counts_after_first,
        "counts_after_second": counts_after_second,
        "field_coverage": field_coverage,
        "readback": readback,
        "pending_before_replay": pending_before,
        "pending_after_replay": pending_after,
        "generated_files": [
            str(OUT / "local_feishu.json"),
            str(OUT / "local_feishu_fail.json"),
            str(OUT / "pending_records_fail.jsonl"),
        ],
    }
    write_json(OUT / "local-storage-proof.json", proof)
    return proof


def maybe_probe_live() -> dict[str, Any]:
    settings = Settings()
    probe = FeishuBitableStorage.environment_probe(settings)
    live = {
        "status": "BLOCKED_BY_ENVIRONMENT" if not probe["ready"] else "REPAIR_REQUIRED",
        "environment_probe": probe,
        "attempted_live_write": False,
        "reason": "missing Feishu credentials, Base token, or required business table IDs" if not probe["ready"] else "live verifier requires explicit two-table write/readback execution",
    }
    write_json(LOGS / "feishu-environment-probe.json", live)
    return live


def write_outputs(local_proof: dict[str, Any], live_probe: dict[str, Any]) -> str:
    local_ok = local_proof["status"] == "PASS"
    blockers = []
    status = "PASS"
    if live_probe["status"] == "BLOCKED_BY_ENVIRONMENT":
        status = "BLOCKED_BY_ENVIRONMENT"
        blockers.append(
            {
                "id": "T03-FEISHU-LIVE-ENV",
                "classification": "BLOCKED_BY_ENVIRONMENT",
                "summary": "Live Feishu Bitable write/upsert/readback is unavailable because credentials, Base token, or required business table IDs are missing.",
                "details": live_probe["environment_probe"],
            }
        )
    elif live_probe["status"] != "PASS":
        status = "REPAIR_REQUIRED"
        blockers.append(
            {
                "id": "T03-FEISHU-LIVE-VERIFIER",
                "classification": "REPAIR_REQUIRED",
                "summary": live_probe["reason"],
            }
        )
    if not local_ok:
        status = "REPAIR_REQUIRED"
        blockers.append(
            {
                "id": "T03-LOCAL-STORAGE-PROOF",
                "classification": "REPAIR_REQUIRED",
                "summary": "Local Feishu double did not satisfy field/upsert/pending/readback checks.",
                "details": local_proof["required_checks"],
            }
        )

    result = {
        "task_pack_id": TASK_PACK_ID,
        "task_id": TASK_ID,
        "task_name": "feishu-bitable-storage-real-and-local-proof",
        "status": status,
        "summary": "T03 proves local Feishu-style storage/upsert/pending replay/readback for DATA-001..DATA-009 and fails closed for live Feishu because the environment lacks real credentials/table IDs or SDK.",
        "coverage": {
            "requirements": ["REQ-007", "REQ-008", "REQ-009"],
            "data_ids": [f"DATA-{i:03d}" for i in range(1, 10)],
        },
        "evidence": [
            {
                "type": "local_storage_proof",
                "path": "docs/auto-execute/external-data/T03/local-storage-proof.json",
                "status": local_proof["status"],
            },
            {
                "type": "local_readback_store",
                "path": "docs/auto-execute/external-data/T03/local_feishu.json",
                "status": "PASS" if local_ok else "FAIL",
            },
            {
                "type": "pending_replay_store",
                "path": "docs/auto-execute/external-data/T03/pending_records_fail.jsonl",
                "status": "PASS" if local_proof["required_checks"]["pending_replay_cleared"] else "FAIL",
            },
            {
                "type": "live_environment_probe",
                "path": "docs/auto-execute/logs/T03/feishu-environment-probe.json",
                "status": live_probe["status"],
            },
        ],
        "blockers": blockers,
        "log_paths": [
            "docs/auto-execute/logs/T03/feishu-environment-probe.json",
            "docs/auto-execute/logs/T03/verification.txt",
        ],
        "changed_files": [
            "shopops/storage/feishu_bitable.py",
            "shopops/storage/__init__.py",
            "scripts/acceptance/verify_feishu_data.py",
            "tests/test_feishu_storage_contract.py",
            "docs/auto-execute/results/T03.json",
            "docs/auto-execute/latest/T03-HANDOFF.md",
            "docs/auto-execute/external-data/T03/local-storage-proof.json",
        ],
        "security": {
            "secrets_logged": False,
            "live_feishu_pass_claimed": False,
            "external_side_effects": False,
        },
    }
    write_json(RESULTS / "T03.json", result)
    handoff_lines = [
        "# T03 HANDOFF - feishu-bitable-storage-real-and-local-proof",
        "",
        f"Task pack: `{TASK_PACK_ID}`",
        f"Task ID: `{TASK_ID}`",
        f"Status: `{status}`",
        "",
        "This worker executed only T03.",
        "",
        "## Evidence",
        "",
        "| Evidence | Path | Result |",
        "| --- | --- | --- |",
        f"| Local field/upsert/pending/readback proof | `docs/auto-execute/external-data/T03/local-storage-proof.json` | `{local_proof['status']}` |",
        "| Local readback store | `docs/auto-execute/external-data/T03/local_feishu.json` | `written` |",
        f"| Live Feishu environment probe | `docs/auto-execute/logs/T03/feishu-environment-probe.json` | `{live_probe['status']}` |",
        "| Result JSON | `docs/auto-execute/results/T03.json` | `written` |",
        "",
        "## Local Checks",
        "",
        *[f"- {name}: `{'PASS' if passed else 'FAIL'}`" for name, passed in local_proof["required_checks"].items()],
        "",
        "## Blockers",
        "",
        *([f"- `{blocker['classification']}`: {blocker['summary']}" for blocker in blockers] or ["- None"]),
        "",
        "## Scope Guard",
        "",
        "No T04 or later task was executed. No live Feishu PASS is claimed without real write/readback evidence.",
        "",
    ]
    (LATEST / "T03-HANDOFF.md").parent.mkdir(parents=True, exist_ok=True)
    (LATEST / "T03-HANDOFF.md").write_text("\n".join(handoff_lines), encoding="utf-8")
    return status


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    local_proof = prove_local_storage()
    live_probe = maybe_probe_live()
    status = write_outputs(local_proof, live_probe)
    (LOGS / "verification.txt").write_text(
        "\n".join(
            [
                "command: python scripts/acceptance/verify_feishu_data.py",
                f"task_pack_id: {TASK_PACK_ID}",
                f"task_id: {TASK_ID}",
                f"status: {status}",
                f"local_storage: {local_proof['status']}",
                f"live_feishu: {live_probe['status']}",
                "result: docs/auto-execute/results/T03.json",
                "handoff: docs/auto-execute/latest/T03-HANDOFF.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if status == "PASS":
        return 0
    if status == "BLOCKED_BY_ENVIRONMENT":
        return 4
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
