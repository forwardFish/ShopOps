from __future__ import annotations

from data_robot.tasks import PLATFORM_TASKS, TASKS
from data_robot.common import (
    compute_cooldown_remaining,
    direct_cdp_duplicate_target_ids,
    direct_cdp_page_family,
    direct_cdp_reusable_target_id,
    followup_export_labels,
    is_recoverable_cdp_error,
    is_recoverable_export_error,
    page_match_score,
    retry_wait_seconds,
    smart_export_labels,
    should_retry_task_result,
    summarize_platform_results,
    summarize_task_results,
)
from data_robot.daily_download import (
    PLATFORM_ENTRY_TASK,
    PLATFORM_PORTS,
    platform_result_failed_on_cdp_connect,
    selected_task_keys,
)
from data_robot.full_flow import (
    build_doctor_command,
    build_download_command,
    build_playwright_check_command,
    download_failed_on_browser_connection,
)
from data_robot.start_chrome import BROWSER_PATHS, build_browser_command


def test_all_requested_download_pages_are_configured():
    assert set(TASKS) == {
        "pinduoduo_orders",
        "pinduoduo_ads",
        "wechat_channels_orders",
        "douyin_ads",
        "douyin_influencer",
        "tmall_orders",
        "tmall_ads",
    }


def test_platform_task_groups_cover_every_task_once():
    grouped = [task for tasks in PLATFORM_TASKS.values() for task in tasks]

    assert sorted(grouped) == sorted(TASKS)
    assert PLATFORM_TASKS == {
        "pinduoduo": ("pinduoduo_orders", "pinduoduo_ads"),
        "wechat_channels": ("wechat_channels_orders",),
        "douyin": ("douyin_ads", "douyin_influencer"),
        "tmall": ("tmall_orders", "tmall_ads"),
    }


def test_task_urls_and_archive_metadata_are_present():
    for key, task in TASKS.items():
        assert task.key == key
        assert task.url.startswith("https://")
        assert task.platform
        assert task.platform_code
        assert task.profile
        assert task.kind in {"orders", "ads", "influencer"}
        assert task.slug


def test_every_task_has_smart_export_labels():
    for task in TASKS.values():
        labels = smart_export_labels(task)
        followups = followup_export_labels(task)

        assert labels
        assert followups
        assert any("\u5bfc\u51fa" in label or "\u4e0b\u8f7d" in label for label in labels)


def test_wechat_order_followup_clicks_export_confirmation():
    assert "导出" in followup_export_labels(TASKS["wechat_channels_orders"])


def test_pinduoduo_orders_uses_specific_primary_export_label():
    assert smart_export_labels(TASKS["pinduoduo_orders"]) == ["批量导出"]
    assert "下载数据" in followup_export_labels(TASKS["pinduoduo_orders"])


def test_cdp_page_matching_prefers_same_task_host_and_path():
    task = TASKS["wechat_channels_orders"]

    assert page_match_score("https://store.weixin.qq.com/shop/order/list", task.url) > page_match_score(
        "https://buyin.jinritemai.com/dashboard/data/financial/list",
        task.url,
    )
    assert page_match_score("https://store.weixin.qq.com/shop/order/list", task.url) > page_match_score(
        "about:blank",
        task.url,
    )


def test_direct_cdp_reuses_best_matching_business_tab():
    targets = [
        {"type": "page", "targetId": "blank", "url": "about:blank"},
        {"type": "page", "targetId": "other", "url": "https://buyin.jinritemai.com/dashboard/data/financial/list"},
        {"type": "page", "targetId": "orders", "url": "https://myseller.taobao.com/home.htm/trade-platform/tp/sold"},
    ]

    assert direct_cdp_reusable_target_id(targets, TASKS["tmall_orders"].url) == "orders"


def test_direct_cdp_reuse_does_not_steal_tmall_ads_page_for_orders():
    targets = [
        {"type": "page", "targetId": "ads", "url": "https://myseller.taobao.com/home.htm/tuiguangcenter_new/"},
        {"type": "page", "targetId": "orders", "url": "https://myseller.taobao.com/home.htm/trade-platform/tp/export-list"},
    ]

    assert direct_cdp_reusable_target_id(targets, TASKS["tmall_orders"].url) == "orders"


def test_direct_cdp_reuses_existing_business_tab_before_opening_new_one():
    targets = [
        {"type": "page", "targetId": "blank", "url": "about:blank"},
        {"type": "page", "targetId": "current", "url": "https://one.alimama.com/index.html#!/report/account"},
        {"type": "other", "targetId": "worker", "url": "https://one.alimama.com/worker.js"},
    ]

    assert direct_cdp_reusable_target_id(targets, TASKS["tmall_ads"].url) == "current"


def test_direct_cdp_duplicate_target_ids_closes_same_task_family_only():
    targets = [
        {"type": "page", "targetId": "keep", "url": "https://myseller.taobao.com/home.htm/trade-platform/tp/export-list"},
        {"type": "page", "targetId": "old", "url": "https://myseller.taobao.com/home.htm/trade-platform/tp/sold"},
        {"type": "page", "targetId": "ads", "url": "https://myseller.taobao.com/home.htm/tuiguangcenter_new/"},
    ]

    assert direct_cdp_page_family(TASKS["tmall_orders"].url) == "tmall_orders"
    assert direct_cdp_duplicate_target_ids(targets, TASKS["tmall_orders"].url, keep_target_id="keep") == ["old"]


def test_daily_download_ports_cover_platforms():
    assert set(PLATFORM_PORTS) == set(PLATFORM_TASKS)
    assert set(PLATFORM_ENTRY_TASK) == set(PLATFORM_TASKS)
    assert len(set(PLATFORM_PORTS.values())) == len(PLATFORM_PORTS)
    for platform, task_key in PLATFORM_ENTRY_TASK.items():
        assert task_key in PLATFORM_TASKS[platform]


def test_browser_command_uses_remote_debugging_profile_suffix(tmp_path):
    command = build_browser_command(
        "pinduoduo_orders",
        port=9333,
        profile_suffix="doctor",
        profile_root=tmp_path,
        start_url="about:blank",
    )

    assert "--remote-debugging-port=9333" in command
    assert "--remote-debugging-address=127.0.0.1" in command
    assert "--remote-allow-origins=*" in command
    assert any("pinduoduo-doctor" in item for item in command)
    assert any(str(tmp_path) in item for item in command)
    assert command[-1] == "about:blank"


def test_default_browser_paths_are_chrome_only():
    browser_paths = [str(path).lower() for path in BROWSER_PATHS]

    assert browser_paths
    assert all("chrome.exe" in path for path in browser_paths)
    assert not any("msedge.exe" in path for path in browser_paths)


def test_daily_download_verifies_only_selected_platform_tasks():
    assert selected_task_keys(["pinduoduo"], None) == ["pinduoduo_orders", "pinduoduo_ads"]
    assert selected_task_keys(["douyin", "tmall"], None) == [
        "douyin_ads",
        "douyin_influencer",
        "tmall_orders",
        "tmall_ads",
    ]
    assert selected_task_keys(["pinduoduo"], ["pinduoduo_orders", "tmall_orders"]) == ["pinduoduo_orders"]


def test_daily_download_detects_stale_cdp_failures():
    result = {
        "results": [
            {"status": "error", "error": "TimeoutError: BrowserType.connect_over_cdp: Timeout"},
            {"status": "error", "error": "URLError: <urlopen error [WinError 10061]>"},
        ]
    }

    assert platform_result_failed_on_cdp_connect(result)


def test_daily_download_does_not_restart_after_partial_success():
    result = {
        "results": [
            {"status": "downloaded"},
            {"status": "error", "error": "TimeoutError: BrowserType.connect_over_cdp: Timeout"},
        ]
    }

    assert not platform_result_failed_on_cdp_connect(result)


def test_downloaded_unmatched_summarizes_as_unmatched_failure():
    assert summarize_task_results([
        {"status": "downloaded"},
        {"status": "downloaded_unmatched"},
    ]) == "finished_with_unmatched_downloads"
    assert summarize_platform_results([
        {"status": "downloaded"},
        {"status": "finished_with_unmatched_downloads"},
    ]) == "finished_with_unmatched_downloads"


def test_common_parser_defaults_to_eight_minute_cooldown_and_five_attempts():
    from data_robot.common import options_from_args, parse_common_args

    parser = parse_common_args("test")
    args = parser.parse_args([])
    options = options_from_args(args)

    assert options.min_task_interval_seconds == 480
    assert options.retry_interval_seconds == 480
    assert options.max_task_attempts == 5
    assert not options.force


def test_common_parser_allows_force_cooldown_bypass():
    from data_robot.common import options_from_args, parse_common_args

    parser = parse_common_args("test")
    args = parser.parse_args([
        "--force",
        "--min-task-interval-seconds",
        "600",
        "--retry-interval-seconds",
        "600",
        "--max-task-attempts",
        "3",
    ])
    options = options_from_args(args)

    assert options.min_task_interval_seconds == 600
    assert options.retry_interval_seconds == 600
    assert options.max_task_attempts == 3
    assert options.force


def test_cooldown_remaining_counts_down_without_going_negative():
    assert compute_cooldown_remaining(1000, 300, now=1100) == 200
    assert compute_cooldown_remaining(1000, 300, now=1400) == 0
    assert compute_cooldown_remaining(0, 300, now=1100) == 0


def test_task_result_summary_distinguishes_run_outcomes():
    assert summarize_task_results([{"status": "downloaded"}]) == "downloaded"
    assert summarize_task_results([{"status": "skipped_cooldown"}]) == "skipped_cooldown"
    assert summarize_task_results([{"status": "downloaded"}, {"status": "no_download"}]) == "finished_with_missing_downloads"
    assert summarize_task_results([{"status": "downloaded"}, {"status": "error"}]) == "finished_with_errors"


def test_retry_policy_retries_no_download_and_recoverable_cdp_errors():
    from data_robot.common import CollectOptions

    assert should_retry_task_result({"status": "no_download"})
    assert should_retry_task_result({"status": "skipped_cooldown"})
    assert retry_wait_seconds({"status": "skipped_cooldown", "cooldown_remaining_seconds": 37}, CollectOptions(retry_interval_seconds=480)) == 37
    assert not should_retry_task_result({"status": "downloaded"})
    cdp_error = {"status": "error", "error": "TimeoutError: BrowserType.connect_over_cdp: Timeout"}

    assert should_retry_task_result(cdp_error)
    assert is_recoverable_cdp_error(cdp_error)
    assert retry_wait_seconds(cdp_error, CollectOptions(retry_interval_seconds=480)) == 60
    assert should_retry_task_result({"status": "error", "error": "ConnectionClosedError: no close frame received or sent"})
    export_error = {"status": "error", "error": "HTTPError: HTTP Error 502: Bad Gateway"}

    assert should_retry_task_result(export_error)
    assert is_recoverable_export_error(export_error)
    assert retry_wait_seconds(export_error, CollectOptions(retry_interval_seconds=20)) == 20


def test_retry_policy_does_not_retry_non_cdp_errors():
    assert not should_retry_task_result({"status": "error", "error": "selector failed"})


def test_cdp_errors_are_reported_without_retry_wait_semantics():
    assert summarize_task_results([
        {"status": "error", "error": "TimeoutError: BrowserType.connect_over_cdp: Timeout"}
    ]) == "finished_with_errors"


def test_platform_result_summary_distinguishes_archive_verification_from_run_success():
    assert summarize_platform_results([{"status": "downloaded"}, {"status": "downloaded"}]) == "downloaded"
    assert summarize_platform_results([{"status": "skipped_cooldown"}]) == "skipped_cooldown"
    assert summarize_platform_results([{"status": "downloaded"}, {"status": "finished_with_skips"}]) == "finished_with_skips"
    assert summarize_platform_results([{"status": "downloaded"}, {"status": "finished_with_errors"}]) == "finished_with_errors"


def test_full_flow_download_command_keeps_anti_risk_defaults():
    class Args:
        archive_root = "D:\\archive"
        evidence_root = "D:\\evidence"
        watch_dir = "C:\\Users\\linyanhui\\Downloads"
        timeout_seconds = 900
        idle_seconds = 30
        max_downloads = 5
        min_task_interval_seconds = 480
        retry_interval_seconds = 480
        max_task_attempts = 5
        platform = None
        task = None
        force = False
        no_cdp = False
        direct_cdp = False
        manual = False
        auto_actions = False
        skip_final_verify = False
        flat_date_folder = False
        browser_profile_suffix = "cdp"
        browser_profile_root = "D:\\tmp\\profiles"

    command = build_download_command(Args, "0613", "23")

    assert "data_robot.daily_download" in command
    assert command[command.index("--batch-hour") + 1] == "23"
    assert command[command.index("--min-task-interval-seconds") + 1] == "480"
    assert command[command.index("--retry-interval-seconds") + 1] == "480"
    assert command[command.index("--max-task-attempts") + 1] == "5"
    assert command[command.index("--browser-profile-suffix") + 1] == "cdp"
    assert command[command.index("--browser-profile-root") + 1] == "D:\\tmp\\profiles"
    assert "--direct-cdp" not in command


def test_full_flow_doctor_command_uses_runtime_gate_profile():
    class Args:
        archive_root = "D:\\archive"
        evidence_root = "D:\\evidence"
        doctor_profile_suffix = "doctor"
        browser_profile_root = "D:\\tmp\\profiles"

    command = build_doctor_command(Args, "0614", "11")

    assert "data_robot.doctor" in command
    assert command[command.index("--date-token") + 1] == "0614"
    assert command[command.index("--batch-hour") + 1] == "11"
    assert command[command.index("--browser-profile-suffix") + 1] == "doctor"
    assert command[command.index("--browser-profile-root") + 1] == "D:\\tmp\\profiles"


def test_full_flow_download_command_can_use_direct_cdp():
    class Args:
        archive_root = "D:\\archive"
        evidence_root = "D:\\evidence"
        watch_dir = "C:\\Users\\linyanhui\\Downloads"
        timeout_seconds = 900
        idle_seconds = 30
        max_downloads = 5
        min_task_interval_seconds = 480
        retry_interval_seconds = 480
        max_task_attempts = 5
        platform = None
        task = None
        force = False
        no_cdp = False
        direct_cdp = True
        manual = False
        auto_actions = False
        skip_final_verify = False
        flat_date_folder = False
        browser_profile_suffix = "cdp-test"
        browser_profile_root = "D:\\tmp\\profiles"

    command = build_download_command(Args, "0614", "11")

    assert "--direct-cdp" in command
    assert command[command.index("--browser-profile-suffix") + 1] == "cdp-test"


def test_full_flow_has_playwright_runtime_preflight_command():
    command = build_playwright_check_command()

    assert command[0]
    assert command[1] == "-c"
    assert "sync_playwright" in command[2]


def test_full_flow_classifies_browser_connection_download_failures():
    summary = {
        "results": [
            {
                "results": [
                    {"status": "error", "error": "ConnectionClosedError: no close frame received or sent"},
                    {"status": "error", "error": "URLError: <urlopen error [WinError 10061]>"},
                ]
            }
        ]
    }

    assert download_failed_on_browser_connection(summary)
    assert not download_failed_on_browser_connection({"results": [{"results": [{"status": "error", "error": "selector failed"}]}]})
