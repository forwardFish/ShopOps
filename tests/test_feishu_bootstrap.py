from __future__ import annotations

from shopops.config import Settings, load_settings
from shopops.storage.feishu_bootstrap import (
    FeishuOpenApiClient,
    bootstrap_douyin_influencer_table,
    bootstrap_platform_tables,
    douyin_influencer_commission_table_spec,
    merge_env_file,
    platform_table_specs,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self.payload


def test_env_file_can_hold_app_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    monkeypatch.delenv("APP_ID", raising=False)
    monkeypatch.delenv("APP_SECRET", raising=False)
    (tmp_path / ".env").write_text(
        "APP_ID=cli_test_app\nAPP_SECRET=test_secret\nFEISHU_APP_TOKEN=app_test\n",
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.feishu_app_id == "cli_test_app"
    assert settings.feishu_app_secret == "test_secret"
    assert settings.feishu_app_token == "app_test"


def test_bootstrap_uses_existing_base_and_creates_platform_tables(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "data": {"tenant_access_token": "tenant_token"}})
        if url.endswith("/tables"):
            table_id = "tbl_order" if json["table"]["name"].startswith("订单明细") else "tbl_promo"
            return FakeResponse({"code": 0, "data": {"table_id": table_id, "default_view_id": "vew_1", "field_id_list": ["fld_1"]}})
        raise AssertionError(url)

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if url.endswith("/tables"):
            return FakeResponse({"code": 0, "data": {"items": []}})
        raise AssertionError(url)

    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.post", fake_post)
    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.get", fake_get)
    settings = Settings(feishu_app_id="cli_x", feishu_app_secret="secret", feishu_app_token="app_existing")

    result = bootstrap_platform_tables(settings=settings, platform_name="千牛淘宝", env_path=tmp_path / ".env")

    assert result["app_token"] == "app_existing"
    assert result["created_base"] is None
    assert result["tables"]["orders_raw"]["table_name"] == "订单明细原始表-千牛淘宝"
    assert result["tables"]["promotion_snapshot"]["table_name"] == "推广数据表-千牛淘宝"
    assert result["tables"]["orders_raw"]["table_id"] == "tbl_order"
    assert result["tables"]["promotion_snapshot"]["table_id"] == "tbl_promo"
    assert not any(call["url"].endswith("/bitable/v1/apps") for call in calls)
    assert len([call for call in calls if call["url"].endswith("/tables") and "json" in call]) == len(platform_table_specs("鍗冪墰娣樺疂"))


def test_bootstrap_creates_base_when_app_token_is_missing(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "data": {"tenant_access_token": "tenant_token"}})
        if url.endswith("/bitable/v1/apps"):
            return FakeResponse({"code": 0, "data": {"app": {"app_token": "app_created", "name": json["name"]}}})
        if url.endswith("/tables"):
            return FakeResponse({"code": 0, "data": {"table_id": "tbl_created"}})
        raise AssertionError(url)

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if url.endswith("/tables"):
            return FakeResponse({"code": 0, "data": {"items": []}})
        raise AssertionError(url)

    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.post", fake_post)
    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.get", fake_get)
    settings = Settings(feishu_app_id="cli_x", feishu_app_secret="secret", feishu_app_token="")

    result = bootstrap_platform_tables(
        settings=settings,
        platform_name="千牛淘宝",
        base_name="ShopOps 测试",
        env_path=tmp_path / ".env",
    )

    assert result["app_token"] == "app_created"
    assert result["created_base"]["app"]["name"] == "ShopOps 测试"
    assert any(call["url"].endswith("/bitable/v1/apps") for call in calls)


def test_platform_table_specs_match_requested_fields():
    specs = platform_table_specs("千牛淘宝")
    by_key = {spec.key: spec for spec in specs}

    assert set(by_key) == {
        "alert_log",
        "daily_report",
        "metrics_10min",
        "monitor_snapshot",
        "orders_raw",
        "promotion_snapshot",
        "task_run_log",
    }
    assert by_key["promotion_snapshot"].fields == [
        {"field_name": "unique_key", "type": 1},
        {"field_name": "平台", "type": 1},
        {"field_name": "店铺ID", "type": 1},
        {"field_name": "店铺名称", "type": 1},
        {"field_name": "采集时间", "type": 1},
        {"field_name": "花费", "type": 2},
        {"field_name": "页面URL", "type": 1},
        {"field_name": "页面截图", "type": 1},
    ]
    order_field_names = [field["field_name"] for field in by_key["orders_raw"].fields]
    assert "订单号" in order_field_names
    assert "创建时间" in order_field_names
    assert "买家昵称" in order_field_names
    assert "交易状态" in order_field_names
    assert "实收款" in order_field_names


def test_douyin_influencer_table_spec_contains_commission_fields():
    spec = douyin_influencer_commission_table_spec()

    assert spec.env_name == "FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION"
    assert spec.key == "douyin_influencer_commission"
    assert spec.name == "抖音达人佣金明细表"
    fields = {field["field_name"]: field["type"] for field in spec.fields}
    assert fields["达人ID"] == 1
    assert fields["达人昵称"] == 1
    assert fields["支付金额"] == 2
    assert fields["佣金率"] == 2
    assert fields["预估佣金"] == 2
    assert fields["结算佣金"] == 2
    assert fields["技术服务费"] == 2


def test_bootstrap_douyin_influencer_table_reuses_existing_base(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "data": {"tenant_access_token": "tenant_token"}})
        if url.endswith("/tables"):
            assert json["table"]["name"] == "抖音达人佣金明细表"
            return FakeResponse({"code": 0, "data": {"table_id": "tbl_influencer"}})
        raise AssertionError(url)

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        if url.endswith("/tables"):
            return FakeResponse({"code": 0, "data": {"items": []}})
        raise AssertionError(url)

    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.post", fake_post)
    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.get", fake_get)
    settings = Settings(feishu_app_id="cli_x", feishu_app_secret="secret", feishu_app_token="app_existing")

    result = bootstrap_douyin_influencer_table(settings=settings, env_path=tmp_path / ".env")

    assert result["app_token"] == "app_existing"
    assert result["table"]["table_id"] == "tbl_influencer"
    assert result["table"]["table_name"] == "抖音达人佣金明细表"
    env_data = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION=tbl_influencer" in env_data
    assert not any(call["url"].endswith("/bitable/v1/apps") for call in calls)


def test_merge_env_file_updates_table_ids_without_removing_secrets(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("APP_ID=cli_x\nAPP_SECRET=secret\nFEISHU_APP_TOKEN=old\n", encoding="utf-8")

    merge_env_file(
        env_path,
        {
            "FEISHU_APP_TOKEN": "app_new",
            "FEISHU_TABLE_ORDERS_RAW": "tbl_order",
            "FEISHU_TABLE_PROMOTION_SNAPSHOT": "tbl_promo",
        },
    )

    data = env_path.read_text(encoding="utf-8")
    assert "APP_ID=cli_x" in data
    assert "APP_SECRET=secret" in data
    assert "FEISHU_APP_TOKEN=app_new" in data
    assert "FEISHU_TABLE_ORDERS_RAW=tbl_order" in data
    assert "FEISHU_TABLE_PROMOTION_SNAPSHOT=tbl_promo" in data


def test_transfer_bitable_owner_uses_drive_permission_api(monkeypatch):
    calls: list[dict] = []

    def fake_post(url, json=None, headers=None, timeout=None, params=None):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout, "params": params})
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "data": {"tenant_access_token": "tenant_token"}})
        if url.endswith("/drive/v1/permissions/app_token/members/transfer_owner"):
            return FakeResponse({"code": 0, "data": {"ok": True}})
        raise AssertionError(url)

    monkeypatch.setattr("shopops.storage.feishu_bootstrap.requests.post", fake_post)
    client = FeishuOpenApiClient("cli_x", "secret")

    result = client.transfer_bitable_owner("app_token", "ou_7ebfaea2177bf1d6120ce21f39f7ac45")

    assert result == {"ok": True}
    transfer_call = calls[-1]
    assert transfer_call["json"] == {"member_type": "openid", "member_id": "ou_7ebfaea2177bf1d6120ce21f39f7ac45"}
    assert transfer_call["params"] == {
        "type": "bitable",
        "remove_old_owner": "false",
        "old_owner_perm": "full_access",
        "stay_put": "false",
    }
