from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from shopops.collectors.base import OrderCollector
from shopops.config import Settings
from shopops.models import OrderCollectResult, dt


ApiPageFetcher = Callable[[int, int, datetime, datetime], list[dict[str, Any]]]


class TaobaoOrderApiCollector(OrderCollector):
    def __init__(
        self,
        settings: Settings,
        trades: list[dict[str, Any]] | None = None,
        fail: bool = False,
        page_fetcher: ApiPageFetcher | None = None,
        page_size: int = 100,
    ) -> None:
        self.settings = settings
        self.trades = trades
        self.fail = fail
        self.page_fetcher = page_fetcher
        self.page_size = page_size

    def fetch_today(self) -> OrderCollectResult:
        fetched_at = datetime.now()
        if self.fail:
            return self._failure(fetched_at, "order_api_failed", "mock order API failure")

        if self.trades is None and self.page_fetcher is None and not self.settings.use_mock_collectors:
            if not all([self.settings.taobao_app_key, self.settings.taobao_app_secret, self.settings.taobao_session_key]):
                return self._failure(fetched_at, "order_api_credentials_missing", "Taobao API credentials are missing")

        try:
            page_count = 1
            if self.page_fetcher is not None:
                trades, page_count = self._fetch_all_pages(fetched_at)
            elif self.trades is not None:
                trades = self.trades
            else:
                trades = self._default_trades(fetched_at)
            paid = [t for t in trades if t.get("status") != "WAIT_BUYER_PAY"]
            orders = [self._normalize_order(t, fetched_at) for t in paid]
            total_amount = round(sum(float(t.get("payment") or 0) for t in paid), 2)
            return OrderCollectResult(
                success=True,
                source="api",
                shop_id=self.settings.shop_id,
                shop_name=self.settings.shop_name,
                order_count=len(paid),
                paid_order_count=len(paid),
                total_amount=total_amount,
                fetched_at=fetched_at,
                raw={
                    "total": len(trades),
                    "page_count": page_count,
                    "page_size": self.page_size,
                    "mock": self.settings.use_mock_collectors,
                },
                orders=orders,
            )
        except Exception as exc:
            return self._failure(fetched_at, "order_api_failed", str(exc))

    def _fetch_all_pages(self, fetched_at: datetime) -> tuple[list[dict[str, Any]], int]:
        if self.page_size <= 0:
            raise ValueError("page_size must be positive")
        today_start = fetched_at.replace(hour=0, minute=0, second=0, microsecond=0)
        all_trades: list[dict[str, Any]] = []
        page_no = 1
        while True:
            trades = self.page_fetcher(page_no, self.page_size, today_start, fetched_at) if self.page_fetcher else []
            all_trades.extend(trades)
            if len(trades) < self.page_size:
                return all_trades, page_no
            page_no += 1

    def _failure(self, fetched_at: datetime, code: str, message: str) -> OrderCollectResult:
        return OrderCollectResult(
            success=False,
            source="api",
            shop_id=self.settings.shop_id,
            shop_name=self.settings.shop_name,
            order_count=None,
            paid_order_count=None,
            total_amount=None,
            fetched_at=fetched_at,
            error_code=code,
            error_message=message,
            raw=None,
        )

    def _normalize_order(self, trade: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        order_id = str(trade["tid"])
        return {
            "unique_key": f"taobao_{self.settings.shop_id}_{order_id}",
            "数据来源": "api",
            "店铺ID": self.settings.shop_id,
            "店铺名称": self.settings.shop_name,
            "订单号": order_id,
            "下单时间": trade.get("created"),
            "支付时间": trade.get("pay_time"),
            "订单状态": trade.get("status"),
            "支付金额": float(trade.get("payment") or 0),
            "商品名称": trade.get("title", ""),
            "采集时间": dt(fetched_at),
            "原始数据": trade,
        }

    @staticmethod
    def _default_trades(fetched_at: datetime) -> list[dict[str, Any]]:
        created = fetched_at.replace(hour=9, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        paid = fetched_at.replace(hour=9, minute=5, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        return [
            {"tid": "10001", "payment": "188.50", "status": "TRADE_FINISHED", "created": created, "pay_time": paid, "title": "连衣裙"},
            {"tid": "10002", "payment": "266.00", "status": "WAIT_SELLER_SEND_GOODS", "created": created, "pay_time": paid, "title": "针织衫"},
            {"tid": "10003", "payment": "99.90", "status": "WAIT_BUYER_PAY", "created": created, "pay_time": None, "title": "未付款商品"},
        ]
