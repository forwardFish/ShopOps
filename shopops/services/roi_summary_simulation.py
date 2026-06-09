from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from shopops.config import Settings
from shopops.services.data_center_demo import ensure_feishu_no_proxy, feishu_base_url
from shopops.storage.feishu_bootstrap import FEISHU_BASE_URL, FeishuOpenApiClient, PlatformTableSpec, number_field, text_field
from shopops.storage.local_feishu import LocalFeishuBitableStorage


ORDERS_RAW = "orders_raw"
AD_COST_RAW = "ad_cost_raw"
INFLUENCER_COMMISSION_RAW = "influencer_commission_raw"
DASHBOARD_TODAY = "dashboard_today"
ROI_DAILY_SUMMARY = "roi_daily_summary"
PLATFORM_COMPARE = "platform_compare"

TOTAL_PLATFORM = "全平台总计"
SHOP_ID = "shopops_demo_store"
SHOP_NAME = "ShopOps 模拟店"
PLATFORMS = ("淘宝", "抖音", "拼多多", "视频号")


@dataclass(frozen=True)
class SimulationCycle:
    cycle: int
    summary_time: str
    saved_count: int
    total_row: dict[str, Any]
    platform_rows: list[dict[str, Any]]


@dataclass(frozen=True)
class SimulationRunResult:
    cycles: list[SimulationCycle]
    table_counts: dict[str, int]
    local_path: str
    evidence_path: str


@dataclass(frozen=True)
class FeishuSimulationWriteResult:
    mode: str
    app_token: str
    app_url: str
    table_ids: dict[str, str]
    saved_count: int


ORDER_EVENTS: dict[str, list[tuple[float, float]]] = {
    "淘宝": [(1280, 0), (1680, 60), (1460, 0), (1980, 120), (1720, 0), (2140, 90)],
    "抖音": [(980, 0), (1540, 0), (2180, 180), (1260, 0), (1850, 0), (2210, 120)],
    "拼多多": [(760, 0), (980, 40), (1320, 0), (1110, 180), (1450, 70), (1680, 0)],
    "视频号": [(420, 0), (680, 0), (530, 60), (740, 0), (620, 0), (830, 90)],
}

AD_COST_EVENTS: dict[str, list[tuple[str, float, int, int, float | None]]] = {
    "淘宝": [
        ("直通车", 260, 12300, 640, 5.2),
        ("万相台", 310, 14800, 710, 5.4),
        ("直通车", 280, 13100, 660, 5.1),
        ("万相台", 390, 16600, 760, 4.8),
        ("直通车", 340, 15100, 720, 5.0),
        ("万相台", 430, 18400, 810, 4.9),
    ],
    "抖音": [
        ("千川", 420, 26800, 1320, 4.9),
        ("千川", 520, 31200, 1510, 5.1),
        ("千川", 610, 35600, 1680, 5.0),
        ("千川", 480, 28900, 1390, 4.8),
        ("千川", 540, 33600, 1590, 5.2),
        ("千川", 580, 35200, 1660, 5.1),
    ],
    "拼多多": [
        ("搜索推广", 180, 18100, 1120, 4.4),
        ("搜索推广", 210, 20500, 1270, 4.5),
        ("场景推广", 260, 22800, 1360, 4.8),
        ("搜索推广", 240, 21700, 1300, 4.3),
        ("场景推广", 280, 24100, 1420, 4.5),
        ("搜索推广", 310, 25800, 1490, 4.6),
    ],
    "视频号": [
        ("微信广告", 140, 8300, 310, 3.8),
        ("微信广告", 160, 9100, 360, 4.0),
        ("微信广告", 130, 7800, 290, 3.7),
        ("微信广告", 170, 9400, 380, 3.9),
        ("微信广告", 150, 8700, 330, 3.8),
        ("微信广告", 170, 9500, 390, 3.9),
    ],
}

DOUYIN_COMMISSION_RATES = (0.18, 0.2, 0.22, 0.18, 0.2, 0.19)
DOUYIN_CREATORS = (
    ("kol_1001", "小鹿种草"),
    ("kol_1002", "老周测评"),
    ("kol_1003", "阿南直播间"),
)


def safe_div(numerator: float | int | None, denominator: float | int | None, digits: int = 4) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), digits)


def cycle_times(start_at: datetime, cycles: int, interval_minutes: int) -> list[datetime]:
    return [start_at + timedelta(minutes=interval_minutes * cycle) for cycle in range(1, cycles + 1)]


def simulate_roi_cycles(
    settings: Settings,
    start_at: datetime,
    cycles: int = 6,
    interval_minutes: int = 5,
    evidence_dir: str | Path = "docs/live-evidence/roi-5min-6cycles",
) -> SimulationRunResult:
    evidence_root = Path(evidence_dir)
    evidence_root.mkdir(parents=True, exist_ok=True)
    local_path = evidence_root / "local_feishu.json"
    pending_path = evidence_root / "pending_records.jsonl"
    if local_path.exists():
        local_path.unlink()
    if pending_path.exists():
        pending_path.unlink()

    local_settings = Settings(
        local_feishu_path=str(local_path),
        pending_records_path=str(pending_path),
        fetch_interval_seconds=interval_minutes * 60,
    )
    storage = LocalFeishuBitableStorage(local_settings)
    raw_orders: list[dict[str, Any]] = []
    raw_ads: list[dict[str, Any]] = []
    raw_commissions: list[dict[str, Any]] = []
    cycle_results: list[SimulationCycle] = []

    for cycle, summary_time in enumerate(cycle_times(start_at, cycles, interval_minutes), start=1):
        orders = build_order_rows(summary_time, cycle)
        ads = build_ad_cost_rows(summary_time, cycle)
        commissions = build_influencer_commission_rows(summary_time, cycle)
        raw_orders.extend(orders)
        raw_ads.extend(ads)
        raw_commissions.extend(commissions)

        saved = 0
        for table, rows in (
            (ORDERS_RAW, orders),
            (AD_COST_RAW, ads),
            (INFLUENCER_COMMISSION_RAW, commissions),
        ):
            for row in rows:
                saved += storage.upsert(table, row)

        summary_rows = build_summary_tables(raw_orders, raw_ads, raw_commissions, summary_time, cycle)
        for table, rows in summary_rows.items():
            for row in rows:
                saved += storage.upsert(table, row)

        platform_rows = summary_rows[PLATFORM_COMPARE]
        total_row = next(row for row in summary_rows[DASHBOARD_TODAY] if row["平台"] == TOTAL_PLATFORM)
        cycle_results.append(
            SimulationCycle(
                cycle=cycle,
                summary_time=summary_time.strftime("%Y-%m-%d %H:%M:%S"),
                saved_count=saved,
                total_row=total_row,
                platform_rows=platform_rows,
            )
        )

    tables = [
        ORDERS_RAW,
        AD_COST_RAW,
        INFLUENCER_COMMISSION_RAW,
        DASHBOARD_TODAY,
        ROI_DAILY_SUMMARY,
        PLATFORM_COMPARE,
    ]
    result = SimulationRunResult(
        cycles=cycle_results,
        table_counts={table: storage.count(table) for table in tables},
        local_path=str(local_path.resolve()),
        evidence_path=str((evidence_root / "simulation-result.json").resolve()),
    )
    write_result_json(result)
    return result


def write_simulation_to_feishu(
    settings: Settings,
    local_path: str | Path,
    base_url: str = FEISHU_BASE_URL,
) -> FeishuSimulationWriteResult:
    ensure_feishu_no_proxy()
    if not settings.feishu_app_id or not settings.feishu_app_secret or not settings.feishu_app_token:
        raise RuntimeError("FEISHU_APP_ID, FEISHU_APP_SECRET, and FEISHU_APP_TOKEN are required for real Feishu write")
    client = FeishuSimulationClient(settings, base_url=base_url)
    table_ids = client.ensure_tables()
    local_data = read_local_records(local_path)
    saved = 0
    for table_key in table_ids:
        rows = [record["fields"] for record in local_data.get(table_key, [])]
        saved += client.upsert_records(table_ids[table_key], rows)
    return FeishuSimulationWriteResult(
        mode="feishu",
        app_token=settings.feishu_app_token,
        app_url=feishu_base_url(settings.feishu_app_token),
        table_ids=table_ids,
        saved_count=saved,
    )


class FeishuSimulationClient:
    def __init__(self, settings: Settings, base_url: str = FEISHU_BASE_URL) -> None:
        self.settings = settings
        self.client = FeishuOpenApiClient(settings.feishu_app_id, settings.feishu_app_secret, base_url=base_url)

    def ensure_tables(self) -> dict[str, str]:
        existing = self.client.list_tables(self.settings.feishu_app_token)
        existing_by_name = {str(item.get("name")): item for item in existing if item.get("name")}
        table_ids: dict[str, str] = {}
        for spec in roi_simulation_table_specs():
            table = self.client.ensure_table(self.settings.feishu_app_token, spec, existing_by_name)
            table_id = str(table.get("table_id") or "")
            if not table_id:
                raise RuntimeError(f"Feishu table {spec.name} did not return table_id")
            table_ids[spec.key] = table_id
            self.ensure_fields(table_id, spec)
        return table_ids

    def ensure_fields(self, table_id: str, spec: PlatformTableSpec) -> None:
        existing = self.list_field_names(table_id)
        for field in spec.fields:
            field_name = str(field["field_name"])
            if field_name in existing:
                continue
            self.request(
                "POST",
                f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/fields",
                {"field_name": field_name, "type": field["type"]},
            )
            existing.add(field_name)

    def list_field_names(self, table_id: str) -> set[str]:
        page_token = None
        names: set[str] = set()
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/fields", params=params)
            for item in data.get("items", []) or []:
                if item.get("field_name"):
                    names.add(str(item["field_name"]))
            if not data.get("has_more"):
                return names
            page_token = data.get("page_token")

    def upsert_records(self, table_id: str, rows: list[dict[str, Any]]) -> int:
        existing = self.record_index(table_id)
        saved = 0
        for row in rows:
            unique_key = str(row.get("unique_key") or "")
            if not unique_key:
                continue
            record_id = existing.get(unique_key)
            payload = {"fields": row}
            if record_id:
                self.request("PUT", f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records/{record_id}", payload)
            else:
                data = self.request("POST", f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records", payload)
                record = data.get("record") or {}
                if record.get("record_id"):
                    existing[unique_key] = str(record["record_id"])
            saved += 1
        return saved

    def record_index(self, table_id: str) -> dict[str, str]:
        page_token = None
        records: dict[str, str] = {}
        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self.request("GET", f"/bitable/v1/apps/{self.settings.feishu_app_token}/tables/{table_id}/records", params=params)
            for item in data.get("items", []) or []:
                fields = item.get("fields") or {}
                unique_key = fields.get("unique_key")
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


def build_order_rows(summary_time: datetime, cycle: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stat_date = summary_time.date().isoformat()
    update_time = summary_time.strftime("%Y-%m-%d %H:%M:%S")
    for platform in PLATFORMS:
        paid, refund = ORDER_EVENTS[platform][cycle - 1]
        order_id = f"{platform_code(platform)}{summary_time.strftime('%Y%m%d%H%M')}"
        rows.append(
            {
                "unique_key": f"{platform}_{SHOP_ID}_{order_id}",
                "统计日期": stat_date,
                "平台": platform,
                "店铺ID": SHOP_ID,
                "店铺名称": SHOP_NAME,
                "订单号": order_id,
                "支付时间": update_time,
                "支付金额": paid,
                "退款金额": refund,
                "净成交额": round(paid - refund, 2),
                "订单状态": "已支付" if refund == 0 else "部分退款",
                "数据来源": "模拟订单",
                "数据状态": "normal",
                "错误信息": None,
                "更新时间": update_time,
            }
        )
    return rows


def build_ad_cost_rows(summary_time: datetime, cycle: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stat_date = summary_time.date().isoformat()
    update_time = summary_time.strftime("%Y-%m-%d %H:%M:%S")
    minute_key = summary_time.strftime("%Y%m%d%H%M")
    for platform in PLATFORMS:
        channel, cost, impressions, clicks, backend_roi = AD_COST_EVENTS[platform][cycle - 1]
        rows.append(
            {
                "unique_key": f"{platform}_{SHOP_ID}_{channel}_{minute_key}",
                "统计日期": stat_date,
                "平台": platform,
                "店铺ID": SHOP_ID,
                "店铺名称": SHOP_NAME,
                "广告渠道": channel,
                "推广消耗": cost,
                "展现量": impressions,
                "点击量": clicks,
                "平台显示ROI": backend_roi,
                "数据来源": "模拟投流",
                "数据状态": "normal",
                "更新时间": update_time,
            }
        )
    return rows


def build_influencer_commission_rows(summary_time: datetime, cycle: int) -> list[dict[str, Any]]:
    paid, refund = ORDER_EVENTS["抖音"][cycle - 1]
    rate = DOUYIN_COMMISSION_RATES[cycle - 1]
    creator_id, creator_name = DOUYIN_CREATORS[(cycle - 1) % len(DOUYIN_CREATORS)]
    order_id = f"{platform_code('抖音')}{summary_time.strftime('%Y%m%d%H%M')}"
    estimated = round((paid - refund) * rate, 2)
    settled = round(estimated * 0.96, 2) if cycle in {1, 2} else None
    adopted = settled if settled is not None else estimated
    update_time = summary_time.strftime("%Y-%m-%d %H:%M:%S")
    return [
        {
            "unique_key": f"抖音_{SHOP_ID}_{order_id}_{creator_id}",
            "统计日期": summary_time.date().isoformat(),
            "平台": "抖音",
            "店铺ID": SHOP_ID,
            "店铺名称": SHOP_NAME,
            "订单号": order_id,
            "达人ID": creator_id,
            "达人昵称": creator_name,
            "支付金额": paid,
            "佣金率": rate,
            "预估佣金": estimated,
            "结算佣金": settled,
            "采用佣金": adopted,
            "结算状态": "已结算" if settled is not None else "未结算",
            "数据来源": "模拟达人佣金",
            "数据状态": "normal",
            "更新时间": update_time,
        }
    ]


def build_summary_tables(
    orders: list[dict[str, Any]],
    ads: list[dict[str, Any]],
    commissions: list[dict[str, Any]],
    summary_time: datetime,
    cycle: int,
) -> dict[str, list[dict[str, Any]]]:
    stat_date = summary_time.date()
    rows = [summary_row(platform, orders, ads, commissions, stat_date, summary_time, cycle) for platform in PLATFORMS]
    total = total_summary_row(rows, stat_date, summary_time, cycle)
    dashboard_rows = [dashboard_fields(row) for row in [*rows, total]]
    roi_rows = [roi_daily_fields(row) for row in [*rows, total]]
    compare_rows = [platform_compare_fields(row) for row in [*rows, total]]
    return {
        DASHBOARD_TODAY: dashboard_rows,
        ROI_DAILY_SUMMARY: roi_rows,
        PLATFORM_COMPARE: compare_rows,
    }


def summary_row(
    platform: str,
    orders: list[dict[str, Any]],
    ads: list[dict[str, Any]],
    commissions: list[dict[str, Any]],
    stat_date: date,
    summary_time: datetime,
    cycle: int,
) -> dict[str, Any]:
    platform_orders = [row for row in orders if row["平台"] == platform and row["统计日期"] == stat_date.isoformat() and row["数据状态"] == "normal"]
    platform_ads = [row for row in ads if row["平台"] == platform and row["统计日期"] == stat_date.isoformat() and row["数据状态"] == "normal"]
    platform_commissions = [
        row for row in commissions if row["平台"] == platform and row["统计日期"] == stat_date.isoformat() and row["数据状态"] == "normal"
    ]
    payment = round(sum(float(row["支付金额"]) for row in platform_orders), 2)
    refund = round(sum(float(row["退款金额"]) for row in platform_orders), 2)
    net = round(sum(float(row["净成交额"]) for row in platform_orders), 2)
    ad_cost = round(sum(float(row["推广消耗"]) for row in platform_ads), 2) if platform_ads else None
    commission = round(sum(float(row["采用佣金"]) for row in platform_commissions), 2)
    known_input = round((ad_cost or 0) + commission, 2) if ad_cost is not None else None
    per_1000_known = safe_div((net - (ad_cost or 0) - commission) * 1000, ad_cost, 2) if ad_cost is not None else None
    return {
        "unique_key": f"{stat_date.isoformat()}_{platform}_{SHOP_ID}_{summary_time.strftime('%H%M')}",
        "统计日期": stat_date.isoformat(),
        "汇总时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
        "模拟轮次": cycle,
        "平台": platform,
        "店铺ID": SHOP_ID,
        "店铺名称": SHOP_NAME,
        "订单数": len(platform_orders),
        "支付金额": payment,
        "退款金额": refund,
        "净成交额": net,
        "广告消耗": ad_cost,
        "达人佣金": commission,
        "已知总投入": known_input,
        "真实ROI_仅广告": safe_div(net, ad_cost),
        "真实ROI_含佣金": safe_div(net, known_input),
        "每投1000净成交": safe_div(net * 1000, ad_cost, 2),
        "每投1000已知贡献": per_1000_known,
        "当前判断": business_judgement(per_1000_known),
        "结算状态": "实时预估",
        "数据状态": "normal" if ad_cost is not None else "partial",
        "更新时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def total_summary_row(rows: list[dict[str, Any]], stat_date: date, summary_time: datetime, cycle: int) -> dict[str, Any]:
    payment = round(sum(float(row["支付金额"]) for row in rows), 2)
    refund = round(sum(float(row["退款金额"]) for row in rows), 2)
    net = round(sum(float(row["净成交额"]) for row in rows), 2)
    ad_cost = round(sum(float(row["广告消耗"] or 0) for row in rows), 2)
    commission = round(sum(float(row["达人佣金"]) for row in rows), 2)
    known_input = round(ad_cost + commission, 2)
    per_1000_known = safe_div((net - ad_cost - commission) * 1000, ad_cost, 2)
    return {
        "unique_key": f"{stat_date.isoformat()}_{TOTAL_PLATFORM}_{SHOP_ID}_{summary_time.strftime('%H%M')}",
        "统计日期": stat_date.isoformat(),
        "汇总时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
        "模拟轮次": cycle,
        "平台": TOTAL_PLATFORM,
        "店铺ID": SHOP_ID,
        "店铺名称": SHOP_NAME,
        "订单数": sum(int(row["订单数"]) for row in rows),
        "支付金额": payment,
        "退款金额": refund,
        "净成交额": net,
        "广告消耗": ad_cost,
        "达人佣金": commission,
        "已知总投入": known_input,
        "真实ROI_仅广告": safe_div(net, ad_cost),
        "真实ROI_含佣金": safe_div(net, known_input),
        "每投1000净成交": safe_div(net * 1000, ad_cost, 2),
        "每投1000已知贡献": per_1000_known,
        "当前判断": business_judgement(per_1000_known),
        "结算状态": "实时预估",
        "数据状态": "normal",
        "更新时间": summary_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def dashboard_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "unique_key": "dashboard_today_" + row["unique_key"],
        "统计日期": row["统计日期"],
        "汇总时间": row["汇总时间"],
        "模拟轮次": row["模拟轮次"],
        "平台": row["平台"],
        "今日订单数": row["订单数"],
        "今日支付金额": row["支付金额"],
        "今日退款金额": row["退款金额"],
        "今日净成交额": row["净成交额"],
        "今日广告消耗": row["广告消耗"],
        "今日达人佣金": row["达人佣金"],
        "已知总投入": row["已知总投入"],
        "真实ROI_仅广告": row["真实ROI_仅广告"],
        "真实ROI_含佣金": row["真实ROI_含佣金"],
        "每投1000净成交": row["每投1000净成交"],
        "每投1000已知贡献": row["每投1000已知贡献"],
        "当前判断": row["当前判断"],
        "数据状态": row["数据状态"],
        "更新时间": row["更新时间"],
    }


def roi_daily_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "unique_key": "roi_daily_" + row["unique_key"],
        "统计日期": row["统计日期"],
        "汇总时间": row["汇总时间"],
        "模拟轮次": row["模拟轮次"],
        "平台": row["平台"],
        "店铺ID": row["店铺ID"],
        "店铺名称": row["店铺名称"],
        "订单数": row["订单数"],
        "支付金额": row["支付金额"],
        "退款金额": row["退款金额"],
        "净成交额": row["净成交额"],
        "广告消耗": row["广告消耗"],
        "达人佣金": row["达人佣金"],
        "已知总投入": row["已知总投入"],
        "真实ROI_仅广告": row["真实ROI_仅广告"],
        "真实ROI_含佣金": row["真实ROI_含佣金"],
        "每投1000净成交": row["每投1000净成交"],
        "每投1000已知贡献": row["每投1000已知贡献"],
        "结算状态": row["结算状态"],
        "数据状态": row["数据状态"],
    }


def platform_compare_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "unique_key": "platform_compare_" + row["unique_key"],
        "统计日期": row["统计日期"],
        "汇总时间": row["汇总时间"],
        "模拟轮次": row["模拟轮次"],
        "平台": row["平台"],
        "广告消耗": row["广告消耗"],
        "净成交额": row["净成交额"],
        "达人佣金": row["达人佣金"],
        "每投1000净成交": row["每投1000净成交"],
        "每投1000已知贡献": row["每投1000已知贡献"],
        "判断": row["当前判断"],
    }


def business_judgement(per_1000_known_contribution: float | None) -> str:
    if per_1000_known_contribution is None:
        return "观察"
    if per_1000_known_contribution < 0:
        return "亏损"
    if per_1000_known_contribution < 1800:
        return "观察"
    return "正常"


def platform_code(platform: str) -> str:
    return {
        "淘宝": "TB",
        "抖音": "DY",
        "拼多多": "PDD",
        "视频号": "SPH",
    }[platform]


def write_result_json(result: SimulationRunResult) -> None:
    payload = {
        "cycles": [
            {
                "cycle": cycle.cycle,
                "summary_time": cycle.summary_time,
                "saved_count": cycle.saved_count,
                "total_row": cycle.total_row,
                "platform_rows": cycle.platform_rows,
            }
            for cycle in result.cycles
        ],
        "table_counts": result.table_counts,
        "local_path": result.local_path,
    }
    Path(result.evidence_path).write_text(json_dumps(payload), encoding="utf-8")


def read_local_records(local_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    import json

    return json.loads(Path(local_path).read_text(encoding="utf-8"))


def roi_simulation_table_specs() -> list[PlatformTableSpec]:
    return [
        PlatformTableSpec("SHOPOPS_ROI_TABLE_ORDERS_RAW", ORDERS_RAW, ORDERS_RAW, typed_fields(order_field_names(), order_number_fields())),
        PlatformTableSpec("SHOPOPS_ROI_TABLE_AD_COST_RAW", AD_COST_RAW, AD_COST_RAW, typed_fields(ad_cost_field_names(), ad_cost_number_fields())),
        PlatformTableSpec(
            "SHOPOPS_ROI_TABLE_INFLUENCER_COMMISSION_RAW",
            INFLUENCER_COMMISSION_RAW,
            INFLUENCER_COMMISSION_RAW,
            typed_fields(influencer_field_names(), influencer_number_fields()),
        ),
        PlatformTableSpec(
            "SHOPOPS_ROI_TABLE_DASHBOARD_TODAY",
            DASHBOARD_TODAY,
            DASHBOARD_TODAY,
            typed_fields(dashboard_field_names(), dashboard_number_fields()),
        ),
        PlatformTableSpec(
            "SHOPOPS_ROI_TABLE_ROI_DAILY_SUMMARY",
            ROI_DAILY_SUMMARY,
            ROI_DAILY_SUMMARY,
            typed_fields(roi_daily_field_names(), roi_daily_number_fields()),
        ),
        PlatformTableSpec(
            "SHOPOPS_ROI_TABLE_PLATFORM_COMPARE",
            PLATFORM_COMPARE,
            PLATFORM_COMPARE,
            typed_fields(platform_compare_field_names(), platform_compare_number_fields()),
        ),
    ]


def typed_fields(names: list[str], number_names: set[str]) -> list[dict[str, Any]]:
    return [number_field(name) if name in number_names else text_field(name) for name in names]


def order_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "平台",
        "店铺ID",
        "店铺名称",
        "订单号",
        "支付时间",
        "支付金额",
        "退款金额",
        "净成交额",
        "订单状态",
        "数据来源",
        "数据状态",
        "错误信息",
        "更新时间",
    ]


def ad_cost_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "平台",
        "店铺ID",
        "店铺名称",
        "广告渠道",
        "推广消耗",
        "展现量",
        "点击量",
        "平台显示ROI",
        "数据来源",
        "数据状态",
        "更新时间",
    ]


def influencer_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "平台",
        "店铺ID",
        "店铺名称",
        "订单号",
        "达人ID",
        "达人昵称",
        "支付金额",
        "佣金率",
        "预估佣金",
        "结算佣金",
        "采用佣金",
        "结算状态",
        "数据来源",
        "数据状态",
        "更新时间",
    ]


def dashboard_field_names() -> list[str]:
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


def roi_daily_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "汇总时间",
        "模拟轮次",
        "平台",
        "店铺ID",
        "店铺名称",
        "订单数",
        "支付金额",
        "退款金额",
        "净成交额",
        "广告消耗",
        "达人佣金",
        "已知总投入",
        "真实ROI_仅广告",
        "真实ROI_含佣金",
        "每投1000净成交",
        "每投1000已知贡献",
        "结算状态",
        "数据状态",
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
    ]


def order_number_fields() -> set[str]:
    return {"支付金额", "退款金额", "净成交额"}


def ad_cost_number_fields() -> set[str]:
    return {"推广消耗", "展现量", "点击量", "平台显示ROI"}


def influencer_number_fields() -> set[str]:
    return {"支付金额", "佣金率", "预估佣金", "结算佣金", "采用佣金"}


def dashboard_number_fields() -> set[str]:
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


def roi_daily_number_fields() -> set[str]:
    return {
        "模拟轮次",
        "订单数",
        "支付金额",
        "退款金额",
        "净成交额",
        "广告消耗",
        "达人佣金",
        "已知总投入",
        "真实ROI_仅广告",
        "真实ROI_含佣金",
        "每投1000净成交",
        "每投1000已知贡献",
    }


def platform_compare_number_fields() -> set[str]:
    return {"模拟轮次", "广告消耗", "净成交额", "达人佣金", "每投1000净成交", "每投1000已知贡献"}


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
