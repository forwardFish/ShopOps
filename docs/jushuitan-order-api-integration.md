# Jushuitan unified order API integration

This adds a second order acquisition path while keeping the existing direct platform API path:

- Direct platform APIs: `ORDER_SOURCE=api`
- Unified Jushuitan API: `ORDER_SOURCE=jushuitan`
- Qianniu PC crawler remains: `ORDER_SOURCE=crawler`

## Configure

```powershell
$env:ORDER_SOURCE = "jushuitan"
$env:USE_MOCK_COLLECTORS = "false"
$env:SHOP_PLATFORM = "taobao" # or pinduoduo / doudian / wechat_channels, used as local metadata
$env:JUSHUITAN_PARTNER_ID = "<partner-id>"
$env:JUSHUITAN_PARTNER_KEY = "<partner-key>"
$env:JUSHUITAN_TOKEN = "<authorized-token>"
```

Optional:

```powershell
$env:JUSHUITAN_API_URL = "https://open.erp321.com/api/open/query.aspx"
$env:JUSHUITAN_ORDER_QUERY_METHOD = "orders.single.query"
$env:JUSHUITAN_SHOP_IDS = "shop-id-1,shop-id-2"
$env:JUSHUITAN_PAGE_SIZE = "100"
```

Run a one-shot order pull:

```powershell
python scripts\run_platform_orders.py
```

Run the existing scheduler/storage path:

```powershell
python main.py
```

## Implemented API shape

Default public parameters:

- `partnerid`
- `token`
- `method`
- `ts`
- `sign`

Default method:

- `orders.single.query`

Default request body:

```json
{
  "page_index": 1,
  "page_size": 100,
  "modified_begin": "YYYY-MM-DD 00:00:00",
  "modified_end": "YYYY-MM-DD HH:mm:ss"
}
```

If `JUSHUITAN_SHOP_IDS` is set to one ID, the body also includes `shop_id`. If multiple comma-separated IDs are set, it includes `shop_ids`.

Signature:

```text
MD5(method + partnerid + "token" + token + "ts" + ts + partner_key)
```

Official endpoints:

- Production: `https://open.erp321.com/api/open/query.aspx`
- Sandbox: `https://c.jushuitan.com/api/open/query.aspx`

## Official-doc boundary

The Jushuitan official order-query page for `orders.single.query` says this interface cannot query Taobao/Tmall or Pinduoduo orders directly; Taobao/Tmall should go through Jushita Qimen. The code keeps `JUSHUITAN_ORDER_QUERY_METHOD` configurable so the approved method from your Jushuitan app package can be swapped without editing code.

## Local verification

```powershell
python -m pytest -q tests\test_jushuitan_order_api.py tests\test_marketplace_order_api.py tests\test_taobao_order_api_boundary.py
```

The tests verify:

- `ORDER_SOURCE=jushuitan` uses the new collector.
- Missing credentials fail closed and do not write zero metrics.
- Signed public params are generated.
- Jushuitan response orders are normalized.
- Pagination continues until a short page.

Mock smoke:

```powershell
$env:ORDER_SOURCE = "jushuitan"
$env:USE_MOCK_COLLECTORS = "true"
python scripts\run_platform_orders.py
```

Live sandbox note:

- A temporary run against `https://c.jushuitan.com/api/open/query.aspx` with publicly documented sandbox credentials timed out from this environment on 2026-06-04.
- Minimal HEAD probes to both sandbox and production domains also did not return normal HTTP status in this environment.
- Treat the sandbox/live call as pending until the operator's network can reach Jushuitan and approved credentials are available.
