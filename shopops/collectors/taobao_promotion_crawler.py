from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from shopops.collectors.base import PromotionCollector
from shopops.config import Settings
from shopops.models import PromotionCollectResult, PromotionItem
from shopops.services.browser_service import BrowserService
from shopops.storage.field_mapping import PROMOTION_CENTER_CHANNEL, PROMOTION_CENTER_NAME


PROMOTION_CENTER_URL = "https://qn.taobao.com/home.htm/tuiguangcenter_new/"
COST_LABEL = "花费"
MOCK_PROMOTION_COST = 123.45


class TaobaoPromotionCrawler(PromotionCollector):
    def __init__(self, settings: Settings, browser_service: BrowserService, fail: bool = False) -> None:
        self.settings = settings
        self.browser_service = browser_service
        self.fail = fail

    def fetch_today(self) -> PromotionCollectResult:
        fetched_at = datetime.now()
        if self.fail:
            return self._failed_result(fetched_at, "promotion_cost_failed", "promotion center cost read failed")

        if self.settings.use_mock_collectors:
            item = PromotionItem(
                PROMOTION_CENTER_CHANNEL,
                PROMOTION_CENTER_NAME,
                MOCK_PROMOTION_COST,
                None,
                None,
                None,
                "success",
                raw={"mock": True, "metric": COST_LABEL},
            )
            return PromotionCollectResult(True, "success", "qianniu_pc", self.settings.shop_id, self.settings.shop_name, [item], item.cost, fetched_at)

        ok, message = self.browser_service.check_cdp_available()
        if not ok:
            return self._failed_result(fetched_at, "qianniu_not_running", message)

        try:
            capture = self.browser_service.capture_page_text(PROMOTION_CENTER_URL, screenshot_path=self._screenshot_path(fetched_at))
        except Exception as exc:
            return self._failed_result(fetched_at, "cdp_connection_failed", str(exc))

        has_login_problem, status = self.browser_service.detect_login_problem(capture.text, capture.url)
        if has_login_problem:
            error_code = status or "login_required"
            return self._failed_result(fetched_at, error_code, f"Qianniu promotion center access failed: {error_code}")

        cost = self._extract_cost(capture.text)
        if cost is None:
            return self._failed_result(fetched_at, "promotion_cost_failed", "cannot read promotion center 花费 metric")

        item = PromotionItem(
            PROMOTION_CENTER_CHANNEL,
            PROMOTION_CENTER_NAME,
            cost,
            None,
            None,
            None,
            "success",
            raw={
                "page_url": capture.url,
                "title": capture.title,
                "metric": COST_LABEL,
                "screenshot_path": capture.screenshot_path,
                "scroll_iterations": capture.scroll_iterations,
                "reached_stable_end": capture.reached_stable_end,
            },
        )
        return PromotionCollectResult(True, "success", "qianniu_pc", self.settings.shop_id, self.settings.shop_name, [item], cost, fetched_at)

    def _screenshot_path(self, fetched_at: datetime) -> str:
        path = Path(self.settings.evidence_dir) / fetched_at.strftime("%Y%m%d-%H%M%S") / "qianniu-promotion.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @staticmethod
    def _failed_item(message: str) -> PromotionItem:
        return PromotionItem(PROMOTION_CENTER_CHANNEL, PROMOTION_CENTER_NAME, None, None, None, None, "failed", message, raw=None)

    def _failed_result(self, fetched_at: datetime, error_code: str, error_message: str | None) -> PromotionCollectResult:
        item = self._failed_item(error_message or error_code)
        status = "permission_denied" if error_code == "permission_denied" else "login_required" if error_code == "login_required" else "failed"
        item.status = status
        return PromotionCollectResult(False, status, "qianniu_pc", self.settings.shop_id, self.settings.shop_name, [item], None, fetched_at, error_code, error_message)

    @staticmethod
    def _extract_cost(text: str) -> float | None:
        normalized = text.replace(",", "").replace("￥", "¥")
        patterns = [
            r"花费\s*(?:¥|￥|元)?\s*([0-9]+(?:\.[0-9]+)?)",
            r"花费[^\d]{0,12}([0-9]+(?:\.[0-9]+)?)\s*元",
            r"([0-9]+(?:\.[0-9]+)?)\s*元?\s*花费",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if match:
                return round(float(match.group(1)), 2)
        return None
