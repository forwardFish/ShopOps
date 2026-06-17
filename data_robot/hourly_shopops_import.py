from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from data_robot.common import DEFAULT_EVIDENCE_ROOT, evidence_token, write_json
from data_robot.daily_download import cdp_base_url
from data_robot.full_flow import run_command
from data_robot.hourly_ad_interval_summary import (
    DEFAULT_INTERVAL_TABLE_NAME,
    configured_interval_table_id,
    interval_table_name,
    summarize_hourly_interval,
)
from data_robot.hourly_order_import import add_schedule_args, next_delay_seconds, next_window_start, run_once as run_orders_once
from data_robot.ocr_ads_snapshot import default_dashboard_url, open_visible_chrome_page
from shopops.config import _load_dotenv, load_settings


ROOT = Path(__file__).resolve().parents[1]


def build_ads_command(args: argparse.Namespace, platform: str, stat_date: str, evidence: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "data_robot.ocr_ads_snapshot",
        "--platform",
        platform,
        "--date",
        stat_date,
        "--evidence",
        str(evidence),
    ]
    cdp_url = platform_ad_cdp_url(args, platform)
    if cdp_url:
        command.extend(["--cdp-url", cdp_url])
    if args.ocr_command:
        command.extend(["--ocr-command", args.ocr_command])
    if args.no_dom_text_fallback:
        command.append("--no-dom-text-fallback")
    if args.ad_page_settle_seconds:
        command.extend(["--page-settle-seconds", str(args.ad_page_settle_seconds)])
    if args.playwright_cdp_ads:
        command.append("--playwright-cdp")
    if args.allow_new_browser:
        command.append("--allow-new-browser")
    browser_profile_root = getattr(args, "browser_profile_root", "")
    if browser_profile_root:
        command.extend(["--browser-profile-root", browser_profile_root])
    if args.headless:
        command.append("--headless")
    if args.dry_run_ads:
        command.append("--dry-run")
    if args.ensure_missing_ad_fields:
        command.append("--ensure-missing-fields")
    if args.wait_login:
        command.append("--wait-login")
        command.extend(["--login-wait-timeout-seconds", str(args.login_wait_timeout_seconds)])
        command.extend(["--login-check-interval-seconds", str(args.login_check_interval_seconds)])
    if args.auto_login:
        command.append("--auto-login")
    return command


def platform_ad_cdp_url(args: argparse.Namespace, platform: str) -> str:
    explicit = {
        "douyin": args.douyin_ad_cdp_url,
        "tmall": args.tmall_ad_cdp_url,
    }.get(platform, "")
    if explicit:
        return explicit
    if args.ad_cdp_url:
        return args.ad_cdp_url
    if args.cdp_url:
        return args.cdp_url
    if platform == "douyin":
        return cdp_base_url("douyin")
    if platform == "tmall":
        return cdp_base_url("tmall")
    return ""


def run_ads_once(args: argparse.Namespace, stat_date: str, run_token: str) -> list[dict[str, Any]]:
    platforms = args.ad_platform or ["douyin", "tmall"]
    results: list[dict[str, Any]] = []
    evidence_root = Path(args.evidence_root)
    for platform in platforms:
        evidence = evidence_root / f"hourly-{platform}-ads-ocr-{run_token}.json"
        command = build_ads_command(args, platform, stat_date, evidence)
        attempts: list[dict[str, Any]] = []
        max_attempts = max(1, int(getattr(args, "ad_max_attempts", 1) or 1))
        result: dict[str, Any] = {}
        for attempt in range(1, max_attempts + 1):
            result = run_command(command, timeout=args.ads_timeout_seconds)
            attempts.append(
                {
                    "attempt": attempt,
                    "result": result,
                    "evidence_exists": evidence.exists(),
                }
            )
            if result.get("returncode") == 0 and evidence.exists():
                break
            if attempt >= max_attempts:
                break
            if getattr(args, "allow_new_browser", False):
                open_visible_chrome_page(
                    platform,
                    default_dashboard_url(platform, stat_date),
                    platform_ad_cdp_url(args, platform),
                    profile_root=args.browser_profile_root,
                )
            retry_interval = max(0, int(getattr(args, "ad_retry_interval_seconds", 0) or 0))
            if retry_interval:
                time.sleep(retry_interval)
        results.append({"platform": platform, "result": result, "evidence": str(evidence), "attempts": attempts})
    return results


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now()
    stat_date = args.import_date or date.today().isoformat()
    run_token = now.strftime("%Y%m%d-%H%M%S")
    order_summary = None if args.skip_orders else run_orders_once(args)
    ads_results = [] if args.skip_ads else run_ads_once(args, stat_date, run_token)
    interval_summary = None
    status = "success"
    if order_summary and order_summary.get("status") != "success":
        status = "order_failed"
    ad_failures = [
        item
        for item in ads_results
        if (item.get("result") or {}).get("returncode") != 0
    ]
    if ad_failures:
        status = "ads_failed" if status == "success" else "partial_failed"
    if not args.skip_hourly_interval_summary and not args.skip_ads and not ad_failures:
        try:
            interval_summary = summarize_hourly_interval(
                ads_results,
                stat_date=stat_date,
                run_token=run_token,
                table_id=args.hourly_interval_table_id or configured_interval_table_id(),
                table_name=args.hourly_interval_table_name or interval_table_name(),
                dry_run=args.dry_run_ads or args.dry_run_hourly_interval_summary,
                default_window_minutes=args.interval_minutes,
            )
            if interval_summary.get("status") not in {"success", "skipped"}:
                status = "interval_summary_failed" if status == "success" else "partial_failed"
        except Exception as exc:
            interval_summary = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            status = "interval_summary_failed" if status == "success" else "partial_failed"
    summary = {
        "status": status,
        "stat_date": stat_date,
        "run_token": run_token,
        "orders": order_summary,
        "ads": ads_results,
        "hourly_interval_summary": interval_summary,
        "strategy": {
            "orders": "Tmall Excel download/import plus Douyin Jushuitan order fallback",
            "ads": "one OCR snapshot row per requested platform",
            "hourly_interval_summary": "stores per-platform and total interval rows using ad cumulative deltas and order rows in the collection window",
            "risk_control": "uses visible existing Chrome/CDP by default, randomized schedule, no stealth or fingerprint bypass",
        },
    }
    evidence = Path(args.evidence_root) / f"hourly-shopops-import-{evidence_token(run_token)}.json"
    write_json(evidence, summary)
    print(json.dumps({**summary, "evidence": str(evidence)}, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return summary


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    ad_platforms = args.ad_platform or ["douyin", "tmall"]
    cdp_checks = {
        platform: check_cdp(platform_ad_cdp_url(args, platform))
        for platform in ad_platforms
        if not args.skip_ads
    }
    env_checks = check_environment(args)
    return {
        "ocr_command": args.ocr_command,
        "ocr_command_available": ocr_command_available(args.ocr_command) if args.ocr_command else False,
        "dom_text_fallback_enabled": not args.no_dom_text_fallback,
        "cdp": cdp_checks,
        "environment": env_checks,
        "orders_enabled": not args.skip_orders,
        "ads_enabled": not args.skip_ads,
    }


def ocr_command_available(command: str) -> bool:
    executable = command.format(image="").strip().split()[0] if "{image}" in command else command.strip().split()[0]
    return shutil.which(executable) is not None


def check_cdp(cdp_url: str) -> dict[str, Any]:
    import urllib.request

    if not cdp_url:
        return {"ok": False, "url": "", "error": "missing_cdp_url"}
    url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return {"ok": response.status == 200, "url": cdp_url, "status": response.status}
    except Exception as exc:
        return {"ok": False, "url": cdp_url, "error": f"{type(exc).__name__}: {exc}"}


def check_environment(args: argparse.Namespace) -> dict[str, Any]:
    _load_dotenv()
    settings = load_settings()
    required: dict[str, bool] = {}
    if not args.skip_ads:
        required.update(
            {
                "FEISHU_APP_ID": bool(settings.feishu_app_id),
                "FEISHU_APP_SECRET": bool(settings.feishu_app_secret),
                "FEISHU_APP_TOKEN": bool(settings.shopops_data_center_app_token),
                "SHOPOPS_AD_TABLE_ID": bool(settings.shopops_ad_table_id),
            }
        )
        if not args.skip_hourly_interval_summary:
            required["SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID_OR_CREATABLE"] = bool(
                args.hourly_interval_table_id
                or configured_interval_table_id()
                or (settings.shopops_data_center_app_token and settings.feishu_app_id and settings.feishu_app_secret)
            )
    if not args.skip_orders:
        required.update(
            {
                "SHOPOPS_ORDER_TABLE_ID": bool(settings.shopops_order_table_id),
                "JUSHUITAN_PARTNER_ID": bool(settings.jushuitan_partner_id),
                "JUSHUITAN_PARTNER_KEY": bool(settings.jushuitan_partner_key),
                "JUSHUITAN_TOKEN": bool(settings.jushuitan_token),
                "JUSHUITAN_SHOP_ID_DOUYIN": bool(settings.jushuitan_douyin_shop_id),
            }
        )
    missing = sorted(name for name, ok in required.items() if not ok)
    return {
        "ok": not missing,
        "required_present": required,
        "missing": missing,
    }


def write_preflight_evidence(args: argparse.Namespace, payload: dict[str, Any]) -> Path:
    evidence = Path(args.evidence_root) / f"hourly-shopops-preflight-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    write_json(evidence, payload)
    return evidence


def open_visible_ad_pages(args: argparse.Namespace, *, reason: str) -> list[dict[str, Any]]:
    opened: list[dict[str, Any]] = []
    if args.skip_ads:
        return opened
    stat_date = args.import_date or date.today().isoformat()
    for platform in args.ad_platform or ["douyin", "tmall"]:
        opened.append(
            open_visible_chrome_page(
                platform,
                default_dashboard_url(platform, stat_date),
                platform_ad_cdp_url(args, platform),
                profile_root=args.browser_profile_root,
            )
            | {"reason": reason}
        )
    return opened


def main() -> int:
    parser = argparse.ArgumentParser(description="Hourly ShopOps order plus OCR ad import orchestrator.")
    add_schedule_args(parser)
    parser.add_argument("--ad-platform", action="append", choices=("douyin", "tmall"), help="Ad OCR platform; defaults to both.")
    parser.add_argument("--ad-cdp-url", default="", help="CDP URL for ad screenshot capture. Defaults to --cdp-url.")
    parser.add_argument("--douyin-ad-cdp-url", default="", help="Douyin-specific ad screenshot CDP URL.")
    parser.add_argument("--tmall-ad-cdp-url", default="", help="Tmall-specific ad screenshot CDP URL.")
    parser.add_argument("--ocr-command", default="", help="Local OCR command; use {image} as placeholder.")
    parser.add_argument("--no-dom-text-fallback", action="store_true", help="Require OCR for ad screenshots instead of allowing visible page text fallback.")
    parser.add_argument("--playwright-cdp-ads", action="store_true", help="Use Playwright over the existing CDP browser for ad screenshots so login/captcha waiting can run.")
    parser.add_argument("--ads-timeout-seconds", type=int, default=300)
    parser.add_argument("--ad-max-attempts", type=int, default=2, help="Retry each ad platform this many times before failing the cycle.")
    parser.add_argument("--ad-retry-interval-seconds", type=int, default=20, help="Seconds to wait between ad platform retries.")
    parser.add_argument("--ad-page-settle-seconds", type=int, default=90, help="Seconds to let ad dashboard pages settle before reading metrics.")
    parser.add_argument("--dry-run-ads", action="store_true")
    parser.add_argument("--dry-run-hourly-interval-summary", action="store_true")
    parser.add_argument("--skip-hourly-interval-summary", action="store_true")
    parser.add_argument("--hourly-interval-table-id", default="", help="Feishu table for hourly ad/order interval rows. Defaults to SHOPOPS_HOURLY_AD_INTERVAL_TABLE_ID or creates by name.")
    parser.add_argument("--hourly-interval-table-name", default=DEFAULT_INTERVAL_TABLE_NAME)
    parser.add_argument("--ensure-missing-ad-fields", action="store_true")
    parser.add_argument("--allow-new-browser", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--wait-login", action="store_true", help="Let ad screenshot jobs pause for manual login/captcha and continue after it is resolved.")
    parser.add_argument("--auto-login", action="store_true", help="Let ad screenshot jobs fill locally configured username/password before manual verification.")
    parser.add_argument("--login-wait-timeout-seconds", type=int, default=900)
    parser.add_argument("--login-check-interval-seconds", type=int, default=15)
    parser.add_argument("--skip-orders", action="store_true")
    parser.add_argument("--skip-ads", action="store_true")
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Run this many real scheduled cycles, then exit. Use 3 for a roughly one-hour half-hourly acceptance test.",
    )
    parser.add_argument("--preflight-only", action="store_true", help="Check OCR/CDP prerequisites and exit.")
    parser.add_argument("--ignore-preflight", action="store_true", help="Run even when OCR/CDP preflight is not ready.")
    args = parser.parse_args()
    preflight_summary = preflight(args)
    visible_browser = []
    if args.preflight_only:
        text_source_ready = (
            args.skip_ads
            or preflight_summary["ocr_command_available"]
            or preflight_summary["dom_text_fallback_enabled"]
        )
        ready = (
            (args.skip_ads or (text_source_ready and all(item["ok"] for item in preflight_summary["cdp"].values())))
            and preflight_summary["environment"]["ok"]
        )
        if not ready and not args.skip_ads:
            visible_browser = open_visible_ad_pages(args, reason="preflight_only_not_ready")
        preflight_evidence = write_preflight_evidence(args, preflight_summary | {"visible_browser": visible_browser})
        print(
            json.dumps(
                {"preflight": preflight_summary, "visible_browser": visible_browser, "evidence": str(preflight_evidence)},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        return 0 if ready else 4
    preflight_evidence = write_preflight_evidence(args, preflight_summary)
    print(json.dumps({"preflight": preflight_summary, "evidence": str(preflight_evidence)}, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    if not args.ignore_preflight and not args.skip_ads:
        text_source_ready = preflight_summary["ocr_command_available"] or preflight_summary["dom_text_fallback_enabled"]
        ads_ready = text_source_ready and all(item["ok"] for item in preflight_summary["cdp"].values())
        if not ads_ready:
            opened = open_visible_ad_pages(args, reason="ads_preflight_not_ready")
            print(json.dumps({"visible_browser": opened}, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
            return 4
    if not args.ignore_preflight and not preflight_summary["environment"]["ok"]:
        return 4

    completed_cycles = 0
    while True:
        now = datetime.now()
        if next_window_start(now, start_hour=args.start_hour, end_hour=args.end_hour) > now:
            delay = next_delay_seconds(
                now,
                start_hour=args.start_hour,
                end_hour=args.end_hour,
                interval_minutes=args.interval_minutes,
                jitter_minutes=args.jitter_minutes,
            )
            print(f"Outside collection window; sleeping {delay} seconds.", flush=True)
            time.sleep(delay)
        result = run_cycle(args)
        if result["status"] in {"ads_failed", "partial_failed"}:
            opened = open_visible_ad_pages(args, reason=result["status"])
            print(json.dumps({"visible_browser": opened}, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
        completed_cycles += 1
        if args.once or (args.cycles and completed_cycles >= args.cycles):
            return 0 if result["status"] == "success" else 4
        delay = next_delay_seconds(
            datetime.now(),
            start_hour=args.start_hour,
            end_hour=args.end_hour,
            interval_minutes=args.interval_minutes,
            jitter_minutes=args.jitter_minutes,
        )
        print(f"Next ShopOps scheduled import starts in {delay} seconds.", flush=True)
        time.sleep(delay)


if __name__ == "__main__":
    raise SystemExit(main())
