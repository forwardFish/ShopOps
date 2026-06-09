# Task T06 - alerts-task-log-daily-report

## 执行命令
```powershell
Set-Location -LiteralPath "D:\lyh\agent\agent-frame\ShopOps"
codex exec "execute D:\lyh\agent\agent-frame\ShopOps\docs\auto-execute\shopops-tasks\T06-alerts-task-log-daily-report.md; write result JSON and HANDOFF; do not stop after planning"
```

## 实现范围
本项目是中文项目。所有文档、页面显示、飞书表名和字段名都必须使用中文。
飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
当前版本只要求真实飞书多维表格和真实千牛 PC 页面采集；淘宝开放平台 API 仅作为后续阶段预留，缺少 TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_SESSION_KEY 不得阻塞当前 crawler 版本。必须仅使用环境变量凭据和已登录授权会话，缺失真实飞书或千牛 PC 会话时写入 BLOCKED_BY_ENVIRONMENT，不得冒充 PASS。

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
- 当前版本只要求真实飞书多维表格和真实千牛 PC 页面采集；淘宝开放平台 API 仅作为后续阶段预留，缺少 TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_SESSION_KEY 不得阻塞当前 crawler 版本。必须仅使用环境变量凭据和已登录授权会话，缺失真实飞书或千牛 PC 会话时写入 BLOCKED_BY_ENVIRONMENT，不得冒充 PASS。
- 采集失败不得写入数字0污柡指标。

## 验收标准
- 飞书数据是最重要的验收面。必须验证中文字段、unique_key、重复运行不重复、失败不写0、本地缓存和读回。
- 不能停在计划阶段。必须实施、测试、修复、写入结果JSON和HANDOFF后退出。

## 后续测试与证据
| type | command | path |
| --- | --- | --- |
| result | write result | `docs/auto-execute/results/T06.json` |
| handoff | write handoff | `docs/auto-execute/latest/T06-HANDOFF.md` |
| logs | write logs | `docs/auto-execute/logs/T06/` |

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
- `alerts-task-log-daily-report`

## 结果 JSON
`docs/auto-execute/results/T06.json`

## HANDOFF
`docs/auto-execute/latest/T06-HANDOFF.md`

## 失败状态
| status | meaning |
| --- | --- |
| REPAIR_REQUIRED | gap found |
| BLOCKED_BY_ENVIRONMENT | 缺少真实凭据或千牛 PC 会话时必须写阻塞证据，不得冒充 PASS |

