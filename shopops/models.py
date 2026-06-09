from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal


OrderSource = Literal["api", "crawler", "jushuitan"]
CollectStatus = Literal["success", "failed", "partial_success", "login_required", "permission_denied", "skipped"]


def dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class OrderCollectResult:
    success: bool
    source: OrderSource
    shop_id: str
    shop_name: str
    order_count: int | None
    paid_order_count: int | None
    total_amount: float | None
    fetched_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    raw: Any | None = None
    orders: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PromotionItem:
    channel: str
    channel_name: str
    cost: float | None
    impressions: int | None
    clicks: int | None
    conversions: int | None
    status: CollectStatus
    error_message: str | None = None
    raw: Any | None = None


@dataclass
class PromotionCollectResult:
    success: bool
    status: CollectStatus
    source: str
    shop_id: str
    shop_name: str
    items: list[PromotionItem]
    total_cost: float | None
    fetched_at: datetime
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class MonitorSnapshot:
    unique_key: str
    fetched_at: datetime
    shop_id: str
    shop_name: str
    order_source: str
    promotion_source: str
    data_status: str
    promotion_center_cost: float | None
    total_cost: float | None
    order_count: int | None
    paid_order_count: int | None
    total_amount: float | None
    roi: float | None
    cac: float | None
    error_message: str | None
    alert_flag: bool = False


@dataclass
class Metric10Min:
    unique_key: str
    window_start: datetime | None
    window_end: datetime
    shop_id: str
    shop_name: str
    delta_order_count: int | None
    delta_total_amount: float | None
    delta_cost: float | None
    delta_roi: float | None
    delta_cac: float | None
    data_status: str
    abnormal_reason: str | None


@dataclass
class TaskRunLog:
    task_id: str
    task_type: str
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: float | None
    shop_id: str
    order_status: str
    promotion_status: str
    storage_status: str
    total_status: str
    fetched_count: int = 0
    saved_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    alerted: bool = False

    @staticmethod
    def new(task_type: str, shop_id: str, now: datetime | None = None) -> "TaskRunLog":
        return TaskRunLog(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            started_at=now or datetime.now(),
            ended_at=None,
            duration_seconds=None,
            shop_id=shop_id,
            order_status="skipped",
            promotion_status="skipped",
            storage_status="skipped",
            total_status="running",
        )


def model_dict(obj: Any) -> dict[str, Any]:
    data = asdict(obj)
    for key, value in list(data.items()):
        if isinstance(value, datetime):
            data[key] = dt(value)
    return data
