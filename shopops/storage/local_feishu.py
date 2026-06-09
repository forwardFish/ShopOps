from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from shopops.config import Settings, load_settings
from shopops.models import Metric10Min, MonitorSnapshot, TaskRunLog
from shopops.storage.base import Storage
from shopops.storage.field_mapping import metric_10min_fields, monitor_snapshot_fields, task_log_fields


class LocalFeishuBitableStorage(Storage):
    """A deterministic local double for Feishu Bitable create/update/list behavior."""

    def __init__(
        self,
        settings: Settings | None = None,
        path: str | Path | None = None,
        pending_path: str | Path | None = None,
        fail_tables: set[str] | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.path = Path(path or self.settings.local_feishu_path)
        self.pending_path = Path(pending_path or self.settings.pending_records_path)
        self.fail_tables = fail_tables or set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.pending_path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _persist(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _append_pending(self, table: str, fields: dict[str, Any], reason: str) -> None:
        item = {
            "table": table,
            "fields": fields,
            "reason": reason,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with self.pending_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    def upsert(self, table: str, fields: dict[str, Any]) -> int:
        if table in self.fail_tables:
            self._append_pending(table, fields, "local_fail_table")
            return 0

        records = self._data.setdefault(table, [])
        unique_key = fields.get("unique_key")
        if unique_key is not None:
            for record in records:
                if record["fields"].get("unique_key") == unique_key:
                    record["fields"] = dict(fields)
                    record["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._persist()
                    return 1

        record_id = f"rec_{table}_{len(records) + 1:06d}"
        records.append({"record_id": record_id, "fields": dict(fields), "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        self._persist()
        return 1

    def read_table(self, table: str) -> list[dict[str, Any]]:
        return list(self._data.get(table, []))

    def count(self, table: str) -> int:
        return len(self._data.get(table, []))

    def save_orders_raw(self, orders: list[dict[str, Any]]) -> int:
        return sum(self.upsert("orders_raw", order) for order in orders)

    def save_promotion_snapshot(self, rows: list[dict[str, Any]]) -> int:
        return sum(self.upsert("promotion_snapshot", row) for row in rows)

    def save_douyin_influencer_commission(self, rows: list[dict[str, Any]]) -> int:
        return sum(self.upsert("douyin_influencer_commission", row) for row in rows)

    def save_monitor_snapshot(self, snapshot: MonitorSnapshot) -> int:
        return self.upsert("monitor_snapshot", monitor_snapshot_fields(snapshot))

    def get_last_monitor_snapshot(self, shop_id: str) -> MonitorSnapshot | None:
        rows = [
            record["fields"]
            for record in self._data.get("monitor_snapshot", [])
            if record["fields"].get("店铺ID") == shop_id
        ]
        if not rows:
            return None
        row = sorted(rows, key=lambda item: item.get("采集时间") or "")[-1]
        fetched_at = datetime.strptime(row["采集时间"], "%Y-%m-%d %H:%M:%S")
        return MonitorSnapshot(
            unique_key=row["unique_key"],
            fetched_at=fetched_at,
            shop_id=row["店铺ID"],
            shop_name=row["店铺名称"],
            order_source=row["订单来源"],
            promotion_source=row["推广来源"],
            data_status=row["数据状态"],
            promotion_center_cost=row.get("推广中心花费"),
            total_cost=row.get("总推广消耗"),
            order_count=row.get("今日订单数"),
            paid_order_count=row.get("今日订单数"),
            total_amount=row.get("今日成交额"),
            roi=row.get("实时ROI"),
            cac=row.get("获客成本"),
            error_message=row.get("错误信息"),
            alert_flag=bool(row.get("是否告警")),
        )

    def save_metric_10min(self, metric: Metric10Min) -> int:
        return self.upsert("metrics_10min", metric_10min_fields(metric))

    def save_task_log(self, log: TaskRunLog) -> int:
        return self.upsert("task_run_log", task_log_fields(log))

    def save_alert_log(self, alert: dict[str, Any]) -> int:
        return self.upsert("alert_log", alert)

    def save_daily_report(self, report: dict[str, Any]) -> int:
        return self.upsert("daily_report", report)

    def pending_records(self) -> list[dict[str, Any]]:
        if not self.pending_path.exists():
            return []
        return [json.loads(line) for line in self.pending_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def replay_pending(self, limit: int = 100) -> int:
        pending = self.pending_records()
        if not pending:
            return 0
        replayed = 0
        remaining: list[dict[str, Any]] = []
        original_fail_tables = set(self.fail_tables)
        for item in pending[:limit]:
            table = item["table"]
            if table in original_fail_tables:
                remaining.append(item)
                continue
            replayed += self.upsert(table, item["fields"])
        remaining.extend(pending[limit:])
        self.pending_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in remaining),
            encoding="utf-8",
        )
        return replayed
