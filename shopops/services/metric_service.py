from __future__ import annotations

from datetime import timedelta

from shopops.config import Settings
from shopops.models import Metric10Min, MonitorSnapshot, OrderCollectResult, PromotionCollectResult


def safe_div(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), 4)


class MetricService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_snapshot(self, order: OrderCollectResult, promotion: PromotionCollectResult) -> MonitorSnapshot:
        promotion_center_cost = promotion.items[0].cost if promotion.items and promotion.items[0].status == "success" else None
        total_cost = promotion.total_cost if promotion.success else None
        status = self._data_status(order, promotion)
        errors = [msg for msg in [order.error_message, promotion.error_message] if msg]
        total_amount = order.total_amount if order.success else None
        order_count = order.order_count if order.success else None
        return MonitorSnapshot(
            unique_key=f"{self.settings.shop_id}_{order.fetched_at.strftime('%Y%m%d%H%M')}",
            fetched_at=order.fetched_at,
            shop_id=self.settings.shop_id,
            shop_name=self.settings.shop_name,
            order_source=order.source,
            promotion_source=promotion.source,
            data_status=status,
            promotion_center_cost=promotion_center_cost,
            total_cost=total_cost,
            order_count=order_count,
            paid_order_count=order.paid_order_count if order.success else None,
            total_amount=total_amount,
            roi=safe_div(total_amount, total_cost),
            cac=safe_div(total_cost, order_count),
            error_message="; ".join(errors) or None,
            alert_flag=False,
        )

    def build_delta(self, current: MonitorSnapshot, previous: MonitorSnapshot | None) -> Metric10Min:
        if previous is None:
            return Metric10Min(
                unique_key=f"{current.shop_id}_missing_previous_{current.fetched_at.strftime('%Y%m%d%H%M')}",
                window_start=None,
                window_end=current.fetched_at,
                shop_id=current.shop_id,
                shop_name=current.shop_name,
                delta_order_count=None,
                delta_total_amount=None,
                delta_cost=None,
                delta_roi=None,
                delta_cac=None,
                data_status="missing_previous",
                abnormal_reason="previous snapshot is missing",
            )
        if current.data_status in {"order_failed", "login_required", "permission_denied"}:
            return self._invalid_delta(current, previous, "current order collection failed")
        if previous.fetched_at and current.fetched_at - previous.fetched_at > timedelta(minutes=30):
            return self._invalid_delta(current, previous, "collection interval exceeded threshold")

        pairs = [
            (current.order_count, previous.order_count, "order count decreased"),
            (current.total_amount, previous.total_amount, "GMV decreased"),
            (current.total_cost, previous.total_cost, "cost decreased"),
        ]
        for current_value, previous_value, reason in pairs:
            if current_value is not None and previous_value is not None and current_value < previous_value:
                return self._invalid_delta(current, previous, reason)

        delta_orders = None if current.order_count is None or previous.order_count is None else current.order_count - previous.order_count
        delta_amount = None if current.total_amount is None or previous.total_amount is None else round(current.total_amount - previous.total_amount, 2)
        delta_cost = None if current.total_cost is None or previous.total_cost is None else round(current.total_cost - previous.total_cost, 2)
        return Metric10Min(
            unique_key=f"{current.shop_id}_{previous.fetched_at.strftime('%Y%m%d%H%M')}_{current.fetched_at.strftime('%Y%m%d%H%M')}",
            window_start=previous.fetched_at,
            window_end=current.fetched_at,
            shop_id=current.shop_id,
            shop_name=current.shop_name,
            delta_order_count=delta_orders,
            delta_total_amount=delta_amount,
            delta_cost=delta_cost,
            delta_roi=safe_div(delta_amount, delta_cost),
            delta_cac=safe_div(delta_cost, delta_orders),
            data_status="normal",
            abnormal_reason=None,
        )

    @staticmethod
    def _data_status(order: OrderCollectResult, promotion: PromotionCollectResult) -> str:
        if order.error_code in {"login_required", "qianniu_not_running"} or promotion.error_code == "qianniu_not_running":
            return "login_required"
        if order.error_code == "permission_denied" or promotion.error_code == "permission_denied":
            return "permission_denied"
        if not order.success:
            return "order_failed"
        if promotion.status == "failed":
            return "promotion_failed"
        return "normal"

    @staticmethod
    def _invalid_delta(current: MonitorSnapshot, previous: MonitorSnapshot, reason: str) -> Metric10Min:
        return Metric10Min(
            unique_key=f"{current.shop_id}_{previous.fetched_at.strftime('%Y%m%d%H%M')}_{current.fetched_at.strftime('%Y%m%d%H%M')}",
            window_start=previous.fetched_at,
            window_end=current.fetched_at,
            shop_id=current.shop_id,
            shop_name=current.shop_name,
            delta_order_count=None,
            delta_total_amount=None,
            delta_cost=None,
            delta_roi=None,
            delta_cac=None,
            data_status="invalid",
            abnormal_reason=reason,
        )
