# ShopOps 四平台数据接入现状与实现路线

更新时间：2026-06-05

本文档面向 ShopOps 当前项目，覆盖四个平台：抖音、拼多多、天猫、视频号；三类数据：订单数据、投流数据、达人佣金数据。文档分两部分：

1. 已经实现：仓库里已有的代码、配置、脚本、测试和限制。
2. 计划实现：建议的接入方式、表结构、任务拆分和验收标准。

本文的基本判断是：ShopOps 应继续以飞书多维表为业务数据库，以“平台原始明细表 + 统一指标快照表 + 任务日志/告警/日报”为核心，不要为每个平台各自做一套孤立流程。

## 1. 当前项目结论

### 1.1 已实现的核心能力

| 模块 | 当前状态 | 关键文件 |
|---|---|---|
| 配置中心 | 已支持 `SHOP_PLATFORM`、`ORDER_SOURCE`、平台凭证、飞书表 ID、聚水潭/Qimen 配置 | `shopops/config.py`, `.env.example` |
| 订单采集 | 已有淘宝/天猫、拼多多、抖店、视频号订单 API 边界；也有聚水潭订单路径 | `shopops/collectors/platform_order_api.py`, `shopops/collectors/jushuitan_order_api.py`, `shopops/collectors/jushuitan_qimen_order_api.py` |
| 天猫/淘宝千牛订单抓取 | 已有千牛订单中心 CDP 抓取器，适合 MVP 或临时补数 | `shopops/collectors/taobao_order_crawler.py` |
| 天猫/淘宝投流 | 已有千牛推广中心采集器和真实推广接口写飞书脚本 | `shopops/collectors/taobao_promotion_crawler.py`, `scripts/run_promotion_api_to_feishu.py` |
| 抖音达人佣金 | 已有聚水潭达人佣金采集器、抖店联盟直连采集器、飞书写入能力 | `shopops/collectors/jushuitan_influencer_api.py`, `shopops/collectors/doudian_alliance_api.py`, `scripts/run_jushuitan_influencers_to_feishu.py`, `scripts/run_doudian_alliance_to_feishu.py` |
| 飞书存储 | 已有本地飞书 double、真实飞书 OpenAPI 存储、唯一键 upsert、pending replay | `shopops/storage/local_feishu.py`, `shopops/storage/feishu_bitable.py` |
| 指标计算 | 已有实时快照、10 分钟增量、ROI、CAC、异常状态、不写假 0 的逻辑 | `shopops/services/metric_service.py`, `shopops/scheduler.py` |
| 告警和日报 | 已有告警、任务日志、每日报告写入 | `shopops/services/alert_service.py`, `shopops/services/daily_report_service.py` |
| 测试 | 已覆盖订单 API 边界、聚水潭、Qimen、抖店联盟、推广、飞书存储、调度器 | `tests/*.py` |

### 1.2 当前最重要的限制

1. 当前调度器是“单店铺单平台”配置模型：`SHOP_PLATFORM` 一次只能是 `taobao`、`pinduoduo`、`doudian`、`wechat_channels` 之一。真正的四平台长期运行，需要升级为“多平台店铺配置表驱动”。
2. 当前 `PROMOTION_SOURCE` 校验只允许 `qianniu_pc`，所以投流数据目前只完整覆盖天猫/淘宝千牛推广中心。抖音、拼多多、视频号投流还没有正式 collector。
3. 达人佣金目前只对抖音有已实现路径：聚水潭达人佣金接口和抖店精选联盟直连接口。拼多多、天猫、视频号的达人/联盟佣金还没有实现。
4. 飞书真实写入能力已存在，但 live 验收依赖环境变量、飞书权限、平台授权、店铺 ID、会话或 token。缺权限时必须返回 `failed` / `partial_success`，不能把缺失数据写成 0。
5. 天猫/拼多多真实订单拉取历史上遇到过聚水潭/Qimen 授权阻塞。普通聚水潭 OpenAPI 凭证不等于 Qimen 路由授权。

## 2. 推荐总体架构

### 2.1 数据流

```text
平台 API / 聚水潭 / 授权导出
  -> 平台 Collector
  -> 原始明细归一化
  -> 飞书多维表 upsert
  -> 指标快照/10 分钟增量/日报/告警
```

不要直接把平台接口返回值汇总成一个数字。建议始终先保存原始明细，再由 ShopOps 自己计算 GMV、花费、佣金、ROI，这样后面发现退款、结算滞后、平台口径变化时可以追溯。

### 2.2 数据表建议

当前已有表可以继续复用：

| 表 | 作用 | 当前状态 |
|---|---|---|
| `orders_raw` | 订单明细原始表 | 已实现本地/飞书写入 |
| `promotion_snapshot` | 推广/投流数据表 | 已实现天猫/淘宝推广中心写入 |
| `douyin_influencer_commission` | 抖音达人佣金明细表 | 已实现 |
| `monitor_snapshot` | 实时监控快照 | 已实现 |
| `metrics_10min` | 10 分钟指标表 | 已实现 |
| `task_run_log` | 任务运行日志 | 已实现 |
| `alert_log` | 告警日志 | 已实现 |
| `daily_report` | 每日报告 | 已实现 |

建议新增或重命名为更通用的表：

| 建议表 | 是否新增 | 说明 |
|---|---:|---|
| `platform_account_config` | 新增 | 四个平台店铺、凭证别名、拉取频率、启停状态、飞书表映射 |
| `ad_spend_raw` | 新增或由 `promotion_snapshot` 升级 | 多平台投流明细，替代只面向千牛的推广表 |
| `influencer_commission_raw` | 新增或由 `douyin_influencer_commission` 升级 | 多平台达人/联盟/分销佣金明细 |
| `reconcile_daily` | 新增 | 订单、投流、佣金、退款、平台后台口径的日级对账 |

如果要少改代码，可以第一阶段不新建 `ad_spend_raw` 和 `influencer_commission_raw`，先给现有 `promotion_snapshot`、`douyin_influencer_commission` 增加 `平台`、`数据来源`、`账户ID`、`口径日期` 字段。第二阶段再拆通用表。

### 2.3 三类数据的统一字段

#### 订单数据 `orders_raw`

建议统一字段：

| 字段 | 说明 |
|---|---|
| `unique_key` | `平台_店铺ID_订单号`，upsert 主键 |
| `平台` | 抖音/拼多多/天猫/视频号 |
| `数据来源` | 平台 OpenAPI / 聚水潭 / Qimen / 千牛抓取 / 手工导入 |
| `店铺ID`、`店铺名称` | 平台或聚水潭店铺 ID |
| `采集时间` | 本次拉取时间 |
| `订单号` | 平台订单号 |
| `创建时间`、`支付时间` | 后续计算归因和当日 GMV 必需 |
| `交易状态`、`履约/售后状态` | 用于排除未支付、关闭、退款订单 |
| `实收款` | 订单实际支付金额 |
| `商品ID`、`商品名称`、`数量` | SKU/商品分析 |
| `达人/推广标识` | 如果订单自带达人、直播间、计划、广告归因，保留在这里 |
| `原始数据` | 脱敏后的原始 JSON |

#### 投流数据 `ad_spend_raw`

建议统一字段：

| 字段 | 说明 |
|---|---|
| `unique_key` | `平台_账户ID_计划ID_口径日期_时间窗口` |
| `平台` | 抖音/拼多多/天猫/视频号 |
| `数据来源` | 巨量千川/拼多多推广/万相台/微信广告/千牛推广中心/导出 |
| `账户ID`、`店铺ID`、`计划ID`、`单元ID`、`创意ID` | 粒度越细越好，不可得则留空 |
| `口径日期`、`窗口开始`、`窗口结束` | 必须明确花费口径 |
| `花费`、`曝光`、`点击`、`转化数`、`转化金额` | 最低可用指标 |
| `投放目标`、`投放场景` | 搜索、推荐、直播间、短视频、商城等 |
| `原始数据` | 原始返回或导出行 |

#### 达人佣金数据 `influencer_commission_raw`

建议统一字段：

| 字段 | 说明 |
|---|---|
| `unique_key` | `平台_店铺ID_订单号_达人ID` |
| `平台` | 抖音/拼多多/天猫/视频号 |
| `数据来源` | 精选联盟/聚水潭/淘宝客/多多进宝/视频号联盟/导出 |
| `店铺ID`、`订单号`、`商品ID` | 对账关键 |
| `达人ID`、`达人昵称`、`直播间/视频ID` | 内容归因 |
| `成交金额` | 佣金对应成交额 |
| `佣金率`、`预估佣金`、`结算佣金`、`技术服务费` | 成本口径 |
| `结算状态`、`结算时间` | 预估和结算要分开 |
| `原始数据` | 原始返回或导出行 |

## 3. 四平台现状矩阵

| 平台 | 订单数据 | 投流数据 | 达人佣金数据 | 当前优先级 |
|---|---|---|---|---|
| 抖音 | 部分已实现：抖店订单 API 边界、聚水潭订单通用路径 | 未实现正式 collector | 已实现抖店联盟直连和聚水潭达人佣金边界，待真实授权打通 | P0 |
| 拼多多 | 部分已实现：拼多多订单 API 边界、聚水潭订单路径 | 未实现 | 未实现 | P1 |
| 天猫 | 已实现最多：千牛抓取、淘宝/TOP API 边界、聚水潭/Qimen 路径 | 已实现千牛推广中心总花费；更细广告 API 未实现 | 未实现 | P0 |
| 视频号 | 部分已实现：视频号订单 API 边界、聚水潭订单路径 | 未实现 | 未实现 | P1 |

状态解释：

- “已实现”表示仓库已有代码路径和测试，不代表当前环境已经拥有 live 授权。
- “部分已实现”表示代码边界存在，但还需要凭证、真实返回样本、字段修正和飞书 readback 证据。
- “未实现”表示目前没有正式 collector，不应在报表中展示为真实数据。

## 4. 抖音实现方案

### 4.1 抖音订单数据

已实现：

- `MarketplaceOrderApiCollector` 支持 `SHOP_PLATFORM=doudian`，默认走抖店订单查询路径。
- `.env.example` 已有 `DOUDIAN_APP_KEY`、`DOUDIAN_APP_SECRET`、`DOUDIAN_ACCESS_TOKEN`、`DOUDIAN_API_URL`。
- `scripts/run_jushuitan_orders_to_feishu.py` 的平台映射中包含 `douyin`，可通过聚水潭店铺 ID 写入飞书订单表。

建议实现：

1. 短期优先用聚水潭订单作为抖音订单主路径，因为聚水潭能统一多平台订单口径，也更适合和天猫/拼多多/视频号共用。
2. 抖店 OpenAPI 作为实时性或聚水潭缺口的补充路径。
3. 在 `orders_raw` 中保留抖店订单号、支付时间、订单状态、售后状态、达人/直播间字段。
4. 新增 `scripts/run_douyin_orders_to_feishu.py` 或把现有 `run_platform_orders.py` 扩展为“按平台配置循环”。

建议环境变量：

```text
SHOP_PLATFORM=doudian
ORDER_SOURCE=api 或 jushuitan
DOUDIAN_APP_KEY=
DOUDIAN_APP_SECRET=
DOUDIAN_ACCESS_TOKEN=
JUSHUITAN_SHOP_ID_DOUYIN=
```

验收标准：

- 拉到至少 1 条真实抖音订单，写入 `orders_raw`。
- 同一订单重复拉取只 update，不新增重复行。
- 未授权或接口失败时任务返回失败状态，不写 `0` GMV。

### 4.2 抖音投流数据

已实现：

- 暂无正式抖音投流 collector。

建议实现：

1. 首选官方广告/千川报表 API。如果当前账号无法开放 API，则先支持运营后台导出 CSV/XLSX 导入。
2. 新增 `DouyinAdSpendCollector`，输出统一 `AdSpendCollectResult`。
3. 字段优先级：花费、曝光、点击、成交订单数、成交金额、计划 ID、单元 ID、创意 ID、直播间/短视频 ID。
4. 飞书写入 `ad_spend_raw` 或升级后的 `promotion_snapshot`。

建议新增文件：

```text
shopops/collectors/douyin_ad_api.py
scripts/run_douyin_ads_to_feishu.py
tests/test_douyin_ad_api.py
```

验收标准：

- 能按日期窗口拉取花费。
- 同一个计划同一天重复拉取不重复。
- 平台返回无权限时标记 `permission_denied`，不写假 0。

### 4.3 抖音达人佣金数据

已实现：

- `JushuitanInfluencerCommissionCollector`：聚水潭达人佣金路径，支持分页、签名、字段归一化、fail-closed。
- `DoudianAllianceOrderCollector`：抖店精选联盟直连路径，使用 `/alliance/getOrderList`，按订单 ID 批量查询达人佣金。
- `FeishuBitableStorage.save_douyin_influencer_commission()` 和本地 double 都已支持佣金表写入。
- `scripts/run_jushuitan_influencers_to_feishu.py` 和 `scripts/run_doudian_alliance_to_feishu.py` 已可运行。

历史限制：

- 聚水潭达人佣金接口曾返回 `190: 接口不存在` 一类错误，说明问题在外部接口名/权限，不在飞书表或本地字段映射。
- 抖店联盟直连需要 `DOUDIAN_ALLIANCE_ORDER_IDS` 或命令行传订单 ID；它更适合“按订单补佣金”，不一定适合全量扫描。

建议实现：

1. 先保留两条路径：聚水潭为主，抖店联盟直连为补偿。
2. 新增“订单拉取后补佣金”任务：当天抖音订单写入后，提取订单号，批量请求抖店联盟佣金。
3. 把表名从 `douyin_influencer_commission` 抽象为 `influencer_commission_raw`，但保持旧表兼容。
4. 佣金不要直接扣到当日 ROI，先分为 `预估佣金` 和 `结算佣金` 两个口径；日报里同时展示“含预估佣金 ROI”和“含结算佣金 ROI”。

验收标准：

- 至少 1 条真实达人佣金写入飞书。
- `unique_key` 能防重复。
- 佣金缺失时订单 ROI 不假装已扣佣金，日报必须写明“佣金未回传/未结算”。

## 5. 拼多多实现方案

### 5.1 拼多多订单数据

已实现：

- `MarketplaceOrderApiCollector` 支持 `SHOP_PLATFORM=pinduoduo`。
- `.env.example` 已有 `PDD_CLIENT_ID`、`PDD_CLIENT_SECRET`、`PDD_ACCESS_TOKEN`、`PDD_ORDER_LIST_TYPE`、`PDD_ORDER_DETAIL_TYPE`。
- `scripts/run_jushuitan_orders_to_feishu.py` 和 `scripts/run_tmall_pdd_real_orders_to_feishu.py` 已包含拼多多店铺 ID 路径。

建议实现：

1. 主路径用聚水潭订单接口：减少平台差异，统一和天猫/抖音/视频号的字段归一化。
2. 直连拼多多 OpenAPI 做备用：用于聚水潭延迟、漏单、平台字段补齐。
3. 当前 `PDD_ORDER_LIST_TYPE`、`PDD_ORDER_DETAIL_TYPE` 需要以商家后台开放平台实际授权文档为准；代码已做成环境变量可配置，后续不需要改核心逻辑。
4. 拼多多订单状态要特别处理售后、仅退款、部分退款，不能只按支付成功计算最终 GMV。

建议环境变量：

```text
SHOP_PLATFORM=pinduoduo
ORDER_SOURCE=jushuitan 或 api
JUSHUITAN_SHOP_ID_PINDUODUO=
PDD_CLIENT_ID=
PDD_CLIENT_SECRET=
PDD_ACCESS_TOKEN=
```

验收标准：

- 用聚水潭或拼多多 API 拉到真实拼多多订单。
- 订单明细中有 `订单号`、`支付时间`、`实收款`、`售后状态`。
- 没有订单时必须能区分“真实 0 单”和“授权/接口未打通”。

### 5.2 拼多多投流数据

已实现：

- 暂无正式拼多多投流 collector。

建议实现：

1. 第一阶段支持拼多多推广后台导出导入，快速验证字段和 ROI 口径。
2. 第二阶段接入拼多多推广/营销 API，按账户、计划、单元、日期拉取。
3. 如果 API 权限拿不到，保留“运营导出文件 -> 标准化导入 -> 飞书 upsert”作为稳定路径。

建议新增文件：

```text
shopops/collectors/pdd_ad_api.py
shopops/collectors/pdd_ad_export.py
scripts/import_pdd_ads_to_feishu.py
tests/test_pdd_ad_import.py
```

验收标准：

- 同一天同计划花费可重复导入且不重复。
- 字段至少包含花费、曝光、点击、成交订单数、成交金额。
- 导入文件缺列时 fail-closed，不写部分错误数据。

### 5.3 拼多多达人佣金数据

已实现：

- 暂无拼多多达人佣金 collector。

建议实现：

1. 先确认业务口径：拼多多这里的“达人佣金”通常可能对应多多进宝、直播带货佣金、招商团长/服务费或分销结算账单。不同口径接口和字段不同。
2. 如果商家后台能导出佣金结算，优先做导入器；导入字段稳定后再接 API。
3. 如果通过聚水潭或第三方服务商能拿到佣金账单，优先复用聚水潭路径，避免单独维护拼多多签名和分页。

建议字段：

```text
平台=拼多多
数据来源=多多进宝/直播佣金/聚水潭/导出
订单号
商品ID
达人/推广者ID
推广计划ID
成交金额
佣金率
预估佣金
结算佣金
结算状态
```

验收标准：

- 至少 1 条佣金明细能和 `orders_raw.订单号` 对上。
- 未结算佣金不能覆盖已结算佣金。

## 6. 天猫实现方案

### 6.1 天猫订单数据

已实现：

- `TaobaoOrderCrawler`：千牛订单中心抓取。
- `MarketplaceOrderApiCollector` 支持 `SHOP_PLATFORM=taobao`，默认方法为 `taobao.open.trades.sold.get`。
- `JushuitanQimenOrderListCollector`：面向天猫/淘宝的 Qimen 路由，方法默认为 `jushuitan.order.list.query`。
- `scripts/run_tmall_pdd_real_orders_to_feishu.py` 已包含天猫 Qimen 拉取并写飞书的逻辑。

外部事实：

- 淘宝/天猫官方文档说明 `taobao.trades.sold.get` 和 `taobao.open.trades.sold.get` 都是卖家已卖出交易查询接口，需要授权，只能获取三个月内交易，并且详情要再查单笔详情接口。
- 官方文档也强调 `type` 字段不传时只查默认订单类型，天猫一些非默认类型订单可能需要补 `type`。

建议实现：

1. 长期主路径用聚水潭/Qimen，不再依赖千牛页面抓取。
2. 保留千牛抓取作为“API 授权未打通时的临时 MVP 路径”。
3. 在 `taobao_order_list_method` 外再增加 `TAOBAO_ORDER_TYPE`、`TAOBAO_FIELDS` 配置，避免天猫特殊订单漏查。
4. 天猫订单要保留退款状态，并在日报里展示“支付 GMV”和“净 GMV”两个口径。

建议环境变量：

```text
SHOP_PLATFORM=taobao
ORDER_SOURCE=jushuitan 或 api 或 crawler
JUSHUITAN_SHOP_ID_TMALL=
JUSHUITAN_QIMEN_APP_KEY=
JUSHUITAN_QIMEN_APP_SECRET=
JUSHUITAN_QIMEN_CUSTOMER_ID=
TAOBAO_APP_KEY=
TAOBAO_APP_SECRET=
TAOBAO_SESSION_KEY=
```

验收标准：

- Qimen 能按 7 天以内窗口拉取真实天猫订单。
- 大于 7 天补数时自动分片。
- 缺 Qimen 授权时明确返回 blocker，不把 0 单当真实结果。

### 6.2 天猫投流数据

已实现：

- `TaobaoPromotionCrawler`：千牛推广中心页面/接口口径的推广中心花费。
- `scripts/run_promotion_api_to_feishu.py`：支持使用千牛推广请求中的 cookie/csrf 等参数拉取并写飞书。
- 调度器能把推广数据写入 `promotion_snapshot`，再计算 ROI/CAC。

当前限制：

- 现有投流只覆盖“推广中心总花费”或当前可解析口径，不等于直通车、万相台、引力魔方、淘宝客等全部投放明细。

建议实现：

1. 第一阶段继续用千牛推广中心总花费，满足老板看整体 ROI。
2. 第二阶段增加广告平台维度：直通车、万相台、引力魔方、超级推荐等。
3. 第三阶段把投放计划、单元、关键词/人群、商品维度拉入 `ad_spend_raw`。

建议新增：

```text
shopops/collectors/taobao_ad_api.py
scripts/run_taobao_ads_to_feishu.py
tests/test_taobao_ad_api.py
```

验收标准：

- 飞书中能同时看到总花费和分计划花费。
- 推广中心失败时 `promotion_center_cost=None`，不写 0。
- ROI 计算明确是“含广告费，不含/含达人佣金”的哪个版本。

### 6.3 天猫达人佣金数据

已实现：

- 暂无天猫达人佣金 collector。

建议实现：

1. 先确认口径：天猫达人佣金可能来自淘宝客/阿里妈妈 CPS、直播带货/热浪引擎、内容种草合作费，不能混为一个字段。
2. 如果业务主要看按订单扣佣金，优先接淘宝客/阿里妈妈订单结算明细或后台导出。
3. 如果达人合作是固定坑位费/服务费，应作为 `ad_spend_raw` 或单独 `content_cost_raw`，不要放进订单佣金。

建议字段：

```text
平台=天猫
数据来源=淘宝客/热浪引擎/阿里妈妈/导出
订单号
达人ID/渠道ID
推广位ID
成交金额
预估佣金
结算佣金
服务费
结算状态
```

验收标准：

- 能按订单号和天猫订单表对账。
- 预估佣金与结算佣金分列，不能互相覆盖。

## 7. 视频号实现方案

### 7.1 视频号订单数据

已实现：

- `MarketplaceOrderApiCollector` 支持 `SHOP_PLATFORM=wechat_channels`。
- `.env.example` 已有 `WECHAT_CHANNELS_APP_ID`、`WECHAT_CHANNELS_APP_SECRET`、`WECHAT_CHANNELS_ACCESS_TOKEN`、`WECHAT_CHANNELS_API_URL`。
- `scripts/run_jushuitan_orders_to_feishu.py` 的平台映射包含 `wechat_channels`。

建议实现：

1. 主路径优先用微信小店/视频号小店官方订单接口；如果聚水潭已经绑定视频号店铺，也可用聚水潭做统一订单入口。
2. access token 获取和刷新要独立封装，避免每个请求重复取 token。
3. 订单详情要补售后、退款、佣金/主播字段；列表接口通常不够完整。

建议环境变量：

```text
SHOP_PLATFORM=wechat_channels
ORDER_SOURCE=api 或 jushuitan
WECHAT_CHANNELS_APP_ID=
WECHAT_CHANNELS_APP_SECRET=
WECHAT_CHANNELS_ACCESS_TOKEN=
JUSHUITAN_SHOP_ID_WECHAT_CHANNELS=
```

验收标准：

- 能拉真实视频号订单并写入 `orders_raw`。
- token 失效时返回明确错误，并在任务日志记录。
- 订单金额单位如果是分，写入前统一转元。

### 7.2 视频号投流数据

已实现：

- 暂无视频号投流 collector。

建议实现：

1. 先确认投放来源：微信广告、视频号加热、直播间推广、公众号/小程序广告是否都算“投流”。
2. 如果走腾讯广告/微信广告 API，按异步报表任务方式设计 collector。
3. 如果只能导出，先做导入器，字段与 `ad_spend_raw` 对齐。

建议新增：

```text
shopops/collectors/wechat_ad_api.py
shopops/collectors/wechat_ad_export.py
scripts/import_wechat_ads_to_feishu.py
tests/test_wechat_ad_import.py
```

验收标准：

- 能按日期拿到花费、曝光、点击、转化。
- 如果平台只给日级数据，`窗口开始/结束` 明确写当天 00:00:00 到 23:59:59。

### 7.3 视频号达人佣金数据

已实现：

- 暂无视频号达人佣金 collector。

建议实现：

1. 先确认业务使用的是视频号小店联盟、优选联盟、服务商结算、还是主播合作手工结算。
2. 若官方 API 未开放或权限未批，第一阶段做结算账单导入。
3. 若订单详情中已有主播佣金/达人佣金字段，先从订单详情抽取到 `influencer_commission_raw`，后续再接独立结算接口。

建议字段：

```text
平台=视频号
数据来源=视频号联盟/微信小店/聚水潭/导出
订单号
主播/达人ID
直播间ID
成交金额
佣金率
预估佣金
结算佣金
结算状态
```

验收标准：

- 至少 1 条佣金记录能关联视频号订单号。
- 没有达人字段时，日报显示“视频号佣金未接入”，而不是 0。

## 8. 建议开发任务拆分

### P0：先把可变成真实业务价值的路径打通

1. 多平台店铺配置表
   - 新增 `platform_account_config`。
   - 支持一轮任务拉多个平台，而不是只靠全局 `SHOP_PLATFORM`。
   - 验收：同一次运行能顺序处理天猫和抖音两个平台。

2. 天猫订单 Qimen live 修复
   - 补齐 `JUSHUITAN_QIMEN_*`。
   - 保留 7 天窗口分片。
   - 验收：真实天猫订单写入飞书，重复运行不重复。

3. 抖音订单 + 抖音佣金闭环
   - 抖音订单写入 `orders_raw`。
   - 根据订单号补抖店联盟佣金。
   - 验收：订单和佣金能通过订单号关联。

4. 投流表升级
   - 将 `promotion_snapshot` 扩为通用 `ad_spend_raw` 字段，或新建 `ad_spend_raw`。
   - 天猫推广中心继续写入，同时保留 `平台=天猫`。
   - 验收：现有天猫推广测试不回退。

### P1：补齐拼多多、视频号订单和导入能力

1. 拼多多订单 live 验证
   - 聚水潭优先，直连 API 备用。
   - 验收：真实拼多多订单写入飞书。

2. 视频号订单 live 验证
   - 官方 token 获取、订单列表、订单详情。
   - 验收：真实视频号订单写入飞书。

3. 投流导入器
   - 拼多多推广导出导入。
   - 视频号/微信广告导出导入。
   - 验收：导入文件格式错误 fail-closed。

### P2：补齐各平台达人佣金和高级 ROI

1. 拼多多佣金账单导入/API。
2. 天猫淘宝客/热浪佣金导入/API。
3. 视频号联盟佣金导入/API。
4. 日报增加多口径 ROI：
   - `广告 ROI = GMV / 广告花费`
   - `含预估佣金 ROI = GMV / (广告花费 + 预估佣金 + 技术服务费)`
   - `含结算佣金 ROI = GMV / (广告花费 + 结算佣金 + 技术服务费)`

## 9. 代码改造建议

### 9.1 新增统一结果模型

当前已有 `OrderCollectResult`、`PromotionCollectResult`。建议新增：

```python
@dataclass
class AdSpendCollectResult:
    success: bool
    status: CollectStatus
    source: str
    platform: str
    account_id: str
    rows: list[dict[str, Any]]
    total_cost: float | None
    fetched_at: datetime
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class InfluencerCommissionCollectResult:
    success: bool
    source: str
    platform: str
    shop_id: str
    rows: list[dict[str, Any]]
    total_estimated_commission: float | None
    total_settled_commission: float | None
    fetched_at: datetime
    error_code: str | None = None
    error_message: str | None = None
```

现有抖音佣金 result 可以迁移到这个通用模型。

### 9.2 新增 collector factory

建议从当前：

```text
create_order_collector(settings)
create_promotion_collector(settings)
```

升级为：

```text
create_order_collector(platform_account)
create_ad_spend_collector(platform_account)
create_influencer_commission_collector(platform_account)
```

这样每个平台可以独立配置拉取方式：

| 平台 | order_source | ad_source | commission_source |
|---|---|---|---|
| 天猫 | qimen/jushuitan/api/crawler | qianniu_pc/alimama/export | taobaoke/export |
| 抖音 | jushuitan/doudian_api | qianchuan/export | doudian_alliance/jushuitan |
| 拼多多 | jushuitan/pdd_api | pdd_ads/export | pdd_duoduojinbao/export |
| 视频号 | wechat_api/jushuitan | wechat_ads/export | wechat_alliance/export |

### 9.3 调度器建议

当前 `Scheduler.run_once()` 是单平台一轮：订单 + 推广 + 快照 + 指标。

建议拆成三种任务：

| 任务 | 频率 | 作用 |
|---|---|---|
| `order_collect` | 5-10 分钟 | 拉订单原始明细 |
| `ad_spend_collect` | 10-30 分钟 | 拉投流数据 |
| `commission_collect` | 30-60 分钟或日级 | 拉佣金/结算数据 |
| `metric_snapshot` | 10 分钟 | 聚合订单/投流/佣金生成指标 |
| `daily_reconcile` | 每日 | 做退款、佣金结算、平台后台口径校正 |

这样不会因为某个平台佣金接口慢，阻塞订单和投流。

## 10. 验收标准

### 10.1 通用验收

每个“平台 + 数据类型”上线前必须满足：

1. 有真实授权环境变量或导入文件样例。
2. 有至少 1 条真实业务数据写入飞书。
3. 有 readback 证据证明飞书里的字段和值与本次拉取一致。
4. 重复运行不会重复写行。
5. 缺权限、token 过期、接口失败、返回空数据能区分。
6. 失败时不写假 0。
7. 任务日志记录拉取条数、写入条数、错误码、错误信息。

### 10.2 推荐测试清单

```powershell
python -m pytest -q tests\test_marketplace_order_api.py
python -m pytest -q tests\test_jushuitan_order_api.py tests\test_jushuitan_qimen_order_api.py
python -m pytest -q tests\test_doudian_alliance_api.py tests\test_jushuitan_influencer_api.py
python -m pytest -q tests\test_feishu_storage_contract.py
python -m pytest -q tests\test_storage_and_scheduler.py tests\test_metric_service.py
python scripts\acceptance\secret_guard.py
```

后续新增平台时，每个 collector 至少补：

- 缺凭证 fail-closed 测试。
- 签名/请求参数测试。
- 平台返回错误测试。
- 字段归一化测试。
- 分页测试。
- 飞书 upsert 测试。

## 11. 外部授权清单

| 平台 | 订单权限 | 投流权限 | 达人佣金权限 |
|---|---|---|---|
| 抖音 | 抖店订单查询或聚水潭抖音店铺授权 | 巨量千川/抖音广告报表或后台导出 | 精选联盟订单佣金或聚水潭佣金接口 |
| 拼多多 | 拼多多订单 API 或聚水潭拼多多店铺授权 | 拼多多推广报表 API 或后台导出 | 多多进宝/直播佣金/招商结算 API 或导出 |
| 天猫 | 淘宝/TOP 商家订单、Qimen/聚水潭授权 | 千牛推广中心、阿里妈妈/万相台等报表 | 淘宝客/热浪/阿里妈妈结算明细 |
| 视频号 | 微信小店/视频号订单 API 或聚水潭授权 | 微信广告/视频号加热/腾讯广告报表 | 视频号联盟/主播佣金/结算账单 |

拿权限时不要只问“有没有 API”，要问清楚：

- 能查多长时间范围？
- 是否支持增量？
- 是否支持订单详情？
- 是否支持退款/售后？
- 金额单位是元还是分？
- 是否有达人/直播间/广告归因字段？
- 是否有结算态和结算时间？
- 是否限制分页、频率、单次窗口？

## 12. 最推荐的实施顺序

1. 先把天猫订单 Qimen 和抖音订单/佣金做成真实闭环。
2. 再把投流表升级成通用多平台结构，但先让天猫推广中心继续稳定写入。
3. 接拼多多、视频号订单，优先聚水潭或官方订单 API。
4. 用导入器补拼多多/视频号/天猫达人佣金和投流，先形成可对账数据。
5. 最后逐步把导入器替换成官方 API collector。

这个顺序的原因很简单：订单是 GMV 的底座，投流是 ROI 的成本底座，达人佣金是“真实利润口径”的成本补充。没有真实订单前，投流和佣金再细也无法证明经营结果。

## 13. 参考资料

- 淘宝开放平台：`taobao.trades.sold.get` / `taobao.open.trades.sold.get` 订单查询文档：<https://developer.alibaba.com/docs/api.htm?apiId=46&source=search>、<https://developer.alibaba.com/docs/api.htm?apiId=45011&source=search>
- 抖店开放平台订单接入说明：<https://op.jinritemai.com/docs/guide-docs/205>
- 拼多多开放平台入口：<https://open.yangkeduo.com/>
- 微信开发者文档入口：<https://developers.weixin.qq.com/>

拼多多和视频号的具体接口字段，请以后续商家后台/开放平台授权包中可见的官方文档为准。当前仓库已把相关接口名做成环境变量，便于拿到最终授权文档后替换。
