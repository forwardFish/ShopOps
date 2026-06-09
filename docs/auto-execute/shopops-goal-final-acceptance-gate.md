# ShopOps Goal Final Acceptance Gate

## Pure PASS 必须同时满足
- T00-T13 required result JSON 和 HANDOFF 都存在且新鲜。
- 所有 P0 需求有实现证据和验证证据。
- 飞书 9 张表的字段映射、payload、upsert、重复运行、pending cache、replay、读回都有证据。
- 千牛 PC 订单中心和推广中心真实 CDP 证据存在，或最终明确为 `BLOCKED_BY_ENVIRONMENT`，不得伪造 PASS。
- 全量 pytest、acceptance script、secret guard、报告完整性检查通过。
- 采集失败没有任何 0 污染。

## Fail Closed
缺任何 P0 证据则最终为 `REPAIR_REQUIRED` 或 `BLOCKED_BY_ENVIRONMENT`，不能 pure PASS。
