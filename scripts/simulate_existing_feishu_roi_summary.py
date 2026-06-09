from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.storage.feishu_bootstrap import FeishuOpenApiClient, PlatformTableSpec, number_field, text_field


ORDER_TABLE_NAME = "订单明细原始表-千牛淘宝"
AD_TABLE_NAME = "推广数据表-千牛淘宝"
INFLUENCER_TABLE_NAME = "抖音达人佣金明细表"
DASHBOARD_TABLE_NAME = "实时汇总看板"
ROI_DAILY_TABLE_NAME = "每日ROI汇总表"
PLATFORM_COMPARE_TABLE_NAME = "平台对比表"

SUMMARY_PLATFORMS = ("淘宝", "抖音", "拼多多", "视频号")
TOTAL_PLATFORM = "全平台总计"
SHOP_ID = "shopops_demo_store"
SHOP_NAME = "ShopOps 模拟店"


class ExistingBaseSimulator:
    def __init__(self, app_token: str) -> None:
        ensure_feishu_no_proxy()
        settings = load_settings()
        self.app_token = app_token
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret)

    def run(self, start_at: datetime, cycles: int, interval_minutes: int, evidence_dir: Path) -> dict[str, Any]:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        tables = self.ensure_allowed_tables()

        influencer_rows = self.build_influencer_rows(start_at, cycles, interval_minutes)
        influencer_saved = self.upsert_records(tables[INFLUENCER_TABLE_NAME], influencer_rows)

        order_rows = self.list_records(tables[ORDER_TABLE_NAME])
        ad_rows = self.list_records(tables[AD_TABLE_NAME])
        influencer_source_rows = self.list_records(tables[INFLUENCER_TABLE_NAME])

        cycles_output: list[dict[str, Any]] = []
        dashboard_to_save: list[dict[str, Any]] = []
        roi_daily_to_save: list[dict[str, Any]] = []
        platform_compare_to_save: list[dict[str, Any]] = []
        for cycle in range(1, cycles + 1):
            summary_time = start_at + timedelta(minutes=interval_minutes * cycle)
            summary_rows = build_summary_rows(order_rows, ad_rows, influencer_source_rows, summary_time, cycle)
            dashboard_rows = [dashboard_fields(row) for row in summary_rows]
            roi_daily_rows = [roi_daily_fields(row) for row in summary_rows]
            compare_rows = [platform_compare_fields(row) for row in summary_rows]
            dashboard_to_save.extend(dashboard_rows)
            roi_daily_to_save.extend(roi_daily_rows)
            platform_compare_to_save.extend(compare_rows)
            cycles_output.append(
                {
                    "cycle": cycle,
                    "summary_time": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_row": dashboard_rows[-1],
                    "platform_compare": compare_rows,
                }
            )

        summary_saved = 0
        summary_saved += self.upsert_records(tables[DASHBOARD_TABLE_NAME], dashboard_to_save)
        summary_saved += self.upsert_records(tables[ROI_DAILY_TABLE_NAME], roi_daily_to_save)
        summary_saved += self.upsert_records(tables[PLATFORM_COMPARE_TABLE_NAME], platform_compare_to_save)

        result = {
            "mode": "feishu",
            "app_token": self.app_token,
            "app_url": feishu_base_url(self.app_token),
            "table_ids": tables,
            "source_counts": {
                ORDER_TABLE_NAME: len(order_rows),
                AD_TABLE_NAME: len(ad_rows),
                INFLUENCER_TABLE_NAME: len(influencer_source_rows),
            },
            "saved_counts": {
                "influencer_commission_rows": influencer_saved,
                "summary_rows": summary_saved,
            },
            "cycles": cycles_output,
        }
        evidence_path = evidence_dir / "existing-base-summary-result.json"
        evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        result["evidence_path"] = str(evidence_path.resolve())
        return result

    def ensure_allowed_tables(self) -> dict[str, str]:
        existing = self.client.list_tables(self.app_token)
        by_name = {str(item.get("name")): str(item.get("table_id")) for item in existing if item.get("name") and item.get("table_id")}
        missing_raw = [name for name in (ORDER_TABLE_NAME, AD_TABLE_NAME, INFLUENCER_TABLE_NAME) if name not in by_name]
        if missing_raw:
            raise RuntimeError("Required existing raw tables are missing; refusing to create raw tables: " + ", ".join(missing_raw))

        result = {
            ORDER_TABLE_NAME: by_name[ORDER_TABLE_NAME],
            AD_TABLE_NAME: by_name[AD_TABLE_NAME],
            INFLUENCER_TABLE_NAME: by_name[INFLUENCER_TABLE_NAME],
        }
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        for spec in summary_table_specs():
            table = self.client.ensure_table(self.app_token, spec, existing_by_name)
            table_id = str(table.get("table_id") or "")
            if not table_id:
                raise RuntimeError(f"Feishu table {spec.name} did not return table_id")
            self.ensure_fields(table_id, spec)
            result[spec.name] = table_id
        return result

    def ensure_fields(self, table_id: str, spec: PlatformTableSpec) -> None:
        existing = self.list_field_names(table_id)
        for field in spec.fields:
            name = str(field["field_name"])
            if name in existing:
                continue
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/fields", {"field_name": name, "type": field["type"]})
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
        try:
            saved = self.batch_create_records(table_id, to_create)
            saved += self.batch_update_records(table_id, to_update)
            return saved
        except Exception:
            return self.upsert_records_one_by_one(table_id, rows, index)

    def batch_create_records(self, table_id: str, records: list[dict[str, Any]]) -> int:
        saved = 0
        for chunk in chunks(records, 500):
            if not chunk:
                continue
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create", {"records": chunk})
            saved += len(chunk)
        return saved

    def batch_update_records(self, table_id: str, records: list[dict[str, Any]]) -> int:
        saved = 0
        for chunk in chunks(records, 500):
            if not chunk:
                continue
            self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_update", {"records": chunk})
            saved += len(chunk)
        return saved

    def upsert_records_one_by_one(self, table_id: str, rows: list[dict[str, Any]], index: dict[str, str]) -> int:
        saved = 0
        for row in rows:
            unique_key = str(row.get("unique_key") or "")
            if not unique_key:
                continue
            payload = {"fields": row}
            record_id = index.get(unique_key)
            if record_id:
                self.request("PUT", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}", payload)
            else:
                data = self.request("POST", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", payload)
                record = data.get("record") or {}
                if record.get("record_id"):
                    index[unique_key] = str(record["record_id"])
            saved += 1
        return saved

    def record_index(self, table_id: str) -> dict[str, str]:
        records: dict[str, str] = {}
        page_token = None
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records", params=params)
            for item in data.get("items", []) or []:
                unique_key = (item.get("fields") or {}).get("unique_key")
                if unique_key:
                    records[str(unique_key)] = str(item.get("record_id"))
            if not data.get("has_more"):
                return records
            page_token = data.get("page_token")

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
        body = response.json()
        if response.status_code >= 400 or body.get("code") != 0:
            raise RuntimeError(f"Feishu API {method} {path} failed HTTP {response.status_code}: {body}")
        return body.get("data") or {}

    @staticmethod
    def build_influencer_rows(start_at: datetime, cycles: int, interval_minutes: int) -> list[dict[str, Any]]:
        samples = [
            ("kol_1001", "小鹿种草", 980.0, 0.18, None),
            ("kol_1002", "老周测评", 1540.0, 0.20, None),
            ("kol_1003", "阿南直播间", 2180.0, 0.22, None),
            ("kol_1001", "小鹿种草", 1260.0, 0.18, None),
            ("kol_1002", "老周测评", 1850.0, 0.20, None),
            ("kol_1003", "阿南直播间", 2210.0, 0.19, None),
        ]
        rows: list[dict[str, Any]] = []
        for cycle in range(1, cycles + 1):
            summary_time = start_at + timedelta(minutes=interval_minutes * cycle)
            creator_id, creator_name, paid, rate, settled = samples[cycle - 1]
            estimated = round(paid * rate, 2)
            service_fee = round(estimated * 0.1, 2)
            order_id = f"DY{summary_time.strftime('%Y%m%d%H%M')}"
            raw = {
                "模拟轮次": cycle,
                "采用佣金": settled if settled is not None else estimated,
                "说明": "仅模拟达人佣金；未写入订单表和投流表",
            }
            rows.append(
                {
                    "unique_key": f"抖音_{SHOP_ID}_{order_id}_{creator_id}",
                    "平台": "抖音",
                    "数据来源": "模拟达人佣金",
                    "店铺ID": SHOP_ID,
                    "店铺名称": SHOP_NAME,
                    "采集时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "订单号": order_id,
                    "下单时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "达人ID": creator_id,
                    "达人昵称": creator_name,
                    "内容类型": "直播",
                    "直播间/视频ID": f"live_{cycle:02d}",
                    "商品ID": f"sku_demo_{cycle:02d}",
                    "商品名称": "ShopOps 达人带货模拟商品",
                    "支付金额": paid,
                    "佣金率": rate,
                    "预估佣金": estimated,
                    "结算佣金": settled,
                    "技术服务费": service_fee,
                    "结算状态": "未结算",
                    "原始数据": json.dumps(raw, ensure_ascii=False, sort_keys=True),
                }
            )
        return rows


def summary_table_specs() -> list[PlatformTableSpec]:
    return [
        PlatformTableSpec("SHOPOPS_SUMMARY_DASHBOARD_TODAY", "dashboard_today", DASHBOARD_TABLE_NAME, typed_fields(summary_field_names(), summary_number_fields())),
        PlatformTableSpec("SHOPOPS_SUMMARY_ROI_DAILY", "roi_daily_summary", ROI_DAILY_TABLE_NAME, typed_fields(summary_field_names(), summary_number_fields())),
        PlatformTableSpec(
            "SHOPOPS_SUMMARY_PLATFORM_COMPARE",
            "platform_compare",
            PLATFORM_COMPARE_TABLE_NAME,
            typed_fields(platform_compare_field_names(), platform_compare_number_fields()),
        ),
    ]


def typed_fields(names: list[str], number_names: set[str]) -> list[dict[str, Any]]:
    return [number_field(name) if name in number_names else text_field(name) for name in names]


def summary_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "汇总时间",
        "模拟轮次",
        "平台",
        "今日订单数",
        "今日支付金额",
        "今日退款金额",
        "今日净成交额",
        "今日广告消耗",
        "今日达人佣金",
        "已知总投入",
        "真实ROI_仅广告",
        "真实ROI_含佣金",
        "每投1000净成交",
        "每投1000已知贡献",
        "当前判断",
        "数据状态",
        "更新时间",
    ]


def platform_compare_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "汇总时间",
        "模拟轮次",
        "平台",
        "广告消耗",
        "净成交额",
        "达人佣金",
        "每投1000净成交",
        "每投1000已知贡献",
        "判断",
        "数据状态",
    ]


def summary_number_fields() -> set[str]:
    return {
        "模拟轮次",
        "今日订单数",
        "今日支付金额",
        "今日退款金额",
        "今日净成交额",
        "今日广告消耗",
        "今日达人佣金",
        "已知总投入",
        "真实ROI_仅广告",
        "真实ROI_含佣金",
        "每投1000净成交",
        "每投1000已知贡献",
    }


def platform_compare_number_fields() -> set[str]:
    return {"模拟轮次", "广告消耗", "净成交额", "达人佣金", "每投1000净成交", "每投1000已知贡献"}


def build_summary_rows(order_records: list[dict[str, Any]], ad_records: list[dict[str, Any]], influencer_records: list[dict[str, Any]], summary_time: datetime, cycle: int) -> list[dict[str, Any]]:
    stat_date = summary_time.date().isoformat()
    orders = aggregate_orders(order_records, stat_date, summary_time)
    ads = aggregate_ads(ad_records, stat_date, summary_time)
    commissions = aggregate_commissions(influencer_records, stat_date, summary_time)

    rows = [summary_row(platform, orders.get(platform), ads.get(platform), commissions.get(platform), stat_date, summary_time, cycle) for platform in SUMMARY_PLATFORMS]
    rows.append(total_row(rows, stat_date, summary_time, cycle))
    return rows


def aggregate_orders(records: list[dict[str, Any]], stat_date: str, summary_time: datetime) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "payment": 0.0, "refund": None, "net": 0.0})
    for record in records:
        fields = record.get("fields") or {}
        happened_at = parse_time(fields.get("采集时间") or fields.get("创建时间"))
        if not happened_at or happened_at.date().isoformat() != stat_date or happened_at > summary_time:
            continue
        platform = normalize_platform(fields.get("平台"))
        payment = parse_number(fields.get("支付金额") or fields.get("实收款"))
        if payment is None:
            continue
        refund = parse_number(fields.get("退款金额"))
        net = parse_number(fields.get("净成交额"))
        if net is None:
            net = payment - (refund or 0)
        buckets[platform]["count"] += 1
        buckets[platform]["payment"] = round(buckets[platform]["payment"] + payment, 2)
        buckets[platform]["net"] = round(buckets[platform]["net"] + net, 2)
        if refund is not None:
            buckets[platform]["refund"] = round((buckets[platform]["refund"] or 0) + refund, 2)
    return dict(buckets)


def aggregate_ads(records: list[dict[str, Any]], stat_date: str, summary_time: datetime) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"cost": 0.0})
    for record in records:
        fields = record.get("fields") or {}
        happened_at = parse_time(fields.get("采集时间") or fields.get("更新时间"))
        if not happened_at or happened_at.date().isoformat() != stat_date or happened_at > summary_time:
            continue
        cost = parse_number(fields.get("推广消耗") or fields.get("推广花费(元)") or fields.get("花费"))
        if cost is None:
            continue
        platform = normalize_platform(fields.get("平台"))
        buckets[platform]["cost"] = round(buckets[platform]["cost"] + cost, 2)
    return dict(buckets)


def aggregate_commissions(records: list[dict[str, Any]], stat_date: str, summary_time: datetime) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"commission": 0.0})
    for record in records:
        fields = record.get("fields") or {}
        happened_at = parse_time(fields.get("采集时间") or fields.get("下单时间"))
        if not happened_at or happened_at.date().isoformat() != stat_date or happened_at > summary_time:
            continue
        adopted = parse_number(fields.get("采用佣金"))
        if adopted is None:
            adopted = parse_number(fields.get("结算佣金"))
        if adopted is None:
            adopted = parse_number(fields.get("预估佣金"))
        if adopted is None:
            continue
        platform = normalize_platform(fields.get("平台"))
        buckets[platform]["commission"] = round(buckets[platform]["commission"] + adopted, 2)
    return dict(buckets)


def summary_row(platform: str, order: dict[str, Any] | None, ad: dict[str, Any] | None, commission: dict[str, Any] | None, stat_date: str, summary_time: datetime, cycle: int) -> dict[str, Any]:
    order_count = order["count"] if order else None
    payment = order["payment"] if order else None
    refund = order["refund"] if order else None
    net = order["net"] if order else None
    ad_cost = ad["cost"] if ad else None
    commission_amount = commission["commission"] if commission else 0.0
    known_input = round((ad_cost or 0) + commission_amount, 2) if ad_cost is not None else None
    per_1000_known = safe_div(((net or 0) - (ad_cost or 0) - commission_amount) * 1000, ad_cost, 2) if net is not None and ad_cost is not None else None
    status = "normal" if order is not None and ad is not None else "partial"
    return {
        "unique_key": f"summary_{stat_date}_{platform}_{summary_time.strftime('%H%M')}",
        "统计日期": stat_date,
        "汇总时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
        "模拟轮次": cycle,
        "平台": platform,
        "今日订单数": order_count,
        "今日支付金额": payment,
        "今日退款金额": refund,
        "今日净成交额": net,
        "今日广告消耗": ad_cost,
        "今日达人佣金": commission_amount,
        "已知总投入": known_input,
        "真实ROI_仅广告": safe_div(net, ad_cost),
        "真实ROI_含佣金": safe_div(net, known_input),
        "每投1000净成交": safe_div((net or 0) * 1000, ad_cost, 2) if net is not None and ad_cost is not None else None,
        "每投1000已知贡献": per_1000_known,
        "当前判断": judgement(per_1000_known),
        "数据状态": status,
        "更新时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def total_row(rows: list[dict[str, Any]], stat_date: str, summary_time: datetime, cycle: int) -> dict[str, Any]:
    order_rows = [row for row in rows if row["今日订单数"] is not None]
    ad_rows = [row for row in rows if row["今日广告消耗"] is not None]
    order_count = sum(int(row["今日订单数"]) for row in order_rows) if order_rows else None
    payment = round(sum(float(row["今日支付金额"]) for row in order_rows), 2) if order_rows else None
    net = round(sum(float(row["今日净成交额"]) for row in order_rows), 2) if order_rows else None
    refund_values = [row["今日退款金额"] for row in order_rows if row["今日退款金额"] is not None]
    refund = round(sum(float(value) for value in refund_values), 2) if refund_values else None
    ad_cost = round(sum(float(row["今日广告消耗"]) for row in ad_rows), 2) if ad_rows else None
    commission = round(sum(float(row["今日达人佣金"] or 0) for row in rows), 2)
    known_input = round((ad_cost or 0) + commission, 2) if ad_cost is not None else None
    per_1000_known = safe_div(((net or 0) - (ad_cost or 0) - commission) * 1000, ad_cost, 2) if net is not None and ad_cost is not None else None
    return {
        "unique_key": f"summary_{stat_date}_{TOTAL_PLATFORM}_{summary_time.strftime('%H%M')}",
        "统计日期": stat_date,
        "汇总时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
        "模拟轮次": cycle,
        "平台": TOTAL_PLATFORM,
        "今日订单数": order_count,
        "今日支付金额": payment,
        "今日退款金额": refund,
        "今日净成交额": net,
        "今日广告消耗": ad_cost,
        "今日达人佣金": commission,
        "已知总投入": known_input,
        "真实ROI_仅广告": safe_div(net, ad_cost),
        "真实ROI_含佣金": safe_div(net, known_input),
        "每投1000净成交": safe_div((net or 0) * 1000, ad_cost, 2) if net is not None and ad_cost is not None else None,
        "每投1000已知贡献": per_1000_known,
        "当前判断": judgement(per_1000_known),
        "数据状态": "normal" if order_rows and ad_rows else "partial",
        "更新时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def dashboard_fields(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def roi_daily_fields(row: dict[str, Any]) -> dict[str, Any]:
    fields = dict(row)
    fields["unique_key"] = "roi_daily_" + fields["unique_key"]
    return fields


def platform_compare_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "unique_key": "platform_compare_" + row["unique_key"],
        "统计日期": row["统计日期"],
        "汇总时间": row["汇总时间"],
        "模拟轮次": row["模拟轮次"],
        "平台": row["平台"],
        "广告消耗": row["今日广告消耗"],
        "净成交额": row["今日净成交额"],
        "达人佣金": row["今日达人佣金"],
        "每投1000净成交": row["每投1000净成交"],
        "每投1000已知贡献": row["每投1000已知贡献"],
        "判断": row["当前判断"],
        "数据状态": row["数据状态"],
    }


def parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    candidates = [text]
    if len(text) >= 19:
        candidates.append(text[:19])
    if len(text) >= 16:
        candidates.append(text[:16])
    for candidate in candidates:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    for fmt in ("%Y-%m-%d",):
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            continue
    return None


def parse_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("¥", "").strip())
    except ValueError:
        return None


def normalize_platform(value: Any) -> str:
    text = str(value or "").strip()
    if "抖音" in text:
        return "抖音"
    if "拼多多" in text:
        return "拼多多"
    if "视频号" in text or "微信" in text:
        return "视频号"
    if "淘宝" in text or "天猫" in text or "千牛" in text:
        return "淘宝"
    return text or "未知平台"


def safe_div(numerator: float | int | None, denominator: float | int | None, digits: int = 4) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), digits)


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def judgement(per_1000_known: float | None) -> str:
    if per_1000_known is None:
        return "观察"
    if per_1000_known < 0:
        return "亏损"
    if per_1000_known < 1800:
        return "观察"
    return "正常"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write only influencer mock rows and summary tables into an existing Feishu Base.")
    parser.add_argument("--app-token", default="KhbEbksLbauw0fssL6EcKAnlnOe")
    parser.add_argument("--start-at", default="2026-06-04 14:00:00")
    parser.add_argument("--cycles", type=int, default=6)
    parser.add_argument("--interval-minutes", type=int, default=5)
    parser.add_argument("--evidence-dir", default="docs/live-evidence/existing-base-roi-5min-6cycles")
    args = parser.parse_args()

    result = ExistingBaseSimulator(args.app_token).run(
        start_at=datetime.strptime(args.start_at, "%Y-%m-%d %H:%M:%S"),
        cycles=args.cycles,
        interval_minutes=args.interval_minutes,
        evidence_dir=Path(args.evidence_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
