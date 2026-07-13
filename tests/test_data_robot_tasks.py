from __future__ import annotations

import asyncio
import time
from pathlib import Path

import data_robot.daily_download as daily_download_module
from data_robot.tasks import PLATFORM_TASKS, TASKS
from data_robot.common import (
    PENDING_EXPORT_STATE_PATH,
    PINDUODUO_ORDER_EXPORT_LIST_URL,
    CollectOptions,
    clear_pending_export,
    DEFAULT_ARCHIVE_ROOT,
    compute_cooldown_remaining,
    collect_task,
    direct_cdp_click_existing_export_result,
    direct_cdp_duplicate_target_ids,
    direct_cdp_initial_url,
    direct_cdp_page_family,
    direct_cdp_preserves_current_page,
    direct_cdp_recover_blank_business_page,
    direct_cdp_business_page_ready,
    direct_cdp_prepare_business_page,
    direct_cdp_reusable_target_id,
    effective_min_task_interval_seconds,
    platform_export_interval_floor_seconds,
    pending_export_for,
    record_pending_export,
    followup_export_labels,
    is_recoverable_cdp_error,
    is_recoverable_export_error,
    matches_task_filename,
    page_match_score,
    pinduoduo_export_list_is_empty,
    retry_wait_seconds,
    smart_export_labels,
    should_preserve_current_page,
    should_retry_task_result,
    summarize_platform_results,
    summarize_task_results,
    text_looks_like_login,
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


def test_pinduoduo_order_url_uses_current_business_route():
    assert TASKS["pinduoduo_orders"].url == "https://mms.pinduoduo.com/orders/list"


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


def test_pinduoduo_ads_prefers_daily_data_download_over_summary_download():
    assert smart_export_labels(TASKS["pinduoduo_ads"])[0] == "下载分天数据"


def test_pinduoduo_pending_export_resumes_from_export_list(tmp_path, monkeypatch):
    state_path = tmp_path / "pending_exports.json"
    monkeypatch.setattr("data_robot.common.PENDING_EXPORT_STATE_PATH", state_path)

    record_pending_export("pinduoduo_orders", "0711")

    assert pending_export_for("pinduoduo_orders", "0711")
    assert direct_cdp_initial_url(TASKS["pinduoduo_orders"], resume_pending_export=True) == PINDUODUO_ORDER_EXPORT_LIST_URL
    assert direct_cdp_initial_url(TASKS["pinduoduo_orders"]) == TASKS["pinduoduo_orders"].url

    clear_pending_export("pinduoduo_orders")

    assert not pending_export_for("pinduoduo_orders", "0711")


def test_pinduoduo_empty_export_list_can_replace_only_a_stale_pending_request():
    assert pinduoduo_export_list_is_empty("\u8ba2\u5355\u67e5\u8be2 / \u5df2\u751f\u6210\u62a5\u8868 \u6682\u65e0\u6570\u636e \u5171\u6709 0 \u6761")
    assert not pinduoduo_export_list_is_empty("\u8ba2\u5355\u67e5\u8be2 / \u5df2\u751f\u6210\u62a5\u8868 \u4e0b\u8f7d\u62a5\u8868 \u5171\u6709 1 \u6761")


def test_account_menu_text_does_not_trigger_a_login_prompt():
    assert not text_looks_like_login("\u5e97\u94fa\u4e8c\u7ef4\u7801 \u8d26\u53f7\u4fe1\u606f \u767b\u5f55\u5176\u4ed6\u8d26\u53f7")
    assert text_looks_like_login("\u8bf7\u626b\u7801\u767b\u5f55")


def test_direct_cdp_keeps_an_already_open_target_without_navigation():
    export_list = PINDUODUO_ORDER_EXPORT_LIST_URL

    assert direct_cdp_preserves_current_page(export_list, export_list)
    assert not direct_cdp_preserves_current_page(export_list, TASKS["pinduoduo_orders"].url)


def test_direct_cdp_recovers_blank_business_view_in_same_tab():
    class Page:
        def __init__(self, blank: bool) -> None:
            self.blank = blank
            self.reloaded = False

        async def evaluate(self, expression: str, *, timeout_seconds: int):
            assert "elementFromPoint" in expression
            return self.blank

        async def reload(self):
            self.reloaded = True

    blank_page = Page(True)
    assert asyncio.run(direct_cdp_recover_blank_business_page(blank_page, TASKS["pinduoduo_orders"]))
    assert blank_page.reloaded

    ready_page = Page(False)
    assert not asyncio.run(direct_cdp_recover_blank_business_page(ready_page, TASKS["pinduoduo_orders"]))
    assert not ready_page.reloaded


def test_business_page_readiness_rejects_stale_pinduoduo_shell():
    task = TASKS["pinduoduo_orders"]
    assert not direct_cdp_business_page_ready(
        task,
        page_url=task.url,
        body_text="订单查询 首页 消息 设置",
    )
    assert direct_cdp_business_page_ready(
        task,
        page_url=task.url,
        body_text="订单编号 商品名称 共有 5016 条",
    )
    assert not direct_cdp_business_page_ready(
        task,
        page_url="https://mms.pinduoduo.com/login/?redirectUrl=%2Forders%2Flist",
        body_text="订单编号 商品名称 共有 5016 条",
    )
    assert not direct_cdp_business_page_ready(
        task,
        page_url=task.url,
        body_text="订单编号 商品名称 网络链接关闭，请检查您的网络连接",
    )


def test_business_page_readiness_requires_real_tmall_ads_view():
    task = TASKS["tmall_ads"]
    assert not direct_cdp_business_page_ready(task, page_url=task.url, body_text="下载报表")
    assert direct_cdp_business_page_ready(
        task,
        page_url=task.url,
        body_text="营销场景报表 下载报表 数据范围",
    )


def test_prepare_business_page_uses_bounded_reload_then_navigation():
    class Page:
        def __init__(self) -> None:
            self.reloads = 0
            self.navigations: list[str] = []

        async def evaluate(self, expression: str, *, timeout_seconds: int):
            if self.reloads == 0 and not self.navigations:
                return {
                    "url": TASKS["pinduoduo_orders"].url,
                    "title": "",
                    "readyState": "complete",
                    "bodyText": "订单查询 首页 消息",
                    "hasQianchuanDownloadButton": False,
                }
            return {
                "url": TASKS["pinduoduo_orders"].url,
                "title": "订单查询",
                "readyState": "complete",
                "bodyText": "订单编号 商品名称 共有 2 条",
                "hasQianchuanDownloadButton": False,
            }

        async def reload(self):
            self.reloads += 1

        async def navigate(self, url: str):
            self.navigations.append(url)

    page = Page()
    result = asyncio.run(
        direct_cdp_prepare_business_page(
            page,
            TASKS["pinduoduo_orders"],
            requested_url=TASKS["pinduoduo_orders"].url,
        )
    )

    assert result["status"] == "ready"
    assert page.reloads == 1
    assert page.navigations == []


def test_pinduoduo_direct_cdp_resume_clicks_existing_report_once():
    class Page:
        def __init__(self) -> None:
            self.labels: list[str] = []

        async def evaluate(self, expression: str, *, timeout_seconds: int):
            assert expression == "location.href"
            return PINDUODUO_ORDER_EXPORT_LIST_URL

        async def click_label(self, label: str, *, exact: bool):
            assert exact
            self.labels.append(label)
            return "direct-cdp button"

    page = Page()
    clicked = asyncio.run(
        direct_cdp_click_existing_export_result(
            page,
            TASKS["pinduoduo_orders"],
            deadline=time.monotonic() + 1,
            watch_dirs=[],
            started_at=0,
        )
    )

    assert clicked
    assert page.labels == ["\u4e0b\u8f7d\u62a5\u8868"]


def test_tmall_pending_report_is_not_replaced_with_another_export():
    class Page:
        async def evaluate(self, expression: str, *, timeout_seconds: int):
            return {"clicked": False, "pending": True}

    from data_robot.common import direct_cdp_click_tmall_report_covering_today

    assert asyncio.run(
        direct_cdp_click_tmall_report_covering_today(
            Page(), deadline=time.monotonic() + 1, watch_dirs=[], started_at=time.time()
        )
    )


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


def test_shared_download_folder_filters_other_task_files_before_watching():
    task = TASKS["wechat_channels_orders"]

    assert not matches_task_filename(task, "商品推广_账户_汇总数据_商品_20260703至20260709.xls")
    assert matches_task_filename(task, "微信小店订单_2026年07月10日.xlsx")
    assert summarize_platform_results([
        {"status": "downloaded"},
        {"status": "finished_with_unmatched_downloads"},
    ]) == "finished_with_unmatched_downloads"


def test_common_parser_defaults_to_platform_aware_cooldowns_and_five_attempts():
    from data_robot.common import options_from_args, parse_common_args

    parser = parse_common_args("test")
    args = parser.parse_args([])
    options = options_from_args(args)

    assert options.min_task_interval_seconds == 0
    assert options.retry_interval_seconds == 0
    assert effective_min_task_interval_seconds(TASKS["tmall_orders"], options.min_task_interval_seconds) == 300
    assert effective_min_task_interval_seconds(TASKS["pinduoduo_orders"], options.min_task_interval_seconds) == 120
    assert options.max_task_attempts == 5
    assert not options.force


def test_standard_download_defaults_to_stable_archive_and_flat_batch_layout():
    from data_robot.common import parse_common_args

    parser = parse_common_args("test")
    args = parser.parse_args([])
    assert Path(args.archive_root) == DEFAULT_ARCHIVE_ROOT
    assert args.flat_date_folder

    hourly = parser.parse_args(["--hourly-batch", "--batch-hour", "23"])
    assert not hourly.flat_date_folder
    assert hourly.batch_hour == "23"


def test_missing_cdp_browser_is_started_automatically(monkeypatch):
    readiness_calls = []
    started = []

    def fake_wait(port, *, timeout_seconds):
        readiness_calls.append((port, timeout_seconds))
        return len(readiness_calls) > 1

    class Process:
        pid = 12345

    monkeypatch.setattr(daily_download_module, "wait_for_cdp", fake_wait)
    monkeypatch.setattr(
        daily_download_module,
        "start_chrome_for_task",
        lambda task_key, **kwargs: started.append((task_key, kwargs)) or Process(),
    )

    result = daily_download_module.ensure_platform_cdp(
        "tmall",
        profile_suffix="cdp-test",
        profile_root="D:\\profiles",
    )

    assert result == {"status": "ready", "started": True, "port": 9225, "pid": 12345}
    assert readiness_calls == [(9225, 2), (9225, 30)]
    assert started == [("tmall_orders", {"port": 9225, "profile_suffix": "cdp-test", "profile_root": "D:\\profiles"})]


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


def test_platform_export_interval_floors_are_enforced():
    assert platform_export_interval_floor_seconds(TASKS["tmall_orders"]) == 300
    assert platform_export_interval_floor_seconds(TASKS["pinduoduo_orders"]) == 120
    assert effective_min_task_interval_seconds(TASKS["tmall_orders"], 0) == 300
    assert effective_min_task_interval_seconds(TASKS["douyin_ads"], 30) == 120
    assert effective_min_task_interval_seconds(TASKS["wechat_channels_orders"], 600) == 600


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
    assert should_retry_task_result({"status": "no_download"})
    assert should_retry_task_result({"status": "skipped_cooldown"})
    assert retry_wait_seconds({"status": "skipped_cooldown", "cooldown_remaining_seconds": 37}, CollectOptions(retry_interval_seconds=480)) == 37
    assert not should_retry_task_result({"status": "downloaded"})
    cdp_error = {"status": "error", "error": "TimeoutError: BrowserType.connect_over_cdp: Timeout"}

    assert should_retry_task_result(cdp_error)
    assert is_recoverable_cdp_error(cdp_error)
    assert retry_wait_seconds(cdp_error, CollectOptions(retry_interval_seconds=480)) == 480
    navigation_error = {"status": "error", "task": "pinduoduo_orders", "error": "Page.goto: net::ERR_CONNECTION_CLOSED"}
    assert should_retry_task_result(navigation_error)
    assert retry_wait_seconds(navigation_error, CollectOptions(retry_interval_seconds=5)) == 120
    assert should_retry_task_result({"status": "error", "error": "ConnectionClosedError: no close frame received or sent"})
    export_error = {"status": "error", "error": "HTTPError: HTTP Error 502: Bad Gateway"}

    assert should_retry_task_result(export_error)
    assert is_recoverable_export_error(export_error)
    assert retry_wait_seconds(export_error, CollectOptions(retry_interval_seconds=20)) == 120
    assert retry_wait_seconds({"status": "no_download", "task": "tmall_orders"}, CollectOptions(retry_interval_seconds=5)) == 300
    assert retry_wait_seconds({"status": "no_download", "task": "douyin_ads"}, CollectOptions(retry_interval_seconds=5)) == 120
    assert retry_wait_seconds(
        {"status": "skipped_cooldown", "task": "tmall_orders", "cooldown_remaining_seconds": 240},
        CollectOptions(retry_interval_seconds=5),
    ) == 240


def test_login_redirect_page_is_preserved_for_manual_login():
    assert should_preserve_current_page(
        TASKS["pinduoduo_orders"],
        "https://mms.pinduoduo.com/login/?redirectUrl=https%3A%2F%2Fmms.pinduoduo.com%2Forders%2Flist%3Ftab%3D0",
    )
    assert not should_preserve_current_page(
        TASKS["pinduoduo_orders"],
        "https://mms.pinduoduo.com/orders/list?tab=0",
    )


def test_cooldown_skip_does_not_create_local_capture_dir(tmp_path, monkeypatch):
    import asyncio
    import data_robot.common as common_module

    monkeypatch.setattr(common_module, "DOWNLOAD_ROOT", tmp_path / "downloads")
    monkeypatch.setattr(common_module, "cooldown_remaining", lambda task_key, seconds: 180)

    result = asyncio.run(
        collect_task(
            TASKS["tmall_orders"],
            CollectOptions(min_task_interval_seconds=0, retry_interval_seconds=5),
            date_token="0613",
        )
    )

    assert result["status"] == "skipped_cooldown"
    assert result["diagnostics"]["local_capture_dir"] == ""
    assert result["diagnostics"]["min_export_interval_seconds"] == 300
    assert not (tmp_path / "downloads").exists()


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
    assert "--hourly-batch" in command
    assert "--direct-cdp" not in command


def test_full_flow_doctor_command_uses_runtime_gate_profile():
    class Args:
        archive_root = "D:\\archive"
        evidence_root = "D:\\evidence"
        doctor_profile_suffix = "doctor"
        browser_profile_root = "D:\\tmp\\profiles"
        flat_date_folder = False

    command = build_doctor_command(Args, "0614", "11")

    assert "data_robot.doctor" in command
    assert command[command.index("--date-token") + 1] == "0614"
    assert command[command.index("--batch-hour") + 1] == "11"
    assert command[command.index("--browser-profile-suffix") + 1] == "doctor"
    assert command[command.index("--browser-profile-root") + 1] == "D:\\tmp\\profiles"
    assert "--hourly-batch" in command


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
