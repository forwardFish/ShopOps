# ShopOps Goal API/DB Contract Matrix

| API/Service ID | Method/Function | Case | Request/Input | Response/Output | Storage Side Effect | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| API-ORDER-CRAWLER | `TaobaoOrderCrawler.fetch_today()` | success | 千牛订单中心文本/CDP page | `OrderCollectResult(success=True)` + orders | `orders_raw`, `monitor_snapshot` | T04 | PLANNED |
| API-ORDER-CRAWLER | `TaobaoOrderCrawler.fetch_today()` | login/CDP failure | CDP 不可用或登录失效 | `success=False`, null metrics | `task_run_log`, alert | T04/T08 | PLANNED |
| API-ORDER-API | `TaobaoOrderApiCollector.fetch_today()` | future boundary | `ORDER_SOURCE=api` | 不阻塞当前 crawler MVP | none or future storage | T05 | PLANNED |
| API-PROMO | `TaobaoPromotionCrawler.fetch_today()` | success | 推广中心页面 | 只读“花费” | `promotion_snapshot`, `monitor_snapshot` | T06 | PLANNED |
| API-METRIC | `MetricService.build_snapshot/build_delta()` | success/error | collector results | ROI/CAC/delta/status | `monitor_snapshot`, `metrics_10min` | T07 | PLANNED |
| API-SCHEDULER | `Scheduler.run_once()` | full collect | collectors + storage | total_status/logs | all P0 tables | T09/T11 | PLANNED |
| API-DAILY | `DailyReportService.send_daily_report()` | report | latest snapshot | daily text + row | `daily_report` | T10 | PLANNED |
