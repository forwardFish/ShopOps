from datetime import datetime, timedelta

from shopops.config import Settings
from shopops.models import Metric10Min, MonitorSnapshot
from shopops.scheduler import Scheduler
from shopops.services.alert_service import AlertService
from shopops.services.daily_report_service import DailyReportService
from shopops.storage.local_feishu import LocalFeishuBitableStorage

from tests.test_metric_scheduler_delta import SequenceOrderCollector, SequencePromotionCollector


def make_snapshot(settings, now, *, total_cost=600.0, roi=0.5, order_count=3):
    return MonitorSnapshot(
        unique_key=f"{settings.shop_id}_{now.strftime('%Y%m%d%H%M')}",
        fetched_at=now,
        shop_id=settings.shop_id,
        shop_name=settings.shop_name,
        order_source="crawler",
        promotion_source="qianniu_pc",
        data_status="normal",
        promotion_center_cost=total_cost,
        total_cost=total_cost,
        order_count=order_count,
        paid_order_count=order_count,
        total_amount=total_cost * roi,
        roi=roi,
        cac=total_cost / order_count if order_count else None,
        error_message=None,
    )


def test_alerts_are_deduplicated_but_logged_once(tmp_path):
    now = datetime(2026, 6, 2, 10, 0)
    settings = Settings(
        local_feishu_path=str(tmp_path / "local_feishu.json"),
        pending_records_path=str(tmp_path / "pending.jsonl"),
        alert_total_cost=100,
        alert_min_roi=1.0,
        alert_dedup_minutes=30,
    )
    storage = LocalFeishuBitableStorage(settings)
    alert_service = AlertService(settings, storage)
    snapshot = make_snapshot(settings, now)
    metric = Metric10Min("m1", now - timedelta(minutes=10), now, settings.shop_id, settings.shop_name, 0, 0.0, 50.0, 0.0, None, "normal", None)

    first = alert_service.evaluate(snapshot, metric, now)
    for alert in first:
        storage.save_alert_log(alert)
    second = alert_service.evaluate(snapshot, metric, now + timedelta(minutes=5))

    assert {alert["告警类型"] for alert in first} == {"cost_over_limit", "roi_low", "cost_no_order"}
    assert second == []
    assert storage.count("alert_log") == 3


def test_scheduler_persists_task_log_and_daily_report_at_configured_time(tmp_path):
    now = datetime(2026, 6, 2, 23, 50)
    settings = Settings(
        local_feishu_path=str(tmp_path / "local_feishu.json"),
        pending_records_path=str(tmp_path / "pending.jsonl"),
        daily_report_time="23:50",
        alert_total_cost=100,
    )
    storage = LocalFeishuBitableStorage(settings)
    scheduler = Scheduler(
        settings,
        storage,
        SequenceOrderCollector(settings, [(now, 3, 300.0)]),
        SequencePromotionCollector(settings, [(now, 150.0)]),
    )

    result = scheduler.run_once(now)

    assert result["log"].total_status == "success"
    assert storage.count("task_run_log") == 1
    task_log = storage.read_table("task_run_log")[0]["fields"]
    assert task_log["任务类型"] == "full_collect"
    assert task_log["飞书写入状态"] == "success"
    assert task_log["是否已告警"] is True
    assert storage.count("daily_report") == 1
    report = storage.read_table("daily_report")[0]["fields"]
    assert report["unique_key"] == f"{settings.shop_id}_20260602"
    assert report["日期"] == "2026-06-02"
    assert "今日订单数：3 单" in report["日报内容"]
    assert "推广中心花费：150.00 元" in report["日报内容"]
    assert "cost_over_limit：1 次" in report["日报内容"]


def test_daily_report_upsert_prevents_duplicate_report_rows(tmp_path):
    now = datetime(2026, 6, 2, 23, 50)
    settings = Settings(local_feishu_path=str(tmp_path / "local_feishu.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = LocalFeishuBitableStorage(settings)
    alert_service = AlertService(settings, storage)
    service = DailyReportService(settings, storage, alert_service)
    snapshot = make_snapshot(settings, now)

    service.send_daily_report(snapshot, now)
    service.send_daily_report(snapshot, now)

    assert storage.count("daily_report") == 1
