from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.services.dynamic_feishu_summary import (
    AD_TABLE,
    COMMISSION_TABLE,
    ORDER_TABLE,
    SUMMARY_TABLE_NAME,
    SourceTableRows,
    build_dynamic_summary,
    summary_field_names,
    summary_number_fields,
)
from shopops.storage.feishu_bootstrap import FeishuOpenApiClient, PlatformTableSpec, merge_env_file, number_field, text_field


class DynamicSummaryFeishuClient:
    def __init__(self, app_token: str, env_path: Path) -> None:
        ensure_feishu_no_proxy()
        settings = load_settings()
        self.app_token = app_token
        self.env_path = env_path
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)

    def run(
        self,
        order_table_id: str,
        ad_table_id: str,
        commission_table_id: str,
        summary_table_id: str | None = None,
        evidence_dir: Path = Path("docs/live-evidence/dynamic-feishu-summary"),
    ) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        summary_time = datetime.now()
        summary_table_id = summary_table_id or self.ensure_summary_table()
        self.ensure_fields(summary_table_id, summary_table_spec())
        source = SourceTableRows(
            orders=self.list_records(order_table_id),
            ads=self.list_records(ad_table_id),
            commissions=self.list_records(commission_table_id),
        )
        result = build_dynamic_summary(source, summary_time=summary_time)
        saved = self.upsert_records(summary_table_id, result.summary_rows)
        readback = self.readback_unique_keys(summary_table_id, [row["unique_key"] for row in result.summary_rows])
        payload = {
            "mode": "feishu",
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "source_table_ids": {
                ORDER_TABLE: order_table_id,
                AD_TABLE: ad_table_id,
                COMMISSION_TABLE: commission_table_id,
            },
            "summary_table": {
                "name": SUMMARY_TABLE_NAME,
                "table_id": summary_table_id,
            },
            "source_counts": result.source_counts,
            "summary_row_count": len(result.summary_rows),
            "coverage": coverage_metrics(result.summary_rows),
            "saved_count": saved,
            "readback_count": readback,
            "summary_time": result.summary_time,
            "sample_rows": result.summary_rows[:5],
        }
        evidence_path = evidence_dir / "dynamic-summary-result.json"
        evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        payload["evidence_path"] = str(evidence_path.resolve())
        return payload

    def ensure_summary_table(self) -> str:
        existing = self.client.list_tables(self.app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        spec = summary_table_spec()
        table = self.client.ensure_table(self.app_token, spec, existing_by_name)
        table_id = str(table.get("table_id") or "")
        if not table_id:
            raise RuntimeError(f"Feishu table {SUMMARY_TABLE_NAME} did not return table_id")
        self.ensure_fields(table_id, spec)
        merge_env_file(self.env_path, {"SHOPOPS_DYNAMIC_SUMMARY_TABLE_ID": table_id})
        return table_id

    def ensure_fields(self, table_id: str, spec: PlatformTableSpec) -> None:
        existing = self.list_field_names(table_id)
        for field in spec.fields:
            name = str(field["field_name"])
            if name in existing:
                continue
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields",
                {"field_name": name, "type": field["type"]},
            )
            existing.add(name)

    def list_field_names(self, table_id: str) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items", []) or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def list_records(self, table_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items", []) or [])
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")

    def upsert_records(self, table_id: str, rows: list[dict[str, Any]]) -> int:
        index = self.record_index(table_id)
        to_create: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        for row in rows:
            unique_key = str(row.get("unique_key") or "")
            if not unique_key:
                continue
            record_id = index.get(unique_key)
            if record_id:
                to_update.append({"record_id": record_id, "fields": row})
            else:
                to_create.append({"fields": row})
        saved = self.batch_create(table_id, to_create)
        saved += self.batch_update(table_id, to_update)
        return saved

    def batch_create(self, table_id: str, records: list[dict[str, Any]]) -> int:
        saved = 0
        for chunk in chunks(records, 500):
            if chunk:
                self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create", {"records": chunk})
                saved += len(chunk)
        return saved

    def batch_update(self, table_id: str, records: list[dict[str, Any]]) -> int:
        saved = 0
        for chunk in chunks(records, 500):
            if chunk:
                self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
                saved += len(chunk)
        return saved

    def record_index(self, table_id: str) -> dict[str, str]:
        records: dict[str, str] = {}
        for item in self.list_records(table_id):
            fields = item.get("fields") or {}
            unique_key = fields.get("unique_key")
            if unique_key:
                records[str(unique_key)] = str(item.get("record_id"))
        return records

    def readback_unique_keys(self, table_id: str, unique_keys: list[str]) -> int:
        expected = set(unique_keys)
        seen = set()
        for item in self.list_records(table_id):
            unique_key = (item.get("fields") or {}).get("unique_key")
            if unique_key in expected:
                seen.add(unique_key)
        return len(seen)

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{self.client.base_url}{path}",
            headers=self.client.headers(),
            json=payload,
            params=params,
            timeout=30,
        )
        try:
            body = response.json()
        except ValueError as exc:
            text = response.text[:1000]
            raise RuntimeError(f"Feishu API {method} {path} returned non-JSON HTTP {response.status_code}: {text}") from exc
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def summary_table_spec() -> PlatformTableSpec:
    return PlatformTableSpec(
        "SHOPOPS_DYNAMIC_SUMMARY_TABLE_ID",
        "dynamic_summary",
        SUMMARY_TABLE_NAME,
        [number_field(name) if name in summary_number_fields() else text_field(name) for name in summary_field_names()],
    )


def coverage_metrics(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "normal_rows": sum(1 for row in rows if row.get("数据状态") == "normal"),
        "partial_rows": sum(1 for row in rows if row.get("数据状态") == "partial"),
        "roi_rows": sum(1 for row in rows if row.get("ROI") is not None),
        "platform_roi_rows": sum(1 for row in rows if row.get("平台ROI") is not None),
        "commission_rows": sum(1 for row in rows if float(row.get("达人佣金") or 0) > 0),
        "known_profit_rows": sum(1 for row in rows if row.get("已知费用后利润") is not None),
        "operating_profit_rows": sum(1 for row in rows if row.get("经营利润估算") is not None),
    }


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Build a SQL-like dynamic business summary from existing Feishu source tables.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN") or "KhbEbksLbauw0fssL6EcKAnlnOe")
    parser.add_argument("--order-table-id", default=os.getenv("SHOPOPS_ORDER_TABLE_ID") or os.getenv("FEISHU_TABLE_ORDERS_RAW"))
    parser.add_argument("--ad-table-id", default=os.getenv("SHOPOPS_AD_TABLE_ID") or os.getenv("FEISHU_TABLE_PROMOTION_SNAPSHOT"))
    parser.add_argument("--commission-table-id", default=os.getenv("SHOPOPS_COMMISSION_TABLE_ID") or os.getenv("FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION"))
    parser.add_argument("--summary-table-id", default=os.getenv("SHOPOPS_DYNAMIC_SUMMARY_TABLE_ID"))
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/dynamic-feishu-summary")
    args = parser.parse_args()

    missing = [
        name
        for name, value in {
            "app-token": args.app_token,
            "order-table-id": args.order_table_id,
            "ad-table-id": args.ad_table_id,
            "commission-table-id": args.commission_table_id,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("Missing required Feishu inputs: " + ", ".join(missing))

    result = DynamicSummaryFeishuClient(args.app_token, Path(args.env_path)).run(
        order_table_id=args.order_table_id,
        ad_table_id=args.ad_table_id,
        commission_table_id=args.commission_table_id,
        summary_table_id=args.summary_table_id,
        evidence_dir=Path(args.evidence_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
