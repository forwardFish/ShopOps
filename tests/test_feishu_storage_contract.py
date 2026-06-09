import pytest

from shopops.config import Settings
from shopops.storage.feishu_bitable import FeishuBitableStorage, FeishuEnvironmentError
from shopops.storage.local_feishu import LocalFeishuBitableStorage


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self.payload


def test_feishu_environment_probe_fails_closed_without_real_credentials(monkeypatch):
    for name in ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "APP_ID", "APP_SECRET", "FEISHU_APP_TOKEN", "APP_TOKEN"]:
        monkeypatch.delenv(name, raising=False)
    settings = Settings()

    probe = FeishuBitableStorage.environment_probe(settings)

    assert probe["ready"] is False
    assert "FEISHU_APP_ID" in probe["missing"]
    assert "FEISHU_APP_SECRET" in probe["missing"]
    assert "FEISHU_APP_TOKEN" in probe["missing"]
    assert "FEISHU_TABLE_MONITOR_SNAPSHOT" in probe["missing"]
    assert "FEISHU_TABLE_ORDERS_RAW" in probe["missing"]
    assert "FEISHU_TABLE_PROMOTION_SNAPSHOT" in probe["missing"]
    assert "FEISHU_TABLE_METRICS_10MIN" in probe["missing"]
    assert "FEISHU_TABLE_TASK_LOG" in probe["missing"]
    assert "FEISHU_TABLE_ALERT_LOG" in probe["missing"]
    assert "FEISHU_TABLE_DAILY_REPORT" in probe["missing"]
    assert "FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION" in probe["missing"]


def test_real_feishu_storage_constructor_fails_closed_without_environment(tmp_path):
    settings = Settings(pending_records_path=str(tmp_path / "pending.jsonl"))

    with pytest.raises(FeishuEnvironmentError):
        FeishuBitableStorage(settings)


def test_real_feishu_storage_uses_direct_openapi_for_business_tables(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"method": "POST", "url": url, "json": json, "headers": headers})
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "data": {"tenant_access_token": "tenant_token"}})
        raise AssertionError(url)

    def fake_request(method, url, headers=None, json=None, params=None, timeout=None):
        calls.append({"method": method, "url": url, "json": json, "params": params, "headers": headers})
        if method == "GET":
            return FakeResponse({"code": 0, "data": {"items": [], "has_more": False}})
        if method == "POST":
            return FakeResponse({"code": 0, "data": {"record": {"record_id": "rec_1"}}})
        raise AssertionError((method, url))

    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.post", fake_post)
    monkeypatch.setattr("shopops.storage.feishu_bitable.requests.request", fake_request)
    settings = Settings(
        feishu_app_id="cli_x",
        feishu_app_secret="secret",
        feishu_app_token="app_token",
        table_monitor_snapshot="tbl_monitor",
        table_orders_raw="tbl_orders",
        table_promotion_snapshot="tbl_promo",
        table_metrics_10min="tbl_metrics",
        table_task_log="tbl_task",
        table_alert_log="tbl_alert",
        table_daily_report="tbl_daily",
        table_douyin_influencer_commission="tbl_influencer",
        pending_records_path=str(tmp_path / "pending.jsonl"),
    )
    storage = FeishuBitableStorage(settings)

    assert storage.save_orders_raw([{"unique_key": "order_1", "订单号": "10001"}]) == 1
    assert storage.save_douyin_influencer_commission([{"unique_key": "kol_1", "达人昵称": "Creator A"}]) == 1

    assert any(call["method"] == "GET" and "/tables/tbl_orders/records" in call["url"] for call in calls)
    create_call = next(call for call in calls if call["method"] == "POST" and "/tables/tbl_orders/records" in call["url"])
    assert create_call["json"] == {"fields": {"unique_key": "order_1", "订单号": "10001"}}
    assert create_call["headers"]["Authorization"] == "Bearer tenant_token"
    assert any(call["method"] == "POST" and "/tables/tbl_influencer/records" in call["url"] for call in calls)


def test_local_feishu_double_supports_all_required_tables_upsert_and_readback(tmp_path):
    settings = Settings(local_feishu_path=str(tmp_path / "local.json"), pending_records_path=str(tmp_path / "pending.jsonl"))
    storage = LocalFeishuBitableStorage(settings)
    required_tables = [
        "system_config",
        "shop_config",
        "monitor_snapshot",
        "orders_raw",
        "promotion_snapshot",
        "metrics_10min",
        "task_run_log",
        "alert_log",
        "daily_report",
        "douyin_influencer_commission",
    ]

    for table in required_tables:
        storage.upsert(table, {"unique_key": f"{table}_001", "field": "first"})
        storage.upsert(table, {"unique_key": f"{table}_001", "field": "updated"})

    assert {table: storage.count(table) for table in required_tables} == {table: 1 for table in required_tables}
    assert all(storage.read_table(table)[0]["fields"]["field"] == "updated" for table in required_tables)
