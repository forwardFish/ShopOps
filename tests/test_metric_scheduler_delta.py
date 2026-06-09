from datetime import datetime

from shopops.config import Settings
from shopops.models import OrderCollectResult, PromotionCollectResult, PromotionItem
from shopops.scheduler import Scheduler
from shopops.storage.local_feishu import LocalFeishuBitableStorage


class SequenceOrderCollector:
    def __init__(self, settings, values):
        self.settings = settings
        self.values = list(values)

    def fetch_today(self):
        fetched_at, order_count, total_amount = self.values.pop(0)
        return OrderCollectResult(
            True,
            "crawler",
            self.settings.shop_id,
            self.settings.shop_name,
            order_count,
            order_count,
            total_amount,
            fetched_at,
            orders=[],
        )


class SequencePromotionCollector:
    def __init__(self, settings, values):
        self.settings = settings
        self.values = list(values)

    def fetch_today(self):
        fetched_at, cost = self.values.pop(0)
        item = PromotionItem("tuiguangcenter", "promotion center", cost, None, None, None, "success")
        return PromotionCollectResult(
            True,
            "success",
            "qianniu_pc",
            self.settings.shop_id,
            self.settings.shop_name,
            [item],
            cost,
            fetched_at,
        )


def test_scheduler_second_run_uses_previous_snapshot_for_10min_delta(tmp_path):
    settings = Settings(
        local_feishu_path=str(tmp_path / "local_feishu.json"),
        pending_records_path=str(tmp_path / "pending.jsonl"),
    )
    storage = LocalFeishuBitableStorage(settings)
    first = datetime(2026, 6, 2, 16, 0)
    second = datetime(2026, 6, 2, 16, 10)
    scheduler = Scheduler(
        settings,
        storage,
        SequenceOrderCollector(settings, [(first, 10, 1000.0), (second, 14, 1300.0)]),
        SequencePromotionCollector(settings, [(first, 100.0), (second, 160.0)]),
    )

    first_result = scheduler.run_once(first)
    second_result = scheduler.run_once(second)

    assert first_result["metric"].data_status == "missing_previous"
    metric = second_result["metric"]
    assert metric.data_status == "normal"
    assert metric.delta_order_count == 4
    assert metric.delta_total_amount == 300.0
    assert metric.delta_cost == 60.0
    assert metric.delta_roi == 5.0
    assert metric.delta_cac == 15.0
    assert metric.window_start == first
    assert metric.window_end == second
    assert storage.count("monitor_snapshot") == 2
    assert storage.count("metrics_10min") == 2
