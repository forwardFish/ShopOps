from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from shopops.models import Metric10Min, MonitorSnapshot, TaskRunLog


class Storage(ABC):
    @abstractmethod
    def upsert(self, table: str, fields: dict[str, Any]) -> int:
        raise NotImplementedError

    @abstractmethod
    def save_orders_raw(self, orders: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    @abstractmethod
    def save_promotion_snapshot(self, rows: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    @abstractmethod
    def save_douyin_influencer_commission(self, rows: list[dict[str, Any]]) -> int:
        raise NotImplementedError

    @abstractmethod
    def save_monitor_snapshot(self, snapshot: MonitorSnapshot) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_last_monitor_snapshot(self, shop_id: str) -> MonitorSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def save_metric_10min(self, metric: Metric10Min) -> int:
        raise NotImplementedError

    @abstractmethod
    def save_task_log(self, log: TaskRunLog) -> int:
        raise NotImplementedError

    @abstractmethod
    def save_alert_log(self, alert: dict[str, Any]) -> int:
        raise NotImplementedError
