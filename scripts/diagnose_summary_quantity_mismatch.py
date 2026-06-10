from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from collections import Counter
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv, load_settings
from shopops.services.product_breakdown import DEFAULT_PRODUCT_CATALOG_TABLE_ID, product_rules_from_records
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient


SUMMARY_TABLE_ID = "tblepMIg19Ov1kSw"
ORDER_TABLES = {
    "天猫": "tbl0gBiMcAKMCcwI",
    "抖音": "tblTbbFkEepZAGru",
    "拼多多": "tblFI9ZNPzrjR6Jm",
    "视频号": "tblFlMuPnVEn8qkw",
}
DATA_NOT_READY_CODE = 1254607


class FeishuReader:
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

    def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        for attempt in range(8):
            response = self.session.request(
                method,
                f"{FEISHU_BASE_URL}{path}",
                headers=self.auth.headers(),
                params=params,
                timeout=60,
            )
            body = response.json()
            if response.status_code < 400 and body.get("code") == 0:
                return body.get("data") or {}
            if body.get("code") == DATA_NOT_READY_CODE and attempt < 7:
                time.sleep(2 + attempt)
                continue
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        raise RuntimeError(f"Feishu API {method} {path} failed unexpectedly")

    def records(self, table_id: str, field_names: list[str] | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            if field_names:
                params["field_names"] = json.dumps(field_names, ensure_ascii=False)
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


def date_text(value: Any) -> str:
    text = scalar(value)
    return text[:10] if len(text) >= 10 else text


def diagnose(target_key: str, evidence: Path) -> dict[str, Any]:
    reader = FeishuReader()
    rules = product_rules_from_records(reader.records(DEFAULT_PRODUCT_CATALOG_TABLE_ID))
    quantity_fields = [rule.quantity_field for rule in rules]
    main_quantity_fields = [rule.quantity_field for rule in rules if rule.name not in {"配件", "补差价"}]
    valid_sales_fields = [rule.valid_sales_field for rule in rules]
    summary_fields = ["统计日期", "平台", "实际卖出数量", *quantity_fields, *valid_sales_fields]

    summary_mismatches: list[dict[str, Any]] = []
    target_summary: dict[str, Any] | None = None
    target_date, target_platform = target_key.split("-", 3)[0:3], target_key.rsplit("-", 1)[-1]
    target_date_text = "-".join(target_date)

    for record in reader.records(SUMMARY_TABLE_ID, summary_fields):
        fields = record.get("fields") or {}
        stat_date = date_text(fields.get("统计日期"))
        platform = scalar(fields.get("平台"))
        if platform not in ORDER_TABLES or not stat_date:
            continue
        actual = number(fields.get("实际卖出数量"))
        product_quantity_total = sum(number(fields.get(field)) for field in quantity_fields)
        main_product_quantity_total = sum(number(fields.get(field)) for field in main_quantity_fields)
        cleanser = number(fields.get("洗面奶数量"))
        row = {
            "record_id": record.get("record_id"),
            "统计日期": stat_date,
            "平台": platform,
            "实际卖出数量": actual,
            "洗面奶数量": cleanser,
            "主商品数量合计": round(main_product_quantity_total, 6),
            "商品数量合计": round(product_quantity_total, 6),
            "洗面奶数量-实际卖出数量": round(cleanser - actual, 6),
            "主商品数量合计-实际卖出数量": round(main_product_quantity_total - actual, 6),
            "商品数量合计-实际卖出数量": round(product_quantity_total - actual, 6),
        }
        if stat_date == target_date_text and platform == target_platform:
            target_summary = row
        if cleanser > actual or main_product_quantity_total > actual:
            summary_mismatches.append(row)

    order_fields = [
        "unique_key",
        "商品名称",
        "公式_统计日期",
        "公式_实际卖出数量",
        "公式_有效销售额",
        *quantity_fields,
        *valid_sales_fields,
    ]
    order_rollups: dict[str, dict[str, Any]] = {}
    target_order_samples: list[dict[str, Any]] = []
    order_mismatch_days: list[dict[str, Any]] = []
    for platform, table_id in ORDER_TABLES.items():
        by_date: dict[str, dict[str, float]] = defaultdict(lambda: {"actual": 0.0, "cleanser": 0.0, "product_total": 0.0, "main_product_total": 0.0})
        for record in reader.records(table_id, order_fields):
            fields = record.get("fields") or {}
            stat_date = date_text(fields.get("公式_统计日期"))
            if not stat_date:
                continue
            actual = number(fields.get("公式_实际卖出数量"))
            cleanser = number(fields.get("洗面奶数量"))
            product_total = sum(number(fields.get(field)) for field in quantity_fields)
            main_product_total = sum(number(fields.get(field)) for field in main_quantity_fields)
            by_date[stat_date]["actual"] += actual
            by_date[stat_date]["cleanser"] += cleanser
            by_date[stat_date]["product_total"] += product_total
            by_date[stat_date]["main_product_total"] += main_product_total
            if platform == target_platform and stat_date == target_date_text and (cleanser > actual or main_product_total > actual) and len(target_order_samples) < 30:
                target_order_samples.append(
                    {
                        "record_id": record.get("record_id"),
                        "unique_key": scalar(fields.get("unique_key")),
                        "商品名称": scalar(fields.get("商品名称")),
                        "公式_实际卖出数量": actual,
                        "公式_有效销售额": number(fields.get("公式_有效销售额")),
                        **{field: number(fields.get(field)) for field in [*quantity_fields, *valid_sales_fields] if number(fields.get(field))},
                    }
                )
        for stat_date, values in sorted(by_date.items()):
            actual = values["actual"]
            cleanser = values["cleanser"]
            product_total = values["product_total"]
            main_product_total = values["main_product_total"]
            row = {
                "统计日期": stat_date,
                "平台": platform,
                "实际卖出数量": round(actual, 6),
                "洗面奶数量": round(cleanser, 6),
                "主商品数量合计": round(main_product_total, 6),
                "商品数量合计": round(product_total, 6),
                "洗面奶数量-实际卖出数量": round(cleanser - actual, 6),
                "主商品数量合计-实际卖出数量": round(main_product_total - actual, 6),
                "商品数量合计-实际卖出数量": round(product_total - actual, 6),
            }
            if stat_date == target_date_text and platform == target_platform:
                order_rollups["target"] = row
            if cleanser > actual or main_product_total > actual:
                order_mismatch_days.append(row)

    result = {
        "status": "success",
        "target_key": target_key,
        "target_summary": target_summary,
        "target_order_rollup": order_rollups.get("target"),
        "target_order_samples": target_order_samples,
        "summary_mismatch_count": len(summary_mismatches),
        "summary_mismatch_count_by_platform": dict(Counter(row["平台"] for row in summary_mismatches)),
        "summary_mismatch_examples": summary_mismatches[:50],
        "order_mismatch_day_count": len(order_mismatch_days),
        "order_mismatch_day_count_by_platform": dict(Counter(row["平台"] for row in order_mismatch_days)),
        "order_mismatch_day_examples": order_mismatch_days[:50],
        "explanation": "实际卖出数量来自订单表公式_实际卖出数量；修正后应等于主商品数量合计，并排除配件、补差价等非主商品数量。",
    }
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose summary actual quantity versus product breakdown quantity mismatches.")
    parser.add_argument("--target-key", default="2026-04-24-抖音")
    parser.add_argument("--evidence", default="docs/live-evidence/product-breakdown/summary-quantity-mismatch-diagnosis.json")
    args = parser.parse_args()
    print(json.dumps(diagnose(args.target_key, Path(args.evidence)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
