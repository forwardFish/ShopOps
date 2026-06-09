# Platform order API integration

This note records the current API-facing order collection paths for the four requested platforms. The code is ready for credential substitution, but live order pulling still requires approved merchant/app permissions from each platform.

## Supported values

Set these common variables first:

```powershell
$env:ORDER_SOURCE = "api"
$env:USE_MOCK_COLLECTORS = "false"
$env:SHOP_ID = "<your-shop-id>"
$env:SHOP_NAME = "<your-shop-name>"
```

Then set exactly one `SHOP_PLATFORM`:

```text
taobao
pinduoduo
doudian
wechat_channels
```

Run a single order pull:

```powershell
python scripts\run_platform_orders.py
```

Run the scheduler path that also writes storage/metrics:

```powershell
python main.py
```

## Taobao / Tmall / Qianniu

Use `SHOP_PLATFORM=taobao`.

```powershell
$env:TAOBAO_APP_KEY = "<app-key>"
$env:TAOBAO_APP_SECRET = "<app-secret>"
$env:TAOBAO_SESSION_KEY = "<seller-session-key>"
```

Implemented default:

- Gateway: `https://eco.taobao.com/router/rest`
- List method: `taobao.open.trades.sold.get`
- Configurable env override: `TAOBAO_ORDER_LIST_METHOD`
- Signature: TOP MD5 signature over sorted request params.

Notes:

- Alibaba developer docs list seller trade APIs including `taobao.open.trades.sold.get`, `taobao.open.trade.get`, `taobao.open.trades.sold.increment.get`, and the common TOP public parameters/signature model.
- For older app categories, you may need to override `TAOBAO_ORDER_LIST_METHOD=taobao.trades.sold.get`.

## Pinduoduo

Use `SHOP_PLATFORM=pinduoduo`.

```powershell
$env:PDD_CLIENT_ID = "<client-id>"
$env:PDD_CLIENT_SECRET = "<client-secret>"
$env:PDD_ACCESS_TOKEN = "<access-token>"
```

Implemented default:

- Gateway: `https://gw-api.pinduoduo.com/api/router`
- List type: `pdd.order.number.list.increment.get`
- Detail type: `pdd.order.information.get`
- Configurable env overrides: `PDD_ORDER_LIST_TYPE`, `PDD_ORDER_DETAIL_TYPE`
- Signature: POP MD5 signature over sorted request params.

Notes:

- The public Pinduoduo docs site was not fetchable from this environment, so the connector keeps the method names configurable.
- If your approved app exposes a different order-list type, change `PDD_ORDER_LIST_TYPE` without changing code.

## Doudian / Qianchuan

Use `SHOP_PLATFORM=doudian`.

```powershell
$env:DOUDIAN_APP_KEY = "<app-key>"
$env:DOUDIAN_APP_SECRET = "<app-secret>"
$env:DOUDIAN_ACCESS_TOKEN = "<access-token>"
```

Implemented default:

- Gateway: `https://openapi-fxg.jinritemai.com`
- List path/method: `/order/searchList` / `order.searchList`
- Signature: `hmac-sha256` by default, configurable with `DOUDIAN_SIGN_METHOD=md5`.

Notes:

- Doudian official docs recommend `/order/searchList` for order lists and `/order/orderDetail` for details.
- Qianchuan ad APIs are separate from Doudian order APIs. This implementation targets order acquisition first; ad-cost collection can share the existing scheduler/storage flow later.

## WeChat Channels / WeChat Store

Use `SHOP_PLATFORM=wechat_channels`.

```powershell
$env:WECHAT_CHANNELS_APP_ID = "<appid>"
$env:WECHAT_CHANNELS_APP_SECRET = "<app-secret>"
```

Or provide a token directly:

```powershell
$env:WECHAT_CHANNELS_ACCESS_TOKEN = "<access-token>"
```

Implemented default:

- Token: `/cgi-bin/token`
- List path: `/channels/ec/order/list/get`
- Detail path: `/channels/ec/order/get`

Notes:

- If `WECHAT_CHANNELS_ACCESS_TOKEN` is blank, the script fetches one from `appid + secret`.
- The official WeChat docs page was not fetchable from this environment, but the endpoint names are kept isolated in code and can be changed in one place if your approval package names a newer route.

## Verification already run

```powershell
python -m pytest -q tests\test_marketplace_order_api.py tests\test_taobao_order_api_boundary.py
```

Result: `12 passed`.

Full `python -m pytest -q` is currently blocked during collection by access-denied historical pytest temp directories under `docs/auto-execute/logs/...`.

`python -m pytest -q tests` currently has three pre-existing Feishu bootstrap failures unrelated to this connector: the tests hit live Feishu table listing and still expect only two platform tables.
