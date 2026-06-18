from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.storage.feishu_bootstrap import merge_env_file
from scripts.import_daily_files_to_feishu import FeishuDailyClient, NUMBER_FIELD, TEXT_FIELD, scalar_text


SOURCE_TABLE_NAME = "投流小时段归因汇总"
TARGET_TABLE_NAME = "今日投流效果仪表盘数据"
TARGET_TABLE_ENV = "SHOPOPS_AD_EFFECT_DASHBOARD_TABLE_ID"
DEFAULT_EVIDENCE_DIR = ROOT / "docs" / "live-evidence" / "data-robot"
LOCAL_EVIDENCE_PATTERN = "hourly-shopops-import-*.json"
TOTAL_PLATFORMS = {"总计", "全平台总计"}
DASHBOARD_VIEW_NAMES = ["默认总览", "按小时变化", "按天汇总", "按平台最新"]
DASHBOARD_VIEW_FILTERS = {
    "默认总览": "默认总览",
    "按小时变化": "按小时",
    "按天汇总": "按天",
    "按平台最新": "按平台",
}

TEXT_FIELDS = [
    "unique_key",
    "展示粒度",
    "采集日期",
    "小时",
    "平台",
    "本次采集时间",
    "数据口径",
    "今日投流结论",
]

NUMBER_FIELDS = [
    "排序序号",
    "投流消耗",
    "投流成交金额",
    "投流ROI",
    "订单数",
    "销售额",
    "有效销售额",
    "退款金额",
    "退款率",
    "单订单投流成本",
    "展现量",
    "点击量",
    "点击率",
]

FIELD_TYPES = {**{name: TEXT_FIELD for name in TEXT_FIELDS}, **{name: NUMBER_FIELD for name in NUMBER_FIELDS}}


def text(value: Any) -> str:
    return scalar_text(value).strip()


def number(value: Any) -> float:
    raw = text(value).replace(",", "").replace("元", "").strip()
    if not raw:
        return 0.0
    if raw.endswith("%"):
        raw = raw[:-1]
    try:
        return float(raw)
    except ValueError:
        return 0.0


def parse_time(value: Any) -> datetime | None:
    raw = text(value).replace("T", " ").replace("/", "-")
    if not raw:
        return None
    if "." in raw:
        raw = raw.split(".", 1)[0]
    candidates = [raw, raw[:19], raw[:16], raw[:10]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


def hour_label(row: dict[str, Any]) -> str:
    dt = parse_time(row.get("本次采集时间")) or parse_time(row.get("窗口结束"))
    return dt.strftime("%H:00") if dt else ""


def source_fields(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else record
        if isinstance(fields, dict):
            rows.append(fields)
    return rows


def load_local_hourly_rows(evidence_dir: str | Path = DEFAULT_EVIDENCE_DIR) -> list[dict[str, Any]]:
    """Read locally captured hourly attribution rows as a fallback for Feishu list gaps."""
    path = Path(evidence_dir)
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for evidence_file in sorted(path.glob(LOCAL_EVIDENCE_PATTERN)):
        try:
            data = json.loads(evidence_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = data.get("hourly_interval_summary")
        if not isinstance(summary, dict):
            continue
        summary_rows = summary.get("rows")
        if not isinstance(summary_rows, list):
            continue
        rows.extend(row for row in summary_rows if isinstance(row, dict))
    return rows


def merge_source_rows(feishu_records: Iterable[dict[str, Any]], local_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    anonymous_rows: list[dict[str, Any]] = []
    for row in source_fields(feishu_records):
        key = text(row.get("unique_key"))
        if key:
            merged[key] = row
        else:
            anonymous_rows.append(row)
    for row in local_rows:
        key = text(row.get("unique_key"))
        if key:
            merged[key] = row
        else:
            anonymous_rows.append(row)
    return anonymous_rows + list(merged.values())


def latest_rows_by(rows: Iterable[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(text(row.get(field)) for field in key_fields)
        if not all(key):
            continue
        current = latest.get(key)
        current_time = parse_time(current.get("本次采集时间")) if current else None
        row_time = parse_time(row.get("本次采集时间"))
        if current is None or (row_time or datetime.min) >= (current_time or datetime.min):
            latest[key] = row
    return list(latest.values())


def latest_date(rows: list[dict[str, Any]], preferred: date | None = None) -> str:
    dates = sorted({text(row.get("采集日期")) for row in rows if text(row.get("采集日期"))})
    if preferred and preferred.isoformat() in dates:
        return preferred.isoformat()
    return dates[-1] if dates else (preferred or date.today()).isoformat()


def metric_row(
    row: dict[str, Any],
    *,
    unique_key: str,
    grain: str,
    sort_order: int,
    metric_prefix: str,
    mouth: str,
) -> dict[str, Any]:
    spend = number(row.get(f"{metric_prefix}投流消耗"))
    ad_deal = number(row.get(f"{metric_prefix}投流成交金额"))
    roi = number(row.get(f"{metric_prefix}投流ROI") or row.get(f"{metric_prefix}平台ROI") or row.get(f"{metric_prefix}ROI"))
    orders = number(row.get(f"{metric_prefix}订单数"))
    sales = number(row.get(f"{metric_prefix}销售额"))
    valid_sales = number(row.get(f"{metric_prefix}有效销售额")) or sales
    refund = number(row.get(f"{metric_prefix}退款金额"))
    refund_rate = number(row.get(f"{metric_prefix}退款率"))
    return {
        "unique_key": unique_key,
        "展示粒度": grain,
        "采集日期": text(row.get("采集日期")),
        "小时": hour_label(row),
        "平台": text(row.get("平台")),
        "本次采集时间": text(row.get("本次采集时间")),
        "排序序号": sort_order,
        "投流消耗": round(spend, 6),
        "投流成交金额": round(ad_deal, 6),
        "投流ROI": round(roi, 6),
        "订单数": round(orders, 6),
        "销售额": round(sales, 6),
        "有效销售额": round(valid_sales, 6),
        "退款金额": round(refund, 6),
        "退款率": round(refund_rate, 6),
        "单订单投流成本": round(spend / orders, 6) if orders else 0,
        "展现量": number(row.get("展现量")),
        "点击量": number(row.get("点击量")),
        "点击率": number(row.get("点击率")),
        "数据口径": mouth,
    }


def build_conclusion(row: dict[str, Any]) -> str:
    roi = number(row.get("投流ROI"))
    spend = number(row.get("投流消耗"))
    deal = number(row.get("投流成交金额"))
    valid_sales = number(row.get("有效销售额"))
    orders = int(number(row.get("订单数")))
    cost = number(row.get("单订单投流成本"))
    refund_rate = number(row.get("退款率"))
    status = "达标" if roi >= 2 else "需关注"
    return (
        f"今日最新总览：投流ROI {roi:.2f}，{status}；"
        f"投流消耗 {spend:.2f}，投流成交 {deal:.2f}，有效销售额 {valid_sales:.2f}，订单 {orders}；"
        f"单订单投流成本 {cost:.2f}，退款率 {refund_rate:.2%}。"
    )


def build_dashboard_rows(records: list[dict[str, Any]], today: date | None = None) -> list[dict[str, Any]]:
    rows = source_fields(records)
    if not rows:
        return []
    active_date = latest_date(rows, today)
    rows_for_date = [row for row in rows if text(row.get("采集日期")) == active_date]
    total_rows_for_date = [row for row in rows_for_date if text(row.get("平台")) in TOTAL_PLATFORMS]
    latest_total = latest_rows_by(total_rows_for_date, ("采集日期", "平台"))
    latest_total_row = latest_rows_by(latest_total, ("采集日期",))[0] if latest_total else None

    output: list[dict[str, Any]] = []
    if latest_total_row:
        overview = metric_row(
            latest_total_row,
            unique_key=f"default-{active_date}-latest-total",
            grain="默认总览",
            sort_order=0,
            metric_prefix="今日累计",
            mouth="未筛选时使用：今天最新采集时间的总计行",
        )
        overview["今日投流结论"] = build_conclusion(overview)
        output.append(overview)

    day_rows = latest_rows_by(rows, ("采集日期", "平台"))
    for row in day_rows:
        row_date = text(row.get("采集日期"))
        platform = text(row.get("平台"))
        output.append(
            metric_row(
                row,
                unique_key=f"day-{row_date}-{platform}",
                grain="按天",
                sort_order=100,
                metric_prefix="今日累计",
                mouth="按天看：每天每个平台取当天最新采集时间的累计值",
            )
        )

    hour_rows = [row for row in rows if text(row.get("采集日期")) and text(row.get("平台"))]
    for row in hour_rows:
        row_date = text(row.get("采集日期"))
        row_time = text(row.get("本次采集时间"))
        platform = text(row.get("平台"))
        output.append(
            metric_row(
                row,
                unique_key=f"hour-{row_date}-{row_time}-{platform}",
                grain="按小时",
                sort_order=200,
                metric_prefix="新增",
                mouth="按小时看：每次采集相对上一轮的新增/区间值",
            )
        )

    dates = sorted({text(row.get("采集日期")) for row in rows if text(row.get("采集日期"))})
    for row_date in dates:
        rows_for_platform_date = [row for row in rows if text(row.get("采集日期")) == row_date]
        total_for_platform_date = [row for row in rows_for_platform_date if text(row.get("平台")) in TOTAL_PLATFORMS]
        latest_total_for_date = latest_rows_by(total_for_platform_date, ("采集日期",))
        if latest_total_for_date:
            latest_time = text(latest_total_for_date[0].get("本次采集时间"))
        else:
            times = sorted(text(row.get("本次采集时间")) for row in rows_for_platform_date if text(row.get("本次采集时间")))
            latest_time = times[-1] if times else ""
        platform_rows = [row for row in rows_for_platform_date if text(row.get("本次采集时间")) == latest_time]
        for row in platform_rows:
            platform = text(row.get("平台"))
            output.append(
                metric_row(
                    row,
                    unique_key=f"platform-{row_date}-{platform}",
                    grain="按平台",
                    sort_order=300,
                    metric_prefix="今日累计",
                    mouth="按平台看：所选日期最新采集时间下各平台累计值",
                )
            )

    return output


def list_tables(client: FeishuDailyClient) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    page_token = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        data = client.request("GET", f"/bitable/v1/apps/{client.app_token}/tables", params=params)
        tables.extend(data.get("items") or [])
        if not data.get("has_more"):
            return tables
        page_token = data.get("page_token")


def find_table_id(client: FeishuDailyClient, table_name: str) -> str:
    for table in list_tables(client):
        if text(table.get("name")) == table_name:
            return text(table.get("table_id"))
    return ""


def ensure_dashboard_table(client: FeishuDailyClient, table_id: str = "", env_path: str | Path = ".env") -> str:
    if table_id:
        client.ensure_missing_fields_for_rows(table_id, [FIELD_TYPES], FIELD_TYPES)
        return table_id
    table_id = find_table_id(client, TARGET_TABLE_NAME)
    if table_id:
        client.ensure_missing_fields_for_rows(table_id, [FIELD_TYPES], FIELD_TYPES)
        merge_env_file(env_path, {TARGET_TABLE_ENV: table_id})
        return table_id
    fields = [{"field_name": name, "type": field_type} for name, field_type in FIELD_TYPES.items()]
    data = client.request(
        "POST",
        f"/bitable/v1/apps/{client.app_token}/tables",
        {"table": {"name": TARGET_TABLE_NAME, "default_view_name": "默认总览", "fields": fields}},
    )
    table_id = text(data.get("table_id") or (data.get("table") or {}).get("table_id"))
    if not table_id:
        raise RuntimeError(f"Feishu create table did not return table_id: {data}")
    merge_env_file(env_path, {TARGET_TABLE_ENV: table_id})
    return table_id


def ensure_dashboard_views(client: FeishuDailyClient, table_id: str) -> list[dict[str, Any]]:
    data = client.request("GET", f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/views", params={"page_size": 100})
    views = data.get("items") or []
    existing_names = {text(view.get("view_name")) for view in views}
    for view_name in DASHBOARD_VIEW_NAMES:
        if view_name in existing_names:
            continue
        client.request(
            "POST",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/views",
            {"view_name": view_name, "view_type": "grid"},
        )
    data = client.request("GET", f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/views", params={"page_size": 100})
    views = data.get("items") or []
    grain_field = client.field_index(table_id).get("展示粒度")
    if not grain_field or not grain_field.get("field_id"):
        raise RuntimeError(f"Target table {table_id} is missing 展示粒度 field for dashboard view filters")
    for view in views:
        view_name = text(view.get("view_name"))
        grain = DASHBOARD_VIEW_FILTERS.get(view_name)
        view_id = text(view.get("view_id"))
        if not grain or not view_id:
            continue
        client.request(
            "PATCH",
            f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/views/{view_id}",
            {"property": dashboard_view_filter_property(grain_field, grain)},
        )
    data = client.request("GET", f"/bitable/v1/apps/{client.app_token}/tables/{table_id}/views", params={"page_size": 100})
    return data.get("items") or []


def dashboard_view_filter_property(grain_field: dict[str, Any], grain: str) -> dict[str, Any]:
    return {
        "filter_info": {
            "conditions": [
                {
                    "field_id": grain_field["field_id"],
                    "field_type": int(grain_field.get("type") or TEXT_FIELD),
                    "operator": "is",
                    "value": json.dumps([grain], ensure_ascii=False),
                }
            ],
            "conjunction": "and",
        }
    }


def sync_dashboard_data(
    *,
    source_table_id: str = "",
    target_table_id: str = "",
    env_path: str | Path = ".env",
    evidence_dir: str | Path = DEFAULT_EVIDENCE_DIR,
    today: date | None = None,
) -> dict[str, Any]:
    client = FeishuDailyClient()
    source_table_id = source_table_id or os.getenv("SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID") or find_table_id(client, SOURCE_TABLE_NAME)
    if not source_table_id:
        raise RuntimeError(f"Cannot find source table: {SOURCE_TABLE_NAME}")
    target_table_id = ensure_dashboard_table(client, target_table_id or os.getenv(TARGET_TABLE_ENV, ""), env_path)
    source_records = list(client.iter_records(source_table_id))
    local_rows = load_local_hourly_rows(evidence_dir)
    merged_rows = merge_source_rows(source_records, local_rows)
    rows = build_dashboard_rows(merged_rows, today=today)
    client.ensure_missing_fields_for_rows(target_table_id, rows, FIELD_TYPES)
    result = client.upsert_rows(
        table_id=target_table_id,
        rows=rows,
        required_fields=["unique_key"],
        fallback_match_fields=("展示粒度", "采集日期", "小时", "平台"),
        allow_partial_fields=False,
    )
    views = ensure_dashboard_views(client, target_table_id)
    return {
        "status": "PASS",
        "source_table_id": source_table_id,
        "target_table_id": target_table_id,
        "target_table_name": TARGET_TABLE_NAME,
        "target_url": f"https://my.feishu.cn/base/{client.app_token}?table={target_table_id}",
        "source_feishu_rows": len(source_records),
        "source_local_evidence_rows": len(local_rows),
        "source_merged_rows": len(merged_rows),
        "row_count": len(rows),
        "rows_by_grain": {grain: sum(1 for row in rows if row.get("展示粒度") == grain) for grain in ["默认总览", "按天", "按小时", "按平台"]},
        "views": views,
        "upsert": result,
        "default_overview": next((row for row in rows if row.get("展示粒度") == "默认总览"), {}),
    }


def parse_today(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Sync normalized ad-effect dashboard data for day/hour/platform analysis.")
    parser.add_argument("--source-table-id", default=os.getenv("SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID"))
    parser.add_argument("--target-table-id", default=os.getenv(TARGET_TABLE_ENV))
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default=str(DEFAULT_EVIDENCE_DIR))
    parser.add_argument("--today", default=os.getenv("SHOPOPS_DASHBOARD_TODAY"))
    parser.add_argument("--output-json", default="docs/live-evidence/feishu-dashboard/ad-effect-dashboard-data-sync.json")
    args = parser.parse_args()

    result = sync_dashboard_data(
        source_table_id=args.source_table_id,
        target_table_id=args.target_table_id,
        env_path=args.env_path,
        evidence_dir=args.evidence_dir,
        today=parse_today(args.today),
    )
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result | {"evidence_path": str(output.resolve())}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
