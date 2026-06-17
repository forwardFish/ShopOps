from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from shopops.config import _load_dotenv, load_settings
from shopops.storage.feishu_bootstrap import merge_env_file
from scripts.import_daily_files_to_feishu import (
    F_ACTUAL_SPEND,
    F_CLICKS,
    F_CREATED_AT,
    F_DATE,
    F_DEAL_AMOUNT,
    F_FETCHED_AT,
    F_IMPRESSIONS,
    F_ORDER_NO,
    F_PAID_AMOUNT,
    F_PLATFORM,
    F_PLATFORM_ROI,
    F_FREIGHT_COST,
    F_OTHER_FEE,
    F_PLATFORM_FEE,
    F_PRODUCT_COST,
    F_RAW,
    F_REFUND_AMOUNT,
    F_ROI,
    F_SPEND,
    F_TRADE_AMOUNT,
    F_TRUE_ROI,
    F_QUANTITY,
    F_UNIQUE_KEY,
    NUMBER_FIELD,
    ORDER_TABLE_ENV,
    TEXT_FIELD,
    FeishuDailyClient,
    scalar_text,
)


PLATFORM_CODES = ("tmall", "douyin")
PLATFORM_NAMES = {"tmall": "天猫", "douyin": "抖音"}
TOTAL_PLATFORM = "总计"
DEFAULT_INTERVAL_TABLE_NAME = "投流小时段归因汇总"

ORDER_DETAIL_NUMBER_FIELDS = [
    "订单数",
    "实际卖出数量",
    "销售额",
    "退款金额",
    "有效销售额",
    "退款订单数",
    "退款率",
    "客单价",
    "件单价",
    "商品成本",
    "运费成本",
    "平台扣点",
    "其他费用",
    "预估佣金支出",
    "实际佣金支出",
    "达人佣金",
    "已知费用后利润",
    "经营利润估算",
    "已知费用利润率",
    "已知总投入",
    "投流后毛利",
    "ROI",
    "平台ROI",
    "喷壶数量",
    "喷壶有效销售额",
    "两用喷壶数量",
    "两用喷壶有效销售额",
    "皂液器数量",
    "皂液器有效销售额",
    "洗面奶数量",
    "洗面奶有效销售额",
    "配件数量",
    "配件有效销售额",
    "补差价数量",
    "补差价有效销售额",
]

PRODUCT_METRIC_FIELDS = [
    "喷壶数量",
    "喷壶有效销售额",
    "两用喷壶数量",
    "两用喷壶有效销售额",
    "皂液器数量",
    "皂液器有效销售额",
    "洗面奶数量",
    "洗面奶有效销售额",
    "配件数量",
    "配件有效销售额",
    "补差价数量",
    "补差价有效销售额",
]

ORDER_FORMULA_FIELDS = {
    "actual_sold_quantity": "公式_实际卖出数量",
    "sales_amount": "公式_销售额",
    "refund_amount": "公式_退款金额",
    "valid_sales_amount": "公式_有效销售额",
    "product_cost": "公式_商品成本",
    "freight_cost": "公式_运费成本",
    "platform_fee": "公式_平台扣点",
    "other_fee": "公式_其他费用",
}

ORDER_TIME_FIELDS = ["支付时间", "付款时间", F_CREATED_AT, "下单时间"]
ORDER_RATIO_FIELDS = {"退款率", "客单价", "件单价", "ROI", "平台ROI", "已知费用利润率"}
ORDER_ADDITIVE_DETAIL_FIELDS = [field_name for field_name in ORDER_DETAIL_NUMBER_FIELDS if field_name not in ORDER_RATIO_FIELDS]
ORDER_DETAIL_PREFIXES = ("今日累计", "新增")
AD_ROLLUP_NUMBER_FIELDS = [
    "今日累计投流消耗",
    "新增投流消耗",
    "今日累计投流成交金额",
    "新增投流成交金额",
    "今日累计投流ROI",
    "新增投流ROI",
]

ORDER_WINDOW_FIELDS = [
    F_ORDER_NO,
    *ORDER_TIME_FIELDS,
    F_PAID_AMOUNT,
    F_REFUND_AMOUNT,
    F_QUANTITY,
    F_PRODUCT_COST,
    F_FREIGHT_COST,
    F_PLATFORM_FEE,
    F_OTHER_FEE,
    "预估佣金支出",
    "实际佣金支出",
    *ORDER_FORMULA_FIELDS.values(),
    *PRODUCT_METRIC_FIELDS,
]

S_REQUIRED_FIELDS = [F_UNIQUE_KEY, "采集日期", F_PLATFORM, "窗口开始", "窗口结束"]
S_FIELD_TYPES = {
    F_UNIQUE_KEY: TEXT_FIELD,
    "采集日期": TEXT_FIELD,
    F_PLATFORM: TEXT_FIELD,
    "窗口开始": TEXT_FIELD,
    "窗口结束": TEXT_FIELD,
    "窗口小时": NUMBER_FIELD,
    "上次采集时间": TEXT_FIELD,
    "本次采集时间": TEXT_FIELD,
    "本次投流消耗": NUMBER_FIELD,
    "上次投流消耗": NUMBER_FIELD,
    "区间投流消耗": NUMBER_FIELD,
    "本次投流成交金额": NUMBER_FIELD,
    "上次投流成交金额": NUMBER_FIELD,
    "区间投流成交金额": NUMBER_FIELD,
    "区间订单数": NUMBER_FIELD,
    "区间订单销售额": NUMBER_FIELD,
    "区间实收款": NUMBER_FIELD,
    "区间退款金额": NUMBER_FIELD,
    "区间ROI": NUMBER_FIELD,
    "投流平台ROI": NUMBER_FIELD,
    F_IMPRESSIONS: NUMBER_FIELD,
    F_CLICKS: NUMBER_FIELD,
    "点击率": NUMBER_FIELD,
    **{field_name: NUMBER_FIELD for field_name in ORDER_DETAIL_NUMBER_FIELDS},
    **{f"{prefix}{field_name}": NUMBER_FIELD for prefix in ORDER_DETAIL_PREFIXES for field_name in ORDER_DETAIL_NUMBER_FIELDS},
    **{field_name: NUMBER_FIELD for field_name in AD_ROLLUP_NUMBER_FIELDS},
    "基准类型": TEXT_FIELD,
    "数据来源": TEXT_FIELD,
    F_RAW: TEXT_FIELD,
}


@dataclass(frozen=True)
class Snapshot:
    platform_code: str
    platform_name: str
    fetched_at: datetime
    stat_date: str
    spend: float
    deal_amount: float
    impressions: float | None = None
    clicks: float | None = None
    roi: float | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreviousSnapshot:
    fetched_at: datetime
    spend: float
    deal_amount: float


@dataclass(frozen=True)
class OrderWindowSummary:
    count: int = 0
    actual_sold_quantity: float = 0.0
    sales_amount: float = 0.0
    paid_amount: float = 0.0
    refund_amount: float = 0.0
    valid_sales_override: float | None = None
    product_cost: float = 0.0
    freight_cost: float = 0.0
    platform_fee: float = 0.0
    other_fee: float = 0.0
    estimated_commission: float = 0.0
    actual_commission: float = 0.0
    refund_order_count: int = 0
    product_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def valid_sales_amount(self) -> float:
        if self.valid_sales_override is not None:
            return round(max(0.0, self.valid_sales_override), 6)
        return round(max(0.0, self.sales_amount - self.refund_amount), 6)

    @property
    def commission_amount(self) -> float:
        return round(self.actual_commission or self.estimated_commission, 6)

    @property
    def known_fee_profit(self) -> float:
        return round(
            self.valid_sales_amount
            - self.product_cost
            - self.freight_cost
            - self.platform_fee
            - self.other_fee
            - self.commission_amount,
            6,
        )

    @property
    def refund_rate(self) -> float | None:
        return safe_div(self.refund_amount, self.sales_amount)

    @property
    def avg_order_amount(self) -> float | None:
        return safe_div(self.sales_amount, self.count)

    @property
    def avg_item_amount(self) -> float | None:
        return safe_div(self.sales_amount, self.actual_sold_quantity)

    @property
    def known_fee_profit_rate(self) -> float | None:
        return safe_div(self.known_fee_profit, self.valid_sales_amount)


def interval_table_name() -> str:
    _load_dotenv()
    settings = load_settings()
    return os.getenv("SHOPOPS_HOURLY_AD_INTERVAL_TABLE_NAME") or getattr(
        settings, "shopops_hourly_ad_interval_table_name", DEFAULT_INTERVAL_TABLE_NAME
    )


def configured_interval_table_id() -> str:
    _load_dotenv()
    settings = load_settings()
    return os.getenv("SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID") or getattr(
        settings, "shopops_hourly_ad_interval_table_id", ""
    )


def ensure_interval_table(
    client: FeishuDailyClient,
    *,
    table_id: str = "",
    table_name: str = DEFAULT_INTERVAL_TABLE_NAME,
    env_path: str | Path = ".env",
) -> dict[str, Any]:
    if table_id:
        created_fields = client.ensure_missing_fields_for_rows(table_id, [S_FIELD_TYPES], S_FIELD_TYPES)
        return {"table_id": table_id, "table_name": table_name, "reused": True, "created_fields": created_fields}

    existing = list_tables(client)
    for item in existing:
        if str(item.get("name") or "") == table_name:
            found_id = str(item.get("table_id") or "")
            created_fields = client.ensure_missing_fields_for_rows(found_id, [S_FIELD_TYPES], S_FIELD_TYPES)
            persist_interval_table_env(found_id, table_name, env_path)
            return {"table_id": found_id, "table_name": table_name, "reused": True, "created_fields": created_fields}

    fields = [{"field_name": name, "type": field_type} for name, field_type in S_FIELD_TYPES.items()]
    data = client.request(
        "POST",
        f"/bitable/v1/apps/{client.app_token}/tables",
        {"table": {"name": table_name, "default_view_name": "默认表格视图", "fields": fields}},
    )
    new_id = str(data.get("table_id") or (data.get("table") or {}).get("table_id") or "")
    if not new_id:
        raise RuntimeError(f"Feishu create interval table did not return table_id: {data}")
    persist_interval_table_env(new_id, table_name, env_path)
    return {"table_id": new_id, "table_name": table_name, "reused": False, "created_fields": list(S_FIELD_TYPES)}


def persist_interval_table_env(table_id: str, table_name: str, env_path: str | Path = ".env") -> None:
    try:
        merge_env_file(
            env_path,
            {
                "SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID": table_id,
                "SHOPOPS_HOURLY_AD_INTERVAL_TABLE_NAME": table_name,
            },
        )
    except Exception:
        # Table lookup by name is enough for future runs; env persistence is only a convenience.
        return


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


def summarize_hourly_interval(
    ads_results: list[dict[str, Any]],
    *,
    stat_date: str,
    run_token: str,
    table_id: str = "",
    table_name: str = DEFAULT_INTERVAL_TABLE_NAME,
    env_path: str | Path = ".env",
    client: FeishuDailyClient | None = None,
    default_window_minutes: int = 60,
    dry_run: bool = False,
) -> dict[str, Any]:
    snapshots = snapshots_from_ads_results(ads_results)
    if not snapshots:
        return {"status": "skipped", "reason": "no_successful_ad_snapshots", "rows": []}

    client = client or FeishuDailyClient()
    ensured = ensure_interval_table(client, table_id=table_id, table_name=table_name, env_path=env_path)
    target_table_id = str(ensured["table_id"])

    rows: list[dict[str, Any]] = []
    per_platform: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        previous = latest_previous_snapshot(client, target_table_id, snapshot.platform_name, snapshot.stat_date, snapshot.fetched_at)
        window_start, baseline = previous_window_start(snapshot, previous, default_window_minutes)
        order_summary = summarize_orders_for_window(client, snapshot.platform_name, window_start, snapshot.fetched_at)
        today_start = datetime.combine(snapshot.fetched_at.date(), datetime.min.time()) - timedelta(microseconds=1)
        today_order_summary = summarize_orders_for_window(client, snapshot.platform_name, today_start, snapshot.fetched_at)
        row = build_platform_row(
            snapshot,
            previous,
            window_start,
            baseline,
            order_summary,
            today_order_summary,
            run_token,
        )
        rows.append(row)
        per_platform[snapshot.platform_code] = {
            "row": row,
            "orders": order_summary,
            "today_orders": today_order_summary,
            "previous": previous,
        }

    if rows:
        rows.append(build_total_row(rows, stat_date, run_token))

    if dry_run:
        write_result = {"status": "dry_run", "rows": rows}
        readback_count = 0
    else:
        client.ensure_missing_fields_for_rows(target_table_id, rows, S_FIELD_TYPES)
        write_result = client.upsert_rows(
            table_id=target_table_id,
            rows=rows,
            required_fields=S_REQUIRED_FIELDS,
            fallback_match_fields=(F_PLATFORM, "窗口结束"),
            allow_partial_fields=False,
        )
        readback = client.readback_by_unique_key(target_table_id, {row[F_UNIQUE_KEY] for row in rows})
        readback_count = len(readback)

    status = "success" if dry_run or readback_count == len(rows) else "readback_mismatch"
    return {
        "status": status,
        "table": ensured,
        "row_count": len(rows),
        "rows": rows,
        "write": write_result,
        "readback_count": readback_count,
        "platforms": sorted(per_platform),
    }


def snapshots_from_ads_results(ads_results: list[dict[str, Any]]) -> list[Snapshot]:
    snapshots: list[Snapshot] = []
    for item in ads_results:
        result = item.get("result") or {}
        if result.get("returncode") not in (0, None):
            continue
        evidence_path = Path(str(item.get("evidence") or ""))
        if not evidence_path.exists():
            continue
        try:
            payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(payload.get("status") or "") not in {"success", "dry_run"}:
            continue
        row = payload.get("row") or {}
        platform_code = str(payload.get("platform") or item.get("platform") or "")
        snapshot = snapshot_from_ad_row(row, platform_code=platform_code, stat_date=str(payload.get("date") or ""))
        if snapshot:
            snapshots.append(snapshot)
    snapshots.sort(key=lambda item: PLATFORM_CODES.index(item.platform_code) if item.platform_code in PLATFORM_CODES else 99)
    return snapshots


def snapshot_from_ad_row(row: dict[str, Any], *, platform_code: str = "", stat_date: str = "") -> Snapshot | None:
    platform_name = scalar_text(row.get(F_PLATFORM))
    if not platform_name and platform_code in PLATFORM_NAMES:
        platform_name = PLATFORM_NAMES[platform_code]
    if not platform_code:
        platform_code = next((code for code, name in PLATFORM_NAMES.items() if name == platform_name), "")
    if platform_code not in PLATFORM_NAMES:
        return None
    fetched_at = parse_datetime(row.get(F_FETCHED_AT)) or datetime.now()
    date_text = scalar_text(row.get(F_DATE)) or stat_date or fetched_at.date().isoformat()
    spend = first_number(row, F_ACTUAL_SPEND, F_SPEND) or 0.0
    deal = first_number(row, F_DEAL_AMOUNT, F_TRADE_AMOUNT) or 0.0
    return Snapshot(
        platform_code=platform_code,
        platform_name=platform_name or PLATFORM_NAMES[platform_code],
        fetched_at=fetched_at,
        stat_date=date_text,
        spend=spend,
        deal_amount=deal,
        impressions=first_number(row, F_IMPRESSIONS),
        clicks=first_number(row, F_CLICKS),
        roi=first_number(row, F_ROI, F_PLATFORM_ROI, F_TRUE_ROI),
        raw=row,
    )


def latest_previous_snapshot(
    client: FeishuDailyClient,
    table_id: str,
    platform_name: str,
    stat_date: str,
    before: datetime,
) -> PreviousSnapshot | None:
    latest: PreviousSnapshot | None = None
    fields = [F_PLATFORM, "采集日期", "本次采集时间", "本次投流消耗", "本次投流成交金额"]
    for record in client.iter_records(table_id, fields):
        item = record.get("fields") or {}
        if scalar_text(item.get(F_PLATFORM)) != platform_name:
            continue
        if scalar_text(item.get("采集日期")) != stat_date:
            continue
        fetched_at = parse_datetime(item.get("本次采集时间"))
        if not fetched_at or fetched_at >= before:
            continue
        previous = PreviousSnapshot(
            fetched_at=fetched_at,
            spend=to_number(item.get("本次投流消耗")) or 0.0,
            deal_amount=to_number(item.get("本次投流成交金额")) or 0.0,
        )
        if latest is None or previous.fetched_at > latest.fetched_at:
            latest = previous
    return latest


def previous_window_start(
    snapshot: Snapshot,
    previous: PreviousSnapshot | None,
    default_window_minutes: int,
) -> tuple[datetime, str]:
    if previous:
        return previous.fetched_at, "上一轮采集"
    start = snapshot.fetched_at - timedelta(minutes=default_window_minutes)
    day_start = datetime.combine(snapshot.fetched_at.date(), datetime.min.time())
    if start < day_start:
        start = day_start
    return start, "无上一轮，默认回看"


def summarize_orders_for_window(
    client: FeishuDailyClient,
    platform_name: str,
    window_start: datetime,
    window_end: datetime,
) -> OrderWindowSummary:
    table_id = order_table_id(platform_name)
    if not table_id:
        return OrderWindowSummary()
    paid = 0.0
    sales = 0.0
    refund = 0.0
    valid_sales = 0.0
    actual_sold_quantity = 0.0
    product_cost = 0.0
    freight_cost = 0.0
    platform_fee = 0.0
    other_fee = 0.0
    estimated_commission = 0.0
    actual_commission = 0.0
    seen_orders: set[str] = set()
    refund_orders: set[str] = set()
    product_metrics = {field_name: 0.0 for field_name in PRODUCT_METRIC_FIELDS}
    existing_fields = client.field_names(table_id) if hasattr(client, "field_names") else set(ORDER_WINDOW_FIELDS)
    readable_fields = [field_name for field_name in ORDER_WINDOW_FIELDS if field_name in existing_fields]
    if not any(field_name in existing_fields for field_name in ORDER_TIME_FIELDS):
        return OrderWindowSummary()
    for record in client.iter_records(table_id, readable_fields):
        fields = record.get("fields") or {}
        order_time = first_datetime(fields, *ORDER_TIME_FIELDS)
        if not order_time or not (window_start < order_time <= window_end):
            continue
        order_no = scalar_text(fields.get(F_ORDER_NO)) or str(record.get("record_id") or "")
        seen_orders.add(order_no)
        row_actual_sold_quantity = first_number(fields, ORDER_FORMULA_FIELDS["actual_sold_quantity"], F_QUANTITY, "商品数量") or 0.0
        row_sales = first_number(fields, ORDER_FORMULA_FIELDS["sales_amount"], F_PAID_AMOUNT, "支付金额", "实收款") or 0.0
        row_paid = first_number(fields, F_PAID_AMOUNT, "支付金额", ORDER_FORMULA_FIELDS["sales_amount"]) or row_sales
        row_refund = first_number(fields, ORDER_FORMULA_FIELDS["refund_amount"], F_REFUND_AMOUNT) or 0.0
        row_valid_sales = first_number(fields, ORDER_FORMULA_FIELDS["valid_sales_amount"])
        if row_valid_sales is None:
            row_valid_sales = max(0.0, row_sales - row_refund)
        actual_sold_quantity += row_actual_sold_quantity
        sales += row_sales
        paid += row_paid
        refund += row_refund
        valid_sales += row_valid_sales
        product_cost += first_number(fields, ORDER_FORMULA_FIELDS["product_cost"], F_PRODUCT_COST) or 0.0
        freight_cost += first_number(fields, ORDER_FORMULA_FIELDS["freight_cost"], F_FREIGHT_COST) or 0.0
        platform_fee += first_number(fields, ORDER_FORMULA_FIELDS["platform_fee"], F_PLATFORM_FEE) or 0.0
        other_fee += first_number(fields, ORDER_FORMULA_FIELDS["other_fee"], F_OTHER_FEE) or 0.0
        estimated_commission += first_number(fields, "预估佣金支出") or 0.0
        actual_commission += first_number(fields, "实际佣金支出") or 0.0
        if row_refund > 0:
            refund_orders.add(order_no)
        for field_name in PRODUCT_METRIC_FIELDS:
            product_metrics[field_name] += to_number(fields.get(field_name)) or 0.0
    return OrderWindowSummary(
        count=len(seen_orders),
        actual_sold_quantity=round(actual_sold_quantity, 6),
        sales_amount=round(sales, 6),
        paid_amount=round(paid, 6),
        refund_amount=round(refund, 6),
        valid_sales_override=round(valid_sales, 6),
        product_cost=round(product_cost, 6),
        freight_cost=round(freight_cost, 6),
        platform_fee=round(platform_fee, 6),
        other_fee=round(other_fee, 6),
        estimated_commission=round(estimated_commission, 6),
        actual_commission=round(actual_commission, 6),
        refund_order_count=len(refund_orders),
        product_metrics={key: round(value, 6) for key, value in product_metrics.items()},
    )


def order_table_id(platform_name: str) -> str:
    _load_dotenv()
    env_name = ORDER_TABLE_ENV.get(platform_name, "")
    if env_name:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    settings = load_settings()
    return settings.shopops_order_table_id


def build_platform_row(
    snapshot: Snapshot,
    previous: PreviousSnapshot | None,
    window_start: datetime,
    baseline: str,
    order_summary: OrderWindowSummary,
    today_order_summary: OrderWindowSummary,
    run_token: str,
) -> dict[str, Any]:
    previous_spend = previous.spend if previous else 0.0
    previous_deal = previous.deal_amount if previous else 0.0
    delta_spend = non_negative_delta(snapshot.spend, previous_spend)
    delta_deal = non_negative_delta(snapshot.deal_amount, previous_deal)
    interval_platform_roi = safe_div(delta_deal, delta_spend)
    today_platform_roi = snapshot.roi if snapshot.roi is not None else safe_div(snapshot.deal_amount, snapshot.spend)
    detail_fields = build_order_detail_fields(
        order_summary,
        ad_spend=delta_spend,
        ad_deal_amount=delta_deal,
        platform_roi=interval_platform_roi,
    )
    today_detail_fields = build_order_detail_fields(
        today_order_summary,
        ad_spend=snapshot.spend,
        ad_deal_amount=snapshot.deal_amount,
        platform_roi=today_platform_roi,
    )
    return {
        F_UNIQUE_KEY: interval_unique_key(snapshot.platform_code, snapshot.fetched_at, run_token),
        "采集日期": snapshot.stat_date,
        F_PLATFORM: snapshot.platform_name,
        "窗口开始": format_dt(window_start),
        "窗口结束": format_dt(snapshot.fetched_at),
        "窗口小时": round((snapshot.fetched_at - window_start).total_seconds() / 3600, 4),
        "上次采集时间": format_dt(previous.fetched_at) if previous else "",
        "本次采集时间": format_dt(snapshot.fetched_at),
        "本次投流消耗": snapshot.spend,
        "上次投流消耗": previous_spend,
        "区间投流消耗": delta_spend,
        "本次投流成交金额": snapshot.deal_amount,
        "上次投流成交金额": previous_deal,
        "区间投流成交金额": delta_deal,
        "区间订单数": order_summary.count,
        "区间订单销售额": order_summary.valid_sales_amount,
        "区间实收款": order_summary.paid_amount,
        "区间退款金额": order_summary.refund_amount,
        "区间ROI": safe_div(order_summary.valid_sales_amount, delta_spend),
        "投流平台ROI": snapshot.roi,
        "今日累计投流消耗": snapshot.spend,
        "新增投流消耗": delta_spend,
        "今日累计投流成交金额": snapshot.deal_amount,
        "新增投流成交金额": delta_deal,
        "今日累计投流ROI": today_platform_roi,
        "新增投流ROI": interval_platform_roi,
        F_IMPRESSIONS: snapshot.impressions,
        F_CLICKS: snapshot.clicks,
        "点击率": safe_div(snapshot.clicks, snapshot.impressions),
        **detail_fields,
        **prefix_detail_fields("新增", detail_fields),
        **prefix_detail_fields("今日累计", today_detail_fields),
        "基准类型": baseline,
        "数据来源": "hourly_shopops_import",
        F_RAW: json.dumps(snapshot.raw or {}, ensure_ascii=False, sort_keys=True),
    }


def build_total_row(rows: list[dict[str, Any]], stat_date: str, run_token: str) -> dict[str, Any]:
    window_end = max(scalar_text(row.get("窗口结束")) for row in rows)
    window_start = min(scalar_text(row.get("窗口开始")) for row in rows)
    spend = sum(row_number(row, "区间投流消耗") for row in rows)
    sales = sum(row_number(row, "区间订单销售额") for row in rows)
    order_count = sum(row_number(row, "订单数") for row in rows)
    quantity = sum(row_number(row, "实际卖出数量") for row in rows)
    gross_sales = sum(row_number(row, "销售额") for row in rows)
    refund = sum(row_number(row, "退款金额") for row in rows)
    valid_sales = sum(row_number(row, "有效销售额") for row in rows)
    known_fee_profit = sum(row_number(row, "已知费用后利润") for row in rows)
    total_row = {
        F_UNIQUE_KEY: f"hourly_ads_total_{date_key(window_end)}_{run_token}",
        "采集日期": stat_date,
        F_PLATFORM: TOTAL_PLATFORM,
        "窗口开始": window_start,
        "窗口结束": window_end,
        "窗口小时": round(sum(row_number(row, "窗口小时") for row in rows) / max(1, len(rows)), 4),
        "上次采集时间": "",
        "本次采集时间": window_end,
        "本次投流消耗": sum(row_number(row, "本次投流消耗") for row in rows),
        "上次投流消耗": sum(row_number(row, "上次投流消耗") for row in rows),
        "区间投流消耗": spend,
        "本次投流成交金额": sum(row_number(row, "本次投流成交金额") for row in rows),
        "上次投流成交金额": sum(row_number(row, "上次投流成交金额") for row in rows),
        "区间投流成交金额": sum(row_number(row, "区间投流成交金额") for row in rows),
        "区间订单数": sum(row_number(row, "区间订单数") for row in rows),
        "区间订单销售额": sales,
        "区间实收款": sum(row_number(row, "区间实收款") for row in rows),
        "区间退款金额": sum(row_number(row, "区间退款金额") for row in rows),
        "区间ROI": safe_div(sales, spend),
        "投流平台ROI": safe_div(sum(row_number(row, "区间投流成交金额") for row in rows), spend),
        "今日累计投流消耗": sum(row_number(row, "今日累计投流消耗") for row in rows),
        "新增投流消耗": sum(row_number(row, "新增投流消耗") for row in rows),
        "今日累计投流成交金额": sum(row_number(row, "今日累计投流成交金额") for row in rows),
        "新增投流成交金额": sum(row_number(row, "新增投流成交金额") for row in rows),
        F_IMPRESSIONS: sum(row_number(row, F_IMPRESSIONS) for row in rows),
        F_CLICKS: sum(row_number(row, F_CLICKS) for row in rows),
        "点击率": safe_div(sum(row_number(row, F_CLICKS) for row in rows), sum(row_number(row, F_IMPRESSIONS) for row in rows)),
        "基准类型": "平台合计",
        "数据来源": "hourly_shopops_import",
        F_RAW: json.dumps({"platform_rows": [row[F_UNIQUE_KEY] for row in rows]}, ensure_ascii=False, sort_keys=True),
    }
    for field_name in ORDER_ADDITIVE_DETAIL_FIELDS:
        total_row[field_name] = sum(row_number(row, field_name) for row in rows)
    total_row.update(
        {
            "订单数": order_count,
            "实际卖出数量": quantity,
            "销售额": gross_sales,
            "退款金额": refund,
            "有效销售额": valid_sales,
            "退款率": safe_div(refund, gross_sales),
            "客单价": safe_div(gross_sales, order_count),
            "件单价": safe_div(gross_sales, quantity),
            "ROI": safe_div(valid_sales, spend),
            "平台ROI": safe_div(sum(row_number(row, "区间投流成交金额") for row in rows), spend),
            "已知费用利润率": safe_div(known_fee_profit, valid_sales),
        }
    )
    total_row["今日累计投流ROI"] = safe_div(total_row["今日累计投流成交金额"], total_row["今日累计投流消耗"])
    total_row["新增投流ROI"] = safe_div(total_row["新增投流成交金额"], total_row["新增投流消耗"])
    add_prefixed_total_fields(total_row, rows, "新增")
    add_prefixed_total_fields(total_row, rows, "今日累计")
    return total_row


def build_order_detail_fields(
    order_summary: OrderWindowSummary,
    *,
    ad_spend: float,
    ad_deal_amount: float,
    platform_roi: float | None,
) -> dict[str, Any]:
    known_fee_profit = order_summary.known_fee_profit
    known_costs = (
        order_summary.product_cost
        + order_summary.freight_cost
        + order_summary.platform_fee
        + order_summary.other_fee
        + order_summary.commission_amount
    )
    fields: dict[str, Any] = {
        "订单数": order_summary.count,
        "实际卖出数量": order_summary.actual_sold_quantity,
        "销售额": order_summary.sales_amount,
        "退款金额": order_summary.refund_amount,
        "有效销售额": order_summary.valid_sales_amount,
        "退款订单数": order_summary.refund_order_count,
        "退款率": order_summary.refund_rate,
        "客单价": order_summary.avg_order_amount,
        "件单价": order_summary.avg_item_amount,
        "商品成本": order_summary.product_cost,
        "运费成本": order_summary.freight_cost,
        "平台扣点": order_summary.platform_fee,
        "其他费用": order_summary.other_fee,
        "预估佣金支出": order_summary.estimated_commission,
        "实际佣金支出": order_summary.actual_commission,
        "达人佣金": order_summary.commission_amount,
        "已知费用后利润": known_fee_profit,
        "经营利润估算": known_fee_profit,
        "已知费用利润率": order_summary.known_fee_profit_rate,
        "已知总投入": round(ad_spend + known_costs, 6),
        "投流后毛利": round(known_fee_profit - ad_spend, 6),
        "ROI": safe_div(order_summary.valid_sales_amount, ad_spend),
        "平台ROI": platform_roi if platform_roi is not None else safe_div(ad_deal_amount, ad_spend),
    }
    fields.update(order_summary.product_metrics)
    return fields


def prefix_detail_fields(prefix: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}{field_name}": value for field_name, value in fields.items() if field_name in ORDER_DETAIL_NUMBER_FIELDS}


def add_prefixed_total_fields(total_row: dict[str, Any], rows: list[dict[str, Any]], prefix: str) -> None:
    for field_name in ORDER_ADDITIVE_DETAIL_FIELDS:
        total_row[f"{prefix}{field_name}"] = sum(row_number(row, f"{prefix}{field_name}") for row in rows)

    order_count = total_row[f"{prefix}订单数"]
    quantity = total_row[f"{prefix}实际卖出数量"]
    gross_sales = total_row[f"{prefix}销售额"]
    refund = total_row[f"{prefix}退款金额"]
    valid_sales = total_row[f"{prefix}有效销售额"]
    known_fee_profit = total_row[f"{prefix}已知费用后利润"]
    ad_spend = row_number(total_row, f"{prefix}投流消耗")
    ad_deal_amount = row_number(total_row, f"{prefix}投流成交金额")

    total_row.update(
        {
            f"{prefix}退款率": safe_div(refund, gross_sales),
            f"{prefix}客单价": safe_div(gross_sales, order_count),
            f"{prefix}件单价": safe_div(gross_sales, quantity),
            f"{prefix}ROI": safe_div(valid_sales, ad_spend),
            f"{prefix}平台ROI": safe_div(ad_deal_amount, ad_spend),
            f"{prefix}已知费用利润率": safe_div(known_fee_profit, valid_sales),
        }
    )


def interval_unique_key(platform_code: str, fetched_at: datetime, run_token: str) -> str:
    return f"hourly_ads_{platform_code}_{fetched_at.strftime('%Y%m%d%H%M%S')}_{run_token}"


def format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def date_key(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit()) or date.today().strftime("%Y%m%d%H%M%S")


def first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = to_number(row.get(key))
        if value is not None:
            return value
    return None


def first_datetime(row: dict[str, Any], *keys: str) -> datetime | None:
    for key in keys:
        value = parse_datetime(row.get(key))
        if value is not None:
            return value
    return None


def row_number(row: dict[str, Any], key: str) -> float:
    return to_number(row.get(key)) or 0.0


def to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return round(float(value), 6)
    text = scalar_text(value).replace(",", "").replace("元", "").strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return round(float(text), 6)
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp)
        except (OSError, OverflowError, ValueError):
            return None
    text = scalar_text(value)
    if not text:
        return None
    text = text.replace("T", " ").replace("/", "-").strip()
    if text.endswith("Z"):
        text = text[:-1].strip()
    if "." in text:
        text = text.split(".", 1)[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def non_negative_delta(current: float, previous: float) -> float:
    return round(max(0.0, current - previous), 6)


def safe_div(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), 6)


def load_records_from_table(client: FeishuDailyClient, table_id: str, fields: list[str]) -> Iterable[dict[str, Any]]:
    yield from client.iter_records(table_id, fields)
