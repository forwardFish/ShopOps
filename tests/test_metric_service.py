from datetime import datetime, timedelta

from shopops.config import Settings
from shopops.models import MonitorSnapshot, OrderCollectResult, PromotionCollectResult, PromotionItem
from shopops.services.metric_service import MetricService, safe_div


def test_safe_division_handles_zero():
    assert safe_div(1000, 200) == 5
    assert safe_div(1000, 0) is None
    assert safe_div(None, 10) is None


def test_snapshot_failure_does_not_write_zero():
    settings = Settings()
    service = MetricService(settings)
    now = datetime(2026, 6, 2, 16, 10)
    order = OrderCollectResult(False, "api", settings.shop_id, settings.shop_name, None, None, None, now, "order_api_failed", "failed")
    promo = PromotionCollectResult(True, "success", "qianniu_pc", settings.shop_id, settings.shop_name, [PromotionItem("tuiguangcenter", "推广中心", 123.0, None, None, None, "success")], 123.0, now)
    snapshot = service.build_snapshot(order, promo)
    assert snapshot.data_status == "order_failed"
    assert snapshot.order_count is None
    assert snapshot.total_amount is None
    assert snapshot.roi is None
    assert snapshot.cac is None


def test_delta_normal_and_invalid_decrease():
    settings = Settings()
    service = MetricService(settings)
    prev = MonitorSnapshot("k1", datetime(2026, 6, 2, 16, 0), settings.shop_id, settings.shop_name, "api", "qianniu_pc", "normal", 60, 60, 10, 10, 1000, 16.6667, 6, None)
    cur = MonitorSnapshot("k2", datetime(2026, 6, 2, 16, 10), settings.shop_id, settings.shop_name, "api", "qianniu_pc", "normal", 90, 90, 15, 15, 1300, 14.4444, 6, None)
    delta = service.build_delta(cur, prev)
    assert delta.data_status == "normal"
    assert delta.delta_order_count == 5
    assert delta.delta_total_amount == 300
    assert delta.delta_cost == 30
    invalid = service.build_delta(prev, cur)
    assert invalid.data_status == "invalid"
    assert invalid.delta_order_count is None


def test_delta_missing_or_late_previous_is_invalid():
    settings = Settings()
    service = MetricService(settings)
    cur = MonitorSnapshot("k2", datetime(2026, 6, 2, 16, 10), settings.shop_id, settings.shop_name, "api", "qianniu_pc", "normal", 90, 90, 15, 15, 1300, 14.4444, 6, None)
    assert service.build_delta(cur, None).data_status == "missing_previous"
    old = MonitorSnapshot("k1", cur.fetched_at - timedelta(minutes=40), settings.shop_id, settings.shop_name, "api", "qianniu_pc", "normal", 60, 60, 10, 10, 1000, 16.6667, 6, None)
    assert service.build_delta(cur, old).data_status == "invalid"
