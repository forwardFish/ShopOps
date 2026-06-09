# 淘宝单平台 MVP 需求文档

版本：v1.0  
日期：2026-06-02  
项目名称：淘宝店铺订单与推广费用实时监控 MVP  
当前范围：仅支持淘宝单平台；后续可扩展抖音、视频号、数据库存储。

---

## 1. 项目背景

商家需要每 10 分钟了解淘宝店铺的经营效果，核心关注：

1. 今日订单数；
2. 今日成交额；
3. 今日推广费用；
4. 最近 10 分钟新增订单、成交额、推广消耗；
5. 实时 ROI / ROAS；
6. 获客成本；
7. 消耗超标、ROI 过低、订单突降、采集失败等异常告警。

当前只实现淘宝平台。当前阶段订单数据只启用千牛 PC 客户端页面采集；后续再切换为淘宝官方 API。

- 当前阶段：千牛 PC 客户端订单中心页面采集；
- 后续阶段：淘宝官方 API。

推广费用当前阶段统一通过千牛 PC 客户端内的推广中心页面采集，只读取页面上的“花费”指标。

所有数据先写入飞书多维表格，同时通过 `Storage` 抽象层保留后续切换 MySQL / PostgreSQL / ClickHouse 的能力。

---

## 2. 项目目标

### 2.1 核心目标

系统每 10 分钟自动运行一次，完成以下动作：

1. 通过千牛 PC 客户端订单中心页面获取订单数据；
2. 通过千牛 PC 客户端推广中心页面获取推广花费；
3. 计算今日累计指标；
4. 计算最近一个采集周期的增量指标；
5. 写入飞书多维表格；
6. 记录任务日志；
7. 触发必要的飞书机器人告警；
8. 每日发送日报。

### 2.2 非目标

本 MVP 不做以下内容：

1. 不接入抖音、视频号、快手、小红书；
2. 不做商家多租户后台；
3. 不做投放计划自动调价、暂停、创建、编辑等操作；
4. 不绕过验证码、登录校验、权限校验或平台安全机制；
5. 不保存淘宝主账号密码；
6. 不存储买家手机号、地址、姓名等敏感个人信息；
7. 不把飞书作为永久数据仓库，飞书仅作为 MVP 存储和看板。

---

## 3. 总体结论

淘宝单平台 MVP 的最终架构约束如下：

1. **当前阶段订单数据使用千牛 PC 客户端订单中心页面采集**；
2. **淘宝官方 API 作为后续阶段接入目标，当前不要求提供 `TAOBAO_APP_KEY` / `TAOBAO_APP_SECRET` / `TAOBAO_SESSION_KEY`**；
3. **订单来源保留 `ORDER_SOURCE` 配置位，当前默认 `crawler`，未来切 `api` 不改主流程代码**；
4. **推广费用当前阶段只通过千牛 PC 客户端推广中心页面采集“花费”**；
5. **不支持千牛网页版作为采集入口**；
6. **当前存储使用飞书多维表格**；
7. **系统必须有 Storage 抽象层，未来可切换数据库**；
8. **采集失败不能写 0，必须写失败状态**；
9. **每次采集都要写任务日志**；
10. **所有告警都要写告警日志，避免重复轰炸**。

---

## 4. 使用角色

| 角色 | 说明 | 权限 |
|---|---|---|
| 商家老板 | 查看经营结果 | 查看飞书看板、接收日报和告警 |
| 运营人员 | 维护账号和阈值 | 修改飞书配置表、处理登录失效 |
| 技术人员 | 开发和维护系统 | 配置环境变量、部署程序、排查日志 |
| 淘宝子账号 | 数据采集账号 | 只读：订单查看、推广数据查看 |

---

## 5. 运行环境要求

### 5.1 必须环境

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / Windows 11 优先 |
| 千牛 | 千牛 PC 客户端，已登录淘宝子账号 |
| Python | Python 3.10+ |
| 网络 | 商家常用办公网络 |
| 飞书 | 已创建飞书自建应用、多维表格、群机器人 |
| 淘宝 API | 当前阶段不需要；后续切 API 模式时再准备 App Key / App Secret / Session Key |

### 5.2 千牛 PC 约束

页面采集任务只允许通过千牛 PC 客户端执行。工程上明确禁止：

1. 不使用千牛网页版；
2. 不使用普通浏览器打开淘宝或阿里妈妈后台做采集；
3. 不使用代理 IP；
4. 不在云服务器上运行千牛 PC 客户端；
5. 不绕过验证码或短信验证；
6. 登录失效时通知人工处理。

### 5.3 账号权限原则

1. 不使用淘宝主账号执行页面采集；
2. 使用独立淘宝子账号；
3. 子账号只开订单查看、推广数据查看权限；
4. 不开资金操作、商品编辑、订单处理、投放修改等权限；
5. 系统不保存主账号密码；
6. 子账号登录、验证码、扫码由商家人工处理。

---

## 6. 业务功能需求

## 6.1 订单数据采集

### 6.1.1 功能描述

系统支持两种订单数据来源：

| 来源 | 配置值 | 用途 |
|---|---|---|
| 千牛 PC 页面采集 | `ORDER_SOURCE=crawler` | 当前阶段默认启用，从千牛 PC 客户端订单中心抓取订单数据 |
| 淘宝官方 API | `ORDER_SOURCE=api` | 后续阶段启用，作为更稳定的主通道 |

切换订单来源时，只修改配置，不修改主流程代码。

### 6.1.2 API 订单采集要求

API 模式为后续阶段能力，当前阶段不阻塞交付。后续切换 API 时必须实现：

1. 查询当天 00:00:00 到当前时间的订单；
2. 支持分页，不能只取前 100 条；
3. 只统计有效支付订单；
4. 过滤未付款订单；
5. 保存订单原始明细到 `orders_raw`；
6. 保存订单聚合快照到 `monitor_snapshot`；
7. 失败时返回 `success=false`，不能返回 0；
8. 记录错误码、错误信息、请求时间。

### 6.1.3 页面订单采集要求

Crawler 模式必须实现：

1. 只通过千牛 PC 客户端内打开的订单中心页面采集，不使用普通浏览器或千牛网页版；
2. 进入订单中心 / 已卖出宝贝 / 订单列表页面；
3. 抓取当前页面及分页中的所有订单相关数据，至少包含订单号、创建时间、宝贝名称、单价、数量、履约/售后状态、交易状态、实收款、操作区可见链接或状态；
4. 支持翻页或滚动加载，不能只抓首屏订单；
5. 保存订单明细到 `orders_raw`，并基于明细聚合今日订单数、今日成交额到 `monitor_snapshot`；
6. 如果某些字段在页面不可见或读取失败，字段可为空，但整条订单必须记录采集状态和错误信息；
7. 登录失效、验证码、权限不足时终止任务并告警；
8. 失败不能写 0。

### 6.1.4 订单数据统一返回格式

无论 API 还是页面采集，最终都必须返回同一种结构。

```json
{
  "success": true,
  "source": "api",
  "shop_id": "taobao_shop_001",
  "shop_name": "淘宝店铺A",
  "order_count": 123,
  "paid_order_count": 120,
  "total_amount": 45678.90,
  "fetched_at": "2026-06-02 16:10:00",
  "error_code": null,
  "error_message": null,
  "raw": {}
}
```

失败时：

```json
{
  "success": false,
  "source": "crawler",
  "shop_id": "taobao_shop_001",
  "shop_name": "淘宝店铺A",
  "order_count": null,
  "paid_order_count": null,
  "total_amount": null,
  "fetched_at": "2026-06-02 16:10:00",
  "error_code": "login_required",
  "error_message": "千牛登录失效，请人工重新登录",
  "raw": null
}
```

---

## 6.2 推广费用采集

### 6.2.1 功能描述

推广费用当前阶段只使用千牛 PC 客户端内打开的推广中心页面采集。

当前页面入口为推广中心，示例 URL 形态为 `https://qn.taobao.com/home.htm/tuiguangcenter_new/`。当前阶段只采集经营概览中的“花费”项目，不采集曝光量、点击量、转化数、投入产出比、总成交金额等其他推广指标。

系统只读取商家账号中已授权可见的数据，不执行任何投放操作。

### 6.2.2 采集数据

推广中心至少采集：

| 字段 | 说明 |
|---|---|
| 页面名称 | 推广中心 |
| 指标名称 | 花费 |
| 今日累计花费 | 页面当前日期展示的“花费”数值 |
| 采集状态 | success / failed / login_required / permission_denied |
| 错误信息 | 失败时记录 |

### 6.2.3 推广费用统一返回格式

```json
{
  "success": true,
  "source": "qianniu_pc",
  "shop_id": "taobao_shop_001",
  "shop_name": "淘宝店铺A",
  "items": [
    {
      "channel": "tuiguangcenter",
      "channel_name": "推广中心",
      "cost": 123.45,
      "impressions": null,
      "clicks": null,
      "conversions": null,
      "status": "success",
      "error_message": null,
      "raw": {}
    }
  ],
  "total_cost": 123.45,
  "fetched_at": "2026-06-02 16:10:00"
}
```

当前版本只有 1 个推广采集目标：推广中心经营概览中的“花费”。因此本版本不做直通车、万相台、引力魔方等渠道拆分，也不存在多渠道 `partial_success` 口径。推广中心“花费”读取失败时，整体推广状态为 `failed`，`monitor_snapshot` 必须标记为 `promotion_failed` 或对应失败状态，并且不得把推广消耗写成 0。

---

## 6.3 指标计算

系统需要计算两类指标：

1. 今日累计指标；
2. 最近一个采集周期增量指标。

### 6.3.1 今日累计指标

| 指标 | 公式 |
|---|---|
| 今日订单数 | 当前采集到的今日订单数 |
| 今日成交额 | 当前采集到的今日成交额 |
| 今日推广消耗 | 推广中心“花费” |
| 实时 ROI | 今日成交额 / 今日推广消耗 |
| 获客成本 | 今日推广消耗 / 今日订单数 |

### 6.3.2 最近周期增量指标

因为订单和推广费用页面通常是今日累计值，所以最近 10 分钟数据通过快照差值计算。

| 指标 | 公式 |
|---|---|
| 周期新增订单数 | 当前今日订单数 - 上一次今日订单数 |
| 周期新增成交额 | 当前今日成交额 - 上一次今日成交额 |
| 周期推广消耗 | 当前今日推广消耗 - 上一次今日推广消耗 |
| 周期 ROI | 周期新增成交额 / 周期推广消耗 |
| 周期获客成本 | 周期推广消耗 / 周期新增订单数 |

### 6.3.3 异常处理

如果出现以下情况，增量指标不计算或标记异常：

1. 上一次快照不存在；
2. 当前值小于上一次值，且不是跨天重置；
3. 当前任务订单失败；
4. 当前任务推广费用全部失败；
5. 两次采集间隔超过配置阈值，比如超过 30 分钟。

---

## 6.4 飞书多维表格存储

### 6.4.1 表结构总览

MVP 至少创建以下表。飞书多维表格中的可见表名必须使用中文；英文名只作为代码内部表键或环境变量含义，不作为飞书界面表名。

| 飞书中文表名 | 代码内部表键 | 用途 | 是否必须 |
|---|---|---|---|
| 系统配置表 | `system_config` | 系统配置 | 必须 |
| 店铺配置表 | `shop_config` | 店铺和账号配置 | 必须 |
| 实时监控快照表 | `monitor_snapshot` | 老板看的实时快照 | 必须 |
| 订单明细原始表 | `orders_raw` | 订单中心页面采集到的订单明细；后续 API 模式也复用 | 必须 |
| 推广数据快照表 | `promotion_snapshot` | 推广中心花费快照 | 必须 |
| 十分钟指标表 | `metrics_10min` | 10 分钟增量指标 | 必须 |
| 任务运行日志表 | `task_run_log` | 任务运行日志 | 必须 |
| 告警日志表 | `alert_log` | 告警记录 | 必须 |
| 每日报告表 | `daily_report` | 每日汇总 | 推荐 |

---

### 6.4.2 `system_config` 表

| 字段名 | 类型 | 示例 | 说明 |
|---|---|---|---|
| config_key | 文本 | ORDER_SOURCE | 配置键 |
| config_value | 文本 | api | 配置值 |
| enabled | 复选框 | true | 是否启用 |
| remark | 文本 | 订单来源 | 说明 |
| updated_at | 日期时间 | 2026-06-02 16:00:00 | 更新时间 |

核心配置：

| config_key | 可选值 | 默认值 |
|---|---|---|
| ORDER_SOURCE | crawler / api | crawler |
| PROMOTION_SOURCE | qianniu_pc | qianniu_pc |
| FETCH_INTERVAL_SECONDS | 600 | 600 |
| ALERT_TOTAL_COST | 数字 | 500 |
| ALERT_MIN_ROI | 数字 | 1.0 |
| ALERT_ORDER_DROP_RATE | 数字 | 0.5 |
| DAILY_REPORT_TIME | HH:mm | 23:50 |

---

### 6.4.3 `shop_config` 表

| 字段名 | 类型 | 示例 |
|---|---|---|
| shop_id | 文本 | taobao_shop_001 |
| shop_name | 文本 | 淘宝女装店A |
| platform | 单选 | taobao |
| qianniu_cdp_url | 文本 | http://127.0.0.1:9222 |
| order_source | 单选 | api / crawler |
| promotion_source | 单选 | qianniu_pc |
| status | 单选 | active / disabled / login_required |
| remark | 文本 | 备注 |

---

### 6.4.4 `monitor_snapshot` 表

这是老板和运营主要看的表。

| 字段名 | 类型 | 说明 |
|---|---|---|
| unique_key | 文本 | `shop_id + 日期 + 采集时间分钟` |
| 采集时间 | 日期时间 | 当前采集时间 |
| 店铺ID | 文本 | shop_id |
| 店铺名称 | 文本 | shop_name |
| 订单来源 | 单选 | api / crawler |
| 推广来源 | 单选 | qianniu_pc |
| 数据状态 | 单选 | normal / order_failed / promotion_failed / login_required |
| 推广中心花费(元) | 数字 | 今日累计 |
| 总推广消耗(元) | 数字 | 今日累计 |
| 今日订单数 | 数字 | 今日累计 |
| 今日成交额(元) | 数字 | 今日累计 |
| 实时ROI | 数字 | 今日成交额 / 总推广消耗 |
| 获客成本(元) | 数字 | 总推广消耗 / 今日订单数 |
| 错误信息 | 长文本 | 失败说明 |
| 是否告警 | 复选框 | true / false |

---

### 6.4.5 `orders_raw` 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| unique_key | 文本 | `taobao + shop_id + order_id` |
| 数据来源 | 单选 | api / crawler |
| 店铺ID | 文本 | shop_id |
| 店铺名称 | 文本 | shop_name |
| 订单号 | 文本 | tid |
| 下单时间 | 日期时间 | created |
| 支付时间 | 日期时间 | pay_time |
| 订单状态 | 文本 | status |
| 支付金额 | 数字 | payment |
| 商品名称 | 文本 | 可选 |
| 采集时间 | 日期时间 | fetched_at |
| 原始数据 | 长文本 | JSON 字符串 |

页面采集模式如果拿不到订单号，可以不写 `orders_raw`，但必须写 `monitor_snapshot` 和 `task_run_log`。

---

### 6.4.6 `promotion_snapshot` 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| unique_key | 文本 | `shop_id + channel + 采集时间分钟` |
| 采集时间 | 日期时间 | fetched_at |
| 店铺ID | 文本 | shop_id |
| 店铺名称 | 文本 | shop_name |
| 推广渠道 | 单选 | 推广中心 |
| 今日累计消耗(元) | 数字 | cost |
| 曝光 | 数字 | 可为空 |
| 点击 | 数字 | 可为空 |
| 转化 | 数字 | 可为空 |
| 状态 | 单选 | success / failed / login_required / permission_denied |
| 错误信息 | 长文本 | 失败时写入 |
| 原始数据 | 长文本 | JSON 字符串 |

---

### 6.4.7 `metrics_10min` 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| unique_key | 文本 | `shop_id + window_start + window_end` |
| 时间开始 | 日期时间 | 上一次采集时间 |
| 时间结束 | 日期时间 | 本次采集时间 |
| 店铺ID | 文本 | shop_id |
| 店铺名称 | 文本 | shop_name |
| 新增订单数 | 数字 | delta_order_count |
| 新增成交额(元) | 数字 | delta_gmv |
| 推广消耗(元) | 数字 | delta_cost |
| 周期ROI | 数字 | delta_gmv / delta_cost |
| 周期获客成本(元) | 数字 | delta_cost / delta_order_count |
| 数据状态 | 单选 | normal / invalid / missing_previous |
| 异常原因 | 长文本 | 异常说明 |

---

### 6.4.8 `task_run_log` 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| task_id | 文本 | UUID |
| 任务类型 | 单选 | full_collect / order_api / order_crawler / promotion_crawler / metrics / daily_report |
| 开始时间 | 日期时间 | started_at |
| 结束时间 | 日期时间 | ended_at |
| 耗时秒 | 数字 | duration_seconds |
| 店铺ID | 文本 | shop_id |
| 订单状态 | 单选 | success / failed / skipped |
| 推广状态 | 单选 | success / failed / skipped |
| 飞书写入状态 | 单选 | success / failed |
| 总状态 | 单选 | success / partial_success / failed |
| 拉取数量 | 数字 | fetched_count |
| 写入数量 | 数字 | saved_count |
| 错误码 | 文本 | error_code |
| 错误信息 | 长文本 | error_message |
| 是否已告警 | 复选框 | true / false |

---

### 6.4.9 `alert_log` 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| alert_id | 文本 | UUID |
| 触发时间 | 日期时间 | triggered_at |
| 店铺ID | 文本 | shop_id |
| 告警类型 | 单选 | cost_over_limit / roi_low / order_drop / login_required / collect_failed / feishu_failed |
| 告警级别 | 单选 | info / warning / critical |
| 告警内容 | 长文本 | message |
| 当前值 | 数字 | current_value |
| 阈值 | 数字 | threshold |
| 是否已发送 | 复选框 | sent |
| 发送结果 | 文本 | success / failed |

---

## 6.5 告警需求

### 6.5.1 经营告警

| 告警 | 触发条件 | 级别 |
|---|---|---|
| 总消耗超标 | 今日总推广消耗 > `ALERT_TOTAL_COST` | warning |
| ROI 过低 | 今日推广消耗 > 100 且 ROI < `ALERT_MIN_ROI` | warning |
| 订单突降 | 本次今日订单数 < 上次今日订单数 × (1 - `ALERT_ORDER_DROP_RATE`) | critical |
| 有消耗无订单 | 最近周期推广消耗 > 0 且周期新增订单 = 0 | warning |

### 6.5.2 系统告警

| 告警 | 触发条件 | 级别 |
|---|---|---|
| 千牛未运行 | 无法连接 CDP 地址 | critical |
| 登录失效 | 页面出现登录、验证码、无权限状态 | critical |
| 订单采集失败 | 订单来源失败 | warning |
| 推广中心花费采集失败 | 无法读取推广中心“花费” | critical |
| 推广中心页面异常 | 推广中心登录失效、验证码、无权限或页面结构变化 | warning |
| 飞书写入失败 | 多维表格写入失败 | critical |
| 连续失败 | 同一任务连续失败 >= 2 次 | critical |

### 6.5.3 告警去重

同一店铺、同一告警类型，在 30 分钟内只发送一次，避免刷屏。每次触发都写入 `alert_log`，但不一定都发送群消息。

---

## 6.6 日报需求

每天固定时间发送日报，默认 23:50。

日报内容：

```text
【淘宝店铺日报】
日期：2026-06-02
店铺：淘宝女装店A

今日订单数：xxx 单
今日成交额：xxxx.xx 元
推广中心花费：xxxx.xx 元
总推广消耗：xxxx.xx 元
今日 ROI：x.xx
获客成本：xx.xx 元/单

异常统计：
- 采集失败：x 次
- 登录失效：x 次
- ROI 过低：x 次
- 消耗超标：x 次

数据状态：实时采集数据，以平台后台最终结算为准。
```

---

## 7. 配置需求

配置优先级：

1. `.env` 环境变量；
2. 飞书 `system_config`；
3. 代码默认值。

### 7.1 `.env` 示例

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

FEISHU_APP_ID=xxx
FEISHU_APP_SECRET=xxx
FEISHU_APP_TOKEN=xxx
FEISHU_TABLE_SYSTEM_CONFIG=tbl_xxx
FEISHU_TABLE_SHOP_CONFIG=tbl_xxx
FEISHU_TABLE_MONITOR_SNAPSHOT=tbl_xxx
FEISHU_TABLE_ORDERS_RAW=tbl_xxx
FEISHU_TABLE_PROMOTION_SNAPSHOT=tbl_xxx
FEISHU_TABLE_METRICS_10MIN=tbl_xxx
FEISHU_TABLE_TASK_LOG=tbl_xxx
FEISHU_TABLE_ALERT_LOG=tbl_xxx
FEISHU_TABLE_DAILY_REPORT=tbl_xxx
FEISHU_WEBHOOK=xxx

ALERT_TOTAL_COST=500
ALERT_MIN_ROI=1.0
ALERT_ORDER_DROP_RATE=0.5
ALERT_DEDUP_MINUTES=30
DAILY_REPORT_TIME=23:50
```

---

## 8. 数据状态定义

| 状态 | 说明 |
|---|---|
| normal | 订单和推广均成功 |
| order_failed | 订单采集失败，推广成功 |
| promotion_failed | 推广全部失败 |
| login_required | 千牛需要人工登录或验证 |
| permission_denied | 子账号权限不足 |
| feishu_failed | 飞书写入失败 |
| invalid_delta | 增量计算异常 |

---

## 9. 可靠性要求

1. 单次任务失败不能导致程序退出；
2. 每个子任务失败要互相隔离；
3. 订单中心采集成功但推广中心采集失败时，订单结果仍然写入；
4. 推广中心花费采集失败时，不写 0，必须写失败状态和错误信息；
5. 所有失败都写任务日志；
6. 飞书写入失败时，需要本地缓存待补写数据；
7. 程序重启后可以继续运行；
8. 采集失败不能写 0；
9. 飞书 upsert 必须基于 `unique_key`，避免重复记录。

---

## 10. 验收标准

### 10.1 功能验收

1. 默认 `ORDER_SOURCE=crawler` 时，订单使用千牛 PC 客户端订单中心页面采集；
2. 订单中心可抓取当前筛选范围内所有订单相关数据，并写入 `orders_raw`；
3. 系统保留 `ORDER_SOURCE=api` 配置和接口边界，后续不改主流程代码即可切换；
4. 推广中心可采集经营概览中的“花费”数值；
5. 数据写入飞书 `monitor_snapshot`；
6. 推广中心花费快照写入 `promotion_snapshot`；
7. 订单中心订单明细写入 `orders_raw`；
8. 每次运行写入 `task_run_log`；
9. 异常触发写入 `alert_log` 并发送飞书消息；
10. 每日固定时间发送日报。

### 10.2 数据验收

1. 今日订单数与淘宝后台误差为 0 或可解释；
2. 今日成交额与淘宝后台误差为 0 或可解释；
3. 推广花费与千牛 PC 推广中心页面展示一致或可解释；
4. ROI = 今日成交额 / 今日推广消耗；
5. 获客成本 = 今日推广消耗 / 今日订单数；
6. 10 分钟增量 = 当前快照 - 上一次快照；
7. 重复运行不会产生重复 `unique_key` 数据。

### 10.3 稳定性验收

1. 连续运行 24 小时无主程序崩溃；
2. 断网、千牛关闭、登录失效、飞书失败均能记录日志；
3. 采集失败不会写 0 污染指标；
4. 任务失败后下一轮仍能继续；
5. 飞书重复写入不会产生重复记录。

---

## 11. 后续扩展

### 11.1 扩展平台

后续新增抖音、视频号时，只新增 Collector：

```text
OrderCollector
  - TaobaoOrderApiCollector
  - TaobaoOrderCrawler
  - DouyinOrderApiCollector
  - WechatOrderApiCollector

PromotionCollector
  - TaobaoPromotionQianNiuCollector
  - DouyinPromotionApiCollector
  - WechatPromotionCollector
```

### 11.2 切换数据库

当前使用：

```text
FeishuBitableStorage
```

未来新增：

```text
PostgresStorage
MySQLStorage
ClickHouseStorage
```

业务层只依赖 `Storage` 接口，不直接依赖飞书 API。

---
