from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


FIELDS = [
    "unique_key",
    "商品名称",
    "数量",
    "公式_实际卖出数量",
    "公式_有效销售额",
    "配件数量",
    "配件有效销售额",
    "补差价数量",
    "补差价有效销售额",
    "原始数据",
]


class Client:
    def __init__(self) -> None:
        _load_dotenv()
        settings = load_settings()
        self.app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
        self.auth = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(method, FEISHU_BASE_URL + path, headers=self.auth.headers(), timeout=60, **kwargs)
        body = response.json()
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"{method} {path} failed {response.status_code}: {body}")
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
        fields = [field for field in FIELDS if field in self.field_names(table_id)]
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


def scalar(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") if isinstance(item, dict) else item) for item in value).strip()
    return "" if value is None else str(value).strip()


def number(value: Any) -> float:
    if isinstance(value, list) and value:
        value = value[0].get("text") if isinstance(value[0], dict) else value[0]
    try:
        text = str(value).replace(",", "").strip()
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def raw_quantity(raw_text: str) -> Any:
    try:
        raw = json.loads(raw_text)
    except Exception:
        return None
    row = raw.get("row") if isinstance(raw, dict) else raw
    if not isinstance(row, dict):
        return None
    for key in ("商品数量", "商品数量(件)", "宝贝总数量", "数量"):
        if key in row:
            return row.get(key)
    return None


def inspect(table_id: str, evidence: Path) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    counters = {"accessory_sales_nonzero_qty_zero": 0, "price_diff_sales_nonzero_qty_zero": 0}
    for record in Client().records(table_id):
        fields = record.get("fields") or {}
        accessory_problem = number(fields.get("配件有效销售额")) and not number(fields.get("配件数量"))
        price_diff_problem = number(fields.get("补差价有效销售额")) and not number(fields.get("补差价数量"))
        if accessory_problem:
            counters["accessory_sales_nonzero_qty_zero"] += 1
        if price_diff_problem:
            counters["price_diff_sales_nonzero_qty_zero"] += 1
        if (accessory_problem or price_diff_problem) and len(samples) < 30:
            samples.append(
                {
                    "record_id": record.get("record_id"),
                    "unique_key": scalar(fields.get("unique_key")),
                    "商品名称": scalar(fields.get("商品名称")),
                    "数量": scalar(fields.get("数量")),
                    "公式_实际卖出数量": scalar(fields.get("公式_实际卖出数量")),
                    "公式_有效销售额": scalar(fields.get("公式_有效销售额")),
                    "配件数量": scalar(fields.get("配件数量")),
                    "配件有效销售额": scalar(fields.get("配件有效销售额")),
                    "补差价数量": scalar(fields.get("补差价数量")),
                    "补差价有效销售额": scalar(fields.get("补差价有效销售额")),
                    "原始数量": raw_quantity(scalar(fields.get("原始数据"))),
                }
            )
    result = {"status": "success", "table_id": table_id, **counters, "samples": samples}
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table-id", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.table_id, Path(args.evidence)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
