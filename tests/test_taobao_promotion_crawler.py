from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shopops.collectors.taobao_order_api import TaobaoOrderApiCollector
from shopops.collectors.taobao_promotion_crawler import PROMOTION_CENTER_URL, TaobaoPromotionCrawler
from shopops.config import Settings
from shopops.scheduler import Scheduler
from shopops.services.browser_service import PageCapture
from shopops.storage.local_feishu import LocalFeishuBitableStorage


@dataclass
class FakeBrowserService:
    text: str
    url: str = PROMOTION_CENTER_URL
    available: bool = True
    error_message: str = "Qianniu CDP unavailable"

    def check_cdp_available(self):
        return self.available, None if self.available else self.error_message

    def capture_page_text(self, url: str, **kwargs):
        assert url == PROMOTION_CENTER_URL
        return PageCapture(
            url=self.url,
            title="推广中心",
            text=self.text,
            scroll_iterations=2,
            reached_stable_end=True,
        )

    @staticmethod
    def detect_login_problem(text: str, url: str = ""):
        if "login" in url.lower() or "登录" in text or "验证码" in text:
            return True, "login_required"
        if "无权限" in text or "权限不足" in text:
            return True, "permission_denied"
        return False, None


def test_promotion_crawler_reads_only_cost_metric_from_qianniu_page():
    settings = Settings(use_mock_collectors=False)
    browser = FakeBrowserService("经营概览\n曝光 999\n点击 88\n花费 ¥123.45\n转化 3\n投入产出比 2.3")
    result = TaobaoPromotionCrawler(settings, browser).fetch_today()

    assert result.success is True
    assert result.status == "success"
    assert result.total_cost == 123.45
    assert len(result.items) == 1
    item = result.items[0]
    assert item.channel == "tuiguangcenter"
    assert item.channel_name == "推广中心"
    assert item.cost == 123.45
    assert item.impressions is None
    assert item.clicks is None
    assert item.conversions is None
    assert item.raw["metric"] == "花费"
    assert "曝光" not in str(item.raw)
    assert "点击" not in str(item.raw)


def test_promotion_crawler_failure_does_not_return_zero_cost():
    settings = Settings(use_mock_collectors=False)
    browser = FakeBrowserService("经营概览\n曝光 999\n点击 88")
    result = TaobaoPromotionCrawler(settings, browser).fetch_today()

    assert result.success is False
    assert result.status == "failed"
    assert result.total_cost is None
    assert result.items[0].cost is None
    assert result.error_code == "promotion_cost_failed"


def test_promotion_crawler_classifies_qianniu_access_failures():
    settings = Settings(use_mock_collectors=False)

    no_cdp = TaobaoPromotionCrawler(settings, FakeBrowserService("", available=False)).fetch_today()
    assert no_cdp.success is False
    assert no_cdp.error_code == "qianniu_not_running"
    assert no_cdp.total_cost is None

    login = TaobaoPromotionCrawler(settings, FakeBrowserService("请登录后查看")).fetch_today()
    assert login.status == "login_required"
    assert login.total_cost is None

    denied = TaobaoPromotionCrawler(settings, FakeBrowserService("无权限查看推广中心")).fetch_today()
    assert denied.status == "permission_denied"
    assert denied.total_cost is None


def test_scheduler_writes_single_promotion_center_snapshot_without_channel_split(tmp_path):
    settings = Settings(
        use_mock_collectors=False,
        local_feishu_path=str(tmp_path / "local_feishu.json"),
        pending_records_path=str(tmp_path / "pending.jsonl"),
    )
    storage = LocalFeishuBitableStorage(settings)
    promotion = TaobaoPromotionCrawler(settings, FakeBrowserService("经营概览\n花费 88.66 元\n曝光 1000\n点击 20"))
    scheduler = Scheduler(
        settings,
        storage,
        TaobaoOrderApiCollector(settings),
        promotion,
    )

    result = scheduler.run_once(datetime(2026, 6, 2, 16, 40))

    assert result["promotion"].total_cost == 88.66
    assert storage.count("promotion_snapshot") == 1
    row = storage.read_table("promotion_snapshot")[0]["fields"]
    assert row["平台"] == "千牛淘宝"
    assert row["花费"] == 88.66
    assert "曝光" not in row
    assert "点击" not in row
    assert "转化" not in row
    monitor = storage.read_table("monitor_snapshot")[0]["fields"]
    assert monitor["推广中心花费"] == 88.66
    assert monitor["总推广消耗"] == 88.66
