# 聚水潭抖音达人佣金接入说明

## 当前结论

飞书多维表已在既有 Base `KhbEbksLbauw0fssL6EcKAnlnOe` 中新增：

| 项目 | 值 |
|---|---|
| 飞书表名 | 抖音达人佣金明细表 |
| 飞书表 ID | `tblhBsehmQbzWEVm` |
| 环境变量 | `FEISHU_TABLE_DOUYIN_INFLUENCER_COMMISSION` |
| 代码内部表键 | `douyin_influencer_commission` |

代码已实现聚水潭达人佣金采集器和飞书写入路径，但真实聚水潭接口尚未打通。当前凭据调用以下 method 均返回 `190: 接口不存在`：

| 尝试 method | 结果 |
|---|---|
| `doudian.alliance.kol.orders.query` | `190: 接口不存在` |
| `alliance.getOrderList` | `190: 接口不存在` |
| `/alliance/getOrderList` | `190: 接口不存在` |
| `alliance/getOrderList` | `190: 接口不存在` |
| `doudian.alliance.getOrderList` | `190: 接口不存在` |

这说明当前问题不在飞书建表或本地字段映射，而在聚水潭开放平台侧的达人佣金接口名称或权限。

## 已实现文件

| 文件 | 作用 |
|---|---|
| `shopops/collectors/jushuitan_influencer_api.py` | 聚水潭达人佣金采集器，支持分页、签名、字段归一化、fail-closed |
| `scripts/bootstrap_douyin_influencer_table.py` | 在既有飞书 Base 中创建或复用达人佣金表 |
| `scripts/run_jushuitan_influencers_to_feishu.py` | 从聚水潭拉取达人佣金数据并写入本地或真实飞书 |
| `shopops/storage/feishu_bootstrap.py` | 新增达人佣金表结构 |
| `shopops/storage/feishu_bitable.py` | 真实飞书 OpenAPI 写入达人佣金表 |
| `shopops/storage/local_feishu.py` | 本地飞书 double 写入达人佣金表 |
| `tests/test_jushuitan_influencer_api.py` | 聚水潭达人佣金采集器单测 |

## 飞书字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `unique_key` | 文本 | 去重键，默认 `douyin_influencer_{shop_id}_{order_id}` |
| `平台` | 文本 | 固定为 `抖音` |
| `数据来源` | 文本 | 固定为 `聚水潭` |
| `店铺ID` | 文本 | 聚水潭/抖音店铺 ID |
| `店铺名称` | 文本 | 店铺名称 |
| `采集时间` | 文本 | 采集时间 |
| `订单号` | 文本 | 抖音/聚水潭订单号 |
| `下单时间` | 文本 | 下单或支付时间 |
| `达人ID` | 文本 | 达人/作者 ID |
| `达人昵称` | 文本 | 达人/作者昵称 |
| `内容类型` | 文本 | 直播、短视频、商品卡等来源 |
| `直播间/视频ID` | 文本 | 直播间、视频或素材 ID |
| `商品ID` | 文本 | 商品 ID |
| `商品名称` | 文本 | 商品名称 |
| `支付金额` | 数字 | 订单支付金额 |
| `佣金率` | 数字 | 佣金比例，10% 归一化为 `0.1` |
| `预估佣金` | 数字 | 预估达人佣金 |
| `结算佣金` | 数字 | 实际结算佣金 |
| `技术服务费` | 数字 | 平台/技术服务费 |
| `结算状态` | 文本 | 佣金或订单结算状态 |
| `原始数据` | 文本 | 聚水潭返回的原始 JSON |

## 需要向聚水潭确认

请向聚水潭客服、实施或开放平台技术支持确认以下任一信息：

1. 当前账号是否开通“抖音达人佣金 / 精选联盟 / 达人订单明细”开放接口权限。
2. 如果已开通，在聚水潭开放平台 `https://open.erp321.com/api/open/query.aspx` 下准确的 `method` 是什么。
3. 返回数据中达人和佣金字段的原始字段名，尤其是达人 ID、达人昵称、订单号、支付金额、佣金率、预估佣金、结算佣金、服务费、结算状态。
4. 如果聚水潭没有该接口，是否只能从抖店官方接口 `/alliance/getOrderList` 获取。

抖店官方文档中，联盟达人佣金订单明细对应接口为 `/alliance/getOrderList`，公共参数 method 为 `alliance.getOrderList`。但当前聚水潭开放接口不识别这个 method，所以不能直接把抖店官方 method 当作聚水潭 method。

## 抖店官方直连备用方案

由于当前聚水潭接口返回 `190: 接口不存在`，项目已新增抖店官方 `/alliance/getOrderList` 直连脚本。

官方接口要点：

| 项目 | 值 |
|---|---|
| 请求域名 | `https://openapi-fxg.jinritemai.com` |
| API path | `/alliance/getOrderList` |
| method | `alliance.getOrderList` |
| 权限 | 精选联盟 / 联盟订单明细查询；可能需要定向权限 |
| 授权 | 需获取店铺授权 `access_token` |
| 查询方式 | 按 `order_ids` 查询，一次最多 5 个订单号 |
| 签名 | `hmac-sha256` |

新增文件：

| 文件 | 作用 |
|---|---|
| `shopops/collectors/doudian_alliance_api.py` | 抖店官方达人佣金采集器 |
| `scripts/run_doudian_alliance_to_feishu.py` | 抖店官方达人佣金写入飞书脚本 |
| `tests/test_doudian_alliance_api.py` | 官方接口签名、分组、字段归一化测试 |

需要配置：

```env
DOUDIAN_APP_KEY=
DOUDIAN_APP_SECRET=
DOUDIAN_ACCESS_TOKEN=
DOUDIAN_API_URL=https://openapi-fxg.jinritemai.com
DOUDIAN_SIGN_METHOD=hmac-sha256
DOUDIAN_ALLIANCE_ORDER_IDS=
```

拿到抖店凭据和订单号后，运行真实飞书写入：

```powershell
python scripts\run_doudian_alliance_to_feishu.py --storage feishu --order-ids "订单号1,订单号2"
```

如果暂时只想验证本地写入链路：

```powershell
python scripts\run_doudian_alliance_to_feishu.py --storage local --order-ids "订单号1,订单号2" --local-path cache\doudian_alliance_local.json
```

注意：`/alliance/getOrderList` 本身不按日期拉全量列表，只能对已知订单号查询达人佣金明细。生产运行时需要先从抖店订单接口、聚水潭订单接口或飞书订单表中拿到抖音订单号，再批量调用该接口补齐达人和佣金字段。

## 后续命令

拿到聚水潭 method 后，更新 `.env`：

```powershell
$env:JUSHUITAN_INFLUENCER_QUERY_METHOD = "聚水潭确认的method"
```

然后运行真实写入：

```powershell
python scripts\run_jushuitan_influencers_to_feishu.py --storage feishu
```

如果成功，脚本会输出 `success=true`、`row_count`、`saved_count` 和佣金汇总。
