from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from shopops.collectors.base import OrderCollector
from shopops.config import Settings
from shopops.models import OrderCollectResult, dt
from shopops.services.browser_service import BrowserService


ORDER_CENTER_URL = "https://qn.taobao.com/home.htm/trade-platform/tp/sold"
PAID_STATUS_KEYWORDS = ("买家已付款", "等待卖家发货", "卖家已发货", "交易成功", "TRADE_FINISHED", "WAIT_SELLER_SEND_GOODS")
UNPAID_OR_CLOSED_KEYWORDS = ("等待买家付款", "未付款", "交易关闭", "退款成功", "WAIT_BUYER_PAY", "TRADE_CLOSED")


class TaobaoOrderCrawler(OrderCollector):
    def __init__(self, settings: Settings, browser_service: BrowserService, fail_code: str | None = None) -> None:
        self.settings = settings
        self.browser_service = browser_service
        self.fail_code = fail_code

    def fetch_today(self) -> OrderCollectResult:
        fetched_at = datetime.now()
        if self.fail_code:
            return self._failure(fetched_at, self.fail_code, f"Qianniu crawler failed: {self.fail_code}")
        if self.settings.use_mock_collectors:
            return self._success(fetched_at, self._mock_orders(fetched_at), {"mock": True, "scroll_iterations": 2, "pagination_or_scroll": True})

        ok, message = self.browser_service.check_cdp_available()
        if not ok:
            return self._failure(fetched_at, "qianniu_not_running", message or "Qianniu CDP unavailable")
        try:
            capture = self.browser_service.capture_page_text(ORDER_CENTER_URL, screenshot_path=self._screenshot_path(fetched_at))
        except Exception as exc:
            return self._failure(fetched_at, "order_crawler_failed", str(exc))

        has_problem, code = self.browser_service.detect_login_problem(capture.text, capture.url)
        if has_problem:
            return self._failure(fetched_at, code or "login_required", f"千牛已卖出宝贝页面不可采集：{code}")

        orders = self.parse_order_center_text(capture.text, fetched_at)
        if not orders:
            return self._failure(fetched_at, "order_crawler_no_orders", "已卖出宝贝页面未解析到订单号，未写入 0 指标")

        for order in orders:
            order["页面URL"] = capture.url
            order["页面截图"] = capture.screenshot_path
        return self._success(
            fetched_at,
            orders,
            {
                "mock": False,
                "page_url": capture.url,
                "page_title": capture.title,
                "screenshot_path": capture.screenshot_path,
                "scroll_iterations": capture.scroll_iterations,
                "pagination_or_scroll": capture.reached_stable_end or capture.scroll_iterations > 0,
            },
        )

    def _screenshot_path(self, fetched_at: datetime) -> str:
        path = Path(self.settings.evidence_dir) / fetched_at.strftime("%Y%m%d-%H%M%S") / "qianniu-orders.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _success(self, fetched_at: datetime, orders: list[dict[str, Any]], raw: dict[str, Any]) -> OrderCollectResult:
        paid_orders = [order for order in orders if self._is_paid_order(order)]
        total_amount = sum(Decimal(str(order.get("实收款") or "0")) for order in paid_orders)
        return OrderCollectResult(
            success=True,
            source="crawler",
            shop_id=self.settings.shop_id,
            shop_name=self.settings.shop_name,
            order_count=len({order["订单号"] for order in orders}),
            paid_order_count=len({order["订单号"] for order in paid_orders}),
            total_amount=float(round(total_amount, 2)),
            fetched_at=fetched_at,
            raw=raw | {"order_rows": len(orders)},
            orders=orders,
        )

    def _failure(self, fetched_at: datetime, code: str, message: str) -> OrderCollectResult:
        return OrderCollectResult(
            success=False,
            source="crawler",
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

    def parse_order_center_text(self, text: str, fetched_at: datetime) -> list[dict[str, Any]]:
        rows = self._parse_json_orders(text, fetched_at)
        if rows:
            return rows
        return self._parse_text_orders(text, fetched_at)

    def _parse_json_orders(self, text: str, fetched_at: datetime) -> list[dict[str, Any]]:
        marker = "SHOPOPS_ORDER_ROWS="
        if marker not in text:
            return []
        payload = text.split(marker, 1)[1].splitlines()[0].strip()
        try:
            source_rows = json.loads(payload)
        except json.JSONDecodeError:
            return []
        return [self._normalize_source_row(row, fetched_at) for row in source_rows if row.get("订单号") or row.get("order_id")]

    def _parse_text_orders(self, text: str, fetched_at: datetime) -> list[dict[str, Any]]:
        normalized_text = re.sub(r"\r\n?", "\n", text)
        matches = list(re.finditer(r"(?:订单号[:：]?\s*)?(\d{12,24})(?!\d)", normalized_text))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, match in enumerate(matches):
            order_id = match.group(1)
            if order_id in seen:
                continue
            seen.add(order_id)
            block_start = match.start()
            block_end = matches[index + 1].start() if index + 1 < len(matches) else min(len(normalized_text), match.end() + 900)
            block = normalized_text[block_start:block_end]
            rows.append(self._normalize_source_row(self._extract_fields_from_block(order_id, block), fetched_at))
        return rows

    def _extract_fields_from_block(self, order_id: str, block: str) -> dict[str, Any]:
        compact = " ".join(line.strip() for line in block.splitlines() if line.strip())
        return {
            "订单号": order_id,
            "创建时间": self._first_match(compact, r"创建时间[:：]?\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)")
            or self._first_match(compact, r"下单时间[:：]?\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?)"),
            "买家昵称": self._extract_buyer(compact),
            "商品名称": self._labeled_value(compact, ("宝贝名称", "商品名称", "宝贝标题", "标题")) or self._guess_product_name(compact),
            "单价": self._money_after_label(compact, ("单价",)),
            "数量": self._int_after_label(compact, ("数量", "件数")),
            "履约/售后状态": self._labeled_value(compact, ("履约/售后状态", "售后状态", "履约状态")),
            "交易状态": self._labeled_value(compact, ("交易状态", "订单状态", "状态")),
            "实收款": self._money_after_label(compact, ("实收款", "支付金额", "实付", "应收")),
            "操作信息": self._labeled_value(compact, ("操作区", "操作信息", "操作")),
            "原始数据": compact,
        }

    def _normalize_source_row(self, row: dict[str, Any], fetched_at: datetime) -> dict[str, Any]:
        order_id = str(row.get("订单号") or row.get("order_id") or "").strip()
        raw = row.get("原始数据", row)
        return {
            "unique_key": f"taobao_{self.settings.shop_id}_{order_id}",
            "平台": self.settings.feishu_platform_name,
            "数据来源": "crawler",
            "店铺ID": self.settings.shop_id,
            "店铺名称": self.settings.shop_name,
            "采集时间": dt(fetched_at),
            "订单号": order_id,
            "创建时间": row.get("创建时间") or row.get("下单时间") or row.get("created"),
            "买家昵称": row.get("买家昵称") or row.get("buyer_nick") or "",
            "商品名称": row.get("商品名称") or row.get("宝贝名称") or row.get("title") or "",
            "单价": self._to_float(row.get("单价") or row.get("price")),
            "数量": self._to_int(row.get("数量") or row.get("quantity")),
            "履约/售后状态": row.get("履约/售后状态") or row.get("售后状态") or "",
            "交易状态": row.get("交易状态") or row.get("订单状态") or row.get("status") or "",
            "实收款": self._to_float(row.get("实收款") or row.get("支付金额") or row.get("payment")),
            "操作信息": row.get("操作信息") or row.get("操作区") or "",
            "页面URL": row.get("页面URL"),
            "页面截图": row.get("页面截图"),
            "采集状态": "success",
            "错误信息": None,
            "原始数据": raw,
        }

    @staticmethod
    def _is_paid_order(order: dict[str, Any]) -> bool:
        status_text = " ".join(str(order.get(key) or "") for key in ("交易状态", "履约/售后状态"))
        if any(keyword in status_text for keyword in UNPAID_OR_CLOSED_KEYWORDS):
            return False
        return any(keyword in status_text for keyword in PAID_STATUS_KEYWORDS) or order.get("实收款") is not None

    def _mock_orders(self, fetched_at: datetime) -> list[dict[str, Any]]:
        created = fetched_at.replace(hour=9, minute=0, second=0, microsecond=0)
        rows = [
            {"订单号": "3306183637220018070", "创建时间": dt(created), "买家昵称": "牛**", "商品名称": "趣白全自动洗面奶打泡机感应泡沫机绵密泡沫礼", "单价": 199.0, "数量": 1, "履约/售后状态": "退款成功", "交易状态": "交易关闭", "实收款": 169.0, "操作信息": "详情"},
            {"订单号": "3306183637220018071", "创建时间": dt(created), "买家昵称": "星**", "商品名称": "趣白全自动洗面奶打泡机感应泡沫机绵密泡沫礼", "单价": 199.0, "数量": 1, "履约/售后状态": "发货未超时", "交易状态": "买家已付款", "实收款": 169.0, "操作信息": "详情 寄件 打单 发货"},
        ]
        return [self._normalize_source_row(row, fetched_at) for row in rows]

    @staticmethod
    def _first_match(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_buyer(text: str) -> str:
        match = re.search(r"创建时间[:：]?\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\s+([^\s]+)", text)
        if not match:
            return ""
        buyer = match.group(1).strip()
        return "" if buyer in {"号码保护订单", "订单号"} else buyer

    @staticmethod
    def _guess_product_name(text: str) -> str:
        match = re.search(r"(趣白[^\s]+)", text)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _labeled_value(text: str, labels: tuple[str, ...]) -> str:
        stop_labels = "订单号|创建时间|下单时间|支付时间|宝贝名称|商品名称|宝贝标题|标题|单价|数量|履约/售后状态|售后状态|履约状态|交易状态|订单状态|状态|实收款|支付金额|实付|应收|操作区|操作信息|操作"
        for label in labels:
            match = re.search(rf"{re.escape(label)}\s*[:：]?\s*(.+?)(?=\s+(?:{stop_labels})\s*[:：]?|$)", text)
            if match:
                return match.group(1).strip()
        return ""

    def _money_after_label(self, text: str, labels: tuple[str, ...]) -> float | None:
        for label in labels:
            value = self._first_match(text, rf"{re.escape(label)}\s*[:：]?\s*[¥￥]?\s*([0-9]+(?:\.[0-9]+)?)")
            if value is not None:
                return self._to_float(value)
        return None

    def _int_after_label(self, text: str, labels: tuple[str, ...]) -> int | None:
        for label in labels:
            value = self._first_match(text, rf"{re.escape(label)}\s*[:：]?\s*(\d+)")
            if value is not None:
                return self._to_int(value)
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(Decimal(str(value).replace(",", "").replace("¥", "").replace("￥", "").strip()))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(str(value).strip())
        except ValueError:
            return None
