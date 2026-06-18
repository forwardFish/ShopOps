from __future__ import annotations

import time
import json
import random
from datetime import datetime
from types import SimpleNamespace

import data_robot.hourly_shopops_import as orchestrator
from data_robot.hourly_shopops_import import (
    build_ads_command,
    check_environment,
    ad_platforms_to_collect,
    first_run_delay_seconds,
    latest_successful_run_time,
    ocr_command_available,
    run_ads_once,
)


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


def test_environment_check_does_not_require_jushuitan_for_tmall_only_orders(monkeypatch):
    settings = SimpleNamespace(
        feishu_app_id="app",
        feishu_app_secret="secret",
        shopops_data_center_app_token="token",
        shopops_ad_table_id="ads",
        shopops_order_table_id="orders",
        jushuitan_partner_id="",
        jushuitan_partner_key="",
        jushuitan_token="",
        jushuitan_douyin_shop_id="",
    )
    args = SimpleNamespace(
        skip_ads=False,
        skip_orders=False,
        skip_hourly_interval_summary=True,
        hourly_interval_table_id="",
        order_platform=["天猫"],
    )

    monkeypatch.setattr(orchestrator, "_load_dotenv", lambda: None)
    monkeypatch.setattr(orchestrator, "load_settings", lambda: settings)

    result = check_environment(args)

    assert result["ok"] is True
    assert result["missing"] == []


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
    args.required_ad_platform = ["tmall"]
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


def test_ad_platform_collection_defaults_to_required_douyin_and_tmall_ads():
    args = SimpleNamespace(ad_platform=None, required_ad_platform=None)

    assert ad_platforms_to_collect(args) == ["douyin", "tmall"]


def test_ad_platform_collection_keeps_required_platforms_when_partially_overridden():
    args = SimpleNamespace(ad_platform=["tmall"], required_ad_platform=None)

    assert ad_platforms_to_collect(args) == ["douyin", "tmall"]


def test_main_success_cycles_counts_only_successful_runs(tmp_path, monkeypatch):
    statuses = iter(["ads_failed", "success", "success"])
    runs = []
    opened = []
    sleeps = []

    monkeypatch.setattr(
        orchestrator,
        "preflight",
        lambda args: {
            "ocr_command_available": True,
            "dom_text_fallback_enabled": True,
            "cdp": {"douyin": {"ok": True}, "tmall": {"ok": True}},
            "environment": {"ok": True},
        },
    )
    monkeypatch.setattr(orchestrator, "write_preflight_evidence", lambda args, payload: tmp_path / "preflight.json")
    monkeypatch.setattr(orchestrator, "next_delay_seconds", lambda *args, **kwargs: 0)
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(orchestrator, "open_visible_ad_pages", lambda *args, **kwargs: opened.append(kwargs) or [])

    def fake_run_cycle(args):
        status = next(statuses)
        runs.append(status)
        return {"status": status}

    monkeypatch.setattr(orchestrator, "run_cycle", fake_run_cycle)
    monkeypatch.setattr(
        orchestrator.sys,
        "argv",
        [
            "hourly_shopops_import",
            "--success-cycles",
            "2",
            "--start-hour",
            "0",
            "--end-hour",
            "24",
            "--evidence-root",
            str(tmp_path),
        ],
    )

    assert orchestrator.main() == 0
    assert runs == ["ads_failed", "success", "success"]
    assert len(opened) == 1
    assert sleeps == [0, 0]


def test_preflight_only_does_not_open_browser_when_only_environment_is_missing(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(
        orchestrator,
        "preflight",
        lambda args: {
            "ocr_command_available": False,
            "dom_text_fallback_enabled": True,
            "cdp": {"tmall": {"ok": True}},
            "environment": {"ok": False, "missing": ["JUSHUITAN_TOKEN"]},
        },
    )
    monkeypatch.setattr(orchestrator, "write_preflight_evidence", lambda args, payload: tmp_path / "preflight.json")
    monkeypatch.setattr(orchestrator, "open_visible_ad_pages", lambda *args, **kwargs: opened.append(kwargs) or [])
    monkeypatch.setattr(
        orchestrator.sys,
        "argv",
        [
            "hourly_shopops_import",
            "--preflight-only",
            "--evidence-root",
            str(tmp_path),
        ],
    )

    assert orchestrator.main() == 4
    assert opened == []


def test_wait_preflight_retries_until_environment_is_ready(tmp_path, monkeypatch):
    preflight_results = iter(
        [
            {
                "ocr_command_available": False,
                "dom_text_fallback_enabled": True,
                "cdp": {"tmall": {"ok": True}},
                "environment": {"ok": False, "missing": ["JUSHUITAN_TOKEN"]},
            },
            {
                "ocr_command_available": False,
                "dom_text_fallback_enabled": True,
                "cdp": {"tmall": {"ok": True}},
                "environment": {"ok": True, "missing": []},
            },
        ]
    )
    sleeps = []
    runs = []
    monkeypatch.setattr(orchestrator, "preflight", lambda args: next(preflight_results))
    monkeypatch.setattr(orchestrator, "write_preflight_evidence", lambda args, payload: tmp_path / f"preflight-{len(sleeps)}.json")
    monkeypatch.setattr(time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(orchestrator, "run_cycle", lambda args: runs.append(True) or {"status": "success"})
    monkeypatch.setattr(
        orchestrator.sys,
        "argv",
        [
            "hourly_shopops_import",
            "--once",
            "--wait-preflight",
            "--preflight-retry-seconds",
            "60",
            "--start-hour",
            "0",
            "--end-hour",
            "24",
            "--evidence-root",
            str(tmp_path),
        ],
    )

    assert orchestrator.main() == 0
    assert sleeps == [60]
    assert runs == [True]


def test_run_cycle_skips_ads_and_interval_summary_when_orders_fail(monkeypatch):
    ads_called = []
    interval_calls = []

    args = SimpleNamespace(
        skip_orders=False,
        skip_ads=False,
        skip_hourly_interval_summary=False,
        import_date="2026-06-18",
        evidence_root=".",
    )

    monkeypatch.setattr(orchestrator, "run_orders_once", lambda _args: {"status": "archive_incomplete"})
    monkeypatch.setattr(orchestrator, "run_ads_once", lambda *_args: ads_called.append(True) or [])
    monkeypatch.setattr(orchestrator, "summarize_hourly_interval", lambda *_args, **_kwargs: interval_calls.append(True) or {"status": "success"})
    monkeypatch.setattr(orchestrator, "write_json", lambda *_args, **_kwargs: None)

    result = orchestrator.run_cycle(args)

    assert result["status"] == "order_failed"
    assert result["ads"] == []
    assert result["hourly_interval_summary"] is None
    assert ads_called == []
    assert interval_calls == []


def test_run_cycle_writes_interval_summary_when_required_ads_succeed(tmp_path, monkeypatch):
    interval_calls = []
    douyin_evidence = tmp_path / "hourly-douyin-ads-ocr-20260618-140000.json"
    tmall_evidence = tmp_path / "hourly-tmall-ads-ocr-20260618-140000.json"
    douyin_evidence.write_text('{"status":"success"}', encoding="utf-8")
    tmall_evidence.write_text('{"status":"success"}', encoding="utf-8")

    args = SimpleNamespace(
        skip_orders=False,
        skip_ads=False,
        skip_hourly_interval_summary=False,
        import_date="2026-06-18",
        evidence_root=str(tmp_path),
        required_ad_platform=None,
        hourly_interval_table_id="interval_table",
        hourly_interval_table_name="投流小时段归因汇总",
        dry_run_ads=False,
        dry_run_hourly_interval_summary=False,
        interval_minutes=60,
        start_hour=8,
        order_platform=None,
    )

    monkeypatch.setattr(orchestrator, "run_orders_once", lambda _args: {"status": "success"})
    monkeypatch.setattr(
        orchestrator,
        "run_ads_once",
        lambda *_args: [
            {"platform": "douyin", "result": {"returncode": 0}, "evidence": str(douyin_evidence)},
            {"platform": "tmall", "result": {"returncode": 0}, "evidence": str(tmall_evidence)},
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "summarize_hourly_interval",
        lambda *_args, **kwargs: interval_calls.append(kwargs) or {"status": "success"},
    )
    monkeypatch.setattr(orchestrator, "write_json", lambda *_args, **_kwargs: None)

    result = orchestrator.run_cycle(args)

    assert result["status"] == "success"
    assert result["missing_required_ad_platforms"] == []
    assert result["hourly_interval_summary"] == {"status": "success"}
    assert interval_calls[0]["order_platform_codes"] == ["tmall", "douyin"]


def test_latest_successful_run_time_reads_interval_evidence(tmp_path):
    evidence = tmp_path / "hourly-shopops-import-20260618-130000.json"
    evidence.write_text(
        json.dumps(
            {
                "status": "success",
                "run_token": "20260618-130000",
                "hourly_interval_summary": {
                    "rows": [
                        {"平台": "天猫", "窗口结束": "2026-06-18 13:07:37"},
                        {"平台": "总计", "窗口结束": "2026-06-18 13:07:37"},
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert latest_successful_run_time(tmp_path) == datetime(2026, 6, 18, 13, 7, 37)


def test_first_run_delay_respects_recent_success_after_restart(tmp_path):
    evidence = tmp_path / "hourly-shopops-import-20260618-130000.json"
    evidence.write_text(
        json.dumps(
            {
                "status": "success",
                "run_token": "20260618-130000",
                "hourly_interval_summary": {"rows": [{"窗口结束": "2026-06-18 13:07:37"}]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        once=False,
        cycles=0,
        success_cycles=0,
        start_hour=8,
        end_hour=23,
        interval_minutes=60,
        jitter_minutes=0,
        evidence_root=str(tmp_path),
    )

    delay = first_run_delay_seconds(args, datetime(2026, 6, 18, 13, 38, 0), rng=random.Random(1))

    assert delay == 29 * 60 + 37


class PathLike:
    def __init__(self, value: str) -> None:
        self.value = value

    def __fspath__(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value
