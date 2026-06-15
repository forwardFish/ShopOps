from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from data_robot.common import DirectCdpPage
from scripts.import_daily_files_to_feishu import (
    AD_FIELD_TYPES,
    F_ACTUAL_SPEND,
    F_CLICKS,
    F_CLICK_RATE,
    F_DATA_SOURCE,
    F_DATE,
    F_DEAL_AMOUNT,
    F_EXPOSURES,
    F_FETCHED_AT,
    F_IMPRESSIONS,
    F_PLATFORM,
    F_PLATFORM_ROI,
    F_PROMOTION_SPEND,
    F_RAW,
    F_ROI,
    F_SHOP_ID,
    F_SHOP_NAME,
    F_SPEND,
    F_TRADE_AMOUNT,
    F_TRUE_ROI,
    F_UNIQUE_KEY,
    FeishuDailyClient,
    ad_unique_key,
    missing_row_fields,
    ratio,
    write_import_evidence,
)
from shopops.config import _load_dotenv, load_settings


PLATFORMS = {
    "douyin": "\u6296\u97f3",
    "tmall": "\u5929\u732b",
}

DEFAULT_URLS = {
    "douyin": "https://qianchuan.jinritemai.com/home?aavid=1860240208332803",
    "tmall": "https://myseller.taobao.com/home.htm/tuiguangcenter_new/",
}

def default_dashboard_url(platform_code: str, stat_date: str) -> str:
    return DEFAULT_URLS[platform_code]


def url_path_looks_like_login(url: str) -> bool:
    parsed = urlparse(url)
    haystack = f"{parsed.netloc}{parsed.path}".lower()
    return any(token in haystack for token in ("login", "passport", "auth", "captcha", "verify"))


def visible_browser_profile(platform_code: str, cdp_url: str) -> Path:
    port = urlparse(cdp_url).port if cdp_url else None
    suffix = f"{platform_code}-{port}" if port else platform_code
    root = Path(os.getenv("SHOPOPS_CDP_PROFILE_ROOT", os.path.expandvars(r"%LOCALAPPDATA%\ShopOpsCdpProfiles")))
    return root / suffix


def find_chrome_executable() -> str:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    return next((candidate for candidate in candidates if Path(candidate).exists()), "")


def open_visible_chrome_page(platform_code: str, url: str, cdp_url: str = "") -> dict[str, Any]:
    chrome = find_chrome_executable()
    if not chrome:
        return {"status": "chrome_not_found"}
    parsed = urlparse(cdp_url)
    port = parsed.port
    profile = visible_browser_profile(platform_code, cdp_url)
    profile.mkdir(parents=True, exist_ok=True)
    args = [
        "--new-window",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    if port:
        args.insert(2, f"--remote-debugging-port={port}")
        args.insert(3, "--remote-allow-origins=*")
    subprocess.Popen([chrome, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "started", "platform": platform_code, "url": url, "cdp_url": cdp_url, "profile": str(profile)}

NUMBER_PATTERN = r"[-+]?\d[\d,]*(?:\.\d+)?%?"
MANUAL_INTERVENTION_KEYWORDS = (
    "登录",
    "登陆",
    "扫码",
    "二维码",
    "验证码",
    "请验证",
    "安全验证",
    "滑块",
    "拖动滑块",
    "短信验证",
    "人脸验证",
    "身份验证",
    "login",
    "captcha",
    "verify",
)

USERNAME_SELECTORS = (
    "input[name='fm-login-id']",
    "input[name='loginId']",
    "input[name='username']",
    "input[name='account']",
    "input[type='tel']",
    "input[type='text']",
    "input[placeholder*='账号']",
    "input[placeholder*='会员名']",
    "input[placeholder*='手机号']",
)

PASSWORD_SELECTORS = (
    "input[name='fm-login-password']",
    "input[name='password']",
    "input[type='password']",
    "input[placeholder*='密码']",
)

LOGIN_BUTTON_SELECTORS = (
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('登录')",
    "button:has-text('登 录')",
    "a:has-text('登录')",
    ".fm-button",
)

METRIC_LABELS = {
    "spend": (
        "\u5168\u57df\u6295\u653e\u6d88\u8017",
        "\u5168\u57df\u6295\u653e\u6d88\u8017(\u5143)",
        "\u6574\u4f53\u6d88\u8017",
        "\u6574\u4f53\u6d88\u8017(\u5143)",
        "\u8d26\u6237\u6574\u4f53\u6d88\u8017",
        "\u8d26\u6237\u6574\u4f53\u6d88\u8017(\u5143)",
        "\u6d88\u8017",
        "\u82b1\u8d39",
        "\u63a8\u5e7f\u82b1\u8d39",
    ),
    "impressions": (
        "\u6574\u4f53\u5c55\u793a\u6b21\u6570",
        "\u5c55\u73b0\u91cf",
        "\u5c55\u793a\u6b21\u6570",
        "\u66dd\u5149\u91cf",
    ),
    "clicks": (
        "\u6574\u4f53\u70b9\u51fb\u6b21\u6570",
        "\u70b9\u51fb\u91cf",
        "\u70b9\u51fb\u6b21\u6570",
    ),
    "click_rate": (
        "\u6574\u4f53\u70b9\u51fb\u7387",
        "\u70b9\u51fb\u7387",
    ),
    "conversion_rate": (
        "\u6574\u4f53\u8f6c\u5316\u7387",
        "\u8f6c\u5316\u7387",
    ),
    "roi": (
        "\u51c0\u6210\u4ea4ROI",
        "\u6295\u5165\u4ea7\u51fa\u6bd4",
        "\u6574\u4f53\u652f\u4ed8ROI",
        "\u652f\u4ed8ROI",
        "ROI",
        "\u6295\u4ea7\u6bd4",
    ),
    "deal_amount": (
        "\u51c0\u6210\u4ea4\u91d1\u989d",
        "\u51c0\u6210\u4ea4\u91d1\u989d(\u5143)",
        "\u603b\u6210\u4ea4\u91d1\u989d",
        "\u6574\u4f53\u6210\u4ea4\u91d1\u989d",
        "\u6574\u4f53\u6210\u4ea4\u91d1\u989d(\u5143)",
        "\u6210\u4ea4\u91d1\u989d",
    ),
    "order_count": (
        "\u51c0\u6210\u4ea4\u8ba2\u5355\u6570",
        "\u6574\u4f53\u6210\u4ea4\u8ba2\u5355\u6570",
        "\u6210\u4ea4\u8ba2\u5355\u6570",
    ),
}


def normalize_ocr_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\s*\n\s*", "\n", text).strip()


def number_from_text(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip().replace(",", "")
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    return round(number / 100, 6) if is_percent else round(number, 6)


def first_metric_value(text: str, labels: tuple[str, ...]) -> float | None:
    line_value = first_metric_value_by_line(text, labels)
    if line_value is not None:
        return line_value
    compact = normalize_ocr_text(text)
    for label in labels:
        pattern = re.compile(rf"{re.escape(label)}[^\d+-]{{0,32}}({NUMBER_PATTERN})", re.IGNORECASE)
        match = pattern.search(compact)
        if match:
            return number_from_text(match.group(1))
    return None


def first_metric_value_by_line(text: str, labels: tuple[str, ...]) -> float | None:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    lines = [line for line in lines if line]
    label_set = set(labels)
    for index, line in enumerate(lines):
        if line not in label_set:
            continue
        for next_line in lines[index + 1 : index + 4]:
            value = number_from_text(next_line)
            if value is not None:
                return value
    return None


def parse_ad_snapshot_text(platform_code: str, text: str, stat_date: str, *, screenshot_path: str = "") -> dict[str, Any]:
    if platform_code not in PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform_code}")
    platform = PLATFORMS[platform_code]
    metrics = {name: first_metric_value(text, labels) for name, labels in METRIC_LABELS.items()}
    spend = metrics["spend"]
    impressions = metrics["impressions"]
    clicks = metrics["clicks"]
    deal_amount = metrics["deal_amount"]
    order_count = metrics["order_count"]
    if spend is None:
        raise RuntimeError(f"OCR text did not contain a spend metric for {platform}")
    if impressions is None and clicks is None and deal_amount is None and order_count is None:
        raise RuntimeError(f"OCR text did not contain enough non-spend metrics for {platform}")
    roi_value = metrics["roi"] if metrics["roi"] is not None else ratio(deal_amount, spend)
    fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {
        F_UNIQUE_KEY: ad_unique_key(platform, stat_date),
        F_PLATFORM: platform,
        F_DATA_SOURCE: f"{platform}\u6295\u6d41\u622a\u56feOCR",
        F_SHOP_ID: "",
        F_SHOP_NAME: platform,
        F_FETCHED_AT: fetched_at,
        F_DATE: stat_date,
        F_SPEND: spend,
        F_PROMOTION_SPEND: spend,
        F_ACTUAL_SPEND: spend,
        F_DEAL_AMOUNT: deal_amount,
        F_TRADE_AMOUNT: deal_amount,
        F_IMPRESSIONS: impressions,
        F_EXPOSURES: impressions,
        F_CLICKS: clicks,
        F_CLICK_RATE: metrics["click_rate"] if metrics["click_rate"] is not None else ratio(clicks, impressions),
        F_ROI: roi_value,
        F_PLATFORM_ROI: roi_value,
        F_TRUE_ROI: ratio(deal_amount, spend),
        F_RAW: json.dumps(
            {
                "source": "ocr_ads_snapshot",
                "platform_code": platform_code,
                "ocr_text": normalize_ocr_text(text),
                "metrics": metrics,
                "screenshot_path": screenshot_path,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
    }


def detect_manual_intervention_required(text: str, url: str = "") -> bool:
    if url_path_looks_like_login(url):
        return True
    haystack = text.lower()
    keywords = (
        "\u767b\u5f55",
        "\u626b\u7801",
        "\u4e8c\u7ef4\u7801",
        "\u9a8c\u8bc1\u7801",
        "\u5b89\u5168\u9a8c\u8bc1",
        "\u6ed1\u5757",
        "\u77ed\u4fe1\u9a8c\u8bc1",
        "\u4eba\u8138\u9a8c\u8bc1",
        *tuple(keyword for keyword in MANUAL_INTERVENTION_KEYWORDS if keyword.lower() != "login"),
    )
    return any(keyword.lower() in haystack for keyword in keywords)


def load_local_env_files() -> None:
    _load_dotenv(".env")
    _load_dotenv(".env.local")


def get_login_credentials(platform_code: str) -> tuple[str, str]:
    load_local_env_files()
    platform = platform_code.upper()
    prefixes = [
        f"SHOPOPS_{platform}_",
        f"{platform}_",
    ]
    if platform_code == "tmall":
        prefixes.extend(["SHOPOPS_QIANNIU_", "QIANNIU_", "SHOPOPS_TAOBAO_", "TAOBAO_"])
    if platform_code == "douyin":
        prefixes.extend(["SHOPOPS_QIANCHUAN_", "QIANCHUAN_", "SHOPOPS_OCEANENGINE_", "OCEANENGINE_"])
    for prefix in prefixes:
        username = os.getenv(prefix + "USERNAME") or os.getenv(prefix + "ACCOUNT") or os.getenv(prefix + "LOGIN_ID")
        password = os.getenv(prefix + "PASSWORD") or os.getenv(prefix + "PASS")
        if username and password:
            return username, password
    credential = read_dpapi_login_credential(platform_code)
    if credential:
        return credential
    return "", ""


def read_dpapi_login_credential(platform_code: str) -> tuple[str, str] | None:
    secret_root = Path(os.getenv("SHOPOPS_SECRET_ROOT", os.path.expandvars(r"%APPDATA%\ShopOps\secrets")))
    path = secret_root / f"{platform_code}-login.credential.xml"
    if not path.exists():
        return None
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "$c = Import-Clixml -LiteralPath $args[0]; "
            "$p = $c.GetNetworkCredential().Password; "
            "[Console]::Out.Write(($c.UserName + [char]0x1f + $p))"
        ),
        str(path),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=20)
    if completed.returncode != 0 or "\x1f" not in completed.stdout:
        return None
    username, password = completed.stdout.split("\x1f", 1)
    username = username.strip()
    password = password.strip()
    if username and password:
        return username, password
    return None


async def fill_first_visible(page: Any, selectors: tuple[str, ...], value: str) -> bool:
    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=1000):
                    await locator.fill(value, timeout=5000)
                    return True
            except Exception:
                continue
    return False


async def click_first_visible(page: Any, selectors: tuple[str, ...]) -> bool:
    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=1000):
                    await locator.click(timeout=5000)
                    return True
            except Exception:
                continue
    return False


async def auto_fill_login_if_configured(page: Any, platform_code: str) -> dict[str, Any]:
    username, password = get_login_credentials(platform_code)
    if not username or not password:
        return {"status": "missing_credentials"}
    username_filled = await fill_first_visible(page, USERNAME_SELECTORS, username)
    password_filled = await fill_first_visible(page, PASSWORD_SELECTORS, password)
    clicked = False
    if username_filled and password_filled:
        clicked = await click_first_visible(page, LOGIN_BUTTON_SELECTORS)
        await page.wait_for_timeout(3000)
    return {
        "status": "submitted" if clicked else "filled" if username_filled and password_filled else "fields_not_found",
        "username_filled": username_filled,
        "password_filled": password_filled,
        "clicked_login": clicked,
    }


async def click_first_text(page: Any, labels: tuple[str, ...], *, exact: bool = False) -> list[str]:
    clicked: list[str] = []
    for label in labels:
        selectors = [f"text={label}"] if exact else [f"text={label}", f":text('{label}')"]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if await locator.count() and await locator.is_visible(timeout=1000):
                    await locator.click(timeout=5000)
                    clicked.append(label)
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                continue
        if clicked and label.startswith("全域投放消耗"):
            break
    return clicked


async def prepare_playwright_dashboard(page: Any, platform_code: str) -> dict[str, Any]:
    if platform_code == "douyin":
        clicked = await click_first_text(
            page,
            ("全域投放消耗", "全域投放消耗(元)", "账户整体消耗", "数据概览"),
        )
        return {"clicked": clicked}
    if platform_code == "tmall":
        clicked = await click_first_text(page, ("更多数据",))
        return {"clicked": clicked}
    return {"clicked": []}


async def wait_for_manual_intervention_if_needed(
    page: Any,
    *,
    platform_code: str,
    auto_login: bool,
    timeout_seconds: int,
    interval_seconds: int,
) -> dict[str, Any]:
    started_at = datetime.now()
    deadline = started_at.timestamp() + max(1, timeout_seconds)
    checks = 0
    last_url = ""
    last_text = ""
    auto_login_attempted = False
    last_auto_login_result: dict[str, Any] = {"status": "not_attempted"}
    while True:
        checks += 1
        last_url = page.url
        try:
            last_text = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            last_text = ""
        if not detect_manual_intervention_required(last_text, last_url):
            return {
                "status": "ready",
                "checks": checks,
                "waited_seconds": int((datetime.now() - started_at).total_seconds()),
            }
        if auto_login and not auto_login_attempted:
            auto_login_attempted = True
            last_auto_login_result = await auto_fill_login_if_configured(page, platform_code)
            print(f"Auto-login attempt status: {last_auto_login_result['status']}", flush=True)
            if last_auto_login_result["status"] in {"submitted", "filled"}:
                await page.wait_for_timeout(max(1, interval_seconds) * 1000)
                continue
        if datetime.now().timestamp() >= deadline:
            return {
                "status": "manual_intervention_timeout",
                "checks": checks,
                "waited_seconds": int((datetime.now() - started_at).total_seconds()),
                "url": last_url,
                "auto_login": last_auto_login_result,
            }
        print(
            f"Detected login/captcha page. Please finish it in the visible browser; rechecking in {interval_seconds}s.",
            flush=True,
        )
        await page.wait_for_timeout(max(1, interval_seconds) * 1000)


async def capture_screenshot(
    url: str,
    screenshot_path: Path,
    *,
    platform_code: str,
    cdp_url: str = "",
    headless: bool = False,
    allow_new_browser: bool = False,
    wait_login: bool = False,
    auto_login: bool = False,
    login_wait_timeout_seconds: int = 900,
    login_check_interval_seconds: int = 15,
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = None
        if cdp_url:
            browser = await playwright.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
        else:
            if not allow_new_browser:
                raise RuntimeError("Missing --cdp-url for screenshot capture. This entrypoint defaults to an already logged-in local Chrome.")
            context = await playwright.chromium.launch_persistent_context(
                str(ROOT / "data_robot" / "profiles" / "ocr_ads_snapshot"),
                headless=headless,
                viewport={"width": 1440, "height": 960},
                channel="chrome",
            )
        page = context.pages[0] if context.pages else await context.new_page()
        if url not in page.url and not url_path_looks_like_login(page.url):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=120_000)
            except Exception as exc:
                print(f"Navigation did not finish, continuing with current visible page: {type(exc).__name__}: {exc}", flush=True)
        await page.wait_for_timeout(5000)
        manual_wait = {"status": "not_checked"}
        if wait_login:
            manual_wait = await wait_for_manual_intervention_if_needed(
                page,
                platform_code=platform_code,
                auto_login=auto_login,
                timeout_seconds=login_wait_timeout_seconds,
                interval_seconds=login_check_interval_seconds,
            )
            if manual_wait["status"] != "ready":
                raise RuntimeError(f"Manual login/captcha was not completed: {manual_wait}")
        prepare_result = await prepare_playwright_dashboard(page, platform_code)
        final_url = page.url
        try:
            page_text = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            page_text = ""
        await page.screenshot(path=str(screenshot_path), full_page=True)
        if browser is None:
            await context.close()
        return {"manual_wait": manual_wait, "prepare": prepare_result, "final_url": final_url, "page_text": page_text}


async def capture_screenshot_direct_cdp(
    url: str,
    screenshot_path: Path,
    *,
    platform_code: str,
    cdp_url: str,
    settle_seconds: int = 12,
    wait_login: bool = False,
    login_wait_timeout_seconds: int = 900,
    login_check_interval_seconds: int = 15,
) -> dict[str, Any]:
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    async with DirectCdpPage(cdp_url) as page:
        await page.open(url, download_dir=screenshot_path.parent)
        await asyncio.sleep(max(1, settle_seconds))
        manual_wait = await wait_direct_cdp_dashboard_ready(
            page,
            platform_code=platform_code,
            timeout_seconds=login_wait_timeout_seconds if wait_login else max(10, settle_seconds),
            wait_login=wait_login,
            login_check_interval_seconds=login_check_interval_seconds,
            require_metric=False,
        )
        if platform_code == "douyin":
            await prepare_douyin_ads_dashboard(page)
        elif platform_code == "tmall":
            await page.click_label("更多数据")
            await asyncio.sleep(3)
        metric_wait = await wait_direct_cdp_dashboard_ready(
            page,
            platform_code=platform_code,
            timeout_seconds=max(45, settle_seconds),
            wait_login=wait_login,
            login_check_interval_seconds=login_check_interval_seconds,
            require_metric=True,
        )
        page_text = str(metric_wait.get("page_text") or "")
        screenshot = await page.send(
            "Page.captureScreenshot",
            {"format": "png", "captureBeyondViewport": False},
            session=True,
        )
        screenshot_path.write_bytes(base64.b64decode(screenshot["data"]))
        final_url = await page.evaluate("location.href", timeout_seconds=3)
        return {
            "manual_wait": manual_wait,
            "metric_wait": {key: value for key, value in metric_wait.items() if key != "page_text"},
            "final_url": final_url,
            "page_text": page_text,
            "engine": "direct_cdp",
        }


async def prepare_douyin_ads_dashboard(page: DirectCdpPage) -> dict[str, Any]:
    clicks: list[str] = []
    for label in ("全域投放消耗", "全域投放消耗(元)", "账户整体消耗", "数据概览"):
        clicked = await page.click_label(label)
        if clicked:
            clicks.append(label)
            await asyncio.sleep(2)
            if label.startswith("全域投放消耗"):
                break
    return {"clicked": clicks}


async def wait_direct_cdp_dashboard_ready(
    page: DirectCdpPage,
    *,
    platform_code: str,
    timeout_seconds: int,
    wait_login: bool,
    login_check_interval_seconds: int,
    require_metric: bool,
) -> dict[str, Any]:
    started_at = datetime.now()
    deadline = time.monotonic() + max(1, timeout_seconds)
    checks = 0
    last_text = ""
    last_url = ""
    while time.monotonic() < deadline:
        checks += 1
        try:
            last_url = str(await page.evaluate("location.href", timeout_seconds=3) or "")
        except Exception:
            last_url = ""
        last_text = await collect_direct_cdp_text(page, platform_code=platform_code)
        if detect_manual_intervention_required(last_text, last_url):
            if not wait_login:
                raise RuntimeError(f"Manual login/captcha required in visible browser: {last_url}")
            print(
                f"Detected login/captcha page in direct CDP. Please finish it in the visible browser; rechecking in {login_check_interval_seconds}s.",
                flush=True,
            )
            await asyncio.sleep(max(1, login_check_interval_seconds))
            continue
        if not require_metric or direct_cdp_text_has_parseable_metric(last_text, platform_code):
            return {
                "status": "ready",
                "checks": checks,
                "waited_seconds": int((datetime.now() - started_at).total_seconds()),
                "url": last_url,
                "page_text": last_text,
            }
        await asyncio.sleep(2)
    return {
        "status": "metric_timeout" if require_metric else "ready_timeout",
        "checks": checks,
        "waited_seconds": int((datetime.now() - started_at).total_seconds()),
        "url": last_url,
        "page_text": last_text,
    }


async def collect_direct_cdp_text(page: DirectCdpPage, *, platform_code: str) -> str:
    expressions = [
        r"""
        (() => {
          const text = document.body && (document.body.innerText || document.body.textContent) || '';
          return text.replace(/\n{3,}/g, '\n\n').slice(0, 24000);
        })()
        """,
        r"""
        (() => {
          const chunks = [];
          const add = (node) => {
            if (!node) return;
            const text = node.innerText || node.textContent || '';
            if (text) chunks.push(text);
          };
          add(document.body);
          for (const frame of Array.from(document.querySelectorAll('iframe'))) {
            try { add(frame.contentDocument && frame.contentDocument.body); } catch (e) {}
          }
          return chunks.join('\n').replace(/\n{3,}/g, '\n\n').slice(0, 24000);
        })()
        """,
    ]
    text = ""
    for expression in expressions:
        try:
            value = await page.evaluate(expression, timeout_seconds=20)
        except Exception:
            continue
        candidate = str(value or "")
        if len(candidate) > len(text):
            text = candidate
        if direct_cdp_text_has_parseable_metric(candidate, platform_code):
            return candidate
    return text


def direct_cdp_text_has_parseable_metric(text: str, platform_code: str) -> bool:
    if not direct_cdp_text_has_metric_anchor(text, platform_code):
        return False
    metrics = {name: first_metric_value(text, labels) for name, labels in METRIC_LABELS.items()}
    if metrics["spend"] is None:
        return False
    return any(metrics[name] is not None for name in ("impressions", "clicks", "deal_amount", "order_count"))


def direct_cdp_text_has_metric_anchor(text: str, platform_code: str) -> bool:
    if not text:
        return False
    if platform_code == "tmall":
        anchors = ("花费", "展现量", "点击量", "总成交金额", "投入产出比")
    else:
        anchors = (
            "全域投放消耗",
            "账户整体消耗",
            "整体消耗",
            "净成交ROI",
            "净成交金额",
            "净成交订单数",
            "整体成交订单数",
            "整体成交金额",
            "整体支付ROI",
        )
    return any(anchor in text for anchor in anchors)


def captured_page_error(text: str) -> str:
    markers = (
        "ERR_TIMED_OUT",
        "ERR_CONNECTION",
        "ERR_NAME_NOT_RESOLVED",
        "ERR_TUNNEL_CONNECTION_FAILED",
        "无法访问此网站",
        "响应时间过长",
    )
    return next((marker for marker in markers if marker in text), "")


def run_ocr_command(command_template: str, image_path: Path) -> str:
    if "{image}" in command_template:
        command = command_template.format(image=str(image_path))
        completed = subprocess.run(command, shell=True, text=True, capture_output=True, timeout=120)
    else:
        parts = command_template.split()
        completed = subprocess.run([*parts, str(image_path)], text=True, capture_output=True, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError(f"OCR command failed: {completed.stderr[-2000:]}")
    return completed.stdout


def write_ad_row(row: dict[str, Any], *, dry_run: bool, ensure_missing_fields: bool) -> dict[str, Any]:
    _load_dotenv()
    settings = load_settings()
    if not settings.shopops_ad_table_id:
        raise RuntimeError("Missing SHOPOPS_AD_TABLE_ID")
    if dry_run:
        return {"status": "dry_run", "row": row}
    client = FeishuDailyClient()
    if ensure_missing_fields:
        created = client.ensure_missing_fields_for_rows(settings.shopops_ad_table_id, [row], AD_FIELD_TYPES)
    else:
        created = []
        missing = missing_row_fields(client.field_names(settings.shopops_ad_table_id), [row], [F_UNIQUE_KEY, F_PLATFORM, F_DATE])
        if missing:
            raise RuntimeError(f"Target ad table {settings.shopops_ad_table_id} is missing fields: {missing}")
    write_result = client.upsert_rows(
        table_id=settings.shopops_ad_table_id,
        rows=[row],
        required_fields=[F_UNIQUE_KEY, F_PLATFORM, F_DATE],
        fallback_match_fields=(F_PLATFORM, F_DATE),
        allow_partial_fields=False,
    )
    readback = client.readback_by_unique_key(settings.shopops_ad_table_id, {row[F_UNIQUE_KEY]})
    return {
        "status": "success" if row[F_UNIQUE_KEY] in readback else "readback_mismatch",
        "created_missing_fields": created,
        "write": write_result,
        "readback_count": len(readback),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture one ad dashboard snapshot by screenshot/OCR and upsert it into Feishu.")
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    parser.add_argument("--date", default=date.today().isoformat(), help="Stat date, YYYY-MM-DD.")
    parser.add_argument("--url", default="", help="Dashboard URL. Defaults to the configured platform page.")
    parser.add_argument("--screenshot", default="", help="Existing or output screenshot path.")
    parser.add_argument("--ocr-text", default="", help="Already recognized OCR text.")
    parser.add_argument("--ocr-text-file", default="", help="File containing recognized OCR text.")
    parser.add_argument("--ocr-command", default=os.getenv("SHOPOPS_OCR_COMMAND", ""), help="Local OCR command; use {image} as placeholder.")
    parser.add_argument("--no-dom-text-fallback", action="store_true", help="Require OCR text/command instead of parsing visible page text captured through CDP.")
    parser.add_argument("--cdp-url", default="")
    parser.add_argument("--playwright-cdp", action="store_true", help="Use Playwright for CDP capture instead of the native CDP client.")
    parser.add_argument("--page-settle-seconds", type=int, default=12)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--allow-new-browser", action="store_true", help="Open a new visible Chrome profile when CDP is unavailable. Prefer an existing logged-in Chrome.")
    parser.add_argument("--wait-login", action="store_true", help="Pause and recheck when the page asks for manual login, captcha, SMS, or face verification.")
    parser.add_argument("--auto-login", action="store_true", help="Fill username/password from local environment variables, then wait for any manual verification.")
    parser.add_argument("--login-wait-timeout-seconds", type=int, default=900)
    parser.add_argument("--login-check-interval-seconds", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ensure-missing-fields", action="store_true")
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()

    screenshot = Path(args.screenshot) if args.screenshot else ROOT / "docs" / "live-evidence" / "data-robot" / f"{args.platform}-ads-ocr-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    ocr_text = args.ocr_text
    capture_summary = {"status": "not_needed"}

    evidence = Path(args.evidence) if args.evidence else ROOT / "docs" / "live-evidence" / "data-robot" / f"{args.platform}-ads-ocr-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    try:
        if args.ocr_text_file:
            ocr_text = Path(args.ocr_text_file).read_text(encoding="utf-8")
        if not ocr_text:
            if not screenshot.exists():
                if args.cdp_url and not args.playwright_cdp:
                    capture_summary = asyncio.run(
                        capture_screenshot_direct_cdp(
                            args.url or default_dashboard_url(args.platform, args.date),
                            screenshot,
                            platform_code=args.platform,
                            cdp_url=args.cdp_url,
                            settle_seconds=args.page_settle_seconds,
                            wait_login=args.wait_login,
                            login_wait_timeout_seconds=args.login_wait_timeout_seconds,
                            login_check_interval_seconds=args.login_check_interval_seconds,
                        )
                    )
                else:
                    capture_summary = asyncio.run(
                        capture_screenshot(
                            args.url or default_dashboard_url(args.platform, args.date),
                            screenshot,
                            platform_code=args.platform,
                            cdp_url=args.cdp_url,
                            headless=args.headless,
                            allow_new_browser=args.allow_new_browser,
                            wait_login=args.wait_login,
                            auto_login=args.auto_login,
                            login_wait_timeout_seconds=args.login_wait_timeout_seconds,
                            login_check_interval_seconds=args.login_check_interval_seconds,
                        )
                    )
            if not args.ocr_command:
                if args.no_dom_text_fallback:
                    raise RuntimeError("Missing OCR text. Provide --ocr-text, --ocr-text-file, or --ocr-command/SHOPOPS_OCR_COMMAND.")
                ocr_text = str(capture_summary.get("page_text") or "")
                if not ocr_text:
                    raise RuntimeError("Missing OCR text and captured page text was empty.")
            else:
                ocr_text = run_ocr_command(args.ocr_command, screenshot)
        page_error = captured_page_error(ocr_text)
        if page_error:
            raise RuntimeError(f"Captured page is a browser/network error page: {page_error}")
        row = parse_ad_snapshot_text(args.platform, ocr_text, args.date, screenshot_path=str(screenshot))
        write_result = write_ad_row(row, dry_run=args.dry_run, ensure_missing_fields=args.ensure_missing_fields)
        summary = {
            "status": write_result["status"],
            "platform": args.platform,
            "date": args.date,
            "screenshot": str(screenshot),
            "capture": capture_summary,
            "row": row,
            "write": write_result,
        }
    except Exception as exc:
        visible_browser = {"status": "not_needed"}
        error_text = str(exc)
        if (
            "Manual login/captcha" in error_text
            or "ERR_TIMED_OUT" in error_text
            or "Missing --cdp-url" in error_text
            or "Missing OCR text" in error_text
        ):
            visible_browser = open_visible_chrome_page(
                args.platform,
                args.url or default_dashboard_url(args.platform, args.date),
                args.cdp_url,
            )
        summary = {
            "status": "failed",
            "platform": args.platform,
            "date": args.date,
            "screenshot": str(screenshot),
            "capture": capture_summary,
            "visible_browser": visible_browser,
            "error": {
                "type": type(exc).__name__,
                "message": error_text,
            },
            "text_tail": ocr_text[-4000:],
        }
    write_import_evidence(evidence, summary)
    print(json.dumps({**summary, "evidence": str(evidence)}, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if summary["status"] in {"success", "dry_run"} else 4


if __name__ == "__main__":
    raise SystemExit(main())
