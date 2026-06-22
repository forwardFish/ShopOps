from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


DEFAULT_TABLE_ID = "tblElZpyDFNLwqGU"

F_UNIQUE_KEY = "unique_key"
F_CREATOR_NAME = "达人名称"
F_DOUYIN_ID = "抖音号"
F_SEARCH_KEYWORD = "搜索关键词"
F_SOURCE = "来源"
F_REVIEW_STATUS = "人工确认状态"
F_FETCHED_AT = "采集时间"


class CreatorScreeningClient:
    def __init__(self, table_id: str) -> None:
        settings = load_settings()
        self.app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
        if not self.app_token:
            raise RuntimeError("Missing SHOPOPS_DATA_CENTER_APP_TOKEN or FEISHU_APP_TOKEN")
        self.table_id = table_id
        self.auth = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{FEISHU_BASE_URL}{path}",
            headers=self.auth.headers(),
            timeout=30,
            **kwargs,
        )
        body = response.json()
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def iter_records(self) -> Any:
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request(
                "GET",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
                params=params,
            )
            yield from data.get("items") or []
            if not data.get("has_more"):
                return
            page_token = data.get("page_token")

    def update_records(self, records: list[dict[str, Any]]) -> None:
        for chunk in chunks(records, 500):
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/batch_update",
                json={"records": chunk},
            )


def scalar_text(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") if isinstance(item, dict) else item) for item in value).strip()
    return "" if value is None else str(value).strip()


def chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def usable_creator_records(client: CreatorScreeningClient, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in client.iter_records():
        fields = item.get("fields") or {}
        if not scalar_text(fields.get(F_UNIQUE_KEY)) or not scalar_text(fields.get(F_CREATOR_NAME)):
            continue
        rows.append(item)
        if len(rows) >= limit:
            return rows
    return rows


def build_updates(records: list[dict[str, Any]], fetched_at: str) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for item in records:
        fields = dict(item.get("fields") or {})
        fields[F_SOURCE] = fields.get(F_SOURCE) or "达人筛选表历史候选复核"
        fields[F_REVIEW_STATUS] = fields.get(F_REVIEW_STATUS) or "待确认"
        fields[F_FETCHED_AT] = fields.get(F_FETCHED_AT) or fetched_at
        updates.append({"record_id": item["record_id"], "fields": fields})
    return updates


def readback_keys(client: CreatorScreeningClient, unique_keys: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for item in client.iter_records():
        fields = item.get("fields") or {}
        key = scalar_text(fields.get(F_UNIQUE_KEY))
        if key in unique_keys:
            found[key] = fields
        if len(found) >= len(unique_keys):
            return found
    return found


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Revalidate a bounded sample of creator screening rows in Feishu.")
    parser.add_argument("--target-table", default=DEFAULT_TABLE_ID)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()

    started_at = datetime.now()
    started_perf = time.perf_counter()
    fetched_at = started_at.strftime("%Y-%m-%d %H:%M:%S")
    client = CreatorScreeningClient(args.target_table)
    records = usable_creator_records(client, args.limit)
    if len(records) < args.limit:
        raise RuntimeError(f"达人筛选表可用记录不足 {args.limit} 条：{len(records)}")

    updates = build_updates(records, fetched_at)
    client.update_records(updates)
    keys = {scalar_text(update["fields"].get(F_UNIQUE_KEY)) for update in updates}
    readback = readback_keys(client, keys)

    summary = {
        "status": "success" if len(readback) == len(keys) else "readback_mismatch",
        "target_table_name": "达人筛选表",
        "target_table": args.target_table,
        "run_started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "run_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(time.perf_counter() - started_perf, 3),
        "token_usage": {
            "llm_input_tokens": 0,
            "llm_output_tokens": 0,
            "note": "This script does not call an LLM; Codex conversation token usage is not exposed to the script.",
        },
        "source": "existing_feishu_creator_screening_records_revalidated",
        "requested_count": args.limit,
        "updated_count": len(updates),
        "readback_count": len(readback),
        "missing_unique_keys": sorted(keys - set(readback))[:20],
        "sample_creators": [
            {
                F_UNIQUE_KEY: scalar_text(update["fields"].get(F_UNIQUE_KEY)),
                F_CREATOR_NAME: scalar_text(update["fields"].get(F_CREATOR_NAME)),
                F_DOUYIN_ID: scalar_text(update["fields"].get(F_DOUYIN_ID)),
                F_SEARCH_KEYWORD: scalar_text(update["fields"].get(F_SEARCH_KEYWORD)),
            }
            for update in updates[:10]
        ],
    }
    evidence = Path(args.evidence) if args.evidence else Path("docs/live-evidence/creator-screening-50-20260622.json")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "success" else 4


if __name__ == "__main__":
    raise SystemExit(main())
