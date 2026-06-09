from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import _load_dotenv
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.storage.feishu_bootstrap import (
    FeishuOpenApiClient,
    PlatformTableSpec,
    merge_env_file,
    text_field,
)
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient


SOURCE_TABLE_ID = "tblepMIg19Ov1kSw"
SOURCE_VIEW_ID = "vewQvBlgJF"
SOURCE_TABLE_NAME = "公式动态经营汇总表"
KPI_TABLE_NAME = "经营仪表盘KPI快照表"
TOTAL_PLATFORM = "全平台总计"
FORMULA_FIELD = 20

TEXT_FIELDS = [
    "unique_key",
    "期间",
    "开始日期",
    "结束日期",
    "平台",
    "来源表",
]
FORMULA_TEXT_FIELDS = [
    "数据状态",
    "缺失项",
    "更新时间",
]
FORMULA_NUMBER_FIELDS = [
    "订单数",
    "实际卖出数量",
    "销售额",
    "有效销售额",
    "退款金额",
    "达人佣金",
    "投流消耗",
    "已知总投入",
    "已知费用后利润",
    "投流后毛利",
    "经营利润估算",
    "ROI",
    "平台ROI",
    "已知费用利润率",
    "利润率",
    "展现",
    "点击",
    "投流记录数",
    "源表记录数",
]
PERIODS = (
    ("今日", 0),
    ("最近7天", 6),
    ("最近30天", 29),
)


def scalar(value: Any) -> Any:
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value)
    return value


def text(value: Any) -> str:
    value = scalar(value)
    return "" if value is None else str(value)


def number(value: Any) -> float:
    value = scalar(value)
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").replace("￥", "").replace("元", "").strip())
    except (TypeError, ValueError):
        return 0.0


def parse_record_date(value: Any) -> date | None:
    value = scalar(value)
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and value > 10**12:
        return datetime.fromtimestamp(value / 1000).date()
    raw = str(value).strip()
    if raw.isdigit() and len(raw) >= 13:
        return datetime.fromtimestamp(int(raw[:13]) / 1000).date()
    for candidate in (raw, raw[:19], raw[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def iter_fields(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record.get("fields"), dict):
            rows.append(record["fields"])
        else:
            rows.append(record)
    return rows


def build_kpi_dimension_rows(
    records: list[dict[str, Any]],
    today: date | None = None,
    source_table_id: str = SOURCE_TABLE_ID,
) -> list[dict[str, Any]]:
    today = today or date.today()
    last7_start = today - timedelta(days=6)
    source_rows = iter_fields(records)
    platforms = sorted(
        {text(row.get("平台")) for row in source_rows if text(row.get("平台")) and text(row.get("平台")) != TOTAL_PLATFORM}
    )
    if TOTAL_PLATFORM not in platforms:
        platforms.append(TOTAL_PLATFORM)
    else:
        platforms = [platform for platform in platforms if platform != TOTAL_PLATFORM] + [TOTAL_PLATFORM]
    rows: list[dict[str, Any]] = []
    for period_name, days_back in PERIODS:
        start = today - timedelta(days=days_back)
        end = today
        for platform in platforms:
            rows.append(build_dimension_row(period_name, start, end, platform, source_table_id))
    return rows


def build_kpi_snapshot_rows(
    records: list[dict[str, Any]],
    today: date | None = None,
    source_table_id: str = SOURCE_TABLE_ID,
) -> list[dict[str, Any]]:
    return build_kpi_dimension_rows(records, today=today, source_table_id=source_table_id)


def row_in_scope(row: dict[str, Any], start: date, end: date, platform: str) -> bool:
    stat_date = parse_record_date(row.get("统计日期")) or parse_record_date(row.get("仪表盘日期"))
    if stat_date is None or stat_date < start or stat_date > end:
        return False
    return text(row.get("平台")) == platform


def build_dimension_row(
    period_name: str,
    start: date,
    end: date,
    platform: str,
    source_table_id: str,
) -> dict[str, Any]:
    return {
        "unique_key": f"{period_name}-{platform}",
        "期间": period_name,
        "开始日期": start.isoformat(),
        "结束日期": end.isoformat(),
        "平台": platform,
        "来源表": source_table_id,
    }


def ratio(numerator: float, denominator: float, digits: int = 4) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator, digits)


def kpi_table_spec() -> PlatformTableSpec:
    fields = [text_field(field) for field in TEXT_FIELDS]
    return PlatformTableSpec(
        "SHOPOPS_DASHBOARD_KPI_TABLE_ID",
        "dashboard_kpi_snapshot",
        KPI_TABLE_NAME,
        fields,
    )


class DashboardKpiSnapshotSync:
    def __init__(self, app_token: str, env_path: Path) -> None:
        ensure_feishu_no_proxy()
        self.app_token = app_token
        self.env_path = env_path
        self.helper = DynamicSummaryFeishuClient(app_token, env_path)
        self.client: FeishuOpenApiClient = self.helper.client

    def run(
        self,
        source_table_id: str,
        kpi_table_id: str | None,
        today: date,
        evidence_dir: Path,
    ) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        records = self.helper.list_records(source_table_id)
        rows = build_kpi_dimension_rows(records, today=today, source_table_id=source_table_id)
        table_id = kpi_table_id or self.ensure_kpi_table()
        self.ensure_plain_fields(table_id, kpi_table_spec().fields)
        source_table_name = self.table_name(source_table_id)
        self.ensure_kpi_formula_fields(table_id, source_table_name)
        saved_count = self.helper.upsert_records(table_id, rows)
        time.sleep(5)
        readback = self.readback(table_id, [row["unique_key"] for row in rows], today=today)
        result = {
            "status": "PASS" if readback["matched_count"] == len(rows) else "FAIL",
            "mode": "feishu_formula_kpi",
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "source_table_id": source_table_id,
            "source_table_name": source_table_name,
            "source_view_id": SOURCE_VIEW_ID,
            "kpi_table": {"name": KPI_TABLE_NAME, "table_id": table_id},
            "periods": {
                "today": today.isoformat(),
                "last7_start": (today - timedelta(days=6)).isoformat(),
                "last30_start": (today - timedelta(days=29)).isoformat(),
            },
            "source_record_count": len(records),
            "dimension_row_count": len(rows),
            "saved_count": saved_count,
            "readback": readback,
            "formula_fields": [*FORMULA_NUMBER_FIELDS, *FORMULA_TEXT_FIELDS],
            "dashboard_card_filters": dashboard_card_filters(table_id),
            "rows": rows,
        }
        output = evidence_dir / "dashboard-kpi-formula-result.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(output.resolve())
        return result

    def ensure_kpi_table(self) -> str:
        spec = kpi_table_spec()
        existing = self.client.list_tables(self.app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        table = self.client.ensure_table(self.app_token, spec, existing_by_name)
        table_id = str(table.get("table_id") or "")
        if not table_id:
            raise RuntimeError(f"Feishu table {KPI_TABLE_NAME} did not return table_id")
        merge_env_file(self.env_path, {spec.env_name: table_id, f"{spec.env_name}_NAME": spec.name})
        return table_id

    def table_name(self, table_id: str) -> str:
        for item in self.client.list_tables(self.app_token):
            if str(item.get("table_id") or "") == table_id and item.get("name"):
                return str(item["name"])
        return SOURCE_TABLE_NAME

    def field_index(self, table_id: str) -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.helper.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items", []) or []:
                if item.get("field_name"):
                    fields[str(item["field_name"])] = item
            if not data.get("has_more"):
                return fields
            page_token = data.get("page_token")

    def ensure_plain_fields(self, table_id: str, fields: list[dict[str, Any]]) -> None:
        existing = self.field_index(table_id)
        for field in fields:
            if field["field_name"] in existing:
                continue
            self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", field)

    def ensure_kpi_formula_fields(self, table_id: str, source_table_name: str) -> None:
        self.assert_kpi_dimension_table(table_id)
        for name, config in kpi_formulas(source_table_name).items():
            self.ensure_formula_field(table_id, name, config["expression"], formatter=config.get("formatter", "0.00"))

    def assert_kpi_dimension_table(self, table_id: str) -> None:
        existing = self.field_index(table_id)
        missing = [field for field in ("期间", "开始日期", "结束日期") if field not in existing]
        if missing:
            raise RuntimeError(
                f"Table {table_id} is not a KPI period table; missing dimension fields: {', '.join(missing)}"
            )

    def ensure_formula_field(self, table_id: str, name: str, expression: str, formatter: str) -> None:
        existing = self.field_index(table_id)
        payload = {
            "field_name": name,
            "type": FORMULA_FIELD,
            "property": {"formatter": formatter, "formula_expression": expression},
        }
        current = existing.get(name)
        if not current:
            self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", payload)
            return
        field_id = current.get("field_id")
        self.helper.request("PUT", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields/{field_id}", payload)

    def readback(self, table_id: str, unique_keys: list[str], today: date | None = None) -> dict[str, Any]:
        today = today or date.today()
        expected = set(unique_keys)
        records = self.helper.list_records(table_id)
        seen = {
            str((record.get("fields") or {}).get("unique_key")): record.get("fields") or {}
            for record in records
            if str((record.get("fields") or {}).get("unique_key")) in expected
        }
        samples = {key: seen[key] for key in sorted(seen)[:5]}
        sample_keys = [
            f"今日-{TOTAL_PLATFORM}",
            f"最近7天-{TOTAL_PLATFORM}",
            f"最近30天-{TOTAL_PLATFORM}",
        ]
        total_samples = {key: seen[key] for key in sample_keys if key in seen}
        return {
            "expected_count": len(expected),
            "matched_count": len(seen),
            "missing_keys": sorted(expected - set(seen)),
            "sample_rows": samples,
            "total_platform_rows": total_samples,
        }


def kpi_formulas(summary_table_name: str) -> dict[str, dict[str, str]]:
    summary_filter = period_filter_expr(summary_table_name)
    tmall_refund_filter = period_platform_filter_expr(summary_table_name, "天猫")
    return {
        "订单数": {"expression": f"{summary_filter}.[订单数].SUM()", "formatter": "0"},
        "实际卖出数量": {"expression": f"{summary_filter}.[实际卖出数量].SUM()", "formatter": "0"},
        "销售额": {
            "expression": f'IF([平台]="{TOTAL_PLATFORM}",{summary_filter}.[销售额].SUM()-{tmall_refund_filter}.[退款金额].SUM(),{summary_filter}.[销售额].SUM())',
            "formatter": "0.00",
        },
        "有效销售额": {"expression": f"{summary_filter}.[有效销售额].SUM()", "formatter": "0.00"},
        "退款金额": {"expression": f"{summary_filter}.[退款金额].SUM()", "formatter": "0.00"},
        "达人佣金": {"expression": f"{summary_filter}.[达人佣金].SUM()", "formatter": "0.00"},
        "投流消耗": {"expression": f"{summary_filter}.[投流消耗].SUM()", "formatter": "0.00"},
        "商品成本": {"expression": f"{summary_filter}.[商品成本].SUM()", "formatter": "0.00"},
        "运费成本": {"expression": f"{summary_filter}.[运费成本].SUM()", "formatter": "0.00"},
        "平台扣点": {"expression": f"{summary_filter}.[平台扣点].SUM()", "formatter": "0.00"},
        "其他费用": {"expression": f"{summary_filter}.[其他费用].SUM()", "formatter": "0.00"},
        "已知总投入": {"expression": "IF([投流记录数]=0,0,[投流消耗]+[达人佣金])", "formatter": "0.00"},
        "已知费用后利润": {"expression": "[有效销售额]-[商品成本]-[运费成本]-[平台扣点]-[其他费用]-[达人佣金]-[投流消耗]", "formatter": "0.00"},
        "投流后毛利": {"expression": "IF([投流记录数]=0,0,[有效销售额]-[达人佣金]-[投流消耗])", "formatter": "0.00"},
        "经营利润估算": {"expression": "IF([投流记录数]=0,0,[已知费用后利润])", "formatter": "0.00"},
        "ROI": {"expression": "IF([投流记录数]=0,0,IF([投流消耗]=0,0,[有效销售额]/[投流消耗]))", "formatter": "0.00"},
        "平台ROI": {"expression": "IF([投流记录数]=0,0,IF([已知总投入]=0,0,[有效销售额]/[已知总投入]))", "formatter": "0.00"},
        "已知费用利润率": {"expression": "IF([有效销售额]=0,0,[已知费用后利润]/[有效销售额])", "formatter": "0.00"},
        "利润率": {"expression": "IF([投流记录数]=0,0,IF([有效销售额]=0,0,[经营利润估算]/[有效销售额]))", "formatter": "0.00"},
        "展现": {"expression": f"{summary_filter}.[展现].SUM()", "formatter": "0"},
        "点击": {"expression": f"{summary_filter}.[点击].SUM()", "formatter": "0"},
        "投流记录数": {"expression": f"{summary_filter}.[投流记录数].SUM()", "formatter": "0"},
        "源表记录数": {"expression": f"{summary_filter}.[unique_key].COUNTA()", "formatter": "0"},
        "数据状态": {"expression": 'IF([源表记录数]=0,"partial",IF([订单数]=0,"partial",IF([投流记录数]=0,"partial","normal")))', "formatter": ""},
        "缺失项": {"expression": 'IF([源表记录数]=0,"无源记录",IF([订单数]=0,IF([投流记录数]=0,"订单,投流","订单"),IF([投流记录数]=0,"投流","")))', "formatter": ""},
        "更新时间": {"expression": "NOW()", "formatter": ""},
    }


def period_filter_expr(table_name: str) -> str:
    return (
        f"[{table_name}].FILTER("
        "CurrentValue.[统计日期]>=[开始日期]&&"
        "CurrentValue.[统计日期]<=[结束日期]&&"
        "CurrentValue.[平台]=[平台]"
        ")"
    )


def period_platform_filter_expr(table_name: str, platform: str) -> str:
    return (
        f"[{table_name}].FILTER("
        "CurrentValue.[统计日期]>=[开始日期]&&"
        "CurrentValue.[统计日期]<=[结束日期]&&"
        f'CurrentValue.[平台]="{platform}"'
        ")"
    )


def dashboard_card_filters(table_id: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for period in ("今日", "最近7天", "最近30天"):
        for field in ("订单数", "实际卖出数量", "销售额", "有效销售额", "退款金额", "达人佣金", "投流消耗", "已知费用后利润", "ROI", "平台ROI"):
            cards.append(
                {
                    "card": f"{period}{field}",
                    "source_table_id": table_id,
                    "field": field,
                    "aggregation": "求和",
                    "filter": f'期间 = "{period}" AND 平台 = "全平台总计"',
                }
            )
    return cards


def parse_today(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Sync a Feishu formula-based KPI table for dashboard cards.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--source-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID") or SOURCE_TABLE_ID)
    parser.add_argument("--kpi-table-id", default=os.getenv("SHOPOPS_DASHBOARD_KPI_TABLE_ID"))
    parser.add_argument("--today", default=os.getenv("SHOPOPS_DASHBOARD_TODAY"))
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/feishu-dashboard")
    args = parser.parse_args()
    if not args.app_token:
        raise RuntimeError("Missing Feishu app token")
    result = DashboardKpiSnapshotSync(args.app_token, Path(args.env_path)).run(
        source_table_id=args.source_table_id,
        kpi_table_id=args.kpi_table_id,
        today=parse_today(args.today),
        evidence_dir=Path(args.evidence_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
