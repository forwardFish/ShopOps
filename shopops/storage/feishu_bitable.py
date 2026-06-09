from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from shopops.config import Settings, load_settings
from shopops.models import Metric10Min, MonitorSnapshot, TaskRunLog
from shopops.storage.base import Storage
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient
from shopops.storage.field_mapping import metric_10min_fields, monitor_snapshot_fields, task_log_fields


class FeishuEnvironmentError(RuntimeError):
    pass


class FeishuBitableStorage(Storage):
    """Direct Feishu OpenAPI storage for all scheduler-written live tables."""

    required_table_env = {
        "FEISHU_TABLE_MONITOR_SNAPSHOT": "monitor_snapshot",
        "FEISHU_TABLE_ORDERS_RAW": "orders_raw",
        "FEISHU_TABLE_PROMOTION_SNAPSHOT": "promotion_snapshot",
        "FEISHU_TABLE_METRICS_10MIN": "metrics_10min",
        "FEISHU_TABLE_TASK_LOG": "task_run_log",
        "FEISHU_TABLE_ALERT_LOG": "alert_log",
        "FEISHU_TABLE_DAILY_REPORT": "daily_report",
        "FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION": "douyin_influencer_commission",
    }

    def __init__(self, settings: Settings | None = None, pending_path: str | Path | None = None, base_url: str = FEISHU_BASE_URL) -> None:
        self.settings = settings or load_settings()
        self.base_url = base_url.rstrip("/")
        self.pending_path = Path(pending_path or self.settings.pending_records_path)
        self.pending_path.parent.mkdir(parents=True, exist_ok=True)
        self._validate_environment()
        self.auth = FeishuOpenApiClient(self.settings.feishu_app_id, self.settings.feishu_app_secret, base_url=self.base_url)

    @classmethod
    def environment_probe(cls, settings: Settings | None = None) -> dict[str, Any]:
        settings = settings or load_settings()
        missing: list[str] = []
        if not settings.feishu_app_id:
            missing.append("FEISHU_APP_ID")
        if not settings.feishu_app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not settings.feishu_app_token:
            missing.append("FEISHU_APP_TOKEN")
        for env_name, table_key in cls.required_table_env.items():
            table_id = settings.table_ids[table_key]
            if not table_id or not table_id.startswith("tbl"):
                missing.append(env_name)
        return {"missing": sorted(set(missing)), "ready": not missing}

    def _validate_environment(self) -> None:
        probe = self.environment_probe(self.settings)
        if not probe["ready"]:
            raise FeishuEnvironmentError("Feishu Bitable environment is incomplete: " + ", ".join(probe["missing"]))

    def _table_id(self, table: str) -> str:
        if table not in self.required_table_env.values():
            raise KeyError(f"Table {table} is not part of the live Feishu business scope")
        return self.settings.table_ids[table]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth.tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=payload,
            params=params,
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError(f"Feishu API returned non-JSON response: HTTP {response.status_code}") from exc
        if response.status_code >= 400:
            raise RuntimeError(f"Feishu API HTTP {response.status_code}: {body}")
        if body.get("code") != 0:
            raise RuntimeError(f"Feishu API error {body.get('code')}: {body.get('msg')}")
        return body.get("data") or {}

    def _create_record(self, table_id: str, fields: dict[str, Any]) -> str:
        data = self._request(
            "POST",
            f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records",
            {"fields": fields},
        )
        record = data.get("record") or {}
        return str(record.get("record_id") or "")

    def _update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
        self._request(
            "PUT",
            f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records/{record_id}",
            {"fields": fields},
        )

    def _find_record_id_by_unique_key(self, table_id: str, unique_key: str | None) -> str | None:
        if not unique_key:
            return None
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records",
                params=params,
            )
            for record in data.get("items", []) or []:
                fields = record.get("fields") or {}
                if fields.get("unique_key") == unique_key:
                    return str(record.get("record_id"))
            if not data.get("has_more"):
                return None
            page_token = data.get("page_token")

    def _list_records(self, table: str, page_size: int = 500) -> list[dict[str, Any]]:
        table_id = self._table_id(table)
        page_token = None
        records: list[dict[str, Any]] = []
        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records",
                params=params,
            )
            records.extend(data.get("items", []) or [])
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")

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
        table_id = self._table_id(table)
        try:
            record_id = self._find_record_id_by_unique_key(table_id, fields.get("unique_key"))
            if record_id:
                self._update_record(table_id, record_id, fields)
            else:
                self._create_record(table_id, fields)
            return 1
        except Exception as exc:
            self._append_pending(table, fields, type(exc).__name__)
            raise

    def pending_records(self) -> list[dict[str, Any]]:
        if not self.pending_path.exists():
            return []
        return [json.loads(line) for line in self.pending_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def replay_pending(self, limit: int = 100) -> int:
        pending = self.pending_records()
        replayed = 0
        remaining: list[dict[str, Any]] = []
        for item in pending[:limit]:
            try:
                replayed += self.upsert(item["table"], item["fields"])
            except Exception:
                remaining.append(item)
        remaining.extend(pending[limit:])
        self.pending_path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in remaining),
            encoding="utf-8",
        )
        return replayed

    def save_orders_raw(self, orders: list[dict[str, Any]]) -> int:
        return sum(self.upsert("orders_raw", order) for order in orders)

    def save_promotion_snapshot(self, rows: list[dict[str, Any]]) -> int:
        return sum(self.upsert("promotion_snapshot", row) for row in rows)

    def save_douyin_influencer_commission(self, rows: list[dict[str, Any]]) -> int:
        return sum(self.upsert("douyin_influencer_commission", row) for row in rows)

    def save_monitor_snapshot(self, snapshot: MonitorSnapshot) -> int:
        return self.upsert("monitor_snapshot", monitor_snapshot_fields(snapshot))

    def get_last_monitor_snapshot(self, shop_id: str) -> MonitorSnapshot | None:
        field_order = list(
            monitor_snapshot_fields(
                MonitorSnapshot(
                    unique_key="",
                    fetched_at=datetime(2000, 1, 1),
                    shop_id="",
                    shop_name="",
                    order_source="",
                    promotion_source="",
                    data_status="",
                    promotion_center_cost=None,
                    total_cost=None,
                    order_count=None,
                    paid_order_count=None,
                    total_amount=None,
                    roi=None,
                    cac=None,
                    error_message=None,
                    alert_flag=False,
                )
            )
        )
        fetched_at_key = field_order[1]
        shop_id_key = field_order[2]
        shop_name_key = field_order[3]
        order_source_key = field_order[4]
        promotion_source_key = field_order[5]
        data_status_key = field_order[6]
        promotion_center_cost_key = field_order[7]
        total_cost_key = field_order[8]
        order_count_key = field_order[9]
        total_amount_key = field_order[10]
        roi_key = field_order[11]
        cac_key = field_order[12]
        error_message_key = field_order[13]
        alert_flag_key = field_order[14]

        rows = [
            record.get("fields") or {}
            for record in self._list_records("monitor_snapshot")
            if (record.get("fields") or {}).get(shop_id_key) == shop_id
        ]
        if not rows:
            return None
        row = sorted(rows, key=lambda item: item.get(fetched_at_key) or "")[-1]
        fetched_at = datetime.strptime(row[fetched_at_key], "%Y-%m-%d %H:%M:%S")
        return MonitorSnapshot(
            unique_key=row["unique_key"],
            fetched_at=fetched_at,
            shop_id=row[shop_id_key],
            shop_name=row[shop_name_key],
            order_source=row[order_source_key],
            promotion_source=row[promotion_source_key],
            data_status=row[data_status_key],
            promotion_center_cost=row.get(promotion_center_cost_key),
            total_cost=row.get(total_cost_key),
            order_count=row.get(order_count_key),
            paid_order_count=row.get(order_count_key),
            total_amount=row.get(total_amount_key),
            roi=row.get(roi_key),
            cac=row.get(cac_key),
            error_message=row.get(error_message_key),
            alert_flag=bool(row.get(alert_flag_key)),
        )

    def save_metric_10min(self, metric: Metric10Min) -> int:
        return self.upsert("metrics_10min", metric_10min_fields(metric))

    def save_task_log(self, log: TaskRunLog) -> int:
        return self.upsert("task_run_log", task_log_fields(log))

    def save_alert_log(self, alert: dict[str, Any]) -> int:
        return self.upsert("alert_log", alert)

    def save_daily_report(self, report: dict[str, Any]) -> int:
        return self.upsert("daily_report", report)
