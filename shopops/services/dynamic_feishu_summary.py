from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable


SUMMARY_TABLE_NAME = "动态经营汇总表"
TOTAL_PLATFORM = "全平台总计"

ORDER_TABLE = "orders"
AD_TABLE = "ads"
COMMISSION_TABLE = "commissions"


@dataclass(frozen=True)
class SourceTableRows:
    orders: list[dict[str, Any]]
    ads: list[dict[str, Any]]
    commissions: list[dict[str, Any]]


@dataclass(frozen=True)
class DynamicSummaryResult:
    summary_time: str
    source_counts: dict[str, int]
    summary_rows: list[dict[str, Any]]


def build_dynamic_summary(
    source: SourceTableRows,
    summary_time: datetime | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> DynamicSummaryResult:
    summary_time = summary_time or datetime.now()
    orders = aggregate_orders(source.orders, start_date, end_date)
    ads = aggregate_ads(source.ads, start_date, end_date)
    commissions = aggregate_commissions(source.commissions, start_date, end_date)

    group_keys = sorted(set(orders) | set(ads) | set(commissions))
    rows = [
        build_summary_row(group_key, orders.get(group_key), ads.get(group_key), commissions.get(group_key), summary_time)
        for group_key in group_keys
    ]
    rows.extend(build_total_rows(rows, summary_time))
    return DynamicSummaryResult(
        summary_time=format_dt(summary_time),
        source_counts={
            ORDER_TABLE: len(source.orders),
            AD_TABLE: len(source.ads),
            COMMISSION_TABLE: len(source.commissions),
        },
        summary_rows=rows,
    )


def aggregate_orders(
    records: Iterable[dict[str, Any]],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "order_count": 0,
            "sold_quantity": 0.0,
            "sales_amount": 0.0,
            "refund_amount": 0.0,
            "valid_sales_amount": 0.0,
            "product_cost": 0.0,
            "freight_cost": 0.0,
            "platform_fee": 0.0,
            "other_fee": 0.0,
        }
    )
    for fields in iter_fields(records):
        happened_on = get_record_date(fields, ORDER_DATE_FIELDS, ORDER_TIME_FIELDS)
        if not date_in_range(happened_on, start_date, end_date):
            continue
        platform = normalize_platform(first_value(fields, PLATFORM_FIELDS))
        key = (happened_on.isoformat(), platform)
        sales = number(first_value(fields, ORDER_SALES_FIELDS))
        refund = number(first_value(fields, ORDER_REFUND_FIELDS)) or 0.0
        valid_sales = number(first_value(fields, ORDER_VALID_SALES_FIELDS))
        if valid_sales is None and sales is not None:
            valid_sales = sales - refund
        if valid_sales is not None and valid_sales < 0:
            valid_sales = 0.0
        bucket = buckets[key]
        bucket["order_count"] += 1
        bucket["sold_quantity"] = round(bucket["sold_quantity"] + (number(first_value(fields, ORDER_QUANTITY_FIELDS)) or 0.0), 2)
        bucket["sales_amount"] = round(bucket["sales_amount"] + (sales or 0.0), 2)
        bucket["refund_amount"] = round(bucket["refund_amount"] + refund, 2)
        bucket["valid_sales_amount"] = round(bucket["valid_sales_amount"] + (valid_sales or 0.0), 2)
        bucket["product_cost"] = round(bucket["product_cost"] + (number(first_value(fields, PRODUCT_COST_FIELDS)) or 0.0), 2)
        bucket["freight_cost"] = round(bucket["freight_cost"] + (number(first_value(fields, FREIGHT_COST_FIELDS)) or 0.0), 2)
        bucket["platform_fee"] = round(bucket["platform_fee"] + (number(first_value(fields, PLATFORM_FEE_FIELDS)) or 0.0), 2)
        bucket["other_fee"] = round(bucket["other_fee"] + (number(first_value(fields, OTHER_FEE_FIELDS)) or 0.0), 2)
    return dict(buckets)


def aggregate_ads(
    records: Iterable[dict[str, Any]],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"ad_cost": 0.0, "impressions": 0.0, "clicks": 0.0})
    for fields in iter_fields(records):
        happened_on = get_record_date(fields, AD_DATE_FIELDS, AD_TIME_FIELDS)
        if not date_in_range(happened_on, start_date, end_date):
            continue
        cost = number(first_value(fields, AD_COST_FIELDS))
        if cost is None:
            continue
        platform = normalize_platform(first_value(fields, PLATFORM_FIELDS))
        key = (happened_on.isoformat(), platform)
        bucket = buckets[key]
        bucket["ad_cost"] = round(bucket["ad_cost"] + cost, 2)
        bucket["impressions"] = round(bucket["impressions"] + (number(first_value(fields, IMPRESSION_FIELDS)) or 0.0), 2)
        bucket["clicks"] = round(bucket["clicks"] + (number(first_value(fields, CLICK_FIELDS)) or 0.0), 2)
    return dict(buckets)


def aggregate_commissions(
    records: Iterable[dict[str, Any]],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"influencer_commission": 0.0})
    for fields in iter_fields(records):
        happened_on = get_record_date(fields, COMMISSION_DATE_FIELDS, COMMISSION_TIME_FIELDS)
        if not date_in_range(happened_on, start_date, end_date):
            continue
        amount = number(first_value(fields, COMMISSION_AMOUNT_FIELDS))
        if amount is None:
            amount = number(first_value(fields, COMMISSION_SETTLED_FIELDS))
        if amount is None:
            amount = number(first_value(fields, COMMISSION_ESTIMATED_FIELDS))
        amount = amount or 0.0
        platform = normalize_platform(first_value(fields, PLATFORM_FIELDS))
        key = (happened_on.isoformat(), platform)
        buckets[key]["influencer_commission"] = round(buckets[key]["influencer_commission"] + amount, 2)
    return dict(buckets)


def build_summary_row(
    group_key: tuple[str, str],
    order: dict[str, Any] | None,
    ad: dict[str, Any] | None,
    commission: dict[str, Any] | None,
    summary_time: datetime,
) -> dict[str, Any]:
    stat_date, platform = group_key
    order = order or {}
    ad = ad or {}
    commission = commission or {}
    valid_sales = money(order.get("valid_sales_amount"))
    ad_cost = maybe_money(ad.get("ad_cost")) if ad else None
    influencer_commission = money(commission.get("influencer_commission"))
    product_cost = money(order.get("product_cost"))
    freight_cost = money(order.get("freight_cost"))
    platform_fee = money(order.get("platform_fee"))
    other_fee = money(order.get("other_fee"))
    known_input = maybe_money((ad_cost or 0.0) + influencer_commission) if ad_cost is not None else None
    known_cost_profit = maybe_money(valid_sales - product_cost - freight_cost - platform_fee - other_fee - influencer_commission - (ad_cost or 0.0))
    gross_profit_after_ad = maybe_money(valid_sales - influencer_commission - (ad_cost or 0.0)) if ad_cost is not None else None
    operating_profit = maybe_money(valid_sales - product_cost - freight_cost - platform_fee - other_fee - influencer_commission - (ad_cost or 0.0)) if ad_cost is not None else None
    missing = missing_items(order, ad)
    return {
        "unique_key": f"{stat_date}-{platform}",
        "统计日期": stat_date,
        "平台": platform,
        "汇总key": f"{stat_date}-{platform}",
        "订单数": int(order.get("order_count") or 0),
        "实际卖出数量": money(order.get("sold_quantity")),
        "销售额": money(order.get("sales_amount")),
        "退款金额": money(order.get("refund_amount")),
        "有效销售额": valid_sales,
        "达人佣金": influencer_commission,
        "投流消耗": ad_cost,
        "商品成本": product_cost,
        "运费成本": freight_cost,
        "平台扣点": platform_fee,
        "其他费用": other_fee,
        "已知总投入": known_input,
        "已知费用后利润": known_cost_profit,
        "投流后毛利": gross_profit_after_ad,
        "经营利润估算": operating_profit,
        "ROI": ratio(valid_sales, ad_cost),
        "平台ROI": ratio(valid_sales, known_input),
        "已知费用利润率": ratio(known_cost_profit, valid_sales),
        "利润率": ratio(operating_profit, valid_sales),
        "展现": int(ad.get("impressions") or 0),
        "点击": int(ad.get("clicks") or 0),
        "数据状态": "partial" if missing else "normal",
        "缺失项": ",".join(missing),
        "汇总时间": format_dt(summary_time),
    }


def build_total_rows(rows: list[dict[str, Any]], summary_time: datetime) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[str(row["统计日期"])].append(row)
    return [build_total_row(stat_date, date_rows, summary_time) for stat_date, date_rows in sorted(by_date.items())]


def build_total_row(stat_date: str, rows: list[dict[str, Any]], summary_time: datetime) -> dict[str, Any]:
    valid_sales = sum_money(rows, "有效销售额")
    ad_cost = nullable_sum(rows, "投流消耗")
    influencer_commission = sum_money(rows, "达人佣金")
    product_cost = sum_money(rows, "商品成本")
    freight_cost = sum_money(rows, "运费成本")
    platform_fee = sum_money(rows, "平台扣点")
    other_fee = sum_money(rows, "其他费用")
    known_input = maybe_money((ad_cost or 0.0) + influencer_commission) if ad_cost is not None else None
    known_cost_profit = maybe_money(valid_sales - product_cost - freight_cost - platform_fee - other_fee - influencer_commission - (ad_cost or 0.0))
    operating_profit = maybe_money(valid_sales - product_cost - freight_cost - platform_fee - other_fee - influencer_commission - (ad_cost or 0.0)) if ad_cost is not None else None
    missing = sorted({item for row in rows for item in str(row.get("缺失项") or "").split(",") if item})
    return {
        "unique_key": f"{stat_date}-{TOTAL_PLATFORM}",
        "统计日期": stat_date,
        "平台": TOTAL_PLATFORM,
        "汇总key": f"{stat_date}-{TOTAL_PLATFORM}",
        "订单数": sum(int(row.get("订单数") or 0) for row in rows),
        "实际卖出数量": sum_money(rows, "实际卖出数量"),
        "销售额": sum_money(rows, "销售额"),
        "退款金额": sum_money(rows, "退款金额"),
        "有效销售额": valid_sales,
        "达人佣金": influencer_commission,
        "投流消耗": ad_cost,
        "商品成本": product_cost,
        "运费成本": freight_cost,
        "平台扣点": platform_fee,
        "其他费用": other_fee,
        "已知总投入": known_input,
        "已知费用后利润": known_cost_profit,
        "投流后毛利": maybe_money(valid_sales - influencer_commission - (ad_cost or 0.0)) if ad_cost is not None else None,
        "经营利润估算": operating_profit,
        "ROI": ratio(valid_sales, ad_cost),
        "平台ROI": ratio(valid_sales, known_input),
        "已知费用利润率": ratio(known_cost_profit, valid_sales),
        "利润率": ratio(operating_profit, valid_sales),
        "展现": sum(int(row.get("展现") or 0) for row in rows),
        "点击": sum(int(row.get("点击") or 0) for row in rows),
        "数据状态": "partial" if missing else "normal",
        "缺失项": ",".join(missing),
        "汇总时间": format_dt(summary_time),
    }


def summary_field_names() -> list[str]:
    return [
        "unique_key",
        "统计日期",
        "平台",
        "汇总key",
        "订单数",
        "实际卖出数量",
        "销售额",
        "退款金额",
        "有效销售额",
        "达人佣金",
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
    ]


def summary_number_fields() -> set[str]:
    return {
        "订单数",
        "实际卖出数量",
        "销售额",
        "退款金额",
        "有效销售额",
        "达人佣金",
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
    }


ORDER_DATE_FIELDS: tuple[str, ...] = ()
ORDER_TIME_FIELDS = ("创建时间", "订单创建时间", "订单下单时间", "下单时间", "订单提交时间", "订单成交时间")
ORDER_QUANTITY_FIELDS = ("数量", "商品数量", "商品数量(件)", "宝贝总数量", "购买数量")
ORDER_SALES_FIELDS = ("有效销售额", "支付金额", "实付金额", "实收款", "成交金额", "销售额", "付款金额")
ORDER_REFUND_FIELDS = ("退款金额", "已退金额", "售后退款")
ORDER_VALID_SALES_FIELDS = ("净成交额", "有效销售额")
PRODUCT_COST_FIELDS = ("商品成本", "成本", "采购成本")
FREIGHT_COST_FIELDS = ("运费成本", "运费", "物流成本")
PLATFORM_FEE_FIELDS = ("平台扣点", "平台服务费", "技术服务费")
OTHER_FEE_FIELDS = ("其他费用", "其他成本")

AD_DATE_FIELDS = ("统计日期", "投放日期", "日期")
AD_TIME_FIELDS = ("采集时间", "更新时间", "投放时间")
AD_COST_FIELDS = ("投流消耗", "推广消耗", "推广花费", "花费", "消耗金额", "广告消耗", "广告花费")
IMPRESSION_FIELDS = ("展现", "展现量")
CLICK_FIELDS = ("点击", "点击量")

COMMISSION_DATE_FIELDS = ("统计日期", "结算日期", "下单日期", "日期")
COMMISSION_TIME_FIELDS = ("支付时间", "订单下单时间", "下单时间", "采集时间", "更新时间")
COMMISSION_AMOUNT_FIELDS = ("带货佣金", "带货费用", "采用佣金", "达人佣金", "佣金金额", "佣金")
COMMISSION_SETTLED_FIELDS = ("实际佣金支出", "结算佣金", "结算金额")
COMMISSION_ESTIMATED_FIELDS = ("预估佣金支出", "预估佣金", "带货佣金", "带货费用")
COMMISSION_SERVICE_FEE_FIELDS = ("技术服务费", "服务费", "机构服务费")

PLATFORM_FIELDS = ("平台", "来源平台", "店铺平台")


def iter_fields(records: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for record in records:
        if "fields" in record and isinstance(record["fields"], dict):
            yield record["fields"]
        else:
            yield record


def first_value(fields: dict[str, Any], names: Iterable[str]) -> Any:
    for name in names:
        if name in fields and fields[name] not in (None, ""):
            return fields[name]
    return None


def get_record_date(fields: dict[str, Any], date_names: Iterable[str], time_names: Iterable[str]) -> date | None:
    value = first_value(fields, date_names)
    parsed = parse_date_or_datetime(value)
    if parsed:
        return parsed.date()
    value = first_value(fields, time_names)
    parsed = parse_date_or_datetime(value)
    return parsed.date() if parsed else None


def parse_date_or_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if text.isdigit() and len(text) >= 13:
        return datetime.fromtimestamp(int(text[:13]) / 1000)
    for candidate in (text, text[:19], text[:16], text[:10]):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


def date_in_range(value: date | None, start_date: date | None, end_date: date | None) -> bool:
    if value is None:
        return False
    if start_date and value < start_date:
        return False
    if end_date and value > end_date:
        return False
    return True


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).replace(",", "").replace("￥", "").replace("元", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def normalize_platform(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未知平台"
    if "抖音" in text or "douyin" in text.lower():
        return "抖音"
    if "拼多多" in text or "pdd" in text.lower():
        return "拼多多"
    if "视频号" in text or "微信" in text:
        return "视频号"
    if "淘宝" in text or "天猫" in text or "千牛" in text:
        return "淘宝"
    return text


def missing_items(order: dict[str, Any], ad: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not order:
        missing.append("订单")
    if not ad:
        missing.append("投流")
    return missing


def ratio(numerator: float | int | None, denominator: float | int | None, digits: int = 4) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), digits)


def money(value: Any) -> float:
    return round(float(value or 0.0), 2)


def maybe_money(value: Any) -> float | None:
    if value is None:
        return None
    return money(value)


def sum_money(rows: list[dict[str, Any]], key: str) -> float:
    return money(sum(float(row.get(key) or 0.0) for row in rows))


def nullable_sum(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return money(sum(float(value) for value in values))


def format_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")
