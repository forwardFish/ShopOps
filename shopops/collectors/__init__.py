from __future__ import annotations

from shopops.collectors.jushuitan_order_api import JushuitanOrderApiCollector
from shopops.collectors.platform_order_api import MarketplaceOrderApiCollector
from shopops.collectors.taobao_order_api import TaobaoOrderApiCollector
from shopops.collectors.taobao_order_crawler import TaobaoOrderCrawler
from shopops.collectors.taobao_promotion_crawler import TaobaoPromotionCrawler
from shopops.config import Settings
from shopops.services.browser_service import BrowserService


def create_order_collector(settings: Settings):
    if settings.order_source == "jushuitan":
        return JushuitanOrderApiCollector(settings)
    if settings.order_source == "api":
        return MarketplaceOrderApiCollector(settings)
    if settings.order_source == "crawler":
        return TaobaoOrderCrawler(settings, BrowserService(settings.qianniu_cdp_url))
    raise ValueError("Unsupported ORDER_SOURCE")


def create_promotion_collector(settings: Settings):
    return TaobaoPromotionCrawler(settings, BrowserService(settings.qianniu_cdp_url))
