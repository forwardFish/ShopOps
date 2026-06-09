# 四平台实际数据抓取状态表

更新时间：2026-06-06

覆盖平台：抖音、天猫、视频号、拼多多。

覆盖数据：订单数据、投流数据、达人订单和佣金数据。

本文档只回答一个问题：**现在什么方式能抓到实际业务数据；哪些只是写了代码但没有打通，必须作为备用方式。**

## 状态口径

| 状态 | 含义 | 后续处理 |
|---|---|---|
| `主路径-已有实际数据证据` | 仓库里有真实接口返回、真实数值或飞书 readback 证据 | 优先保留，继续工程化 |
| `主路径-建议接口+Cookie` | 官方 OpenAPI / 服务商路径未打通，但后台接口理论上可用登录态 Cookie 抓取 | 改造为接口+Cookie 采集 |
| `备用-代码已写但未打通` | 有 collector / 脚本 / 测试，但缺授权、真实返回、真实写入证据 | 保留代码，不作为当前可用数据源 |
| `未完成` | 没有正式 collector，也没有实际数据证据 | 需要新开发，优先接口+Cookie 或后台导入 |

## 结论先行

当前能证明“有实际数据”的路径只有两类：

| 平台 | 数据 | 当前最可靠路径 | 证据 | 是否可直接作为主路径 |
|---|---|---|---|---|
| 天猫 | 投流数据 | 千牛/淘宝推广后台接口 + Cookie：`https://1bp.taobao.com/report/query.json`，参数包含 Cookie、`csrfId`、`loginPointId`、`bizCode=universalBP` | `docs/live-evidence/promotion-api-feishu-5min-3cycles/latest-run.json` 里 3 轮均成功，并且写入飞书后 readback 匹配 | 是 |
| 抖音 | 投流数据 / 千川推广订单报表 | 巨量千川 API token 路径，已跑出 `stat_cost`、GMV、订单数、投流订单列表等真实返回 | `docs/live-evidence/qianchuan_correct_api_results_utf8_20260601_20260606.json` | 可以作为主路径，但还需要整理成正式 collector + 飞书写入 |

当前不能证明“已经能抓到实际数据”的路径：

| 平台 | 数据 | 现在的问题 | 处理 |
|---|---|---|---|
| 天猫 | 订单数据 | TOP / 聚水潭 Qimen / 千牛 CDP 都没有当前 live 订单成功证据；Qimen 授权缺口明确 | 改为接口+Cookie 抓千牛订单后台接口；官方 API 和 Qimen 只保留备用 |
| 抖音 | 店铺订单数据 | 抖店订单 OpenAPI 只有代码边界，没有真实订单返回证据 | 优先找抖店后台订单列表接口+Cookie；OpenAPI 保留备用 |
| 抖音 | 达人订单和佣金 | 抖店联盟 `/alliance/getOrderList` 代码可跑但需要已知订单号；聚水潭达人佣金返回过 `190: 接口不存在` | 先用抖店/精选联盟后台接口+Cookie；官方联盟接口和聚水潭保留备用 |
| 拼多多 | 订单、投流、达人佣金 | 只有订单 API 边界或聚水潭尝试，没有实际数据成功证据 | 全部优先接口+Cookie 或后台导入；官方 API / 聚水潭保留备用 |
| 视频号 | 订单、投流、达人佣金 | 只有视频号订单 API 边界，没有实际数据成功证据；投流/佣金 collector 未完成 | 全部优先接口+Cookie 或后台导入；官方 API 保留备用 |

## 四平台矩阵

| 平台 | 数据类型 | 当前主路径 | 是否有实际数据证据 | 已写但无法作为主路径的备用代码/API | 需要改成接口+Cookie 的动作 |
|---|---|---|---|---|---|
| 天猫 | 订单数据 | `主路径-建议接口+Cookie`：抓千牛/淘宝订单后台实际请求，而不是依赖 TOP/Qimen | 无。当前只有本地解析/本地写入证据，live 订单中心 CDP 证明被环境阻塞 | TOP：`taobao.open.trades.sold.get` / `taobao.trades.sold.get`；聚水潭/Qimen：`jushuitan.order.list.query`；千牛 CDP 页面抓取 | 用登录后的千牛/淘宝订单中心抓包，确定订单列表接口、分页、时间筛选、订单金额/状态字段；新增 Cookie 接口采集器并写入 `orders_raw` |
| 天猫 | 投流数据 | `主路径-已有实际数据证据`：千牛/淘宝推广后台接口 + Cookie | 有。3 轮 live 采集成功，字段包括 `charge`、`adPv`、`click`、`roi`、`alipayInshopAmt`，并写入飞书 readback 匹配 | 页面/CDP 推广抓取和未来官方广告 API 只作为备用；当前 `PROMOTION_SOURCE=qianniu_pc` 仍是配置名，但实际可靠路径是 Cookie 接口 | 继续沿用 `scripts/run_promotion_api_to_feishu.py`；后续把 Cookie、csrf、loginPointId 做成可刷新配置，并升级为通用 `ad_spend_raw` |
| 天猫 | 达人订单和佣金 | `主路径-建议接口+Cookie` 或后台导入 | 无 | 淘宝客/阿里妈妈/热浪等仅停留在可能来源，没有 collector | 先确认业务口径是淘宝客、热浪、达人合作费还是服务费；再抓对应后台结算/订单接口，或先做导出导入 |
| 抖音 | 订单数据 | `主路径-建议接口+Cookie`：抓抖店后台订单列表接口 | 无。抖店订单 OpenAPI 只有代码边界，没有真实订单样本 | 抖店 OpenAPI：`/order/searchList` / `order.searchList`；聚水潭订单路径 | 用抖店后台登录态抓订单列表接口，覆盖分页、时间窗口、订单状态、支付金额、售后状态；OpenAPI 仅保留备用 |
| 抖音 | 投流数据 | `主路径-已有实际数据证据`：巨量千川 API token 路径 | 有。千川报表返回了真实花费、GMV、订单数、广告订单列表 | 旧 `roi` 字段组合会被接口拒绝；当前 `QianchuanReportClient` 仍是探针，不是正式调度 collector | 把已成功的千川接口字段固化为正式 `DouyinAdSpendCollector`；写入飞书投流表；如果 token 续期不稳定，再补千川后台接口+Cookie |
| 抖音 | 达人订单和佣金 | `主路径-建议接口+Cookie`：抖店/精选联盟后台达人订单或佣金接口 | 无完整可用证据。当前没有按日期全量佣金成功拉取证据 | 抖店联盟：`/alliance/getOrderList` / `alliance.getOrderList` 已写，但只能按已知订单号查，一次最多 5 个；聚水潭达人佣金 method 返回过 `190: 接口不存在` | 抓抖店精选联盟/达人订单后台接口，优先拿按日期列表；如果只能按订单号查，则先从订单表取订单号再补佣金 |
| 拼多多 | 订单数据 | `主路径-建议接口+Cookie`：抓拼多多商家后台订单接口 | 无。官方 API/聚水潭路径未证明有真实订单返回 | 拼多多 OpenAPI：`pdd.order.number.list.increment.get`、`pdd.order.information.get`；聚水潭订单路径；`scripts/run_tmall_pdd_real_orders_to_feishu.py` | 抓商家后台订单列表接口，确认订单号、支付时间、实收款、售后/退款字段；官方 API 和聚水潭只作为备用 |
| 拼多多 | 投流数据 | `主路径-建议接口+Cookie` 或后台导入 | 无 | 没有正式 collector | 抓拼多多推广后台报表接口；拿不到稳定接口时先做 CSV/XLSX 导入，字段对齐 `ad_spend_raw` |
| 拼多多 | 达人订单和佣金 | `主路径-建议接口+Cookie` 或后台导入 | 无 | 没有正式 collector；多多进宝/直播佣金/招商团长只是候选口径 | 先确认佣金口径，再抓多多进宝/直播/团长结算后台接口；拿不到接口就做账单导入 |
| 视频号 | 订单数据 | `主路径-建议接口+Cookie`：抓视频号小店/微信小店后台订单接口 | 无。官方订单 API 只有边界代码，没有真实订单返回证据 | 微信/视频号订单 API：`/channels/ec/order/list/get`、`/channels/ec/order/get`；聚水潭路径 | 抓视频号小店订单后台接口；重点确认金额单位、token/cookie 有效期、售后/退款字段 |
| 视频号 | 投流数据 | `主路径-建议接口+Cookie` 或后台导入 | 无 | 没有正式 collector | 确认投流来源是微信广告、腾讯广告、视频号加热还是直播推广；先抓后台报表接口或导入报表 |
| 视频号 | 达人订单和佣金 | `主路径-建议接口+Cookie` 或后台导入 | 无 | 没有正式 collector | 确认视频号联盟/主播佣金/服务商结算口径；优先抓结算后台接口或导入账单 |

## 备用方式清单

这些路径有代码或配置，但不能当成“当前可拿实际数据”的主路径。

| 备用方式 | 覆盖平台/数据 | 当前文件 | 为什么降级为备用 |
|---|---|---|---|
| 淘宝/TOP 订单 API | 天猫订单 | `shopops/collectors/platform_order_api.py`、`docs/platform-order-api-integration.md` | 有接口名和签名边界，但没有当前真实授权和真实订单 readback 证据 |
| 聚水潭/Qimen 订单 | 天猫订单、拼多多订单 | `shopops/collectors/jushuitan_qimen_order_api.py`、`scripts/run_tmall_pdd_real_orders_to_feishu.py` | 需要 Qimen 三件套：`JUSHUITAN_QIMEN_APP_KEY`、`JUSHUITAN_QIMEN_APP_SECRET`、`JUSHUITAN_QIMEN_CUSTOMER_ID`；普通聚水潭凭证不够；历史任务明确 blocked |
| 聚水潭普通订单 OpenAPI | 抖音/拼多多/视频号等订单 | `shopops/collectors/jushuitan_order_api.py` | 普通 OpenAPI 能力不等于当前账号已授权，且淘系/拼多多有 Qimen 边界 |
| 千牛订单 CDP 页面抓取 | 天猫订单 | `shopops/collectors/taobao_order_crawler.py` | 本地解析可用，但 live CDP 订单证明被 `127.0.0.1:9222` 环境阻塞；后续应用接口+Cookie 替代 |
| 抖店订单 OpenAPI | 抖音订单 | `shopops/collectors/platform_order_api.py` | 只有代码边界，没有真实订单返回证据 |
| 抖店联盟订单佣金 API | 抖音达人佣金 | `shopops/collectors/doudian_alliance_api.py`、`scripts/run_doudian_alliance_to_feishu.py` | 只能按已知订单号查询，不能直接按日期全量扫描；适合作为补充查询 |
| 聚水潭达人佣金 | 抖音达人佣金 | `shopops/collectors/jushuitan_influencer_api.py`、`scripts/run_jushuitan_influencers_to_feishu.py` | 当前 method 返回过 `190: 接口不存在`，问题在聚水潭接口名或权限 |
| 拼多多 OpenAPI 订单 | 拼多多订单 | `shopops/collectors/platform_order_api.py` | 有接口边界，没有真实授权和真实订单数据证据 |
| 视频号官方订单 API | 视频号订单 | `shopops/collectors/platform_order_api.py` | 有接口边界，没有真实 token、真实订单和金额单位校验证据 |

## 接口+Cookie 改造优先级

| 优先级 | 改造项 | 原因 | 验收标准 |
|---|---|---|---|
| P0 | 天猫订单接口+Cookie | 订单是 GMV 底座；TOP/Qimen/CDP 都不能证明当前可用 | 能按日期拉到真实订单，写入 `orders_raw`，重复运行不重复，失败不写假 0 |
| P0 | 抖音订单接口+Cookie | 抖音投流已有真实数据，但缺店铺订单会影响 ROI 对账 | 能拉真实抖店订单，字段包含订单号、支付时间、支付金额、订单/售后状态 |
| P0 | 抖音达人佣金接口+Cookie | 官方联盟按订单号补查可以保留，但需要按日期列表主路径 | 能按日期获得达人订单/佣金列表，或至少从订单表批量补佣金并写入佣金表 |
| P1 | 拼多多订单接口+Cookie | 官方/聚水潭未打通，先拿实际订单比等待授权更重要 | 能区分真实 0 单和接口失败，保留售后/退款状态 |
| P1 | 视频号订单接口+Cookie | 官方 API 未验证；金额单位和 token/cookie 生命周期需要实测 | 能拉真实视频号订单并写入 `orders_raw` |
| P1 | 拼多多/视频号投流接口+Cookie 或导入 | 当前完全无 collector，先形成成本数据 | 至少拿到花费、曝光、点击、成交订单数、成交金额 |
| P2 | 天猫/拼多多/视频号佣金接口+Cookie 或导入 | 佣金口径不统一，要先确认业务来源 | 佣金能按订单号关联订单表，预估佣金和结算佣金分列 |

## 当前可直接复用的实际证据

| 证据文件 | 说明 |
|---|---|
| `docs/live-evidence/promotion-api-feishu-5min-3cycles/latest-run.json` | 天猫/淘宝推广 Cookie 接口 3 轮采集并写入飞书，`matched=true` |
| `docs/live-evidence/promotion-api-only-20260605-5min-3cycles/latest-run.json` | 天猫/淘宝推广 Cookie 接口 3 轮纯 API 采集成功 |
| `docs/live-evidence/qianchuan_correct_api_results_utf8_20260601_20260606.json` | 抖音千川接口返回真实投流花费、GMV、订单数、广告订单列表 |
| `docs/auto-execute/blockers.md` | 明确记录天猫订单 CDP、飞书 live、Qimen 等历史阻塞，不应误报为已打通 |

## 文档结论

1. **天猫投流**：已经有实际数据主路径，继续用接口+Cookie。
2. **抖音投流**：已经有实际数据返回，优先整理成正式 collector；必要时再补 Cookie 路径。
3. **天猫订单、抖音订单、抖音佣金、拼多多全量、视频号全量**：当前都不能宣称已打通实际数据，应改为接口+Cookie 或后台导入主路径。
4. 已写好的官方 OpenAPI、聚水潭、Qimen、CDP crawler 代码全部保留，但统一降级为备用方式，直到它们有真实返回和飞书 readback 证据。

