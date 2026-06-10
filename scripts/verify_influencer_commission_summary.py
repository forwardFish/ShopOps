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


COMMISSION_FIELDS = [
    "平台",
    "公式_统计日期",
    "支付时间",
    "订单下单时间",
    "下单时间",
    "采集时间",
    "带货费用",
    "预估佣金支出",
    "实际佣金支出",
    "公式_预估佣金支出",
    "公式_实际佣金支出",
    "公式_达人费用",
]
SUMMARY_FIELDS = ["统计日期", "平台", "达人佣金", "预估佣金支出", "实际佣金支出", "订单数", "销售额"]


class FeishuReader:
    def __init__(self) -> None:
        _load_dotenv()
        settings = load_settings()
        self.app_token = settings.shopops_data_center_app_token or settings.feishu_app_token
        if not self.app_token:
            raise RuntimeError("Missing FEISHU_APP_TOKEN or SHOPOPS_DATA_CENTER_APP_TOKEN")
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.session = requests.Session()
        self.session.trust_env = False
        os.environ["NO_PROXY"] = "open.feishu.cn"
        os.environ["no_proxy"] = "open.feishu.cn"

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(method, f"{FEISHU_BASE_URL}{path}", headers=self.client.headers(), timeout=60, **kwargs)
        body = response.json()
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    def field_index(self, table_id: str) -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items") or []:
                if item.get("field_name"):
                    fields[str(item["field_name"])] = item
            if not data.get("has_more"):
                return fields
            page_token = data.get("page_token")

    def records(self, table_id: str, wanted_fields: list[str]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
        existing = self.field_index(table_id)
        field_names = [name for name in wanted_fields if name in existing]
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500, "field_names": json.dumps(field_names, ensure_ascii=False)}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            records.extend(data.get("items") or [])
            if not data.get("has_more"):
                return records, existing, field_names
            page_token = data.get("page_token")


def scalar(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item.get("text") if isinstance(item, dict) else item) for item in value)
    return "" if value is None else str(value)


def number(value: Any) -> float:
    if isinstance(value, list) and value:
        value = value[0].get("text") if isinstance(value[0], dict) else value[0]
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    try:
        text = str(value).replace(",", "").replace("%", "").strip()
        return float(text) if text else 0.0
    except Exception:
        return 0.0


def record_date(fields: dict[str, Any]) -> str:
    for name in ("公式_统计日期", "支付时间", "订单下单时间", "下单时间", "采集时间"):
        value = scalar(fields.get(name)).strip()
        if len(value) >= 10:
            return value[:10]
    return ""


def verify(commission_table: str, summary_table: str, evidence: Path) -> dict[str, Any]:
    reader = FeishuReader()
    commission_records, commission_fields, commission_used = reader.records(commission_table, COMMISSION_FIELDS)
    source_sums: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    formula_nonzero = 0
    for record in commission_records:
        fields = record.get("fields") or {}
        platform = scalar(fields.get("平台"))
        if platform not in {"抖音", "视频号"}:
            continue
        date = record_date(fields)
        if not date.startswith("2026-06-"):
            continue
        for name in ("带货费用", "预估佣金支出", "实际佣金支出", "公式_预估佣金支出", "公式_实际佣金支出", "公式_达人费用"):
            source_sums[(date, platform)][name] += number(fields.get(name))
        if number(fields.get("公式_达人费用")):
            formula_nonzero += 1

    summary_records, _, summary_used = reader.records(summary_table, SUMMARY_FIELDS)
    summary_rows: list[dict[str, Any]] = []
    for record in summary_records:
        fields = record.get("fields") or {}
        platform = scalar(fields.get("平台"))
        date = scalar(fields.get("统计日期"))[:10]
        if platform in {"抖音", "视频号"} and date.startswith("2026-06-"):
            row = {
                "统计日期": date,
                "平台": platform,
                "达人佣金": number(fields.get("达人佣金")),
                "预估佣金支出": number(fields.get("预估佣金支出")),
                "实际佣金支出": number(fields.get("实际佣金支出")),
                "订单数": number(fields.get("订单数")),
                "销售额": number(fields.get("销售额")),
            }
            if row["达人佣金"] or row["预估佣金支出"] or row["实际佣金支出"]:
                summary_rows.append(row)

    result = {
        "status": "success",
        "commission_record_count_read": len(commission_records),
        "commission_fields_used": commission_used,
        "commission_formula_nonzero_rows": formula_nonzero,
        "commission_source_sums": {
            f"{date}|{platform}": {name: round(value, 2) for name, value in values.items()}
            for (date, platform), values in sorted(source_sums.items())
        },
        "summary_record_count_read": len(summary_records),
        "summary_fields_used": summary_used,
        "summary_nonzero_rows": sorted(summary_rows, key=lambda row: (row["统计日期"], row["平台"])),
        "summary_nonzero_count": len(summary_rows),
        "commission_formula_configs": {
            name: (commission_fields.get(name) or {}).get("property", {})
            for name in ("公式_预估佣金支出", "公式_实际佣金支出", "公式_达人费用")
        },
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify influencer commission formulas and formula summary values.")
    parser.add_argument("--commission-table", default="tblhBsehmQbzWEVm")
    parser.add_argument("--summary-table", default="tblepMIg19Ov1kSw")
    parser.add_argument("--evidence", default="docs/live-evidence/influencer-commission-0609-summary-readback.json")
    args = parser.parse_args()
    print(json.dumps(verify(args.commission_table, args.summary_table, Path(args.evidence)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
