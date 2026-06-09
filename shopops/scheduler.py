from __future__ import annotations

import time
from datetime import datetime

from shopops.collectors import create_order_collector, create_promotion_collector
from shopops.config import Settings, load_settings
from shopops.models import TaskRunLog
from shopops.services.alert_service import AlertService
from shopops.services.daily_report_service import DailyReportService
from shopops.services.metric_service import MetricService
from shopops.storage.field_mapping import promotion_item_fields
from shopops.storage import create_storage


class Scheduler:
    def __init__(self, settings: Settings | None = None, storage=None, order_collector=None, promotion_collector=None) -> None:
        self.settings = settings or load_settings()
        self.storage = storage or create_storage(self.settings)
        self.order_collector = order_collector
        self.promotion_collector = promotion_collector
        self.metric_service = MetricService(self.settings)
        self.alert_service = AlertService(self.settings, self.storage)
        self.daily_report_service = DailyReportService(self.settings, self.storage, self.alert_service)

    def run_forever(self) -> None:
        while True:
            self.run_once()
            time.sleep(self.settings.fetch_interval_seconds)

    def run_once(self, now: datetime | None = None) -> dict:
        started = now or datetime.now()
        log = TaskRunLog.new("full_collect", self.settings.shop_id, started)
        saved_count = 0
        pending_replay_error = None
        try:
            if hasattr(self.storage, "replay_pending"):
                try:
                    saved_count += int(self.storage.replay_pending() or 0)
                except Exception as exc:
                    pending_replay_error = exc
            order_collector = self.order_collector or create_order_collector(self.settings)
            promotion_collector = self.promotion_collector or create_promotion_collector(self.settings)
            order = order_collector.fetch_today()
            promotion = promotion_collector.fetch_today()

            log.order_status = "success" if order.success else "failed"
            log.promotion_status = promotion.status

            previous = self.storage.get_last_monitor_snapshot(self.settings.shop_id)
            if order.orders:
                saved_count += self.storage.save_orders_raw(order.orders)
            promo_rows = [
                promotion_item_fields(
                    self.settings.shop_id,
                    self.settings.shop_name,
                    promotion.fetched_at,
                    item,
                    self.settings.feishu_platform_name,
                )
                for item in promotion.items
            ]
            saved_count += self.storage.save_promotion_snapshot(promo_rows)

            snapshot = self.metric_service.build_snapshot(order, promotion)
            saved_count += self.storage.save_monitor_snapshot(snapshot)
            metric = self.metric_service.build_delta(snapshot, previous)
            saved_count += self.storage.save_metric_10min(metric)

            alerts = self.alert_service.evaluate(snapshot, metric, started)
            for alert in alerts:
                sent = self.alert_service.send_to_feishu(alert)
                alert["是否已发送"] = sent
                alert["发送结果"] = "success" if sent else "failed"
                saved_count += self.storage.save_alert_log(alert)
            snapshot.alert_flag = bool(alerts)

            log.storage_status = "success"
            log.total_status = "success" if order.success and promotion.status == "success" else "partial_success"
            if pending_replay_error is not None and log.total_status == "success":
                log.total_status = "partial_success"
                log.error_code = "pending_replay_failed"
                log.error_message = str(pending_replay_error)
            log.fetched_count = (len(order.orders) if order.orders else 0) + len(promotion.items)
            log.saved_count = saved_count
            log.alerted = bool(alerts)
            if started.strftime("%H:%M") == self.settings.daily_report_time:
                self.daily_report_service.send_daily_report(snapshot, started)
            return {"order": order, "promotion": promotion, "snapshot": snapshot, "metric": metric, "alerts": alerts, "log": log}
        except Exception as exc:
            log.total_status = "failed"
            log.storage_status = "failed"
            log.error_code = "main_loop_failed"
            log.error_message = str(exc)
            return {"log": log, "error": exc}
        finally:
            ended = datetime.now()
            log.ended_at = ended
            log.duration_seconds = round((ended - log.started_at).total_seconds(), 3)
            try:
                self.storage.save_task_log(log)
            except Exception:
                pass
