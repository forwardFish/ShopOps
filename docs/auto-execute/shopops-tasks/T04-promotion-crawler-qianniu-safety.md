# Task T04 - promotion-crawler-qianniu-safety

## 执行命令
```powershell
Set-Location -LiteralPath "D:\lyh\agent\agent-frame\ShopOps"
codex exec "execute D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-tasks\T04-promotion-crawler-qianniu-safety.md; write result JSON and HANDOFF; do not stop after planning"
```

## 实现范围
本项目是中文项目。所有文档、页面显示、飞书表名和字段名都必须使用中文。
飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
当前版本推广数据只通过千牛 PC 客户端中的推广中心页面采集，并且只读取经营概览里的“花费”项目。

本任务必须实现的当前版本范围：
- 打开千牛 PC 客户端内的推广中心页面，示例 URL 形态为 `https://qn.taobao.com/home.htm/tuiguangcenter_new/`。
- 只读取“花费”这个指标。
- 写入 `promotion_snapshot` 时推广渠道固定为“推广中心”，费用字段使用“今日累计消耗(元)”。
- `monitor_snapshot` 中的推广消耗来自推广中心“花费”。
- 登录失效、验证码、权限不足、千牛未运行、页面结构变化或无法读取花费时返回失败状态和错误信息，不得写 0 污染指标。

## 必须读取的输入
- `AGENTS.md`
- `docs/taobao_mvp_requirements.md`
- `docs/taobao_mvp_development.md`
- `docs/auto-execute/shopops-external-data-validation-matrix.md`

## 允许改动文件
- `shopops/**`
- `tests/**`
- `scripts/**`
- `docs/auto-execute/**`

## 禁止事项
- 本任务聚焦真实千牛 PC 推广中心页面采集；不得使用淘宝开放平台补充推广数据，不得绕过登录、验证码、权限或平台安全机制。
- 不得使用普通浏览器、淘宝网页版或千牛网页版替代千牛 PC 客户端推广中心。
- 不得新增除推广中心之外的推广采集页面。
- 不得采集曝光、点击、转化、投入产出比、总成交金额。
- 不得采集或拆分直通车、万相台、引力魔方等推广渠道。
- 不得执行任何投放修改、预算修改、充值或推广操作。
- 采集失败不得写入数字0污柡指标。

## 验收标准
- 飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
- 推广中心页面采集必须证明：只读取“花费”，只写 1 条“推广中心”快照，不产生直通车/万相台/引力魔方拆分记录。
- “花费”读取失败时必须写失败状态和错误信息，`promotion_snapshot` 与 `monitor_snapshot` 不得写 0。
- 不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。

## 后续测试与证据
| type | command | path |
| --- | --- | --- |
| result | write result | `docs/auto-execute/results/T04.json` |
| handoff | write handoff | `docs/auto-execute/latest/T04-HANDOFF.md` |
| logs | write logs | `docs/auto-execute/logs/T04/` |

## 依赖与续跑门槛
| dependency | evidence | rule |
| --- | --- | --- |
| previous result JSON and HANDOFF | result JSON + HANDOFF | only skip when both exist |

## 防停止规则
- 不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。

## 失败修复路由
| status | output | next |
| --- | --- | --- |
| REPAIR_REQUIRED | result JSON + repair item | repair queue |
| BLOCKED_BY_ENVIRONMENT | blocker file | retry or limitation |

## 输出文件
- `promotion-crawler-qianniu-safety`

## 结果 JSON
`docs/auto-execute/results/T04.json`

## HANDOFF
`docs/auto-execute/latest/T04-HANDOFF.md`

## 失败状态
| status | meaning |
| --- | --- |
| REPAIR_REQUIRED | gap found |
| BLOCKED_BY_ENVIRONMENT | 缺少真实千牛 PC 会话、真实飞书授权或必要本地运行环境时必须写阻塞证据；缺少淘宝 API 凭据不阻塞当前 crawler 版本 |
