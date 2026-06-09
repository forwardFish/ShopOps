from datetime import datetime

from shopops.collectors import create_order_collector
from shopops.collectors.platform_order_api import MarketplaceOrderApiCollector
from shopops.collectors.taobao_order_api import TaobaoOrderApiCollector
from shopops.config import Settings


def test_api_source_factory_switches_without_changing_scheduler_flow():
    settings = Settings(order_source="api")

    collector = create_order_collector(settings)

    assert isinstance(collector, MarketplaceOrderApiCollector)


def test_default_crawler_source_does_not_require_taobao_api_credentials():
    settings = Settings(
        order_source="crawler",
        taobao_app_key="",
        taobao_app_secret="",
        taobao_session_key="",
        use_mock_collectors=False,
    )

    settings.validate_business()

    assert settings.order_source == "crawler"


def test_api_mode_without_credentials_fails_without_zero_metrics_when_mocks_disabled():
    settings = Settings(
        order_source="api",
        taobao_app_key="",
        taobao_app_secret="",
        taobao_session_key="",
        use_mock_collectors=False,
    )

    result = TaobaoOrderApiCollector(settings).fetch_today()

    assert result.success is False
    assert result.source == "api"
    assert result.order_count is None
    assert result.paid_order_count is None
    assert result.total_amount is None
    assert result.raw is None
    assert result.error_code == "order_api_credentials_missing"


def test_api_boundary_fetches_all_pages_and_filters_unpaid_orders():
    settings = Settings(order_source="api", use_mock_collectors=False)
    calls: list[tuple[int, int, datetime, datetime]] = []

    def page_fetcher(page_no: int, page_size: int, start_created: datetime, end_created: datetime):
        calls.append((page_no, page_size, start_created, end_created))
        pages = {
            1: [
                {"tid": "10001", "payment": "188.50", "status": "TRADE_FINISHED", "created": "2026-06-02 09:00:00", "pay_time": "2026-06-02 09:05:00", "title": "连衣裙"},
                {"tid": "10002", "payment": "266.00", "status": "WAIT_SELLER_SEND_GOODS", "created": "2026-06-02 09:01:00", "pay_time": "2026-06-02 09:06:00", "title": "针织衫"},
            ],
            2: [
                {"tid": "10003", "payment": "99.90", "status": "WAIT_BUYER_PAY", "created": "2026-06-02 09:02:00", "pay_time": None, "title": "未付款商品"},
            ],
        }
        return pages.get(page_no, [])

    result = TaobaoOrderApiCollector(settings, page_fetcher=page_fetcher, page_size=2).fetch_today()

    assert result.success is True
    assert [call[0] for call in calls] == [1, 2]
    assert all(call[1] == 2 for call in calls)
    assert all(call[2].hour == 0 and call[2].minute == 0 and call[2].second == 0 for call in calls)
    assert result.raw["total"] == 3
    assert result.raw["page_count"] == 2
    assert result.order_count == 2
    assert result.paid_order_count == 2
    assert result.total_amount == 454.5
    assert [order["订单号"] for order in result.orders] == ["10001", "10002"]
    assert all(order["数据来源"] == "api" for order in result.orders)
    assert all(order["unique_key"].startswith("taobao_taobao_shop_001_") for order in result.orders)


def test_api_boundary_explicit_failure_does_not_return_zero():
    settings = Settings(order_source="api")

    result = TaobaoOrderApiCollector(settings, fail=True).fetch_today()

    assert result.success is False
    assert result.order_count is None
    assert result.paid_order_count is None
    assert result.total_amount is None
    assert result.error_code == "order_api_failed"


def test_api_boundary_page_fetch_exception_returns_failure_without_zero_metrics():
    settings = Settings(order_source="api", use_mock_collectors=False)

    def page_fetcher(page_no: int, page_size: int, start_created: datetime, end_created: datetime):
        raise RuntimeError("upstream api unavailable")

    result = TaobaoOrderApiCollector(settings, page_fetcher=page_fetcher).fetch_today()

    assert result.success is False
    assert result.order_count is None
    assert result.paid_order_count is None
    assert result.total_amount is None
    assert result.raw is None
    assert result.error_code == "order_api_failed"
    assert "upstream api unavailable" in result.error_message
