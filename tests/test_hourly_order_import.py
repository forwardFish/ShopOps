from __future__ import annotations

import argparse
import random
from datetime import datetime
from types import SimpleNamespace

import data_robot.hourly_order_import as hourly_order_import
from data_robot.hourly_order_import import add_schedule_args, build_download_command, build_import_command, next_delay_seconds


class Args:
    archive_root = "D:\\archive"
    evidence_root = "D:\\evidence"
    watch_dir = "C:\\Users\\linyanhui\\Downloads"
    timeout_seconds = 900
    idle_seconds = 30
    max_downloads = 3
    min_task_interval_seconds = 2400
    retry_interval_seconds = 600
    max_task_attempts = 3
    browser_profile_suffix = "cdp"
    browser_profile_root = "D:\\tmp\\profiles"
    no_cdp = False
    direct_cdp = True
    manual = False
    auto_actions = False
    force = False
    dry_run_import = True
    restart_stale_cdp = False


def test_hourly_delay_uses_jitter_inside_window():
    delay = next_delay_seconds(
        datetime(2026, 6, 15, 10, 0, 0),
        interval_minutes=60,
        jitter_minutes=12,
        rng=random.Random(1),
    )

    assert 48 * 60 <= delay <= 72 * 60


def test_schedule_args_default_to_production_window():
    parser = argparse.ArgumentParser()
    add_schedule_args(parser)
    args = parser.parse_args([])

    assert args.start_hour == 8
    assert args.end_hour == 23
    assert args.interval_minutes == 60
    assert args.jitter_minutes == 12
    assert args.order_lookback_days == 0


def test_hourly_delay_after_23_waits_until_next_8am_with_jitter():
    delay = next_delay_seconds(
        datetime(2026, 6, 18, 23, 5, 0),
        start_hour=8,
        end_hour=23,
        interval_minutes=60,
        jitter_minutes=12,
        rng=random.Random(1),
    )

    assert 8 * 60 * 60 + 55 * 60 <= delay <= 9 * 60 * 60 + 7 * 60


def test_hourly_delay_waits_until_next_collection_window():
    delay = next_delay_seconds(
        datetime(2026, 6, 15, 1, 0, 0),
        start_hour=9,
        end_hour=24,
        interval_minutes=60,
        jitter_minutes=0,
        rng=random.Random(1),
    )

    assert delay == 8 * 60 * 60


def test_download_command_copies_existing_tmall_order_download_program_shape():
    command = build_download_command(Args, "0615", "10")

    assert "data_robot.daily_download" in command
    assert command[command.index("--platform") + 1] == "tmall"
    assert command[command.index("--task") + 1] == "tmall_orders"
    assert command[command.index("--min-task-interval-seconds") + 1] == "2400"
    assert "--direct-cdp" in command
    assert "--restart-stale-cdp" not in command


def test_import_command_imports_tmall_and_douyin_orders_only():
    command = build_import_command(Args, PathLike("D:\\archive\\0615\\10点下载"), "2026-06-15", PathLike("D:\\evidence\\hourly.json"))

    assert "import_daily_files_to_feishu.py" in command[1]
    assert command.count("--kind") == 1
    assert command[command.index("--kind") + 1] == "orders"
    assert command.count("--platform") == 2
    assert "天猫" in command
    assert "抖音" in command
    assert command[command.index("--order-lookback-days") + 1] == "0"
    assert "--dry-run" in command


def test_import_command_can_limit_to_tmall_orders_only():
    args = SimpleNamespace(**{name: getattr(Args, name) for name in dir(Args) if not name.startswith("__")})
    args.order_platform = ["\u5929\u732b"]

    command = build_import_command(args, PathLike("D:\\archive\\0615\\10"), "2026-06-15", PathLike("D:\\evidence\\hourly.json"))

    assert command.count("--platform") == 1
    assert "\u5929\u732b" in command
    assert "\u6296\u97f3" not in command


def test_run_once_does_not_succeed_without_tmall_excel_even_when_import_allowed(monkeypatch, tmp_path):
    commands = []

    def fake_verify_batch(batch_dir, expected_tasks, include_legacy=False):
        return {"status": "missing", "batch_dir": str(batch_dir), "expected_tasks": expected_tasks, "include_legacy": include_legacy}

    def fake_run_command(command, timeout):
        commands.append(command)
        return {"returncode": 0, "stdout": "ok", "stderr": "", "timeout": timeout}

    monkeypatch.setattr(hourly_order_import, "verify_batch", fake_verify_batch)
    monkeypatch.setattr(hourly_order_import, "run_command", fake_run_command)

    args = SimpleNamespace(
        date_token="0615",
        batch_hour="10",
        import_date="2026-06-15",
        archive_root=str(tmp_path / "archive"),
        evidence_root=str(tmp_path / "evidence"),
        skip_download=True,
        allow_missing_tmall_download=True,
        import_timeout_seconds=30,
        dry_run_import=True,
    )

    summary = hourly_order_import.run_once(args)

    assert commands
    assert summary["status"] == "archive_incomplete"
    assert summary["tmall_excel_required"] is True
    assert summary["tmall_excel_ready"] is False
    assert summary["import"]["returncode"] == 0


class PathLike:
    def __init__(self, value: str) -> None:
        self.value = value

    def __fspath__(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value
