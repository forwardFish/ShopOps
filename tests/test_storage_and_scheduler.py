from datetime import datetime

from shopops.collectors.taobao_order_api import TaobaoOrderApiCollector
from shopops.collectors.taobao_promotion_crawler import TaobaoPromotionCrawler
from shopops.config import Settings
from shopops.scheduler import Scheduler
from shopops.services.browser_service import BrowserService
from shopops.storage.local_feishu import LocalFeishuBitableStorage


def make_scheduler(tmp_path):
    settings = Settings(local_feishu_path=str(tmp_path / "local_feishu.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = LocalFeishuBitableStorage(settings)
    scheduler = Scheduler(
        settings,
        storage,
        TaobaoOrderApiCollector(settings),
        TaobaoPromotionCrawler(settings, BrowserService(settings.qianniu_cdp_url)),
    )
    return settings, storage, scheduler


def test_scheduler_writes_required_feishu_tables(tmp_path):
    _, storage, scheduler = make_scheduler(tmp_path)
    result = scheduler.run_once(datetime(2026, 6, 2, 16, 10))
    assert result["snapshot"].data_status == "normal"
    assert storage.count("orders_raw") == 2
    assert storage.count("promotion_snapshot") == 1
    assert storage.count("monitor_snapshot") == 1
    assert storage.count("metrics_10min") == 1
    assert storage.count("task_run_log") == 1
    monitor = storage.read_table("monitor_snapshot")[0]["fields"]
    assert monitor["今日订单数"] == 2
    assert monitor["今日成交额"] == 454.5
    assert monitor["推广中心花费"] == 123.45
    assert monitor["总推广消耗"] == 123.45
    assert monitor["实时ROI"] is not None


def test_upsert_prevents_duplicate_snapshot_records(tmp_path):
    _, storage, scheduler = make_scheduler(tmp_path)
    scheduler.run_once(datetime(2026, 6, 2, 16, 10))
    first_count = storage.count("monitor_snapshot")
    scheduler.run_once(datetime(2026, 6, 2, 16, 10))
    assert storage.count("monitor_snapshot") == first_count


def test_pending_cache_and_replay(tmp_path):
    settings = Settings(local_feishu_path=str(tmp_path / "local_feishu.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = LocalFeishuBitableStorage(settings, fail_tables={"monitor_snapshot"})
    scheduler = Scheduler(
        settings,
        storage,
        TaobaoOrderApiCollector(settings),
        TaobaoPromotionCrawler(settings, BrowserService(settings.qianniu_cdp_url)),
    )
    scheduler.run_once(datetime(2026, 6, 2, 16, 20))
    assert len(storage.pending_records()) == 1
    storage.fail_tables.clear()
    assert storage.replay_pending() == 1
    assert storage.pending_records() == []
    assert storage.count("monitor_snapshot") == 1


def test_scheduler_replays_pending_cache_before_full_collect(tmp_path):
    settings = Settings(local_feishu_path=str(tmp_path / "local_feishu.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = LocalFeishuBitableStorage(settings, fail_tables={"monitor_snapshot"})
    scheduler = Scheduler(
        settings,
        storage,
        TaobaoOrderApiCollector(settings),
        TaobaoPromotionCrawler(settings, BrowserService(settings.qianniu_cdp_url)),
    )

    first = scheduler.run_once(datetime(2026, 6, 2, 16, 20))
    assert first["log"].total_status == "success"
    assert storage.count("monitor_snapshot") == 0
    assert len(storage.pending_records()) == 1

    storage.fail_tables.clear()
    second = scheduler.run_once(datetime(2026, 6, 2, 16, 30))

    assert second["metric"].data_status == "normal"
    assert storage.pending_records() == []
    assert storage.count("monitor_snapshot") == 1
    assert second["log"].saved_count >= 5


class ReplayFailingStorage(LocalFeishuBitableStorage):
    def replay_pending(self, limit: int = 100) -> int:
        raise RuntimeError("pending replay unavailable")


def test_scheduler_records_pending_replay_failure_without_aborting_collect(tmp_path):
    settings = Settings(local_feishu_path=str(tmp_path / "local_feishu.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = ReplayFailingStorage(settings)
    scheduler = Scheduler(
        settings,
        storage,
        TaobaoOrderApiCollector(settings),
        TaobaoPromotionCrawler(settings, BrowserService(settings.qianniu_cdp_url)),
    )

    result = scheduler.run_once(datetime(2026, 6, 2, 16, 40))

    assert result["log"].total_status == "partial_success"
    assert result["log"].error_code == "pending_replay_failed"
    assert storage.count("orders_raw") == 2
    assert storage.count("monitor_snapshot") == 1
    assert storage.count("task_run_log") == 1


def test_default_config_uses_crawler_and_does_not_require_taobao_api_credentials():
    settings = Settings()
    assert settings.order_source == "crawler"
    assert settings.taobao_app_key == ""
    settings.validate_business()


def test_promotion_center_failure_does_not_write_zero(tmp_path):
    settings = Settings(local_feishu_path=str(tmp_path / "local_feishu.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = LocalFeishuBitableStorage(settings)
    scheduler = Scheduler(
        settings,
        storage,
        TaobaoOrderApiCollector(settings),
        TaobaoPromotionCrawler(settings, BrowserService(settings.qianniu_cdp_url), fail=True),
    )
    result = scheduler.run_once(datetime(2026, 6, 2, 16, 30))
    assert result["promotion"].status == "failed"
    assert result["snapshot"].data_status == "promotion_failed"
    assert result["snapshot"].promotion_center_cost is None
    assert result["snapshot"].total_cost is None
    rows = [record["fields"] for record in storage.read_table("promotion_snapshot")]
    assert len(rows) == 1
    assert rows[0]["平台"] == "千牛淘宝"
    assert rows[0]["花费"] is None
