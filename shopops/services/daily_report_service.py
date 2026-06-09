from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from shopops.config import Settings
from shopops.models import MonitorSnapshot, dt


class DailyReportService:
    def __init__(self, settings: Settings, storage, alert_service) -> None:
        self.settings = settings
        self.storage = storage
        self.alert_service = alert_service

    def build_report(self, snapshot: MonitorSnapshot, alert_stats: dict[str, int] | None = None, now: datetime | None = None) -> dict[str, Any]:
        now = now or snapshot.fetched_at
        stats_text = self._format_alert_stats(alert_stats or {})
        text = (
            f"【淘宝店铺日报】日期：{now.strftime('%Y-%m-%d')}\n"
            f"店铺：{snapshot.shop_name}\n\n"
            f"今日订单数：{self._format_value(snapshot.order_count)} 单\n"
            f"今日成交额：{self._format_value(snapshot.total_amount)} 元\n"
            f"推广中心花费：{self._format_value(snapshot.promotion_center_cost)} 元\n"
            f"总推广消耗：{self._format_value(snapshot.total_cost)} 元\n"
            f"今日 ROI：{self._format_value(snapshot.roi)}\n"
            f"获客成本：{self._format_value(snapshot.cac)} 元/单\n"
            f"异常统计：{stats_text}\n"
            "数据状态：实时采集数据，以平台后台最终结算为准。"
        )
        return {
            "unique_key": f"{snapshot.shop_id}_{now.strftime('%Y%m%d')}",
            "日期": now.strftime("%Y-%m-%d"),
            "店铺ID": snapshot.shop_id,
            "店铺名称": snapshot.shop_name,
            "日报内容": text,
            "生成时间": dt(now),
        }

    def send_daily_report(self, snapshot: MonitorSnapshot, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now()
        alert_stats = self.get_today_alert_stats(snapshot.shop_id, now)
        report = self.build_report(snapshot, alert_stats, now)
        sent = self.alert_service.send_text(report["日报内容"])
        report["是否已发送"] = sent
        report["发送结果"] = "success" if sent else "failed"
        if hasattr(self.storage, "save_daily_report"):
            self.storage.save_daily_report(report)
        return report

    def get_today_alert_stats(self, shop_id: str, now: datetime) -> dict[str, int]:
        if not hasattr(self.storage, "read_table"):
            return {}
        today = now.strftime("%Y-%m-%d")
        counts: Counter[str] = Counter()
        for record in self.storage.read_table("alert_log"):
            fields = record["fields"]
            if fields.get("店铺ID") != shop_id:
                continue
            if not str(fields.get("触发时间", "")).startswith(today):
                continue
            alert_type = str(fields.get("告警类型") or "unknown")
            counts[alert_type] += 1
        return dict(counts)

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return "未采集"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    @staticmethod
    def _format_alert_stats(alert_stats: dict[str, int]) -> str:
        if not alert_stats:
            return "无"
        return "；".join(f"{key}：{value} 次" for key, value in sorted(alert_stats.items()))
