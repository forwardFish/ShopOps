from datetime import datetime

from shopops.collectors.taobao_order_crawler import TaobaoOrderCrawler
from shopops.config import Settings
from shopops.scheduler import Scheduler
from shopops.services.browser_service import PageCapture
from shopops.storage.local_feishu import LocalFeishuBitableStorage


class FakeBrowserService:
    def __init__(self, text="", available=True):
        self.text = text
        self.available = available

    def check_cdp_available(self):
        if self.available:
            return True, None
        return False, "无法连接千牛 CDP：connection refused"

    def capture_page_text(self, url, **kwargs):
        return PageCapture(url=url, title="订单中心", text=self.text, scroll_iterations=3, reached_stable_end=True)

    @staticmethod
    def detect_login_problem(text, url=""):
        if "验证码" in text:
            return True, "login_required"
        return False, None


def test_order_crawler_parses_all_visible_order_rows_from_qianniu_text():
    settings = Settings(use_mock_collectors=False)
    text = """
    订单号：3306183637220018070
    下单时间：2026-06-02 09:00:00
    宝贝名称：连衣裙
    单价：188.50
    数量：1
    履约/售后状态：发货未超时
    交易状态：买家已付款
    实收款：188.50
    操作区：详情 发货

    订单号：3306183637220018071
    下单时间：2026-06-02 09:10:00
    宝贝名称：针织衫
    单价：266.00
    数量：1
    履约/售后状态：无售后
    交易状态：交易成功
    实收款：266.00
    操作区：详情
    """
    collector = TaobaoOrderCrawler(settings, FakeBrowserService(text))
    result = collector.fetch_today()
    assert result.success is True
    assert result.source == "crawler"
    assert result.order_count == 2
    assert result.paid_order_count == 2
    assert result.total_amount == 454.5
    assert result.raw["pagination_or_scroll"] is True
    assert len(result.orders) == 2
    assert result.orders[0]["数据来源"] == "crawler"
    assert result.orders[0]["订单号"] == "3306183637220018070"
    assert result.orders[0]["商品名称"] == "连衣裙"
    assert result.orders[0]["履约/售后状态"] == "发货未超时"
    assert result.orders[0]["操作信息"] == "详情 发货"


def test_order_crawler_missing_qianniu_session_returns_failure_without_zeroes():
    settings = Settings(use_mock_collectors=False)
    collector = TaobaoOrderCrawler(settings, FakeBrowserService(available=False))
    result = collector.fetch_today()
    assert result.success is False
    assert result.error_code == "qianniu_not_running"
    assert result.order_count is None
    assert result.paid_order_count is None
    assert result.total_amount is None
    assert result.orders == []


def test_scheduler_crawler_writes_orders_raw_and_monitor_snapshot(tmp_path):
    settings = Settings(
        use_mock_collectors=True,
        local_feishu_path=str(tmp_path / "local_feishu.json"),
        pending_records_path=str(tmp_path / "pending.jsonl"),
    )
    storage = LocalFeishuBitableStorage(settings)
    scheduler = Scheduler(settings=settings, storage=storage, promotion_collector=None)
    result = scheduler.run_once(datetime(2026, 6, 2, 16, 10))
    assert result["order"].source == "crawler"
    assert result["snapshot"].order_source == "crawler"
    assert storage.count("orders_raw") == 2
    orders = [record["fields"] for record in storage.read_table("orders_raw")]
    assert orders[0]["订单号"] == "3306183637220018070"
    assert orders[0]["采集状态"] == "success"
    monitor = storage.read_table("monitor_snapshot")[0]["fields"]
    assert monitor["今日订单数"] == 2
    assert monitor["今日成交额"] == 169.0
