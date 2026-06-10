from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


FIELDS = ["unique_key", "平台", "订单号", "来源文件", "带货费用", "预估佣金支出", "实际佣金支出", "带货佣金率", "佣金率"]


class FeishuClient:
    def __init__(self) -> None:
        _load_dotenv()
        settings = load_settings()
        self.app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
        if not self.app_token:
            raise RuntimeError("Missing FEISHU_APP_TOKEN or SHOPOPS_DATA_CENTER_APP_TOKEN")
        self.auth = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{FEISHU_BASE_URL}{path}",
            headers=self.auth.headers(),
            json=payload,
            params=params,
            timeout=60,
        )
        body = response.json()
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def field_names(self, table_id: str) -> set[str]:
        names: set[str] = set()
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items") or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def records(self, table_id: str) -> list[dict[str, Any]]:
        fields = [name for name in FIELDS if name in self.field_names(table_id)]
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500, "field_names": json.dumps(fields, ensure_ascii=False)}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")

    def delete_records(self, table_id: str, record_ids: list[str]) -> int:
        deleted = 0
        for chunk in chunks(record_ids, 500):
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_delete", {"records": chunk})
            deleted += len(chunk)
        return deleted


def scalar(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") if isinstance(item, dict) else item) for item in value).strip()
    return "" if value is None else str(value).strip()


def number(value: Any) -> float:
    if isinstance(value, list) and value:
        value = value[0].get("text") if isinstance(value[0], dict) else value[0]
    try:
        text = str(value).replace(",", "").replace("%", "").strip()
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def keep_score(record: dict[str, Any]) -> tuple[int, int, int, int]:
    fields = record.get("fields") or {}
    platform = scalar(fields.get("平台"))
    order_no = scalar(fields.get("订单号")).replace("\t", "").strip("'")
    unique_key = scalar(fields.get("unique_key"))
    source_file = scalar(fields.get("来源文件"))
    has_unified_amount = int(number(fields.get("带货费用")) > 0 and number(fields.get("预估佣金支出")) > 0)
    has_rate = int(bool(scalar(fields.get("带货佣金率")) or number(fields.get("佣金率"))))
    has_current_key = int(unique_key == f"{platform}{order_no}")
    from_0609_sync = int("0609" in source_file and (unique_key == f"{platform}{order_no}"))
    return (from_0609_sync, has_current_key, has_unified_amount, has_rate)


def deduplicate(table_id: str, dry_run: bool, evidence: Path) -> dict[str, Any]:
    client = FeishuClient()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in client.records(table_id):
        fields = record.get("fields") or {}
        platform = scalar(fields.get("平台"))
        order_no = scalar(fields.get("订单号")).replace("\t", "").strip("'")
        if platform in {"抖音", "视频号"} and order_no:
            groups[(platform, order_no)].append(record)

    duplicate_groups = {key: rows for key, rows in groups.items() if len(rows) > 1}
    to_delete: list[str] = []
    samples: list[dict[str, Any]] = []
    for key, rows in duplicate_groups.items():
        keeper = max(rows, key=keep_score)
        keeper_id = str(keeper.get("record_id") or "")
        delete_ids = [str(row.get("record_id") or "") for row in rows if str(row.get("record_id") or "") != keeper_id]
        to_delete.extend(record_id for record_id in delete_ids if record_id)
        if len(samples) < 20:
            samples.append(
                {
                    "key": f"{key[0]}|{key[1]}",
                    "kept_unique_key": scalar((keeper.get("fields") or {}).get("unique_key")),
                    "deleted": len(delete_ids),
                    "scores": [
                        {
                            "unique_key": scalar((row.get("fields") or {}).get("unique_key")),
                            "score": keep_score(row),
                        }
                        for row in rows
                    ],
                }
            )

    deleted = 0 if dry_run else client.delete_records(table_id, to_delete)
    result = {
        "status": "dry_run" if dry_run else "success",
        "table_id": table_id,
        "duplicate_groups": len(duplicate_groups),
        "records_to_delete": len(to_delete),
        "deleted_records": deleted,
        "sample_duplicate_groups": samples,
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Deduplicate influencer commission records by platform and order number.")
    parser.add_argument("--table-id", default="tblhBsehmQbzWEVm")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence", default="docs/live-evidence/influencer-commission-0609-deduplicate.json")
    args = parser.parse_args()
    print(json.dumps(deduplicate(args.table_id, args.dry_run, Path(args.evidence)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
