from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.services.dynamic_feishu_summary import summary_field_names, summary_number_fields
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient


TEXT_FIELDS = {"unique_key", "统计日期", "平台", "汇总key", "数据状态", "缺失项"}
IGNORED_OLD_FIELDS = {"单选"}
IGNORED_COMPARE_FIELDS = {"汇总时间"}
NULL_ZERO_COMPATIBLE_FIELDS = {
    "投流消耗",
    "已知总投入",
    "投流后毛利",
    "经营利润估算",
    "ROI",
    "平台ROI",
    "利润率",
}


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Compare the static dynamic summary table with the formula-driven summary table.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--old-table-id", default=os.getenv("SHOPOPS_DYNAMIC_SUMMARY_TABLE_ID") or "tbldpguqBhSjnIPP")
    parser.add_argument("--formula-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID") or "tblepMIg19Ov1kSw")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--output", default="docs/live-evidence/formula-dynamic-summary/parity-after.json")
    args = parser.parse_args()

    client = DynamicSummaryFeishuClient(args.app_token, Path(args.env_path))
    old_records = client.list_records(args.old_table_id)
    formula_records = client.list_records(args.formula_table_id)
    old = records_by_key(old_records)
    formula = records_by_key(formula_records)
    old_fields = table_fields(old)
    formula_fields = table_fields(formula)

    expected_old_fields = [field for field in summary_field_names() if field not in IGNORED_OLD_FIELDS]
    missing_in_formula = [field for field in expected_old_fields if field not in formula_fields]
    compare_fields = [
        field
        for field in expected_old_fields
        if field in old_fields and field in formula_fields and field not in IGNORED_COMPARE_FIELDS
    ]
    common_keys = sorted(set(old) & set(formula))
    field_results = {field: compare_field(field, common_keys, old, formula) for field in compare_fields}

    strict_mismatches = sum(result["mismatch_count"] for result in field_results.values())
    null_zero_differences = sum(result["null_zero_difference_count"] for result in field_results.values())
    report = {
        "old_table_id": args.old_table_id,
        "formula_table_id": args.formula_table_id,
        "old_record_count": len(old_records),
        "formula_record_count": len(formula_records),
        "common_key_count": len(common_keys),
        "old_only_key_count": len(set(old) - set(formula)),
        "formula_only_key_count": len(set(formula) - set(old)),
        "missing_in_formula": missing_in_formula,
        "extra_formula_fields": sorted(field for field in formula_fields - old_fields if field != "投流记录数"),
        "formula_helper_fields": sorted(field for field in formula_fields - old_fields if field == "投流记录数"),
        "strict_mismatch_count": strict_mismatches,
        "null_zero_difference_count": null_zero_differences,
        "semantic_mismatch_count": strict_mismatches - null_zero_differences,
        "field_results": field_results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def records_by_key(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        fields = record.get("fields") or {}
        key = fields.get("unique_key")
        if key:
            result[str(key)] = fields
    return result


def table_fields(records: dict[str, dict[str, Any]]) -> set[str]:
    fields: set[str] = set()
    for row in records.values():
        fields.update(row)
    return fields


def compare_field(
    field: str,
    keys: list[str],
    old: dict[str, dict[str, Any]],
    formula: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mismatches: list[dict[str, Any]] = []
    null_zero_differences: list[dict[str, Any]] = []
    matched = 0
    for key in keys:
        left = old[key].get(field)
        right = formula[key].get(field)
        if values_match(field, left, right):
            matched += 1
            continue
        item = {"unique_key": key, "old": scalar(left), "formula": scalar(right)}
        if is_null_zero_difference(field, left, right):
            null_zero_differences.append(item)
        else:
            mismatches.append(item)
    return {
        "matched_count": matched,
        "mismatch_count": len(mismatches) + len(null_zero_differences),
        "semantic_mismatch_count": len(mismatches),
        "null_zero_difference_count": len(null_zero_differences),
        "mismatch_examples": mismatches[:10],
        "null_zero_examples": null_zero_differences[:10],
    }


def values_match(field: str, left: Any, right: Any) -> bool:
    if field in summary_number_fields():
        left_number = number(left)
        right_number = number(right)
        if left_number is None and right_number is None:
            return True
        if left_number is None or right_number is None:
            return False
        return abs(left_number - right_number) <= 0.01
    return str(scalar(left) or "") == str(scalar(right) or "")


def is_null_zero_difference(field: str, left: Any, right: Any) -> bool:
    if field not in NULL_ZERO_COMPATIBLE_FIELDS:
        return False
    left_number = number(left)
    right_number = number(right)
    return (left_number is None and right_number == 0) or (right_number is None and left_number == 0)


def scalar(value: Any) -> Any:
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value)
    return value


def number(value: Any) -> float | None:
    value = scalar(value)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
