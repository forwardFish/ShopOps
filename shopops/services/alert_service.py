from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import requests

from shopops.config import Settings
from shopops.models import Metric10Min, MonitorSnapshot, dt


class AlertService:
    def __init__(self, settings: Settings, storage) -> None:
        self.settings = settings
        self.storage = storage

    def evaluate(self, snapshot: MonitorSnapshot, metric: Metric10Min | None, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or snapshot.fetched_at
        alerts: list[dict[str, Any]] = []
        if snapshot.total_cost is not None and snapshot.total_cost > self.settings.alert_total_cost:
            alerts.append(self._alert("cost_over_limit", "warning", f"今日总推广消耗 {snapshot.total_cost:.2f} 元，超过阈值 {self.settings.alert_total_cost:.2f} 元", snapshot.total_cost, self.settings.alert_total_cost, now))
        if snapshot.total_cost and snapshot.total_cost > 100 and snapshot.roi is not None and snapshot.roi < self.settings.alert_min_roi:
            alerts.append(self._alert("roi_low", "warning", f"今日 ROI {snapshot.roi}，低于阈值 {self.settings.alert_min_roi}", snapshot.roi, self.settings.alert_min_roi, now))
        if snapshot.data_status in {"order_failed", "promotion_failed", "login_required", "permission_denied", "feishu_failed"}:
            alerts.append(self._alert("collect_failed", "critical", f"数据采集异常：{snapshot.data_status} {snapshot.error_message or ''}".strip(), None, None, now))
        if metric and metric.data_status == "normal" and metric.delta_cost and metric.delta_cost > 0 and (metric.delta_order_count or 0) == 0:
            alerts.append(self._alert("cost_no_order", "warning", f"周期内有推广消耗 {metric.delta_cost:.2f} 元，但新增订单为 0", metric.delta_cost, None, now))
        return [alert for alert in alerts if not self._is_duplicate(alert, now)]

    def send_to_feishu(self, alert: dict[str, Any]) -> bool:
        return self.send_text(alert["告警内容"])

    def send_text(self, text: str) -> bool:
        if not self.settings.feishu_webhook:
            return False
        try:
            response = requests.post(self.settings.feishu_webhook, json={"msg_type": "text", "content": {"text": text}}, timeout=5)
        except Exception:
            return False
        return response.status_code < 300

    def _alert(self, alert_type: str, level: str, message: str, current_value, threshold, now: datetime) -> dict[str, Any]:
        return {
            "alert_id": f"{self.settings.shop_id}_{alert_type}_{now.strftime('%Y%m%d%H%M%S')}",
            "触发时间": dt(now),
            "店铺ID": self.settings.shop_id,
            "告警类型": alert_type,
            "告警级别": level,
            "告警内容": message,
            "当前值": current_value,
            "阈值": threshold,
            "是否已发送": False,
            "发送结果": "pending",
        }

    def _is_duplicate(self, alert: dict[str, Any], now: datetime) -> bool:
        if not hasattr(self.storage, "read_table"):
            return False
        cutoff = now - timedelta(minutes=self.settings.alert_dedup_minutes)
        for record in self.storage.read_table("alert_log"):
            fields = record["fields"]
            if fields.get("店铺ID") != alert["店铺ID"] or fields.get("告警类型") != alert["告警类型"]:
                continue
            triggered = datetime.strptime(fields["触发时间"], "%Y-%m-%d %H:%M:%S")
            if triggered >= cutoff:
                return True
        return False
