from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class PageCapture:
    url: str
    title: str
    text: str
    scroll_iterations: int
    reached_stable_end: bool
    screenshot_path: str | None = None


class BrowserService:
    def __init__(self, cdp_url: str) -> None:
        self.cdp_url = cdp_url.rstrip("/")
        self._http = requests.Session()
        self._http.trust_env = False

    def check_cdp_available(self) -> tuple[bool, str | None]:
        try:
            response = self._http.get(f"{self.cdp_url}/json/version", timeout=3)
        except Exception as exc:
            return False, f"无法连接千牛 CDP：{exc}"
        if response.status_code != 200:
            return False, f"CDP HTTP 状态异常：{response.status_code}"
        return True, None

    def capture_page_text(
        self,
        url: str,
        wait_ms: int = 3000,
        max_scrolls: int = 20,
        screenshot_path: str | None = None,
    ) -> PageCapture:
        """Connect to the already-running Qianniu PC CDP session, refresh the target page, and read page text."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # pragma: no cover - depends on operator environment
            raise RuntimeError(f"缺少 Playwright，无法连接千牛 PC CDP：{exc}") from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(self.cdp_url)
            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.new_page()
                try:
                    page.goto(url, timeout=30000)
                    page.wait_for_timeout(wait_ms)
                    page.reload(timeout=30000)
                    page.wait_for_timeout(wait_ms)
                    scrolls, stable = self._scroll_until_stable(page, max_scrolls)
                    saved_screenshot = None
                    if screenshot_path:
                        page.screenshot(path=screenshot_path, full_page=True)
                        saved_screenshot = screenshot_path
                    text = page.locator("body").inner_text(timeout=5000)
                    return PageCapture(
                        url=page.url,
                        title=page.title(),
                        text=text,
                        scroll_iterations=scrolls,
                        reached_stable_end=stable,
                        screenshot_path=saved_screenshot,
                    )
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    @staticmethod
    def _scroll_until_stable(page: Any, max_scrolls: int) -> tuple[int, bool]:
        previous_height = -1
        stable_rounds = 0
        scrolls = 0
        for index in range(max_scrolls):
            current_height = int(page.evaluate("() => document.body.scrollHeight") or 0)
            if current_height == previous_height:
                stable_rounds += 1
            else:
                stable_rounds = 0
            if stable_rounds >= 2:
                return scrolls, True
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            previous_height = current_height
            scrolls = index + 1
        return scrolls, False

    @staticmethod
    def detect_login_problem(text: str, url: str = "") -> tuple[bool, str | None]:
        lower_url = url.lower()
        if "login" in lower_url:
            return True, "login_required"
        if any(keyword in text for keyword in ["登录", "扫码", "验证码", "请验证", "安全验证"]):
            return True, "login_required"
        if any(keyword in text for keyword in ["无权限", "权限不足"]):
            return True, "permission_denied"
        return False, None
