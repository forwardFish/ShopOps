# 淘宝单平台 MVP 开发文档

版本：v1.0  
日期：2026-06-02  
技术栈：Python 3.10+、Playwright、淘宝开放平台 SDK、飞书 OpenAPI、多维表格、飞书机器人  
目标：开发人员按本文档实现，即可完成淘宝单平台 MVP。

---

## 1. 技术架构

```text
.env / 飞书配置表
        ↓
Scheduler 调度器
        ↓
┌────────────────────────────┐
│ Collector 采集层            │
│ - TaobaoOrderApiCollector   │
│ - TaobaoOrderCrawler        │
│ - TaobaoPromotionCrawler    │
└─────────────┬──────────────┘
              ↓
┌────────────────────────────┐
│ Normalizer 标准化层         │
│ - 订单统一格式              │
│ - 推广费用统一格式          │
└─────────────┬──────────────┘
              ↓
┌────────────────────────────┐
│ MetricService 指标计算      │
│ - 今日累计指标              │
│ - 周期增量指标              │
└─────────────┬──────────────┘
              ↓
┌────────────────────────────┐
│ Storage 抽象层              │
│ - 当前 FeishuBitableStorage │
│ - 未来 DatabaseStorage      │
└─────────────┬──────────────┘
              ↓
┌────────────────────────────┐
│ AlertService 告警层         │
│ - 飞书机器人                │
│ - 告警日志                  │
└────────────────────────────┘
```

---

## 2. 工程目录

```text
taobao-monitor-mvp/
├── README.md
├── requirements.txt
├── .env.example
├── main.py
├── config.py
├── models.py
├── scheduler.py
├── collectors/
│   ├── __init__.py
│   ├── base.py
│   ├── taobao_order_api.py
│   ├── taobao_order_crawler.py
│   └── taobao_promotion_crawler.py
├── services/
│   ├── __init__.py
│   ├── browser_service.py
│   ├── metric_service.py
│   ├── alert_service.py
│   ├── daily_report_service.py
│   └── task_log_service.py
├── storage/
│   ├── __init__.py
│   ├── base.py
│   ├── feishu_storage.py
│   └── database_storage.py
├── utils/
│   ├── __init__.py
│   ├── time_utils.py
│   ├── money_utils.py
│   ├── retry_utils.py
│   └── json_utils.py
├── logs/
│   └── .gitkeep
├── cache/
│   └── pending_records.jsonl
└── tests/
    ├── test_metric_service.py
    ├── test_money_utils.py
    └── test_storage_mapping.py
```

---

## 3. 依赖安装

### 3.1 `requirements.txt`

```txt
playwright>=1.44.0
requests>=2.31.0
python-dotenv>=1.0.1
pydantic>=2.7.0
tenacity>=8.2.3
loguru>=0.7.2
lark-oapi>=1.2.0
top-sdk-python
pytest>=8.0.0
```

安装：

```bash
pip install -r requirements.txt
playwright install chromium
```

注意：本项目通过 CDP 连接千牛 PC 客户端，不主动启动外部浏览器。`playwright install chromium` 主要用于安装 Playwright 依赖。

---

## 4. 环境变量

### 4.1 `.env.example`

```env
APP_ENV=local
SHOP_ID=taobao_shop_001
SHOP_NAME=淘宝店铺A

ORDER_SOURCE=crawler
PROMOTION_SOURCE=qianniu_pc
FETCH_INTERVAL_SECONDS=600

# 当前阶段使用千牛 PC 页面采集，淘宝 API 信息可留空。
# 后续切换 ORDER_SOURCE=api 时再填写。
TAOBAO_APP_KEY=
TAOBAO_APP_SECRET=
TAOBAO_SESSION_KEY=

QIANNIU_CDP_URL=http://127.0.0.1:9222

FEISHU_APP_ID=your_feishu_app_id
FEISHU_APP_SECRET=your_feishu_app_secret
FEISHU_APP_TOKEN=your_bitable_app_token
FEISHU_WEBHOOK=your_feishu_robot_webhook

FEISHU_TABLE_SYSTEM_CONFIG=tbl_xxx
FEISHU_TABLE_SHOP_CONFIG=tbl_xxx
FEISHU_TABLE_MONITOR_SNAPSHOT=tbl_xxx
FEISHU_TABLE_ORDERS_RAW=tbl_xxx
FEISHU_TABLE_PROMOTION_SNAPSHOT=tbl_xxx
FEISHU_TABLE_METRICS_10MIN=tbl_xxx
FEISHU_TABLE_TASK_LOG=tbl_xxx
FEISHU_TABLE_ALERT_LOG=tbl_xxx
FEISHU_TABLE_DAILY_REPORT=tbl_xxx

ALERT_TOTAL_COST=500
ALERT_MIN_ROI=1.0
ALERT_ORDER_DROP_RATE=0.5
ALERT_DEDUP_MINUTES=30
DAILY_REPORT_TIME=23:50
```

---

## 5. 配置模块

### 5.1 `config.py`

```python
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    app_env: str = Field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    shop_id: str = Field(default_factory=lambda: os.getenv("SHOP_ID", "taobao_shop_001"))
    shop_name: str = Field(default_factory=lambda: os.getenv("SHOP_NAME", "淘宝店铺A"))

    order_source: str = Field(default_factory=lambda: os.getenv("ORDER_SOURCE", "crawler"))
    promotion_source: str = Field(default_factory=lambda: os.getenv("PROMOTION_SOURCE", "qianniu_pc"))
    fetch_interval_seconds: int = Field(default_factory=lambda: int(os.getenv("FETCH_INTERVAL_SECONDS", "600")))

    taobao_app_key: str = Field(default_factory=lambda: os.getenv("TAOBAO_APP_KEY", ""))
    taobao_app_secret: str = Field(default_factory=lambda: os.getenv("TAOBAO_APP_SECRET", ""))
    taobao_session_key: str = Field(default_factory=lambda: os.getenv("TAOBAO_SESSION_KEY", ""))

    qianniu_cdp_url: str = Field(default_factory=lambda: os.getenv("QIANNIU_CDP_URL", "http://127.0.0.1:9222"))

    feishu_app_id: str = Field(default_factory=lambda: os.getenv("FEISHU_APP_ID", ""))
    feishu_app_secret: str = Field(default_factory=lambda: os.getenv("FEISHU_APP_SECRET", ""))
    feishu_app_token: str = Field(default_factory=lambda: os.getenv("FEISHU_APP_TOKEN", ""))
    feishu_webhook: str = Field(default_factory=lambda: os.getenv("FEISHU_WEBHOOK", ""))

    table_system_config: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_SYSTEM_CONFIG", ""))
    table_shop_config: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_SHOP_CONFIG", ""))
    table_monitor_snapshot: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_MONITOR_SNAPSHOT", ""))
    table_orders_raw: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_ORDERS_RAW", ""))
    table_promotion_snapshot: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_PROMOTION_SNAPSHOT", ""))
    table_metrics_10min: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_METRICS_10MIN", ""))
    table_task_log: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_TASK_LOG", ""))
    table_alert_log: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_ALERT_LOG", ""))
    table_daily_report: str = Field(default_factory=lambda: os.getenv("FEISHU_TABLE_DAILY_REPORT", ""))

    alert_total_cost: float = Field(default_factory=lambda: float(os.getenv("ALERT_TOTAL_COST", "500")))
    alert_min_roi: float = Field(default_factory=lambda: float(os.getenv("ALERT_MIN_ROI", "1.0")))
    alert_order_drop_rate: float = Field(default_factory=lambda: float(os.getenv("ALERT_ORDER_DROP_RATE", "0.5")))
    alert_dedup_minutes: int = Field(default_factory=lambda: int(os.getenv("ALERT_DEDUP_MINUTES", "30")))
    daily_report_time: str = Field(default_factory=lambda: os.getenv("DAILY_REPORT_TIME", "23:50"))

    def validate_business(self):
        if self.order_source not in {"api", "crawler"}:
            raise ValueError("ORDER_SOURCE 只能是 api 或 crawler")
        if self.promotion_source != "qianniu_pc":
            raise ValueError("MVP 阶段 PROMOTION_SOURCE 只能是 qianniu_pc")

settings = Settings()
settings.validate_business()
```

---

## 6. 数据模型

### 6.1 `models.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Literal
import uuid

OrderSource = Literal["api", "crawler"]
CollectStatus = Literal["success", "failed", "partial_success", "login_required", "permission_denied", "skipped"]

@dataclass
class OrderCollectResult:
    success: bool
    source: OrderSource
    shop_id: str
    shop_name: str
    order_count: Optional[int]
    paid_order_count: Optional[int]
    total_amount: Optional[float]
    fetched_at: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Optional[Any] = None
    orders: list[dict] = field(default_factory=list)

@dataclass
class PromotionItem:
    channel: str
    channel_name: str
    cost: Optional[float]
    impressions: Optional[int]
    clicks: Optional[int]
    conversions: Optional[int]
    status: CollectStatus
    error_message: Optional[str] = None
    raw: Optional[Any] = None

@dataclass
class PromotionCollectResult:
    success: bool
    status: CollectStatus
    source: str
    shop_id: str
    shop_name: str
    items: list[PromotionItem]
    total_cost: Optional[float]
    fetched_at: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None

@dataclass
class MonitorSnapshot:
    unique_key: str
    fetched_at: datetime
    shop_id: str
    shop_name: str
    order_source: str
    promotion_source: str
    data_status: str
    promotion_center_cost: Optional[float]
    total_cost: Optional[float]
    order_count: Optional[int]
    paid_order_count: Optional[int]
    total_amount: Optional[float]
    roi: Optional[float]
    cac: Optional[float]
    error_message: Optional[str]
    alert_flag: bool = False

@dataclass
class Metric10Min:
    unique_key: str
    window_start: datetime
    window_end: datetime
    shop_id: str
    shop_name: str
    delta_order_count: Optional[int]
    delta_total_amount: Optional[float]
    delta_cost: Optional[float]
    delta_roi: Optional[float]
    delta_cac: Optional[float]
    data_status: str
    abnormal_reason: Optional[str]

@dataclass
class TaskRunLog:
    task_id: str
    task_type: str
    started_at: datetime
    ended_at: Optional[datetime]
    duration_seconds: Optional[float]
    shop_id: str
    order_status: str
    promotion_status: str
    storage_status: str
    total_status: str
    fetched_count: int = 0
    saved_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    alerted: bool = False

    @staticmethod
    def new(task_type: str, shop_id: str) -> "TaskRunLog":
        return TaskRunLog(
            task_id=str(uuid.uuid4()),
            task_type=task_type,
            started_at=datetime.now(),
            ended_at=None,
            duration_seconds=None,
            shop_id=shop_id,
            order_status="skipped",
            promotion_status="skipped",
            storage_status="skipped",
            total_status="running",
        )
```

---

## 7. 采集器接口

### 7.1 `collectors/base.py`

```python
from abc import ABC, abstractmethod
from datetime import datetime
from models import OrderCollectResult, PromotionCollectResult

class OrderCollector(ABC):
    @abstractmethod
    def fetch_today(self) -> OrderCollectResult:
        pass

class PromotionCollector(ABC):
    @abstractmethod
    def fetch_today(self) -> PromotionCollectResult:
        pass
```

---

## 8. 千牛 PC 浏览器服务

### 8.1 设计要求

1. 每次任务开始先检查 CDP 是否可连接；
2. 无法连接时直接返回 `qianniu_not_running`；
3. 登录失效时返回 `login_required`；
4. 验证码、短信、扫码、权限不足时不继续采集；
5. 不做任何绕过验证的动作。

### 8.2 `services/browser_service.py`

```python
import requests
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Browser, Page

class BrowserService:
    def __init__(self, cdp_url: str):
        self.cdp_url = cdp_url.rstrip("/")

    def check_cdp_available(self) -> tuple[bool, str | None]:
        try:
            resp = requests.get(f"{self.cdp_url}/json/version", timeout=3)
            if resp.status_code == 200:
                return True, None
            return False, f"CDP HTTP 状态异常：{resp.status_code}"
        except Exception as e:
            return False, f"无法连接千牛 CDP：{e}"

    @contextmanager
    def page(self):
        ok, err = self.check_cdp_available()
        if not ok:
            raise RuntimeError(err)

        with sync_playwright() as p:
            browser: Browser = p.chromium.connect_over_cdp(self.cdp_url)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page: Page = context.new_page()
            try:
                yield page
            finally:
                try:
                    page.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass

    @staticmethod
    def detect_login_problem(page: Page) -> tuple[bool, str | None]:
        url = page.url.lower()
        text = ""
        try:
            text = page.locator("body").inner_text(timeout=3000)
        except Exception:
            pass

        keywords = ["登录", "扫码", "验证码", "无权限", "权限不足", "请验证", "安全验证"]
        if "login" in url:
            return True, "login_required"
        if any(k in text for k in keywords):
            if "无权限" in text or "权限不足" in text:
                return True, "permission_denied"
            return True, "login_required"
        return False, None
```

---

## 9. 淘宝订单 API 采集器

### 9.1 要求

1. 必须分页；
2. 必须过滤未付款；
3. 失败不能返回 0；
4. 可保存订单原始数据。

### 9.2 `collectors/taobao_order_api.py`

```python
from datetime import datetime
import top.api
import top
from collectors.base import OrderCollector
from models import OrderCollectResult
from config import settings

class TaobaoOrderApiCollector(OrderCollector):
    def fetch_today(self) -> OrderCollectResult:
        fetched_at = datetime.now()
        try:
            all_trades: list[dict] = []
            page_no = 1
            page_size = 100
            today_start = fetched_at.replace(hour=0, minute=0, second=0, microsecond=0)

            while True:
                req = top.api.TradesSoldGetRequest()
                req.set_app_info(top.appinfo(settings.taobao_app_key, settings.taobao_app_secret))
                req.start_created = today_start.strftime("%Y-%m-%d %H:%M:%S")
                req.end_created = fetched_at.strftime("%Y-%m-%d %H:%M:%S")
                req.fields = "tid,payment,status,created,pay_time"
                req.page_size = page_size
                req.page_no = page_no

                resp = req.getResponse(settings.taobao_session_key)
                body = resp.get("trades_sold_get_response", {})
                trades = body.get("trades", {}).get("trade", []) or []
                all_trades.extend(trades)

                if len(trades) < page_size:
                    break
                page_no += 1

            paid_trades = [t for t in all_trades if t.get("status") != "WAIT_BUYER_PAY"]
            total_amount = sum(float(t.get("payment") or 0) for t in paid_trades)

            normalized_orders = []
            for t in paid_trades:
                order_id = str(t.get("tid"))
                normalized_orders.append({
                    "unique_key": f"taobao_{settings.shop_id}_{order_id}",
                    "数据来源": "api",
                    "店铺ID": settings.shop_id,
                    "店铺名称": settings.shop_name,
                    "订单号": order_id,
                    "下单时间": t.get("created"),
                    "支付时间": t.get("pay_time"),
                    "订单状态": t.get("status"),
                    "支付金额": float(t.get("payment") or 0),
                    "商品名称": "",
                    "采集时间": fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "原始数据": str(t),
                })

            return OrderCollectResult(
                success=True,
                source="api",
                shop_id=settings.shop_id,
                shop_name=settings.shop_name,
                order_count=len(paid_trades),
                paid_order_count=len(paid_trades),
                total_amount=round(total_amount, 2),
                fetched_at=fetched_at,
                raw={"total": len(all_trades)},
                orders=normalized_orders,
            )
        except Exception as e:
            return OrderCollectResult(
                success=False,
                source="api",
                shop_id=settings.shop_id,
                shop_name=settings.shop_name,
                order_count=None,
                paid_order_count=None,
                total_amount=None,
                fetched_at=fetched_at,
                error_code="order_api_failed",
                error_message=str(e),
            )
```

---

## 10. 淘宝订单页面采集器

当前阶段订单只从千牛 PC 客户端内的订单中心页面采集，不使用普通浏览器或千牛网页版。采集器需要读取订单列表中的所有可见订单数据，并支持翻页或滚动加载。

订单中心单条订单至少映射以下字段：

| 页面字段 | 存储字段 | 说明 |
|---|---|---|
| 订单号 | 订单号 | 例如 `3306183637220018070` |
| 创建时间 | 下单时间 | 页面显示的创建时间 |
| 宝贝标题 | 商品名称 | 同一订单多商品时可用 JSON 数组保存 |
| 单价 | 单价 | 页面展示单价 |
| 数量 | 数量 | 页面展示数量 |
| 履约/售后状态 | 履约/售后状态 | 例如退款成功、发货未超时 |
| 交易状态 | 订单状态 | 例如买家已付款、交易关闭 |
| 实收款 | 支付金额 | 页面展示实收款 |
| 操作区文本 | 操作信息 | 例如详情、寄件、打单、发货等 |

聚合指标从订单明细计算：今日订单数按订单号去重；今日成交额优先统计买家已付款、交易成功等有效支付订单的实收款，退款成功、交易关闭等状态不参与成交额，具体状态映射保留配置化。

### 10.1 `collectors/taobao_order_crawler.py`

```python
from datetime import datetime
from collectors.base import OrderCollector
from models import OrderCollectResult
from config import settings
from services.browser_service import BrowserService

class TaobaoOrderCrawler(OrderCollector):
    def __init__(self, browser_service: BrowserService):
        self.browser_service = browser_service

    def fetch_today(self) -> OrderCollectResult:
        fetched_at = datetime.now()
        try:
            with self.browser_service.page() as page:
                # 该地址必须由千牛 PC 客户端内页面承载；不要改成普通浏览器或千牛网页版采集。
                page.goto("https://trade.taobao.com/trade/itemlist/list_sold_items.htm", timeout=30000)
                page.wait_for_timeout(3000)

                has_problem, code = self.browser_service.detect_login_problem(page)
                if has_problem:
                    return self._failed(fetched_at, code, f"订单页面采集失败：{code}")

                rows = self._collect_all_order_rows(page)
                paid_rows = [r for r in rows if r.get("订单状态") in {"买家已付款", "交易成功"}]
                total_amount = sum(float(r.get("支付金额") or 0) for r in paid_rows)

                return OrderCollectResult(
                    success=True,
                    source="crawler",
                    shop_id=settings.shop_id,
                    shop_name=settings.shop_name,
                    order_count=len({r["订单号"] for r in rows if r.get("订单号")}),
                    paid_order_count=len({r["订单号"] for r in paid_rows if r.get("订单号")}),
                    total_amount=round(total_amount, 2),
                    fetched_at=fetched_at,
                    raw={"row_count": len(rows)},
                    orders=rows,
                )
        except Exception as e:
            return self._failed(fetched_at, "order_crawler_failed", str(e))

    def _collect_all_order_rows(self, page) -> list[dict]:
        # 选择器需要在首店调试时确认，并挪到配置表或 selector 配置文件。
        # 这里表达实现要求：必须遍历分页/滚动加载后的全部订单，不得只抓首屏。
        rows = []
        while True:
            order_cards = page.locator("[data-order-id], .order-item")
            for index in range(order_cards.count()):
                card = order_cards.nth(index)
                order_id = self._text(card, "text=订单号").replace("订单号：", "").strip()
                rows.append({
                    "unique_key": f"taobao_{settings.shop_id}_{order_id}",
                    "数据来源": "crawler",
                    "店铺ID": settings.shop_id,
                    "店铺名称": settings.shop_name,
                    "订单号": order_id,
                    "下单时间": self._text(card, "text=创建时间").replace("创建时间：", "").strip(),
                    "商品名称": self._text(card, ".item-title, a[href*='item']"),
                    "单价": self._money(self._text(card, ".price, text=/¥/")),
                    "数量": self._int(self._text(card, ".quantity")),
                    "履约/售后状态": self._text(card, ".refund-status, .service-status"),
                    "订单状态": self._text(card, ".trade-status, .order-status"),
                    "支付金额": self._money(self._text(card, ".actual-paid, .amount, text=/¥/")),
                    "操作信息": self._text(card, ".operations"),
                    "采集时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "原始数据": card.inner_text(timeout=3000),
                })

            next_button = page.locator("button:has-text('下一页'), a:has-text('下一页')").first
            if next_button.count() == 0 or next_button.is_disabled():
                break
            next_button.click()
            page.wait_for_timeout(1500)
        return rows

    def _text(self, root, selector: str) -> str:
        try:
            return root.locator(selector).first.inner_text(timeout=2000).strip()
        except Exception:
            return ""

    def _money(self, text: str) -> float | None:
        cleaned = text.replace("¥", "").replace(",", "").replace("￥", "").strip()
        try:
            return float(cleaned)
        except Exception:
            return None

    def _int(self, text: str) -> int | None:
        digits = "".join(filter(str.isdigit, text))
        return int(digits) if digits else None

    def _failed(self, fetched_at, code, msg):
        return OrderCollectResult(
            success=False,
            source="crawler",
            shop_id=settings.shop_id,
            shop_name=settings.shop_name,
            order_count=None,
            paid_order_count=None,
            total_amount=None,
            fetched_at=fetched_at,
            error_code=code,
            error_message=msg,
        )
```

---

## 11. 淘宝推广费用采集器

### 11.1 设计

当前阶段只采集千牛 PC 客户端推广中心页面的经营概览“花费”指标。示例页面地址形态：

```text
https://qn.taobao.com/home.htm/tuiguangcenter_new/
```

不采集曝光量、点击量、投入产出比、总成交金额等其他指标；这些字段在模型中保留为空，便于后续扩展。

### 11.2 `collectors/taobao_promotion_crawler.py`

```python
from datetime import datetime
from collectors.base import PromotionCollector
from models import PromotionCollectResult, PromotionItem
from config import settings
from services.browser_service import BrowserService

PROMOTION_CENTER = {
    "channel": "tuiguangcenter",
    "channel_name": "推广中心",
    "url": "https://qn.taobao.com/home.htm/tuiguangcenter_new/",
    "cost_label": "花费",
}

class TaobaoPromotionCrawler(PromotionCollector):
    def __init__(self, browser_service: BrowserService):
        self.browser_service = browser_service

    def fetch_today(self) -> PromotionCollectResult:
        fetched_at = datetime.now()

        try:
            with self.browser_service.page() as page:
                item = self._fetch_promotion_center_cost(page)
        except Exception as e:
            return PromotionCollectResult(
                success=False,
                status="failed",
                source="qianniu_pc",
                shop_id=settings.shop_id,
                shop_name=settings.shop_name,
                items=[],
                total_cost=None,
                fetched_at=fetched_at,
                error_code="qianniu_cdp_failed",
                error_message=str(e),
            )

        success = item.status == "success"
        status = "success" if success else item.status

        return PromotionCollectResult(
            success=success,
            status=status,
            source="qianniu_pc",
            shop_id=settings.shop_id,
            shop_name=settings.shop_name,
            items=[item],
            total_cost=round(item.cost, 2) if item.cost is not None else None,
            fetched_at=fetched_at,
            error_message=item.error_message,
        )

    def _fetch_promotion_center_cost(self, page) -> PromotionItem:
        try:
            # 该地址必须由千牛 PC 客户端内页面承载；不要改成普通浏览器采集。
            page.goto(PROMOTION_CENTER["url"], timeout=30000)
            page.wait_for_timeout(3000)

            has_problem, code = self.browser_service.detect_login_problem(page)
            if has_problem:
                return PromotionItem(
                    channel=PROMOTION_CENTER["channel"],
                    channel_name=PROMOTION_CENTER["channel_name"],
                    cost=None,
                    impressions=None,
                    clicks=None,
                    conversions=None,
                    status=code,
                    error_message=f"推广中心页面状态异常：{code}",
                )

            # 首店调试时需要确认稳定选择器。当前要求是读取经营概览区域中“花费”下方的数值。
            cost_text = page.locator("text=花费").locator("xpath=following::*[1]").first.text_content(timeout=8000).strip()
            cost = float(cost_text.replace("¥", "").replace(",", "").strip())

            return PromotionItem(
                channel=PROMOTION_CENTER["channel"],
                channel_name=PROMOTION_CENTER["channel_name"],
                cost=round(cost, 2),
                impressions=None,
                clicks=None,
                conversions=None,
                status="success",
                raw={"metric": "花费", "cost_text": cost_text},
            )
        except Exception as e:
            return PromotionItem(
                channel=PROMOTION_CENTER["channel"],
                channel_name=PROMOTION_CENTER["channel_name"],
                cost=None,
                impressions=None,
                clicks=None,
                conversions=None,
                status="failed",
                error_message=f"推广中心花费采集失败：{e}",
            )
```

---

## 12. 指标计算服务

### 12.1 `services/metric_service.py`

```python
from datetime import datetime
from models import OrderCollectResult, PromotionCollectResult, MonitorSnapshot, Metric10Min
from config import settings

class MetricService:
    @staticmethod
    def build_snapshot(order: OrderCollectResult, promotion: PromotionCollectResult) -> MonitorSnapshot:
        data_status = MetricService._get_data_status(order, promotion)

        channel_cost = {i.channel: i.cost for i in promotion.items} if promotion.items else {}
        total_cost = promotion.total_cost if promotion.success else None
        total_amount = order.total_amount if order.success else None
        order_count = order.order_count if order.success else None
        paid_order_count = order.paid_order_count if order.success else None

        roi = round(total_amount / total_cost, 2) if total_amount is not None and total_cost and total_cost > 0 else None
        cac = round(total_cost / order_count, 2) if total_cost is not None and order_count and order_count > 0 else None

        fetched_at = datetime.now()
        key_time = fetched_at.strftime("%Y%m%d%H%M")

        errors = []
        if order.error_message:
            errors.append(order.error_message)
        if promotion.error_message:
            errors.append(promotion.error_message)

        return MonitorSnapshot(
            unique_key=f"{settings.shop_id}_{key_time}",
            fetched_at=fetched_at,
            shop_id=settings.shop_id,
            shop_name=settings.shop_name,
            order_source=order.source,
            promotion_source=promotion.source,
            data_status=data_status,
            promotion_center_cost=channel_cost.get("tuiguangcenter"),
            total_cost=total_cost,
            order_count=order_count,
            paid_order_count=paid_order_count,
            total_amount=total_amount,
            roi=roi,
            cac=cac,
            error_message="; ".join(errors) if errors else None,
        )

    @staticmethod
    def _get_data_status(order, promotion) -> str:
        if not order.success:
            return "order_failed"
        if promotion.status == "failed":
            return "promotion_failed"
        return "normal"

    @staticmethod
    def build_delta(current: MonitorSnapshot, previous: MonitorSnapshot | None) -> Metric10Min:
        if previous is None:
            return Metric10Min(
                unique_key=f"{current.shop_id}_{current.fetched_at.strftime('%Y%m%d%H%M')}_no_prev",
                window_start=current.fetched_at,
                window_end=current.fetched_at,
                shop_id=current.shop_id,
                shop_name=current.shop_name,
                delta_order_count=None,
                delta_total_amount=None,
                delta_cost=None,
                delta_roi=None,
                delta_cac=None,
                data_status="missing_previous",
                abnormal_reason="无上一条快照，无法计算增量",
            )

        def delta(cur, prev):
            if cur is None or prev is None:
                return None
            value = cur - prev
            return round(value, 2) if isinstance(value, float) else value

        d_order = delta(current.order_count, previous.order_count)
        d_amount = delta(current.total_amount, previous.total_amount)
        d_cost = delta(current.total_cost, previous.total_cost)

        invalid_reasons = []
        if d_order is not None and d_order < 0:
            invalid_reasons.append("订单数小于上一快照")
        if d_amount is not None and d_amount < 0:
            invalid_reasons.append("成交额小于上一快照")
        if d_cost is not None and d_cost < 0:
            invalid_reasons.append("推广消耗小于上一快照")

        if invalid_reasons:
            status = "invalid"
            delta_roi = None
            delta_cac = None
        else:
            status = "normal"
            delta_roi = round(d_amount / d_cost, 2) if d_amount is not None and d_cost and d_cost > 0 else None
            delta_cac = round(d_cost / d_order, 2) if d_cost is not None and d_order and d_order > 0 else None

        return Metric10Min(
            unique_key=f"{current.shop_id}_{previous.fetched_at.strftime('%Y%m%d%H%M')}_{current.fetched_at.strftime('%Y%m%d%H%M')}",
            window_start=previous.fetched_at,
            window_end=current.fetched_at,
            shop_id=current.shop_id,
            shop_name=current.shop_name,
            delta_order_count=d_order,
            delta_total_amount=d_amount,
            delta_cost=d_cost,
            delta_roi=delta_roi,
            delta_cac=delta_cac,
            data_status=status,
            abnormal_reason="; ".join(invalid_reasons) if invalid_reasons else None,
        )
```

---

## 13. Storage 抽象层

### 13.1 `storage/base.py`

```python
from abc import ABC, abstractmethod
from models import MonitorSnapshot, Metric10Min, TaskRunLog

class Storage(ABC):
    @abstractmethod
    def save_orders_raw(self, orders: list[dict]) -> int:
        pass

    @abstractmethod
    def save_promotion_snapshot(self, items: list[dict]) -> int:
        pass

    @abstractmethod
    def save_monitor_snapshot(self, snapshot: MonitorSnapshot) -> int:
        pass

    @abstractmethod
    def get_last_monitor_snapshot(self, shop_id: str) -> MonitorSnapshot | None:
        pass

    @abstractmethod
    def save_metric_10min(self, metric: Metric10Min) -> int:
        pass

    @abstractmethod
    def save_task_log(self, log: TaskRunLog) -> int:
        pass

    @abstractmethod
    def save_alert_log(self, alert: dict) -> int:
        pass
```

---

## 14. 飞书存储实现

### 14.1 设计要求

飞书不是数据库，没有天然 `ON CONFLICT UPDATE`。所以需要做伪 upsert：

1. 根据 `unique_key` 查询记录；
2. 存在则更新；
3. 不存在则新增；
4. 查询失败或写入失败时写本地缓存；
5. 下次任务补写。

### 14.2 字段映射

`MonitorSnapshot` → `monitor_snapshot`：

```python
{
    "unique_key": snapshot.unique_key,
    "采集时间": snapshot.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
    "店铺ID": snapshot.shop_id,
    "店铺名称": snapshot.shop_name,
    "订单来源": snapshot.order_source,
    "推广来源": snapshot.promotion_source,
    "数据状态": snapshot.data_status,
    "推广中心花费(元)": snapshot.promotion_center_cost,
    "总推广消耗(元)": snapshot.total_cost,
    "今日订单数": snapshot.order_count,
    "今日成交额(元)": snapshot.total_amount,
    "实时ROI": snapshot.roi,
    "获客成本(元)": snapshot.cac,
    "错误信息": snapshot.error_message,
    "是否告警": snapshot.alert_flag,
}
```

### 14.3 `storage/feishu_storage.py` 核心伪代码

```python
import json
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import *
from storage.base import Storage
from config import settings

class FeishuBitableStorage(Storage):
    def __init__(self):
        self.client = lark.Client.builder() \
            .app_id(settings.feishu_app_id) \
            .app_secret(settings.feishu_app_secret) \
            .log_level(lark.LogLevel.ERROR) \
            .build()

    def _create_record(self, table_id: str, fields: dict) -> bool:
        request = CreateAppTableRecordRequest.builder() \
            .app_token(settings.feishu_app_token) \
            .table_id(table_id) \
            .request_body(AppTableRecord.builder().fields(fields).build()) \
            .build()
        resp = self.client.bitable.v1.app_table_record.create(request)
        if not resp.success():
            raise RuntimeError(f"飞书新增失败：{resp.msg}")
        return True

    def _update_record(self, table_id: str, record_id: str, fields: dict) -> bool:
        request = UpdateAppTableRecordRequest.builder() \
            .app_token(settings.feishu_app_token) \
            .table_id(table_id) \
            .record_id(record_id) \
            .request_body(AppTableRecord.builder().fields(fields).build()) \
            .build()
        resp = self.client.bitable.v1.app_table_record.update(request)
        if not resp.success():
            raise RuntimeError(f"飞书更新失败：{resp.msg}")
        return True

    def _find_record_id_by_unique_key(self, table_id: str, unique_key: str) -> str | None:
        # 实际开发时使用 list/search record，并通过 filter 条件查 unique_key。
        # 如果 SDK 方法名称和版本不同，以安装版本和飞书官方文档为准。
        # 必须保证 unique_key 是表中的文本字段。
        raise NotImplementedError

    def upsert(self, table_id: str, fields: dict) -> int:
        unique_key = fields.get("unique_key")
        if not unique_key:
            self._create_record(table_id, fields)
            return 1

        record_id = self._find_record_id_by_unique_key(table_id, unique_key)
        if record_id:
            self._update_record(table_id, record_id, fields)
        else:
            self._create_record(table_id, fields)
        return 1
```

开发时如果优先追求速度，可以第一版只追加记录；但交付版必须实现 upsert，避免重复快照和重复日志。

---

## 15. 告警服务

### 15.1 `services/alert_service.py`

```python
from datetime import datetime, timedelta
import requests
from config import settings
from models import MonitorSnapshot, Metric10Min

class AlertService:
    def __init__(self, storage):
        self.storage = storage

    def evaluate(self, snapshot: MonitorSnapshot, metric: Metric10Min | None) -> list[dict]:
        alerts = []

        if snapshot.total_cost is not None and snapshot.total_cost > settings.alert_total_cost:
            alerts.append(self._alert("cost_over_limit", "warning", f"今日总推广消耗 {snapshot.total_cost:.2f} 元，超过阈值 {settings.alert_total_cost:.2f} 元", snapshot.total_cost, settings.alert_total_cost))

        if snapshot.total_cost and snapshot.total_cost > 100 and snapshot.roi is not None and snapshot.roi < settings.alert_min_roi:
            alerts.append(self._alert("roi_low", "warning", f"今日 ROI 为 {snapshot.roi}，低于阈值 {settings.alert_min_roi}", snapshot.roi, settings.alert_min_roi))

        if snapshot.data_status in {"order_failed", "promotion_failed", "login_required", "feishu_failed"}:
            alerts.append(self._alert("collect_failed", "critical", f"数据采集异常：{snapshot.data_status}；{snapshot.error_message or ''}", None, None))

        if metric and metric.data_status == "normal" and metric.delta_cost and metric.delta_cost > 0 and (metric.delta_order_count or 0) == 0:
            alerts.append(self._alert("cost_no_order", "warning", f"周期内有推广消耗 {metric.delta_cost:.2f} 元，但新增订单为 0", metric.delta_cost, None))

        return alerts

    def _alert(self, alert_type, level, message, current_value, threshold):
        return {
            "alert_id": f"{settings.shop_id}_{alert_type}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "触发时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "店铺ID": settings.shop_id,
            "告警类型": alert_type,
            "告警级别": level,
            "告警内容": message,
            "当前值": current_value,
            "阈值": threshold,
            "是否已发送": False,
            "发送结果": "pending",
        }

    def send_to_feishu(self, alert: dict) -> bool:
        if not settings.feishu_webhook:
            return False
        try:
            resp = requests.post(settings.feishu_webhook, json={
                "msg_type": "text",
                "content": {"text": f"【淘宝店铺监控告警】\n{alert['告警内容']}\n时间：{alert['触发时间']}"}
            }, timeout=5)
            return resp.status_code < 300
        except Exception:
            return False
```

---

## 16. 任务主流程

### 16.1 Collector 工厂

```python
from config import settings
from services.browser_service import BrowserService
from collectors.taobao_order_api import TaobaoOrderApiCollector
from collectors.taobao_order_crawler import TaobaoOrderCrawler
from collectors.taobao_promotion_crawler import TaobaoPromotionCrawler

def create_order_collector():
    # 当前阶段默认 crawler；api 分支保留为后续切换接口。
    if settings.order_source == "api":
        return TaobaoOrderApiCollector()
    if settings.order_source == "crawler":
        browser_service = BrowserService(settings.qianniu_cdp_url)
        return TaobaoOrderCrawler(browser_service)
    raise ValueError("非法 ORDER_SOURCE")

def create_promotion_collector():
    browser_service = BrowserService(settings.qianniu_cdp_url)
    return TaobaoPromotionCrawler(browser_service)
```

### 16.2 `scheduler.py`

```python
import time
from datetime import datetime
from config import settings
from models import TaskRunLog
from storage.feishu_storage import FeishuBitableStorage
from services.metric_service import MetricService
from services.alert_service import AlertService
from collectors import create_order_collector, create_promotion_collector

class Scheduler:
    def __init__(self):
        self.storage = FeishuBitableStorage()
        self.metric_service = MetricService()
        self.alert_service = AlertService(self.storage)

    def run_forever(self):
        while True:
            self.run_once()
            time.sleep(settings.fetch_interval_seconds)

    def run_once(self):
        log = TaskRunLog.new("full_collect", settings.shop_id)
        try:
            order_collector = create_order_collector()
            promotion_collector = create_promotion_collector()

            order_result = order_collector.fetch_today()
            promotion_result = promotion_collector.fetch_today()

            log.order_status = "success" if order_result.success else "failed"
            log.promotion_status = promotion_result.status

            if order_result.orders:
                self.storage.save_orders_raw(order_result.orders)

            # 推广中心花费快照
            promotion_rows = self._build_promotion_rows(promotion_result)
            self.storage.save_promotion_snapshot(promotion_rows)

            # 实时快照
            snapshot = self.metric_service.build_snapshot(order_result, promotion_result)
            self.storage.save_monitor_snapshot(snapshot)

            # 10 分钟增量
            previous = self.storage.get_last_monitor_snapshot(settings.shop_id)
            metric = self.metric_service.build_delta(snapshot, previous)
            self.storage.save_metric_10min(metric)

            # 告警
            alerts = self.alert_service.evaluate(snapshot, metric)
            for alert in alerts:
                sent = self.alert_service.send_to_feishu(alert)
                alert["是否已发送"] = sent
                alert["发送结果"] = "success" if sent else "failed"
                self.storage.save_alert_log(alert)

            log.storage_status = "success"
            log.total_status = "success" if order_result.success and promotion_result.success else "partial_success"
            log.fetched_count = (len(order_result.orders) if order_result.orders else 0) + len(promotion_result.items)
            log.saved_count = log.fetched_count + 2
            log.alerted = len(alerts) > 0
        except Exception as e:
            log.total_status = "failed"
            log.error_code = "main_loop_failed"
            log.error_message = str(e)
        finally:
            log.ended_at = datetime.now()
            log.duration_seconds = (log.ended_at - log.started_at).total_seconds()
            try:
                self.storage.save_task_log(log)
            except Exception:
                pass

    def _build_promotion_rows(self, promotion_result):
        rows = []
        for item in promotion_result.items:
            rows.append({
                "unique_key": f"{settings.shop_id}_{item.channel}_{promotion_result.fetched_at.strftime('%Y%m%d%H%M')}",
                "采集时间": promotion_result.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                "店铺ID": settings.shop_id,
                "店铺名称": settings.shop_name,
                "推广渠道": item.channel_name,
                "今日累计消耗(元)": item.cost,
                "曝光": item.impressions,
                "点击": item.clicks,
                "转化": item.conversions,
                "状态": item.status,
                "错误信息": item.error_message,
                "原始数据": str(item.raw),
            })
        return rows
```

---

## 17. 入口文件

### 17.1 `main.py`

```python
from scheduler import Scheduler
from loguru import logger

if __name__ == "__main__":
    logger.info("淘宝店铺数据监控 MVP 启动")
    Scheduler().run_forever()
```

---

## 18. 日报服务

### 18.1 要求

日报可以先按最近一条 `monitor_snapshot` 生成。

### 18.2 伪代码

```python
class DailyReportService:
    def __init__(self, storage, alert_service):
        self.storage = storage
        self.alert_service = alert_service

    def send_daily_report(self):
        snapshot = self.storage.get_today_last_snapshot(settings.shop_id)
        alert_stats = self.storage.get_today_alert_stats(settings.shop_id)
        if not snapshot:
            return

        text = f"""
【淘宝店铺日报】
日期：{snapshot.fetched_at.strftime('%Y-%m-%d')}
店铺：{snapshot.shop_name}

今日订单数：{snapshot.order_count} 单
今日成交额：{snapshot.total_amount} 元
推广中心花费：{snapshot.promotion_center_cost} 元
总推广消耗：{snapshot.total_cost} 元
今日 ROI：{snapshot.roi}
获客成本：{snapshot.cac} 元/单

异常统计：{alert_stats}

数据状态：实时采集数据，以平台后台最终结算为准。
""".strip()
        self.alert_service.send_text(text)
```

---

## 19. 错误码规范

| 错误码 | 说明 | 处理方式 |
|---|---|---|
| qianniu_not_running | 千牛未运行或端口未开 | 通知人工打开千牛 |
| cdp_connection_failed | CDP 连接失败 | 通知技术检查端口 |
| login_required | 登录失效或需要验证 | 通知人工登录 |
| permission_denied | 子账号权限不足 | 通知运营调整权限 |
| order_api_failed | 淘宝订单 API 失败 | 记录日志，可切 crawler |
| order_crawler_failed | 订单页面采集失败 | 检查登录和选择器 |
| promotion_cost_failed | 推广中心“花费”读取失败 | critical 告警 |
| promotion_page_changed | 推广中心页面结构变化或选择器失效 | 记录日志并告警 |
| feishu_create_failed | 飞书新增失败 | 本地缓存待补写 |
| feishu_update_failed | 飞书更新失败 | 本地缓存待补写 |
| invalid_delta | 增量计算异常 | 写 metrics_10min 异常状态 |

---

## 20. 本地缓存补写

### 20.1 场景

当飞书写入失败时，不要丢数据。写入 `cache/pending_records.jsonl`。

每行格式：

```json
{"table_id":"tbl_xxx","fields":{"unique_key":"xxx"},"created_at":"2026-06-02 16:10:00"}
```

### 20.2 补写策略

每次任务开始前先处理 pending records：

1. 读取 `pending_records.jsonl`；
2. 尝试写入飞书；
3. 成功则从 pending 中移除；
4. 失败则保留；
5. 单次最多补写 100 条，避免影响采集任务。

---

## 21. 测试用例

### 21.1 单元测试

| 测试 | 输入 | 期望 |
|---|---|---|
| ROI 计算 | 成交额 1000，消耗 200 | ROI = 5 |
| CAC 计算 | 消耗 200，订单 10 | CAC = 20 |
| 消耗为 0 | 成交额 1000，消耗 0 | ROI = None |
| 订单为 0 | 消耗 200，订单 0 | CAC = None |
| 快照增量 | 当前订单 20，上次 10 | 新增 10 |
| 当前小于上次 | 当前订单 5，上次 10 | invalid_delta |
| API 失败 | success=false | 不写 0 |

### 21.2 集成测试

| 测试 | 步骤 | 期望 |
|---|---|---|
| Crawler 模式 | ORDER_SOURCE=crawler，运行一次 | 通过千牛 PC 订单中心读取订单明细、写入 `orders_raw`、生成快照和日志 |
| 推广中心采集 | 千牛登录正常 | 从千牛 PC 推广中心经营概览读取“花费” |
| API 预留 | ORDER_SOURCE=api，运行一次 | 后续阶段启用；当前阶段可跳过真实 API 验收 |
| 千牛关闭 | 关闭千牛运行 | 任务失败并告警 |
| 飞书失败 | 填错 table_id | 写入本地 pending |
| 告警测试 | ALERT_TOTAL_COST=1 | 收到飞书告警 |
| 日报测试 | 手动触发日报 | 群里收到日报 |

---

## 22. 部署说明

### 22.1 本地运行

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

### 22.2 Windows 开机启动

推荐使用 Windows 任务计划程序：

1. 创建基本任务；
2. 触发器选择“用户登录时”；
3. 操作选择启动程序；
4. 程序填写 Python 路径；
5. 参数填写 `main.py`；
6. 起始目录填写项目目录。

### 22.3 运行前检查

1. 千牛 PC 已启动；
2. 子账号已登录；
3. 端口 `9222` 已开启；
4. `.env` 已填完整；
5. 飞书多维表格表 ID 正确；
6. 飞书机器人 webhook 正确；
7. 运行 `python main.py` 控制台无异常。

---

## 23. 开发顺序

建议按以下顺序开发，避免返工：

1. 配置模块；
2. 数据模型；
3. 飞书新增记录；
4. 任务日志表写入；
5. 千牛 CDP 连接检测；
6. 订单中心页面采集器；
7. 推广中心“花费”采集器；
8. 淘宝订单 API 采集器接口预留；
9. 指标计算；
10. 快照写入；
11. 10 分钟增量；
12. 告警；
13. 日报；
14. upsert；
15. 本地缓存补写；
16. 测试和打包。

---

## 24. 关键开发注意事项

1. 失败不能返回 0；
2. 当前阶段默认 `ORDER_SOURCE=crawler`，不要求淘宝 API key；
3. 订单中心页面必须支持分页或滚动加载，不能只抓首屏；
4. 页面选择器必须配置化；
5. 推广中心当前只抓“花费”，不要扩展读取或修改投放项；
6. 飞书写入必须有任务日志；
7. 告警必须去重；
8. 不保存主账号密码；
9. 不绕过验证码；
10. 不执行任何投放修改操作。

---

## 25. 一次性交付清单

开发完成后，交付以下内容：

```text
1. 完整项目源码
2. requirements.txt
3. .env.example
4. 飞书多维表格字段说明
5. Windows 启动说明
6. 千牛 PC 连接说明
7. 常见错误码说明
8. 测试用例结果
9. 运行截图
10. 飞书看板截图
```

---
