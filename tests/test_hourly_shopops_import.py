from __future__ import annotations

from types import SimpleNamespace

import data_robot.hourly_shopops_import as orchestrator
from data_robot.hourly_shopops_import import build_ads_command, ocr_command_available, run_ads_once


class Args:
    ad_cdp_url = "http://127.0.0.1:9222"
    douyin_ad_cdp_url = ""
    tmall_ad_cdp_url = ""
    cdp_url = ""
    ocr_command = "tesseract {image} stdout -l chi_sim"
    allow_new_browser = False
    headless = False
    dry_run_ads = True
    ensure_missing_ad_fields = False
    ads_timeout_seconds = 300
    ad_max_attempts = 2
    ad_retry_interval_seconds = 0
    no_dom_text_fallback = False
    playwright_cdp_ads = False
    wait_login = False
    auto_login = False
    login_wait_timeout_seconds = 900
    login_check_interval_seconds = 15
    ad_page_settle_seconds = 90
    browser_profile_root = ""


def test_build_ads_command_uses_existing_cdp_and_dry_run():
    command = build_ads_command(Args, "douyin", "2026-06-15", PathLike("D:\\evidence\\ads.json"))

    assert "data_robot.ocr_ads_snapshot" in command
    assert command[command.index("--platform") + 1] == "douyin"
    assert command[command.index("--cdp-url") + 1] == "http://127.0.0.1:9222"
    assert "tesseract {image} stdout -l chi_sim" in command
    assert "--dry-run" in command
    assert "--allow-new-browser" not in command
    assert command[command.index("--page-settle-seconds") + 1] == "90"


def test_build_ads_command_defaults_to_platform_cdp_port():
    class DefaultArgs(Args):
        ad_cdp_url = ""

    douyin = build_ads_command(DefaultArgs, "douyin", "2026-06-15", PathLike("D:\\evidence\\douyin.json"))
    tmall = build_ads_command(DefaultArgs, "tmall", "2026-06-15", PathLike("D:\\evidence\\tmall.json"))

    assert douyin[douyin.index("--cdp-url") + 1] == "http://localhost:9224"
    assert tmall[tmall.index("--cdp-url") + 1] == "http://localhost:9225"


def test_build_ads_command_can_wait_for_manual_login():
    class WaitArgs(Args):
        wait_login = True
        playwright_cdp_ads = True
        login_wait_timeout_seconds = 1200
        login_check_interval_seconds = 20

    command = build_ads_command(WaitArgs, "tmall", "2026-06-15", PathLike("D:\\evidence\\tmall.json"))

    assert "--wait-login" in command
    assert "--playwright-cdp" in command
    assert command[command.index("--login-wait-timeout-seconds") + 1] == "1200"
    assert command[command.index("--login-check-interval-seconds") + 1] == "20"


def test_build_ads_command_can_auto_fill_login():
    class LoginArgs(Args):
        wait_login = True
        auto_login = True

    command = build_ads_command(LoginArgs, "tmall", "2026-06-15", PathLike("D:\\evidence\\tmall.json"))

    assert "--wait-login" in command
    assert "--auto-login" in command


def test_ocr_command_available_checks_executable():
    assert ocr_command_available("python {image}") is True
    assert ocr_command_available("definitely-not-a-real-ocr-binary {image}") is False


def test_run_ads_once_retries_failed_platform_and_keeps_success_evidence(tmp_path, monkeypatch):
    calls = []

    def fake_run_command(command, *, timeout):
        calls.append(command)
        if len(calls) == 2:
            (tmp_path / "hourly-tmall-ads-ocr-20260618-030000.json").write_text(
                '{"status":"success"}',
                encoding="utf-8",
            )
            return {"returncode": 0, "timed_out": False}
        return {"returncode": 124, "timed_out": True}

    opened = []
    monkeypatch.setattr(orchestrator, "run_command", fake_run_command)
    monkeypatch.setattr(orchestrator, "open_visible_chrome_page", lambda *args, **kwargs: opened.append((args, kwargs)) or {})

    args = SimpleNamespace(
        **{
            name: getattr(Args, name)
            for name in dir(Args)
            if not name.startswith("__") and not callable(getattr(Args, name))
        }
    )
    args.ad_platform = ["tmall"]
    args.evidence_root = str(tmp_path)
    args.ad_max_attempts = 2
    args.ad_retry_interval_seconds = 0
    args.allow_new_browser = True

    result = run_ads_once(args, "2026-06-18", "20260618-030000")

    assert len(calls) == 2
    assert len(opened) == 1
    assert result[0]["result"]["returncode"] == 0
    assert [attempt["attempt"] for attempt in result[0]["attempts"]] == [1, 2]
    assert result[0]["attempts"][1]["evidence_exists"] is True


class PathLike:
    def __init__(self, value: str) -> None:
        self.value = value

    def __fspath__(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value
