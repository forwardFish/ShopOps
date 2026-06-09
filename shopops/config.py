from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    shop_id: str = field(default_factory=lambda: os.getenv("SHOP_ID", "taobao_shop_001"))
    shop_name: str = field(default_factory=lambda: os.getenv("SHOP_NAME", "淘宝店铺A"))
    shop_platform: str = field(default_factory=lambda: os.getenv("SHOP_PLATFORM", "taobao"))
    order_source: str = field(default_factory=lambda: os.getenv("ORDER_SOURCE", "crawler"))
    promotion_source: str = field(default_factory=lambda: os.getenv("PROMOTION_SOURCE", "qianniu_pc"))
    fetch_interval_seconds: int = field(default_factory=lambda: int(os.getenv("FETCH_INTERVAL_SECONDS", "600")))
    use_mock_collectors: bool = field(default_factory=lambda: _bool_env("USE_MOCK_COLLECTORS", True))
    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    evidence_dir: str = field(default_factory=lambda: os.getenv("EVIDENCE_DIR", "docs/live-evidence"))

    taobao_app_key: str = field(default_factory=lambda: os.getenv("TAOBAO_APP_KEY", ""))
    taobao_app_secret: str = field(default_factory=lambda: os.getenv("TAOBAO_APP_SECRET", ""))
    taobao_session_key: str = field(default_factory=lambda: os.getenv("TAOBAO_SESSION_KEY", ""))
    taobao_api_url: str = field(default_factory=lambda: os.getenv("TAOBAO_API_URL", "https://eco.taobao.com/router/rest"))
    taobao_order_list_method: str = field(default_factory=lambda: os.getenv("TAOBAO_ORDER_LIST_METHOD", "taobao.open.trades.sold.get"))
    taobao_order_detail_method: str = field(default_factory=lambda: os.getenv("TAOBAO_ORDER_DETAIL_METHOD", "taobao.open.trade.get"))
    qianniu_cdp_url: str = field(default_factory=lambda: os.getenv("QIANNIU_CDP_URL", "http://127.0.0.1:9222"))

    pdd_client_id: str = field(default_factory=lambda: os.getenv("PDD_CLIENT_ID", ""))
    pdd_client_secret: str = field(default_factory=lambda: os.getenv("PDD_CLIENT_SECRET", ""))
    pdd_access_token: str = field(default_factory=lambda: os.getenv("PDD_ACCESS_TOKEN", ""))
    pdd_api_url: str = field(default_factory=lambda: os.getenv("PDD_API_URL", "https://gw-api.pinduoduo.com/api/router"))
    pdd_order_list_type: str = field(default_factory=lambda: os.getenv("PDD_ORDER_LIST_TYPE", "pdd.order.number.list.increment.get"))
    pdd_order_detail_type: str = field(default_factory=lambda: os.getenv("PDD_ORDER_DETAIL_TYPE", "pdd.order.information.get"))

    doudian_app_key: str = field(default_factory=lambda: os.getenv("DOUDIAN_APP_KEY", ""))
    doudian_app_secret: str = field(default_factory=lambda: os.getenv("DOUDIAN_APP_SECRET", ""))
    doudian_access_token: str = field(default_factory=lambda: os.getenv("DOUDIAN_ACCESS_TOKEN", ""))
    doudian_api_url: str = field(default_factory=lambda: os.getenv("DOUDIAN_API_URL", "https://openapi-fxg.jinritemai.com"))
    doudian_sign_method: str = field(default_factory=lambda: os.getenv("DOUDIAN_SIGN_METHOD", "hmac-sha256"))
    doudian_alliance_order_ids: str = field(default_factory=lambda: os.getenv("DOUDIAN_ALLIANCE_ORDER_IDS", ""))

    oceanengine_marketing_app_id: str = field(default_factory=lambda: os.getenv("OCEANENGINE_MARKETING_APP_ID", ""))
    oceanengine_marketing_app_secret: str = field(default_factory=lambda: os.getenv("OCEANENGINE_MARKETING_APP_SECRET", ""))
    qianchuan_app_id: str = field(default_factory=lambda: os.getenv("QIANCHUAN_APP_ID", ""))
    qianchuan_app_secret: str = field(default_factory=lambda: os.getenv("QIANCHUAN_APP_SECRET", ""))
    qianchuan_access_token: str = field(default_factory=lambda: os.getenv("QIANCHUAN_ACCESS_TOKEN", ""))
    qianchuan_refresh_token: str = field(default_factory=lambda: os.getenv("QIANCHUAN_REFRESH_TOKEN", ""))
    qianchuan_auth_code: str = field(default_factory=lambda: os.getenv("QIANCHUAN_AUTH_CODE", ""))
    qianchuan_advertiser_id: str = field(default_factory=lambda: os.getenv("QIANCHUAN_ADVERTISER_ID", ""))
    oceanengine_api_url: str = field(default_factory=lambda: os.getenv("OCEANENGINE_API_URL", "https://api.oceanengine.com"))
    oceanengine_auth_api_url: str = field(default_factory=lambda: os.getenv("OCEANENGINE_AUTH_API_URL", "https://ad.oceanengine.com"))

    wechat_channels_app_id: str = field(default_factory=lambda: os.getenv("WECHAT_CHANNELS_APP_ID", ""))
    wechat_channels_app_secret: str = field(default_factory=lambda: os.getenv("WECHAT_CHANNELS_APP_SECRET", ""))
    wechat_channels_access_token: str = field(default_factory=lambda: os.getenv("WECHAT_CHANNELS_ACCESS_TOKEN", ""))
    wechat_channels_api_url: str = field(default_factory=lambda: os.getenv("WECHAT_CHANNELS_API_URL", "https://api.weixin.qq.com"))

    jushuitan_partner_id: str = field(default_factory=lambda: os.getenv("JUSHUITAN_PARTNER_ID", ""))
    jushuitan_partner_key: str = field(default_factory=lambda: os.getenv("JUSHUITAN_PARTNER_KEY", ""))
    jushuitan_token: str = field(default_factory=lambda: os.getenv("JUSHUITAN_TOKEN", ""))
    jushuitan_api_url: str = field(default_factory=lambda: os.getenv("JUSHUITAN_API_URL", "https://open.erp321.com/api/open/query.aspx"))
    jushuitan_order_query_method: str = field(default_factory=lambda: os.getenv("JUSHUITAN_ORDER_QUERY_METHOD", "orders.single.query"))
    jushuitan_influencer_query_method: str = field(default_factory=lambda: os.getenv("JUSHUITAN_INFLUENCER_QUERY_METHOD", "doudian.alliance.kol.orders.query"))
    jushuitan_shop_ids: str = field(default_factory=lambda: os.getenv("JUSHUITAN_SHOP_IDS", ""))
    jushuitan_douyin_shop_id: str = field(default_factory=lambda: os.getenv("JUSHUITAN_SHOP_ID_DOUYIN", ""))
    jushuitan_page_size: int = field(default_factory=lambda: int(os.getenv("JUSHUITAN_PAGE_SIZE", "100")))
    jushuitan_qimen_url: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_URL", "http://a1q40taq0j.api.taobao.com/router/qm"))
    jushuitan_qimen_app_key: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_APP_KEY", ""))
    jushuitan_qimen_app_secret: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_APP_SECRET", ""))
    jushuitan_qimen_customer_id: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_CUSTOMER_ID", ""))
    jushuitan_qimen_session: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_SESSION", ""))
    jushuitan_qimen_target_app_key: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_TARGET_APP_KEY", "23060081"))
    jushuitan_qimen_order_list_method: str = field(default_factory=lambda: os.getenv("JUSHUITAN_QIMEN_ORDER_LIST_METHOD", "jushuitan.order.list.query"))

    feishu_app_id: str = field(default_factory=lambda: os.getenv("FEISHU_APP_ID") or os.getenv("APP_ID", ""))
    feishu_app_secret: str = field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET") or os.getenv("APP_SECRET", ""))
    feishu_app_token: str = field(default_factory=lambda: os.getenv("FEISHU_APP_TOKEN") or os.getenv("APP_TOKEN", ""))
    feishu_webhook: str = field(default_factory=lambda: os.getenv("FEISHU_WEBHOOK", ""))
    feishu_platform_name: str = field(default_factory=lambda: os.getenv("FEISHU_PLATFORM_NAME", "千牛淘宝"))

    shopops_data_center_app_token: str = field(default_factory=lambda: os.getenv("SHOPOPS_DATA_CENTER_APP_TOKEN") or os.getenv("FEISHU_APP_TOKEN") or os.getenv("APP_TOKEN", ""))
    shopops_order_table_id: str = field(default_factory=lambda: os.getenv("SHOPOPS_ORDER_TABLE_ID") or os.getenv("FEISHU_TABLE_ORDERS_RAW", ""))
    shopops_ad_table_id: str = field(default_factory=lambda: os.getenv("SHOPOPS_AD_TABLE_ID") or os.getenv("FEISHU_TABLE_PROMOTION_SNAPSHOT", ""))
    shopops_summary_table_id: str = field(default_factory=lambda: os.getenv("SHOPOPS_SUMMARY_TABLE_ID", ""))

    table_system_config: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_SYSTEM_CONFIG", "system_config"))
    table_shop_config: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_SHOP_CONFIG", "shop_config"))
    table_monitor_snapshot: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_MONITOR_SNAPSHOT", "monitor_snapshot"))
    table_orders_raw: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_ORDERS_RAW", "orders_raw"))
    table_promotion_snapshot: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_PROMOTION_SNAPSHOT", "promotion_snapshot"))
    table_metrics_10min: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_METRICS_10MIN", "metrics_10min"))
    table_task_log: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_TASK_LOG", "task_run_log"))
    table_alert_log: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_ALERT_LOG", "alert_log"))
    table_daily_report: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_DAILY_REPORT", "daily_report"))
    table_douyin_influencer_commission: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION", "douyin_influencer_commission"))
    table_system_config_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_SYSTEM_CONFIG_NAME", "系统配置表"))
    table_shop_config_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_SHOP_CONFIG_NAME", "店铺配置表"))
    table_monitor_snapshot_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_MONITOR_SNAPSHOT_NAME", "实时监控快照表"))
    table_orders_raw_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_ORDERS_RAW_NAME", "订单明细原始表"))
    table_promotion_snapshot_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_PROMOTION_SNAPSHOT_NAME", "推广数据表"))
    table_metrics_10min_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_METRICS_10MIN_NAME", "十分钟指标表"))
    table_task_log_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_TASK_LOG_NAME", "任务运行日志表"))
    table_alert_log_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_ALERT_LOG_NAME", "告警日志表"))
    table_daily_report_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_DAILY_REPORT_NAME", "每日报告表"))
    table_douyin_influencer_commission_name: str = field(default_factory=lambda: os.getenv("FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION_NAME", "抖音达人佣金明细表"))

    local_feishu_path: str = field(default_factory=lambda: os.getenv("LOCAL_FEISHU_PATH", "cache/local_feishu.json"))
    pending_records_path: str = field(default_factory=lambda: os.getenv("PENDING_RECORDS_PATH", "cache/pending_records.jsonl"))

    alert_total_cost: float = field(default_factory=lambda: float(os.getenv("ALERT_TOTAL_COST", "500")))
    alert_min_roi: float = field(default_factory=lambda: float(os.getenv("ALERT_MIN_ROI", "1.0")))
    alert_order_drop_rate: float = field(default_factory=lambda: float(os.getenv("ALERT_ORDER_DROP_RATE", "0.5")))
    alert_dedup_minutes: int = field(default_factory=lambda: int(os.getenv("ALERT_DEDUP_MINUTES", "30")))
    daily_report_time: str = field(default_factory=lambda: os.getenv("DAILY_REPORT_TIME", "23:50"))

    def validate_business(self) -> None:
        if self.order_source not in {"api", "crawler", "jushuitan"}:
            raise ValueError("ORDER_SOURCE must be api, crawler, or jushuitan")
        if self.shop_platform not in {"taobao", "pinduoduo", "doudian", "wechat_channels"}:
            raise ValueError("SHOP_PLATFORM must be taobao, pinduoduo, doudian, or wechat_channels")
        if self.order_source == "crawler" and self.shop_platform != "taobao":
            raise ValueError("ORDER_SOURCE=crawler is only supported for SHOP_PLATFORM=taobao")
        if self.promotion_source != "qianniu_pc":
            raise ValueError("MVP PROMOTION_SOURCE must be qianniu_pc")
        if self.storage_backend not in {"local", "feishu"}:
            raise ValueError("STORAGE_BACKEND must be local or feishu")

    @property
    def table_ids(self) -> dict[str, str]:
        return {
            "system_config": self.table_system_config,
            "shop_config": self.table_shop_config,
            "monitor_snapshot": self.table_monitor_snapshot,
            "orders_raw": self.table_orders_raw,
            "promotion_snapshot": self.table_promotion_snapshot,
            "metrics_10min": self.table_metrics_10min,
            "task_run_log": self.table_task_log,
            "alert_log": self.table_alert_log,
            "daily_report": self.table_daily_report,
            "douyin_influencer_commission": self.table_douyin_influencer_commission,
        }

    @property
    def table_display_names(self) -> dict[str, str]:
        return {
            "system_config": self.table_system_config_name,
            "shop_config": self.table_shop_config_name,
            "monitor_snapshot": self.table_monitor_snapshot_name,
            "orders_raw": self.table_orders_raw_name,
            "promotion_snapshot": self.table_promotion_snapshot_name,
            "metrics_10min": self.table_metrics_10min_name,
            "task_run_log": self.table_task_log_name,
            "alert_log": self.table_alert_log_name,
            "daily_report": self.table_daily_report_name,
            "douyin_influencer_commission": self.table_douyin_influencer_commission_name,
        }


def load_settings() -> Settings:
    _load_dotenv()
    settings = Settings()
    settings.validate_business()
    return settings
