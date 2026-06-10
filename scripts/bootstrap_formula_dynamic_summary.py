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

from shopops.config import _load_dotenv, load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.services.dynamic_feishu_summary import (
    AD_COST_FIELDS,
    CLICK_FIELDS,
    COMMISSION_AMOUNT_FIELDS,
    COMMISSION_ESTIMATED_FIELDS,
    COMMISSION_SERVICE_FEE_FIELDS,
    COMMISSION_SETTLED_FIELDS,
    FREIGHT_COST_FIELDS,
    IMPRESSION_FIELDS,
    ORDER_REFUND_FIELDS,
    ORDER_QUANTITY_FIELDS,
    ORDER_SALES_FIELDS,
    ORDER_VALID_SALES_FIELDS,
    OTHER_FEE_FIELDS,
    PLATFORM_FEE_FIELDS,
    PRODUCT_COST_FIELDS,
    summary_field_names,
)
from shopops.services.product_breakdown import (
    DEFAULT_PRODUCT_CATALOG_TABLE_ID,
    ProductRule,
    order_product_formula_fields,
    product_field_names,
    product_rules_from_records,
    summary_product_formula_fields,
    total_product_formula_fields,
)
from shopops.storage.feishu_bootstrap import (
    NUMBER_FIELD,
    TEXT_FIELD,
    FeishuOpenApiClient,
    PlatformTableSpec,
    merge_env_file,
    text_field,
)
from scripts.run_dynamic_feishu_summary import DynamicSummaryFeishuClient, chunks


FORMULA_FIELD = 20
SINGLE_SELECT_FIELD = 3
ORDER_FORMULA_DATE_ALIASES = ("创建时间", "订单创建时间", "订单下单时间", "下单时间", "订单提交时间", "订单成交时间")
FORMULA_SUMMARY_TABLE_NAME = "公式动态经营汇总表"
FORMULA_TOTAL_SUMMARY_TABLE_NAME = "全周期平台总计表"
TOTAL_PLATFORM = "全平台总计"
SHOP_NAME_FIELD = "店铺名称"
PRODUCT_NAME_FIELD = "商品名称"
ACCESSORY_FLAG_FIELD = "是否是配件"
PLATFORMS = ("天猫", "抖音", "拼多多", "视频号", TOTAL_PLATFORM)
PLATFORM_ORDER_TABLE_ENVS = (
    "SHOPOPS_ORDER_TABLE_TMALL_ID",
    "SHOPOPS_ORDER_TABLE_DOUYIN_ID",
    "SHOPOPS_ORDER_TABLE_PINDUODUO_ID",
    "SHOPOPS_ORDER_TABLE_WECHAT_CHANNELS_ID",
)


class FormulaSummaryBootstrap:
    def __init__(self, app_token: str, env_path: Path) -> None:
        ensure_feishu_no_proxy()
        self.settings = load_settings()
        self.app_token = app_token
        self.env_path = env_path
        self.client = FeishuOpenApiClient(self.settings.feishu_app_id, self.settings.feishu_app_secret)
        self.helper = DynamicSummaryFeishuClient(app_token, env_path)

    def run(
        self,
        order_table_id: str,
        order_table_ids: list[str] | None,
        ad_table_id: str,
        commission_table_id: str,
        summary_table_id: str | None,
        total_summary_table_id: str | None,
        days_ahead: int,
        evidence_dir: Path,
        refresh_source_dates: bool,
        total_only: bool = False,
    ) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        order_table_ids = unique_values(order_table_ids or [order_table_id])
        required_source_table_ids = () if total_only else (*order_table_ids, ad_table_id, commission_table_id)
        table_names = self.table_names_by_id(required_source_table_ids)
        source_names = {
            "orders": [table_names.get(table_id, table_id) for table_id in order_table_ids],
            "ads": table_names.get(ad_table_id, ad_table_id),
            "commissions": table_names.get(commission_table_id, commission_table_id),
        }
        product_table_id = os.getenv("SHOPOPS_PRODUCT_CATALOG_TABLE_ID", DEFAULT_PRODUCT_CATALOG_TABLE_ID).strip()
        product_rules = self.product_rules(product_table_id)
        dimension_source = "source_tables"
        rows: list[dict[str, Any]] = []
        saved = 0
        if not total_only:
            self.ensure_source_helper_formulas(order_table_ids, ad_table_id, commission_table_id, product_rules)
            summary_table_id = summary_table_id or self.ensure_formula_summary_table()
            self.ensure_summary_formula_fields(summary_table_id, source_names, product_rules)
            if not refresh_source_dates:
                rows = self.dimension_rows_from_summary(summary_table_id, days_ahead)
                if rows:
                    dimension_source = "existing_summary"
            if not rows:
                rows = self.dimension_rows(order_table_ids, ad_table_id, commission_table_id, days_ahead)
            saved = self.upsert_dimension_rows(summary_table_id, rows)
        total_summary_table_id = total_summary_table_id or self.ensure_formula_total_summary_table()
        if not summary_table_id:
            summary_table_id = self.ensure_formula_summary_table()
        summary_table_name = table_names.get(summary_table_id, FORMULA_SUMMARY_TABLE_NAME)
        self.ensure_total_summary_formula_fields(total_summary_table_id, summary_table_name, product_rules)
        total_rows = self.total_dimension_rows_from_summary(summary_table_id) if summary_table_id else self.total_dimension_rows()
        total_saved = self.upsert_total_dimension_rows(total_summary_table_id, total_rows)
        time.sleep(5)
        records = self.helper.list_records(summary_table_id) if summary_table_id and not total_only else []
        total_records = self.helper.list_records(total_summary_table_id)
        readback = self.summarize_readback(records) if records else {}
        total_readback = self.summarize_total_readback(total_records)
        result = {
            "mode": "feishu_formula",
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "summary_table": {"name": FORMULA_SUMMARY_TABLE_NAME, "table_id": summary_table_id},
            "total_summary_table": {"name": FORMULA_TOTAL_SUMMARY_TABLE_NAME, "table_id": total_summary_table_id},
            "source_table_ids": {
                "orders": order_table_ids,
                "ads": ad_table_id,
                "commissions": commission_table_id,
            },
            "source_table_names": source_names,
            "dimension_rows": len(rows),
            "saved_dimension_rows": saved,
            "total_dimension_rows": len(total_rows),
            "saved_total_dimension_rows": total_saved,
            "readback": readback,
            "total_readback": total_readback,
            "days_ahead": days_ahead,
            "dimension_source": dimension_source,
            "formula_fields": FORMULA_SUMMARY_FORMULA_NAMES,
            "total_formula_fields": FORMULA_TOTAL_SUMMARY_FORMULA_NAMES,
            "product_breakdown": {
                "product_table_id": product_table_id,
                "products": [rule.name for rule in product_rules],
                "fields": product_field_names(product_rules),
            },
        }
        path = evidence_dir / "formula-summary-result.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(path.resolve())
        return result

    def table_names_by_id(self, required_table_ids: tuple[str, ...] = ()) -> dict[str, str]:
        tables = self.client.list_tables(self.app_token)
        result = {str(item.get("table_id")): str(item.get("name")) for item in tables if item.get("table_id") and item.get("name")}
        missing = [table_id for table_id in required_table_ids if table_id and table_id not in result]
        if missing:
            raise RuntimeError("Cannot find source table names for ids: " + ", ".join(missing))
        return result

    def product_rules(self, product_table_id: str) -> list[ProductRule]:
        return product_rules_from_records(self.helper.list_records(product_table_id))

    def ensure_source_helper_formulas(
        self,
        order_table_ids: list[str],
        ad_table_id: str,
        commission_table_id: str,
        product_rules: list[ProductRule],
    ) -> None:
        for order_table_id in order_table_ids:
            self.ensure_order_helper_formulas(order_table_id, product_rules)
        self.ensure_ad_commission_helper_formulas(ad_table_id, commission_table_id)

    def ensure_order_helper_formulas(self, order_table_id: str, product_rules: list[ProductRule] | None = None) -> None:
        order_fields = self.field_index(order_table_id)
        self.ensure_select_field(order_table_id, ACCESSORY_FLAG_FIELD, ("是", "否"))
        order_fields = self.field_index(order_table_id)

        self.ensure_formula_field(order_table_id, "公式_统计日期", formula_date_expr(order_fields, ORDER_FORMULA_DATE_ALIASES), formatter="")
        self.ensure_formula_field(order_table_id, "公式_汇总平台", NORMALIZE_PLATFORM_EXPR, formatter="")
        self.ensure_formula_field(order_table_id, "公式_销售额", first_number_expr(order_fields, ORDER_SALES_FIELDS), formatter="0.00")
        self.ensure_formula_field(order_table_id, "公式_退款金额", first_number_expr(order_fields, ORDER_REFUND_FIELDS), formatter="0.00")
        self.ensure_formula_field(
            order_table_id,
            "公式_有效销售额",
            first_number_expr(order_fields, ORDER_VALID_SALES_FIELDS, default="[公式_销售额]-[公式_退款金额]"),
            formatter="0.00",
        )
        order_fields = self.field_index(order_table_id)
        self.ensure_formula_field(order_table_id, "公式_实际卖出数量", actual_sold_quantity_expr(order_fields, product_rules), formatter="0")
        self.ensure_formula_field(order_table_id, "公式_商品成本", first_number_expr(order_fields, PRODUCT_COST_FIELDS), formatter="0.00")
        self.ensure_formula_field(order_table_id, "公式_运费成本", first_number_expr(order_fields, FREIGHT_COST_FIELDS), formatter="0.00")
        self.ensure_formula_field(order_table_id, "公式_平台扣点", first_number_expr(order_fields, PLATFORM_FEE_FIELDS), formatter="0.00")
        self.ensure_formula_field(order_table_id, "公式_其他费用", first_number_expr(order_fields, OTHER_FEE_FIELDS), formatter="0.00")
        for name, config in order_product_formula_fields(product_rules or []).items():
            self.ensure_formula_field(order_table_id, name, config["expression"], formatter=config["formatter"])

    def ensure_ad_commission_helper_formulas(self, ad_table_id: str, commission_table_id: str) -> None:
        ad_fields = self.field_index(ad_table_id)
        commission_fields = self.field_index(commission_table_id)

        self.ensure_formula_field(ad_table_id, "公式_统计日期", formula_date_expr(ad_fields, ("统计日期", "投放日期", "日期", "采集时间", "更新时间", "投放时间")), formatter="")
        self.ensure_formula_field(ad_table_id, "公式_汇总平台", NORMALIZE_PLATFORM_EXPR, formatter="")
        self.ensure_formula_field(ad_table_id, "公式_投流消耗", first_number_expr(ad_fields, (*AD_COST_FIELDS, "推广花费(元)")), formatter="0.00")
        self.ensure_formula_field(ad_table_id, "公式_展现", first_number_expr(ad_fields, IMPRESSION_FIELDS), formatter="0")
        self.ensure_formula_field(ad_table_id, "公式_点击", first_number_expr(ad_fields, CLICK_FIELDS), formatter="0")

        self.ensure_formula_field(commission_table_id, "公式_统计日期", formula_date_expr(commission_fields, ("统计日期", "结算日期", "下单日期", "日期", "支付时间", "订单下单时间", "下单时间", "采集时间", "更新时间")), formatter="")
        self.ensure_formula_field(commission_table_id, "公式_汇总平台", NORMALIZE_PLATFORM_EXPR, formatter="")
        self.ensure_formula_field(
            commission_table_id,
            "公式_预估佣金支出",
            first_number_expr(commission_fields, COMMISSION_ESTIMATED_FIELDS),
            formatter="0.00",
        )
        self.ensure_formula_field(
            commission_table_id,
            "公式_实际佣金支出",
            first_number_expr(commission_fields, COMMISSION_SETTLED_FIELDS),
            formatter="0.00",
        )
        self.ensure_formula_field(
            commission_table_id,
            "公式_达人费用",
            first_commission_expr(commission_fields),
            formatter="0.00",
        )

    def ensure_formula_summary_table(self) -> str:
        existing = self.client.list_tables(self.app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        spec = PlatformTableSpec(
            "SHOPOPS_FORMULA_SUMMARY_TABLE_ID",
            "formula_dynamic_summary",
            FORMULA_SUMMARY_TABLE_NAME,
            [text_field("unique_key"), text_field("统计日期"), text_field("平台"), text_field(SHOP_NAME_FIELD), text_field(PRODUCT_NAME_FIELD)],
        )
        table = self.client.ensure_table(self.app_token, spec, existing_by_name)
        table_id = str(table.get("table_id") or "")
        if not table_id:
            raise RuntimeError(f"Feishu table {FORMULA_SUMMARY_TABLE_NAME} did not return table_id")
        self.ensure_plain_fields(table_id, spec.fields)
        merge_env_file(self.env_path, {"SHOPOPS_FORMULA_SUMMARY_TABLE_ID": table_id})
        return table_id

    def ensure_formula_total_summary_table(self) -> str:
        existing = self.client.list_tables(self.app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        spec = PlatformTableSpec(
            "SHOPOPS_FORMULA_TOTAL_SUMMARY_TABLE_ID",
            "formula_total_summary",
            FORMULA_TOTAL_SUMMARY_TABLE_NAME,
            [text_field("unique_key"), text_field("统计范围"), text_field("平台"), text_field(SHOP_NAME_FIELD), text_field(PRODUCT_NAME_FIELD)],
        )
        table = self.client.ensure_table(self.app_token, spec, existing_by_name)
        table_id = str(table.get("table_id") or "")
        if not table_id:
            raise RuntimeError(f"Feishu table {FORMULA_TOTAL_SUMMARY_TABLE_NAME} did not return table_id")
        self.ensure_plain_fields(table_id, spec.fields)
        merge_env_file(self.env_path, {"SHOPOPS_FORMULA_TOTAL_SUMMARY_TABLE_ID": table_id})
        return table_id

    def ensure_summary_formula_fields(
        self,
        table_id: str,
        source_names: dict[str, Any],
        product_rules: list[ProductRule] | None = None,
    ) -> None:
        self.ensure_plain_fields(table_id, [text_field("unique_key"), text_field("统计日期"), text_field("平台"), text_field(SHOP_NAME_FIELD), text_field(PRODUCT_NAME_FIELD)])
        formulas = summary_formulas(source_names)
        formulas.update(summary_product_formula_fields(source_names["orders"], product_rules or []))
        for name, config in formulas.items():
            self.ensure_formula_field(table_id, name, config["expression"], formatter=config.get("formatter", "0.00"))

    def ensure_total_summary_formula_fields(
        self,
        table_id: str,
        summary_table_name: str,
        product_rules: list[ProductRule] | None = None,
    ) -> None:
        self.ensure_plain_fields(table_id, [text_field("unique_key"), text_field("统计范围"), text_field("平台"), text_field(SHOP_NAME_FIELD), text_field(PRODUCT_NAME_FIELD)])
        formulas = total_summary_formulas(summary_table_name)
        formulas.update(total_product_formula_fields(summary_table_name, product_rules or []))
        for name, config in formulas.items():
            self.ensure_formula_field(table_id, name, config["expression"], formatter=config.get("formatter", "0.00"))

    def ensure_plain_fields(self, table_id: str, fields: list[dict[str, Any]]) -> None:
        existing = self.field_index(table_id)
        for field in fields:
            if field["field_name"] in existing:
                continue
            self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", field)

    def ensure_select_field(self, table_id: str, name: str, options: tuple[str, ...]) -> None:
        existing = self.field_index(table_id)
        payload = {
            "field_name": name,
            "type": SINGLE_SELECT_FIELD,
            "property": {"options": [{"name": option} for option in options]},
        }
        current = existing.get(name)
        if not current:
            self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", payload)
            return
        if int(current.get("type") or 0) != SINGLE_SELECT_FIELD:
            raise RuntimeError(f"Field {name} exists in {table_id} but is not a single select field")

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
        if int(current.get("type") or 0) != FORMULA_FIELD:
            raise RuntimeError(f"Field {name} exists in {table_id} but is not a formula field")
        field_id = current.get("field_id")
        self.helper.request("PUT", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields/{field_id}", payload)

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

    def dimension_rows(self, order_table_ids: list[str], ad_table_id: str, commission_table_id: str, days_ahead: int) -> list[dict[str, Any]]:
        dates = set()
        sources = [
            (ad_table_id, ("采集时间",)),
            (commission_table_id, ("支付时间", "订单下单时间", "采集时间")),
        ]
        sources.extend((table_id, ("创建时间",)) for table_id in order_table_ids)
        for table_id, fields in sources:
            for record in self.helper.list_records(table_id):
                source = record.get("fields") or {}
                parsed = None
                for field in fields:
                    parsed = parse_date(source.get(field))
                    if parsed:
                        dates.add(parsed)
                        break
        today = date.today()
        for offset in range(days_ahead + 1):
            dates.add(today + timedelta(days=offset))
        rows: list[dict[str, Any]] = []
        for day in sorted(dates):
            day_text = day.isoformat()
            for platform in PLATFORMS:
                rows.append(dimension_row(day_text, platform))
        return rows

    def dimension_rows_from_summary(self, table_id: str, days_ahead: int) -> list[dict[str, Any]]:
        dates: set[date] = set()
        extra_platforms: set[str] = set()
        for record in self.helper.list_records(table_id):
            fields = record.get("fields") or {}
            parsed = parse_date(fields.get("统计日期"))
            if parsed:
                dates.add(parsed)
            platform = str(fields.get("平台") or "").strip()
            if platform and platform not in PLATFORMS:
                extra_platforms.add(platform)
        if not dates:
            return []
        today = date.today()
        for offset in range(days_ahead + 1):
            dates.add(today + timedelta(days=offset))
        platforms = [*PLATFORMS, *sorted(extra_platforms)]
        rows: list[dict[str, Any]] = []
        for day in sorted(dates):
            day_text = day.isoformat()
            for platform in platforms:
                rows.append(dimension_row(day_text, platform))
        return rows

    def total_dimension_rows_from_summary(self, summary_table_id: str) -> list[dict[str, Any]]:
        platforms: set[str] = set(PLATFORMS)
        for record in self.helper.list_records(summary_table_id):
            fields = record.get("fields") or {}
            platform = str(fields.get("平台") or "").strip()
            if platform:
                platforms.add(platform)
        ordered = [platform for platform in PLATFORMS if platform in platforms]
        ordered.extend(sorted(platform for platform in platforms if platform not in PLATFORMS))
        return [total_dimension_row(platform) for platform in ordered]

    def total_dimension_rows(self) -> list[dict[str, Any]]:
        return [total_dimension_row(platform) for platform in PLATFORMS]

    def upsert_dimension_rows(self, table_id: str, rows: list[dict[str, Any]]) -> int:
        index = self.record_index(table_id)
        to_create: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        for row in rows:
            existing = index.get(row["unique_key"])
            if existing:
                if dimension_row_matches(existing["fields"], row):
                    continue
                to_update.append({"record_id": existing["record_id"], "fields": row})
            else:
                to_create.append({"fields": row})
        saved = 0
        for chunk in chunks(to_create, 500):
            if chunk:
                self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create", {"records": chunk})
                saved += len(chunk)
        for chunk in chunks(to_update, 500):
            if chunk:
                self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
                saved += len(chunk)
        return saved

    def upsert_total_dimension_rows(self, table_id: str, rows: list[dict[str, Any]]) -> int:
        index = self.record_index(table_id)
        to_create: list[dict[str, Any]] = []
        to_update: list[dict[str, Any]] = []
        for row in rows:
            existing = index.get(row["unique_key"])
            if existing:
                if total_dimension_row_matches(existing["fields"], row):
                    continue
                to_update.append({"record_id": existing["record_id"], "fields": row})
            else:
                to_create.append({"fields": row})
        saved = 0
        for chunk in chunks(to_create, 500):
            if chunk:
                self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create", {"records": chunk})
                saved += len(chunk)
        for chunk in chunks(to_update, 500):
            if chunk:
                self.helper.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
                saved += len(chunk)
        return saved

    def record_index(self, table_id: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for record in self.helper.list_records(table_id):
            key = (record.get("fields") or {}).get("unique_key")
            if key:
                result[str(key)] = {"record_id": str(record.get("record_id")), "fields": record.get("fields") or {}}
        return result

    def summarize_readback(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        formula_rows = []
        for record in records:
            fields = record.get("fields") or {}
            if fields.get("订单数") is not None or fields.get("销售额") is not None:
                formula_rows.append(fields)
        latest_rows = [
            fields
            for fields in formula_rows
            if str(fields.get("统计日期") or "") >= date.today().isoformat()
        ][:5]
        nonzero_rows = [
            fields
            for fields in formula_rows
            if any(float(fields.get(name) or 0) for name in ("订单数", "销售额", "投流消耗", "达人佣金"))
        ][:5]
        return {
            "record_count": len(records),
            "formula_value_rows": len(formula_rows),
            "sample_rows": latest_rows,
            "nonzero_sample_rows": nonzero_rows,
        }

    def summarize_total_readback(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        formula_rows = []
        for record in records:
            fields = record.get("fields") or {}
            if fields.get("订单数") is not None or fields.get("销售额") is not None:
                formula_rows.append(fields)
        nonzero_rows = [
            fields
            for fields in formula_rows
            if any(float(fields.get(name) or 0) for name in ("订单数", "销售额", "投流消耗", "达人佣金"))
        ]
        return {
            "record_count": len(records),
            "formula_value_rows": len(formula_rows),
            "platforms": [str((record.get("fields") or {}).get("平台") or "") for record in records],
            "nonzero_sample_rows": nonzero_rows[:5],
        }


NORMALIZE_PLATFORM_EXPR = (
    'IF([平台]="千牛淘宝","天猫",'
    'IF([平台]="淘宝","天猫",'
    'IF([平台].CONTAIN("抖音"),"抖音",'
    'IF([平台].CONTAIN("拼多多"),"拼多多",'
    'IF([平台].CONTAIN("视频号")||[平台].CONTAIN("微信"),"视频号",'
    'IF([平台].CONTAIN("淘宝")||[平台].CONTAIN("天猫")||[平台].CONTAIN("千牛"),"天猫",[平台]))))))'
)

FORMULA_SUMMARY_FORMULA_NAMES = (
    "汇总key",
    "订单数",
    "实际卖出数量",
    "销售额",
    "退款金额",
    "有效销售额",
    "达人佣金",
    "预估佣金支出",
    "实际佣金支出",
    "投流记录数",
    "投流消耗",
    "商品成本",
    "运费成本",
    "平台扣点",
    "其他费用",
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
    "数据状态",
    "缺失项",
    "汇总时间",
)

FORMULA_TOTAL_SUMMARY_FORMULA_NAMES = (
    "汇总key",
    "订单数",
    "实际卖出数量",
    "销售额",
    "退款金额",
    "有效销售额",
    "达人佣金",
    "预估佣金支出",
    "实际佣金支出",
    "投流记录数",
    "投流消耗",
    "商品成本",
    "运费成本",
    "平台扣点",
    "其他费用",
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
    "数据状态",
    "缺失项",
    "汇总时间",
)


def summary_formulas(source_names: dict[str, Any]) -> dict[str, dict[str, str]]:
    order_tables = source_names["orders"]
    if isinstance(order_tables, str):
        order_tables = [order_tables]
    ad_table = source_names["ads"]
    commission_table = source_names["commissions"]
    order_filters = [filter_expr(order_table) for order_table in order_tables]
    ad_filter = filter_expr(ad_table)
    commission_filter = filter_expr(commission_table)
    return {
        "汇总key": {"expression": '[统计日期]&"-"&[平台]', "formatter": ""},
        "订单数": {"expression": sum_order_expr(order_filters, "unique_key", "COUNTA"), "formatter": "0"},
        "实际卖出数量": {"expression": sum_order_expr(order_filters, "公式_实际卖出数量"), "formatter": "0"},
        "销售额": {"expression": sum_order_expr(order_filters, "公式_销售额"), "formatter": "0.00"},
        "退款金额": {"expression": sum_order_expr(order_filters, "公式_退款金额"), "formatter": "0.00"},
        "有效销售额": {"expression": sum_order_expr(order_filters, "公式_有效销售额"), "formatter": "0.00"},
        "达人佣金": {"expression": f"{commission_filter}.[公式_达人费用].SUM()", "formatter": "0.00"},
        "预估佣金支出": {"expression": f"{commission_filter}.[公式_预估佣金支出].SUM()", "formatter": "0.00"},
        "实际佣金支出": {"expression": f"{commission_filter}.[公式_实际佣金支出].SUM()", "formatter": "0.00"},
        "投流记录数": {"expression": f"{ad_filter}.[unique_key].COUNTA()", "formatter": "0"},
        "投流消耗": {"expression": f"{ad_filter}.[公式_投流消耗].SUM()", "formatter": "0.00"},
        "商品成本": {"expression": sum_order_expr(order_filters, "公式_商品成本"), "formatter": "0.00"},
        "运费成本": {"expression": sum_order_expr(order_filters, "公式_运费成本"), "formatter": "0.00"},
        "平台扣点": {"expression": sum_order_expr(order_filters, "公式_平台扣点"), "formatter": "0.00"},
        "其他费用": {"expression": sum_order_expr(order_filters, "公式_其他费用"), "formatter": "0.00"},
        "已知总投入": {"expression": "IF([投流记录数]=0,0,[投流消耗]+[达人佣金])", "formatter": "0.00"},
        "已知费用后利润": {"expression": "[有效销售额]-[商品成本]-[运费成本]-[平台扣点]-[其他费用]-[达人佣金]-[投流消耗]", "formatter": "0.00"},
        "投流后毛利": {"expression": "IF([投流记录数]=0,0,[有效销售额]-[达人佣金]-[投流消耗])", "formatter": "0.00"},
        "经营利润估算": {"expression": "IF([投流记录数]=0,0,[已知费用后利润])", "formatter": "0.00"},
        "ROI": {"expression": "IF([投流记录数]=0,0,IF([投流消耗]=0,0,[有效销售额]/[投流消耗]))", "formatter": "0.00"},
        "平台ROI": {"expression": "IF([投流记录数]=0,0,IF([已知总投入]=0,0,[有效销售额]/[已知总投入]))", "formatter": "0.00"},
        "已知费用利润率": {"expression": "IF([有效销售额]=0,0,[已知费用后利润]/[有效销售额])", "formatter": "0.00"},
        "利润率": {"expression": "IF([投流记录数]=0,0,IF([有效销售额]=0,0,[经营利润估算]/[有效销售额]))", "formatter": "0.00"},
        "展现": {"expression": f"{ad_filter}.[公式_展现].SUM()", "formatter": "0"},
        "点击": {"expression": f"{ad_filter}.[公式_点击].SUM()", "formatter": "0"},
        "数据状态": {"expression": 'IF([订单数]=0,"partial",IF([投流记录数]=0,"partial","normal"))', "formatter": ""},
        "缺失项": {"expression": 'IF([订单数]=0,IF([投流记录数]=0,"订单,投流","订单"),IF([投流记录数]=0,"投流",""))', "formatter": ""},
        "汇总时间": {"expression": "NOW()", "formatter": ""},
    }


def sum_order_expr(order_filters: list[str], field_name: str, op: str = "SUM") -> str:
    parts = [f"{order_filter}.[{field_name}].{op}()" for order_filter in order_filters]
    if not parts:
        return "0"
    return "+".join(parts)


def total_summary_formulas(summary_table_name: str) -> dict[str, dict[str, str]]:
    summary_filter = total_filter_expr(summary_table_name)
    return {
        "汇总key": {"expression": '[统计范围]&"-"&[平台]', "formatter": ""},
        "订单数": {"expression": f"{summary_filter}.[订单数].SUM()", "formatter": "0"},
        "实际卖出数量": {"expression": f"{summary_filter}.[实际卖出数量].SUM()", "formatter": "0"},
        "销售额": {"expression": f"{summary_filter}.[销售额].SUM()", "formatter": "0.00"},
        "退款金额": {"expression": f"{summary_filter}.[退款金额].SUM()", "formatter": "0.00"},
        "有效销售额": {"expression": f"{summary_filter}.[有效销售额].SUM()", "formatter": "0.00"},
        "达人佣金": {"expression": f"{summary_filter}.[达人佣金].SUM()", "formatter": "0.00"},
        "预估佣金支出": {"expression": f"{summary_filter}.[预估佣金支出].SUM()", "formatter": "0.00"},
        "实际佣金支出": {"expression": f"{summary_filter}.[实际佣金支出].SUM()", "formatter": "0.00"},
        "投流记录数": {"expression": f"{summary_filter}.[投流记录数].SUM()", "formatter": "0"},
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
        "数据状态": {"expression": 'IF([订单数]=0,"partial",IF([投流记录数]=0,"partial","normal"))', "formatter": ""},
        "缺失项": {"expression": 'IF([订单数]=0,IF([投流记录数]=0,"订单,投流","订单"),IF([投流记录数]=0,"投流",""))', "formatter": ""},
        "汇总时间": {"expression": "NOW()", "formatter": ""},
    }


def filter_expr(table_name: str) -> str:
    return (
        f"[{table_name}].FILTER("
        'CurrentValue.[公式_统计日期]=[统计日期]&&'
        '([平台]="全平台总计"||CurrentValue.[平台]=[平台])'
        ")"
    )


def total_filter_expr(table_name: str) -> str:
    return (
        f"[{table_name}].FILTER("
        "CurrentValue.[平台]=[平台]"
        ")"
    )


def first_number_expr(existing_fields: dict[str, dict[str, Any]], aliases: tuple[str, ...], default: str = "0") -> str:
    found = [name for name in aliases if name in existing_fields]
    if not found:
        return default
    expr = default
    for name in reversed(found):
        expr = f"IFBLANK([{name}],{expr})"
    return expr


def effective_sales_quantity_expr(existing_fields: dict[str, dict[str, Any]]) -> str:
    quantity = first_number_expr(existing_fields, ORDER_QUANTITY_FIELDS)
    valid_sales = first_number_expr(existing_fields, ("公式_有效销售额",), default="0")
    if not valid_sales:
        valid_sales = first_number_expr(existing_fields, ORDER_VALID_SALES_FIELDS, default="[公式_销售额]-[公式_退款金额]")
    if not valid_sales:
        valid_sales = "0"
    return f"IF(({valid_sales})>0,{quantity},0)"


def actual_sold_quantity_expr(existing_fields: dict[str, dict[str, Any]], product_rules: list[ProductRule] | None = None) -> str:
    product_quantity_fields = [
        rule.quantity_field
        for rule in product_rules or []
        if rule.name not in {"配件", "补差价"} and rule.quantity_field in existing_fields
    ]
    if product_quantity_fields:
        return "+".join(f"IFBLANK([{field}],0)" for field in product_quantity_fields)
    return effective_sales_quantity_expr(existing_fields)


def accessory_adjusted_quantity_expr(existing_fields: dict[str, dict[str, Any]]) -> str:
    return effective_sales_quantity_expr(existing_fields)


def first_commission_expr(existing_fields: dict[str, dict[str, Any]]) -> str:
    estimated = first_number_expr(existing_fields, COMMISSION_ESTIMATED_FIELDS, default="")
    settled = first_number_expr(existing_fields, COMMISSION_SETTLED_FIELDS, default="")
    if settled and estimated:
        return f"IF(({settled})>0,{settled},{estimated})"
    if settled:
        return settled
    if estimated:
        return estimated
    amount = first_number_expr(existing_fields, COMMISSION_AMOUNT_FIELDS, default="")
    return amount or "0"


def formula_date_expr(existing_fields: dict[str, dict[str, Any]], aliases: tuple[str, ...]) -> str:
    chain = first_existing_text_expr(existing_fields, aliases)
    return f"LEFT({chain},10)"


def first_existing_text_expr(existing_fields: dict[str, dict[str, Any]], aliases: tuple[str, ...], default: str = '""') -> str:
    found = [name for name in aliases if name in existing_fields]
    if not found:
        return default
    expr = f"[{found[-1]}]"
    for name in reversed(found[:-1]):
        expr = f"IFBLANK([{name}],{expr})"
    return expr


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for candidate in (text, text[:19], text[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def dimension_row_matches(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(str(existing.get(field) or "") == str(expected.get(field) or "") for field in ("unique_key", "统计日期", "平台", SHOP_NAME_FIELD, PRODUCT_NAME_FIELD))


def total_dimension_row_matches(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(str(existing.get(field) or "") == str(expected.get(field) or "") for field in ("unique_key", "统计范围", "平台", SHOP_NAME_FIELD, PRODUCT_NAME_FIELD))


def dimension_row(stat_date: str, platform: str, shop_name: str = "", product_name: str = "") -> dict[str, Any]:
    shop_name = clean_dimension_text(shop_name)
    product_name = clean_dimension_text(product_name)
    key_parts = [stat_date, platform]
    if shop_name or product_name:
        key_parts.extend([shop_name, product_name])
    return {
        "unique_key": "-".join(key_parts),
        "统计日期": stat_date,
        "平台": platform,
        SHOP_NAME_FIELD: shop_name,
        PRODUCT_NAME_FIELD: product_name,
    }


def total_dimension_row(platform: str, shop_name: str = "", product_name: str = "") -> dict[str, Any]:
    shop_name = clean_dimension_text(shop_name)
    product_name = clean_dimension_text(product_name)
    key_parts = ["all-days", platform]
    if shop_name or product_name:
        key_parts.extend([shop_name, product_name])
    return {
        "unique_key": "-".join(key_parts),
        "统计范围": "所有天数",
        "平台": platform,
        SHOP_NAME_FIELD: shop_name,
        PRODUCT_NAME_FIELD: product_name,
    }


def clean_dimension_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def normalize_platform_value(value: Any) -> str:
    text = clean_dimension_text(value)
    if text in ("千牛淘宝", "淘宝"):
        return "天猫"
    if "抖音" in text:
        return "抖音"
    if "拼多多" in text:
        return "拼多多"
    if "视频号" in text or "微信" in text:
        return "视频号"
    if "淘宝" in text or "天猫" in text or "千牛" in text:
        return "天猫"
    return text or "未知平台"


def default_order_table_ids(fallback: str | None = None) -> list[str]:
    platform_ids = [os.getenv(name, "").strip() for name in PLATFORM_ORDER_TABLE_ENVS]
    platform_ids = [table_id for table_id in platform_ids if table_id]
    if platform_ids:
        return unique_values(platform_ids)
    return unique_values([fallback or ""])


def unique_values(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Create a live formula-based Feishu dynamic business summary table.")
    parser.add_argument("--app-token", default=os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN"))
    parser.add_argument("--order-table-id", action="append", default=None, help="Order source table id. Repeat to include multiple platform order tables.")
    parser.add_argument("--ad-table-id", default=os.getenv("SHOPOPS_AD_TABLE_ID") or os.getenv("FEISHU_TABLE_PROMOTION_SNAPSHOT"))
    parser.add_argument("--commission-table-id", default=os.getenv("SHOPOPS_COMMISSION_TABLE_ID") or os.getenv("FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION"))
    parser.add_argument("--summary-table-id", default=os.getenv("SHOPOPS_FORMULA_SUMMARY_TABLE_ID"))
    parser.add_argument("--total-summary-table-id", default=os.getenv("SHOPOPS_FORMULA_TOTAL_SUMMARY_TABLE_ID"))
    parser.add_argument("--days-ahead", type=int, default=365)
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/formula-dynamic-summary")
    parser.add_argument(
        "--refresh-source-dates",
        action="store_true",
        help="Scan source tables again to add historical dates that are not yet present in the formula summary table.",
    )
    parser.add_argument(
        "--total-only",
        action="store_true",
        help="Only create/update the all-days platform total formula table; do not refresh the daily formula summary table.",
    )
    args = parser.parse_args()
    order_table_ids = args.order_table_id or default_order_table_ids(os.getenv("SHOPOPS_ORDER_TABLE_ID") or os.getenv("FEISHU_TABLE_ORDERS_RAW"))
    required = {
        "app-token": args.app_token,
        "order-table-id": order_table_ids,
        "ad-table-id": args.ad_table_id,
        "commission-table-id": args.commission_table_id,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing required inputs: " + ", ".join(missing))
    result = FormulaSummaryBootstrap(args.app_token, Path(args.env_path)).run(
        order_table_id=order_table_ids[0],
        order_table_ids=order_table_ids,
        ad_table_id=args.ad_table_id,
        commission_table_id=args.commission_table_id,
        summary_table_id=args.summary_table_id,
        total_summary_table_id=args.total_summary_table_id,
        days_ahead=args.days_ahead,
        evidence_dir=Path(args.evidence_dir),
        refresh_source_dates=args.refresh_source_dates,
        total_only=args.total_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
