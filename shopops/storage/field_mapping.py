from __future__ import annotations

from shopops.models import Metric10Min, MonitorSnapshot, TaskRunLog, dt


PROMOTION_CENTER_CHANNEL = "tuiguangcenter"
PROMOTION_CENTER_NAME = "推广中心"
PLATFORM_QIANNIU_TAOBAO = "千牛淘宝"


def monitor_snapshot_fields(snapshot: MonitorSnapshot) -> dict:
    return {
        "unique_key": snapshot.unique_key,
        "采集时间": dt(snapshot.fetched_at),
        "店铺ID": snapshot.shop_id,
        "店铺名称": snapshot.shop_name,
        "订单来源": snapshot.order_source,
        "推广来源": snapshot.promotion_source,
        "数据状态": snapshot.data_status,
        "推广中心花费": snapshot.promotion_center_cost,
        "总推广消耗": snapshot.total_cost,
        "今日订单数": snapshot.order_count,
        "今日成交额": snapshot.total_amount,
        "实时ROI": snapshot.roi,
        "获客成本": snapshot.cac,
        "错误信息": snapshot.error_message,
        "是否告警": snapshot.alert_flag,
    }


def metric_10min_fields(metric: Metric10Min) -> dict:
    return {
        "unique_key": metric.unique_key,
        "时间开始": dt(metric.window_start) if metric.window_start else None,
        "时间结束": dt(metric.window_end),
        "店铺ID": metric.shop_id,
        "店铺名称": metric.shop_name,
        "新增订单数": metric.delta_order_count,
        "新增成交额": metric.delta_total_amount,
        "推广消耗": metric.delta_cost,
        "周期ROI": metric.delta_roi,
        "周期获客成本": metric.delta_cac,
        "数据状态": metric.data_status,
        "异常原因": metric.abnormal_reason,
    }


def task_log_fields(log: TaskRunLog) -> dict:
    return {
        "task_id": log.task_id,
        "任务类型": log.task_type,
        "开始时间": dt(log.started_at),
        "结束时间": dt(log.ended_at) if log.ended_at else None,
        "耗时秒": log.duration_seconds,
        "店铺ID": log.shop_id,
        "订单状态": log.order_status,
        "推广状态": log.promotion_status,
        "飞书写入状态": log.storage_status,
        "总状态": log.total_status,
        "拉取数量": log.fetched_count,
        "写入数量": log.saved_count,
        "错误码": log.error_code,
        "错误信息": log.error_message,
        "是否已告警": log.alerted,
    }


def promotion_item_fields(shop_id: str, shop_name: str, fetched_at, item, platform: str = PLATFORM_QIANNIU_TAOBAO) -> dict:
    raw = item.raw if isinstance(item.raw, dict) else {}
    return {
        "unique_key": f"{shop_id}_{item.channel}_{fetched_at.strftime('%Y%m%d%H%M')}",
        "平台": platform,
        "店铺ID": shop_id,
        "店铺名称": shop_name,
        "采集时间": dt(fetched_at),
        "花费": item.cost,
        "页面URL": raw.get("page_url") or raw.get("source_url"),
        "页面截图": raw.get("screenshot_path"),
    }
