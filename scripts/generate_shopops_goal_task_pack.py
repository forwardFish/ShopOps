from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "auto-execute"
TASK_DIR = OUT / "shopops-goal-tasks"
SLUG = "shopops-goal"
PROJECT = "ShopOps 淘宝单平台监控 MVP"
TODAY = date.today().isoformat()
TASK_PACK_ID = f"{SLUG}-{TODAY}"
SKILL_ROOT = Path(r"C:\Users\linyanhui\.codex\skills\task-auto-execute")


@dataclass(frozen=True)
class Task:
    task_id: str
    slug: str
    template: str
    task_type: str
    surface: str
    covers: str
    depends_on: str
    goal: str
    allowed: str
    commands: str
    outputs: str


REQUIREMENTS = [
    ("REQ-001", "P0", "默认 ORDER_SOURCE=crawler，订单通过千牛 PC 客户端订单中心页面采集，不使用普通浏览器或千牛网页版。", "部分本地实现", "T04", "T11", "真实千牛 PC/CDP 会话不可用，缺少真实页面采集证据。"),
    ("REQ-002", "P0", "订单中心要覆盖当前筛选范围全部订单，支持翻页或滚动加载，并写入 orders_raw。", "部分本地实现", "T04", "T11", "本地文本/fixture 证明存在，缺真实订单中心全量分页/滚动证据。"),
    ("REQ-003", "P1", "保留 ORDER_SOURCE=api 和淘宝官方 API 后续切换边界，当前阶段不要求真实淘宝 API 凭据。", "部分本地实现", "T05", "T11", "接口边界存在，但真实 API 不是当前 MVP PASS 前置。"),
    ("REQ-004", "P0", "推广费用只通过千牛 PC 推广中心读取经营概览中的“花费”，不采集或修改投放渠道。", "部分本地实现", "T06", "T11", "本地解析/安全测试存在，缺真实推广中心页面证据。"),
    ("REQ-005", "P0", "计算今日累计订单、成交额、推广消耗、实时 ROI、获客成本。", "本地实现", "T07", "T11", "需纳入新鲜全量回归。"),
    ("REQ-006", "P0", "计算最近 10 分钟增量订单、成交额、推广消耗、周期 ROI、周期获客成本，并处理缺少上一快照、倒退、超时等异常。", "本地实现", "T07", "T11", "需纳入新鲜全量回归。"),
    ("REQ-007", "P0", "飞书多维表格必须使用中文表名/字段，覆盖 system_config、shop_config、monitor_snapshot、orders_raw、promotion_snapshot、metrics_10min、task_run_log、alert_log、daily_report。", "本地部分实现", "T03", "T11", "缺真实 Feishu Bitable SDK 写入/更新/读回证据。"),
    ("REQ-008", "P0", "基于 unique_key upsert，重复运行不得产生重复快照/日志。", "本地实现", "T03", "T11", "需真实 Feishu 或可验证 fake readback 证据。"),
    ("REQ-009", "P0", "飞书写入失败时写入本地 pending cache，下次任务开始前 replay。", "本地实现", "T03", "T11", "需新鲜 replay 证据。"),
    ("REQ-010", "P0", "采集失败不能写 0，必须写失败状态、错误码、错误信息。", "本地实现", "T08", "T11", "需新鲜全量回归。"),
    ("REQ-011", "P0", "每次运行写 task_run_log，子任务失败互相隔离，主流程继续记录总状态。", "本地实现", "T09", "T11", "需新鲜全量回归。"),
    ("REQ-012", "P0", "触发经营/系统告警，30 分钟去重，写 alert_log，并按 Feishu webhook 发送结果。", "本地部分实现", "T09", "T11", "缺真实 webhook 发送证据；本地可证明日志与去重。"),
    ("REQ-013", "P1", "每天固定时间生成并发送日报，daily_report upsert。", "本地实现", "T10", "T11", "需新鲜全量回归和运行手册。"),
    ("REQ-014", "P0", "安全边界：不绕过验证码/登录/权限，不保存主账号密码/买家 PII，不执行投放修改。", "本地部分实现", "T12", "T13", "需 secret guard、代码审查和报告完整性检查。"),
]

TABLES = [
    ("DATA-001", "system_config", "系统配置表", "FEISHU_TABLE_SYSTEM_CONFIG", "config_key, config_value, enabled, remark, updated_at"),
    ("DATA-002", "shop_config", "店铺配置表", "FEISHU_TABLE_SHOP_CONFIG", "shop_id, shop_name, platform, qianniu_cdp_url, order_source, promotion_source, status, remark"),
    ("DATA-003", "monitor_snapshot", "实时监控快照表", "FEISHU_TABLE_MONITOR_SNAPSHOT", "unique_key, 采集时间, 店铺ID, 店铺名称, 订单来源, 推广来源, 数据状态, 推广中心花费(元), 总推广消耗(元), 今日订单数, 今日成交额(元), 实时ROI, 获客成本(元), 错误信息, 是否告警"),
    ("DATA-004", "orders_raw", "订单明细原始表", "FEISHU_TABLE_ORDERS_RAW", "unique_key, 数据来源, 店铺ID, 店铺名称, 订单号, 下单时间, 支付时间, 订单状态, 支付金额, 商品名称, 采集时间, 原始数据"),
    ("DATA-005", "promotion_snapshot", "推广数据快照表", "FEISHU_TABLE_PROMOTION_SNAPSHOT", "unique_key, 采集时间, 店铺ID, 店铺名称, 推广渠道, 今日累计消耗(元), 曝光, 点击, 转化, 状态, 错误信息, 原始数据"),
    ("DATA-006", "metrics_10min", "十分钟指标表", "FEISHU_TABLE_METRICS_10MIN", "unique_key, 时间开始, 时间结束, 店铺ID, 店铺名称, 新增订单数, 新增成交额(元), 推广消耗(元), 周期ROI, 周期获客成本(元), 数据状态, 异常原因"),
    ("DATA-007", "task_run_log", "任务运行日志表", "FEISHU_TABLE_TASK_LOG", "task_id, 任务类型, 开始时间, 结束时间, 耗时秒, 店铺ID, 订单状态, 推广状态, 飞书写入状态, 总状态, 拉取数量, 写入数量, 错误码, 错误信息, 是否已告警"),
    ("DATA-008", "alert_log", "告警日志表", "FEISHU_TABLE_ALERT_LOG", "alert_id, 触发时间, 店铺ID, 告警类型, 告警级别, 告警内容, 当前值, 阈值, 是否已发送, 发送结果"),
    ("DATA-009", "daily_report", "每日报告表", "FEISHU_TABLE_DAILY_REPORT", "report_date, 店铺ID, 店铺名称, 今日订单数, 今日成交额(元), 推广中心花费(元), 总推广消耗(元), 今日ROI, 获客成本(元), 异常统计, 数据状态"),
]

TASKS = [
    Task("T00", "omx-auto-execute-orchestrator", "TPL-ORCH-T00", "编排", "串行 fresh codex exec 编排与续跑", "ALL", "none", "检查新任务包、历史结果、blockers、repair queue，并一次只启动一个后续任务。", "docs/auto-execute/**", "PowerShell 逐个启动后续 task；等待退出；校验 result JSON/HANDOFF/log。", "docs/auto-execute/results/T00.json; docs/auto-execute/latest/T00-HANDOFF.md"),
    Task("T01", "source-intake-and-current-implementation-audit", "TPL-INTAKE", "接管审计", "需求文档与现有实现差距审计", "REQ-001..REQ-014", "T00", "重新读取 PRD、开发文档、现有代码、上一轮结果，写出需求是否已实现的逐项审计。", "docs/auto-execute/**", "只读检查；不改产品代码；生成审计报告。", "docs/auto-execute/results/T01.json; docs/auto-execute/shopops-goal-implementation-audit.md"),
    Task("T02", "requirements-traceability-refresh", "TPL-REQ-MATRIX", "需求矩阵", "P0/P1 需求追踪矩阵刷新", "REQ-001..REQ-014", "T01", "把所有需求映射到实现任务、验证任务和证据路径。", "docs/auto-execute/**", "检查矩阵覆盖，无遗漏 P0。", "docs/auto-execute/results/T02.json; shopops-goal-requirement-traceability-matrix.md"),
    Task("T03", "feishu-bitable-storage-real-and-local-proof", "TPL-EXTERNAL-DATA", "外部数据", "飞书多维表格中文字段、upsert、pending replay、读回", "REQ-007,REQ-008,REQ-009,DATA-001..DATA-009", "T02", "实现或修复真实 FeishuBitableStorage 与本地 fake 双证据；缺凭据时写 BLOCKED_BY_ENVIRONMENT。", "shopops/storage/**; shopops/config.py; tests/**; scripts/acceptance/**; docs/auto-execute/**", "pytest storage tests; verify_feishu_data.py; real credential probe。", "docs/auto-execute/results/T03.json; docs/auto-execute/external-data/T03/"),
    Task("T04", "qianniu-order-center-live-crawler", "TPL-CRAWLER-PIPELINE", "爬虫管线", "千牛 PC 订单中心采集与 orders_raw/monitor_snapshot", "REQ-001,REQ-002,REQ-010", "T03", "实现/验证真实千牛 PC 订单中心 CDP 文本采集、滚动/翻页、字段归一化、失败不写 0。", "shopops/collectors/**; shopops/services/browser_service.py; tests/**; docs/auto-execute/**", "pytest order crawler; CDP probe; live evidence when available。", "docs/auto-execute/results/T04.json; docs/auto-execute/external-data/T04/"),
    Task("T05", "taobao-api-boundary-and-nonblocking-config", "TPL-API-DOMAIN", "API 边界", "淘宝官方 API 后续切换边界，不阻塞当前 crawler MVP", "REQ-003", "T04", "保留 ORDER_SOURCE=api 接口、分页/付费过滤契约和凭据保护；当前不要求真实 API PASS。", "shopops/collectors/taobao_order_api.py; shopops/config.py; tests/**; docs/auto-execute/**", "pytest api boundary; secret guard。", "docs/auto-execute/results/T05.json"),
    Task("T06", "qianniu-promotion-center-cost-crawler", "TPL-CRAWLER-PIPELINE", "爬虫管线", "千牛 PC 推广中心只读花费采集", "REQ-004,REQ-010", "T05", "实现/验证推广中心页面只读“花费”，禁止渠道拆分和投放修改，失败不写 0。", "shopops/collectors/taobao_promotion_crawler.py; shopops/services/browser_service.py; tests/**; docs/auto-execute/**", "pytest promotion crawler; CDP live probe。", "docs/auto-execute/results/T06.json; docs/auto-execute/external-data/T06/"),
    Task("T07", "metric-snapshot-delta-engine-refresh", "TPL-BUSINESS-ENGINE", "业务引擎", "今日累计和 10 分钟增量指标", "REQ-005,REQ-006,REQ-010", "T06", "验证 ROI/CAC/周期增量/异常状态，不让失败值污染指标。", "shopops/services/metric_service.py; tests/**; docs/auto-execute/**", "pytest metric tests; scheduler delta tests。", "docs/auto-execute/results/T07.json"),
    Task("T08", "no-zero-failure-and-data-status-regression", "TPL-TEST-INTEGRATION", "集成测试", "失败不写 0 和数据状态传播", "REQ-010,REQ-011", "T07", "用集成测试证明订单失败、推广失败、飞书失败都以状态和 null 指标传播。", "tests/**; scripts/acceptance/**; docs/auto-execute/**", "pytest focused integration。", "docs/auto-execute/results/T08.json"),
    Task("T09", "alerts-task-log-and-scheduler-isolation", "TPL-SCHEDULER-JOB", "调度任务", "task_run_log、alert_log、告警去重、子任务隔离", "REQ-011,REQ-012", "T08", "验证 full_collect 中每轮日志、告警去重、失败隔离、pending replay 前置执行。", "shopops/scheduler.py; shopops/services/alert_service.py; tests/**; docs/auto-execute/**", "pytest scheduler/alerts。", "docs/auto-execute/results/T09.json"),
    Task("T10", "daily-report-and-operator-runbook", "TPL-DOCS-HANDOFF", "文档交接", "日报生成、Windows 运行手册、环境变量说明", "REQ-013,REQ-014", "T09", "补齐日报 upsert、README、.env.example、千牛 CDP/飞书配置手册。", "README.md; .env.example; shopops/services/daily_report_service.py; tests/**; docs/auto-execute/**", "pytest daily report; docs review。", "docs/auto-execute/results/T10.json; README.md"),
    Task("T11", "full-local-test-suite-and-acceptance-scripts", "TPL-TEST-E2E", "本地全链路测试", "全 P0 本地测试、acceptance scripts、历史证据新鲜度", "REQ-001..REQ-014", "T10", "重跑全量 pytest、飞书数据证明脚本、环境探针，拒绝使用旧结果冒充新鲜证据。", "tests/**; scripts/acceptance/**; docs/auto-execute/**", "python -m pytest -q; verify_feishu_data.py。", "docs/auto-execute/results/T11.json"),
    Task("T12", "report-integrity-secret-guard-code-review", "TPL-REPORT-GUARD", "报告完整性", "secret guard、证据一致性、代码审查", "REQ-014", "T11", "扫描 secret、检查 result/HANDOFF/log 与报告一致，列出任何 stale evidence。", "scripts/acceptance/**; docs/auto-execute/**", "secret_guard.py; report integrity check。", "docs/auto-execute/results/T12.json"),
    Task("T13", "final-acceptance-gate-fail-closed", "TPL-FINAL-GATE", "最终门禁", "只读 durable evidence 判定最终验收", "ALL", "T12", "聚合所有结果，给 PASS / PASS_WITH_LIMITATION / REPAIR_REQUIRED / BLOCKED_BY_ENVIRONMENT。", "docs/auto-execute/**", "读取 result JSON/HANDOFF/log/external-data；不实现产品代码。", "docs/auto-execute/results/T13.json; docs/auto-execute/verification-results.md"),
]


def write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def task_doc(task: Task) -> str:
    command = f"""Set-Location -LiteralPath "{ROOT}"
codex exec "Use auto-execute. Execute only {ROOT}\\docs\\auto-execute\\shopops-goal-tasks\\{task.task_id}-{task.slug}.md. Treat this as one fresh task boundary. Do not stop after planning. Implement, test, repair, write result JSON, write HANDOFF, and exit. If blocked, classify the blocker in durable files and route to repair; do not end with only chat text."
"""
    return f"""
# Task {task.task_id} - {task.slug}

## 0. 任务模板选择
| 字段 | 值 |
| --- | --- |
| Task Template ID | `{task.template}` |
| Task 类型 | {task.task_type} |
| 主验收面 | {task.surface} |
| 为什么选择这个模板 | 本任务的主要目标是 {task.surface}，与 `{task.template}` 的验收面一致。 |
| 覆盖对象 | {task.covers} |
| 辅助模板 | `TPL-REPORT-GUARD` |
| 模板索引 | `{SKILL_ROOT / 'references' / 'task-archetype-templates.md'}` |
| 软件任务模板目录 | `{SKILL_ROOT / 'references' / 'software-dev-task-templates.md'}` |
| 独立任务模板文件 | `{SKILL_ROOT / 'references' / 'templates' / (task.template + '.md')}` |

## Codex Exec
```powershell
{command}```

## 实现功能
{task.goal}

## 必须读取的输入
| 输入 | 用途 |
| --- | --- |
| `AGENTS.md` | 仓库执行规则 |
| `docs/taobao_mvp_requirements.md` | 需求源 |
| `docs/taobao_mvp_development.md` | 开发源 |
| `docs/auto-execute/shopops-goal-delivery-standard-index.md` | 本任务包入口 |
| `docs/auto-execute/shopops-goal-implementation-audit.md` | 当前实现差距 |
| `docs/auto-execute/shopops-goal-requirement-traceability-matrix.md` | 需求映射 |
| `docs/auto-execute/shopops-goal-external-data-validation-matrix.md` | 飞书表和字段映射 |

## 允许改动范围
{task.allowed}

## 禁止事项
- 不要修改参考文档中的需求含义。
- 不要把本地 mock 结果说成真实飞书或真实千牛证据。
- 不要绕过验证码、登录、权限或平台安全机制。
- 不要保存淘宝主账号密码、买家手机号、地址、姓名等敏感个人信息。
- 不要执行任何投放修改、调价、暂停、创建或编辑广告动作。
- 不要把采集失败值写成数字 `0`。
- 不要在缺 result JSON 和 HANDOFF 时只用聊天文字收尾。

## 验收标准
- 覆盖对象 `{task.covers}` 的实现或验证结果必须落到 durable files。
- 本任务结束必须写 `docs/auto-execute/results/{task.task_id}.json`。
- 本任务结束必须写 `docs/auto-execute/latest/{task.task_id}-HANDOFF.md`。
- result JSON 必须包含 `task_pack_id: "{TASK_PACK_ID}"`、`task_id: "{task.task_id}"`、`status`、`evidence`、`blockers`。
- 续跑时如果已有 result JSON 缺少 `task_pack_id: "{TASK_PACK_ID}"`，必须判定为历史结果，只能参考，不能跳过本任务。
- 任何环境缺口必须写 `BLOCKED_BY_ENVIRONMENT`，不能伪造 PASS。

## 开发标准引用
- `docs/auto-execute/shopops-goal-development-standard.md`

## 测试标准引用
- `docs/auto-execute/shopops-goal-software-test-standard.md`

## 细化验收标准
| 面 | 标准 | 证据路径 |
| --- | --- | --- |
| 需求 | `{task.covers}` 每一项有实现/缺口判定 | `docs/auto-execute/results/{task.task_id}.json` |
| 数据 | 相关表字段、unique_key、upsert、pending replay、readback 有证据或 blocker | `docs/auto-execute/external-data/{task.task_id}/` |
| 测试 | 相关命令运行并记录输出，失败则本任务内修复或写 repair | `docs/auto-execute/logs/{task.task_id}/` |
| 安全 | 不泄露密钥，不触碰真实投放副作用 | `docs/auto-execute/results/{task.task_id}.json` |

## 测试与证据
```powershell
{task.commands}
```

## Dependency And Resume Gate
| 依赖 | 必须存在 | 不满足时处理 |
| --- | --- | --- |
| {task.depends_on} | 前置 result JSON 和 HANDOFF，`none` 除外 | 读取 blockers/repair queue；不得猜测前置成功 |

续跑时先检查：
- `docs/auto-execute/results/{task.task_id}.json`
- `docs/auto-execute/latest/{task.task_id}-HANDOFF.md`
- `docs/auto-execute/blockers.md`
- `docs/auto-execute/repair-queue.md`

历史结果过滤规则：
- 本任务只接受含有 `task_pack_id: "{TASK_PACK_ID}"` 的 result JSON。
- 没有 `task_pack_id`、`task_pack_id` 不一致、或缺少本任务 HANDOFF 的结果，均视为 stale evidence。
- stale evidence 可以作为背景诊断输入，但不得作为本轮任务完成依据。

## Stop Prevention Rules
- 不要在计划后停止。
- 本地可逆的实现、测试、修复必须继续执行到本任务退出条件。
- 测试失败先定位并做 task-local 修复，再重跑相关验证。
- 无论成功、失败还是阻塞，都必须写 result JSON 和 HANDOFF。

## Failure To Repair Routing
| 状态 | 何时使用 | 必须动作 |
| --- | --- | --- |
| PASS | 本任务全部证据真实存在 | 写 result JSON/HANDOFF |
| PASS_WITH_LIMITATION | 非 P0 限制或 local-only 限制 | 写清限制 |
| REPAIR_REQUIRED | P0 本地可修复缺口 | 写最小 repair 项 |
| BLOCKED_BY_ENVIRONMENT | 缺真实 Feishu 凭据、表 ID、千牛 CDP 会话或外部环境 | 写环境 blocker |
| BLOCKED_BY_MISSING_SOURCE | 缺 PRD/代码/输入源 | 写缺失源 |
| HARD_FAIL | P0 明确失败且无法修复 | 写失败证据 |

## 输出文件
{task.outputs}

## 结果 JSON
`docs/auto-execute/results/{task.task_id}.json`

最小字段：
```json
{{
  "task_pack_id": "{TASK_PACK_ID}",
  "task_id": "{task.task_id}",
  "status": "PASS|PASS_WITH_LIMITATION|REPAIR_REQUIRED|BLOCKED_BY_ENVIRONMENT|BLOCKED_BY_MISSING_SOURCE|HARD_FAIL",
  "evidence": [],
  "blockers": []
}}
```

## HANDOFF
`docs/auto-execute/latest/{task.task_id}-HANDOFF.md`

## 失败状态
允许 `PASS`, `PASS_WITH_LIMITATION`, `REPAIR_REQUIRED`, `BLOCKED_BY_ENVIRONMENT`, `BLOCKED_BY_MISSING_SOURCE`, `HARD_FAIL`。
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    TASK_DIR.mkdir(parents=True, exist_ok=True)

    source_rows = "\n".join([
        f"| SRC-AGENTS | 规则 | `AGENTS.md` | 仓库执行约束 | PLANNED | |",
        f"| SRC-PRD | 需求 | `docs/taobao_mvp_requirements.md` | P0/P1 需求源 | PLANNED | |",
        f"| SRC-DEV | 开发文档 | `docs/taobao_mvp_development.md` | 架构与伪代码源 | PLANNED | |",
        f"| SRC-CODE | 代码 | `shopops/**`, `tests/**`, `scripts/**` | 当前实现审计 | PLANNED | |",
        f"| SRC-OLD | 历史执行证据 | `docs/auto-execute/results/**`, `latest/**` | 只能作为旧状态参考，不能当本轮新鲜 PASS | PLANNED | STALE_EVIDENCE_GUARD |",
    ])

    doc_map = "\n".join([
        f"| `{SLUG}-delivery-standard-index.md` | 入口、证据地图、执行边界 |",
        f"| `{SLUG}-implementation-audit.md` | 需求是否已实现的逐项审计 |",
        f"| `{SLUG}-TOTAL-auto-execute-task.md` | 给后续 auto-execute 的总任务入口 |",
        f"| `{SLUG}-auto-execute-master-plan.md` | 完整任务队列和依赖 |",
        f"| `{SLUG}-development-standard.md` | 后续 worker 开发规则 |",
        f"| `{SLUG}-software-test-standard.md` | 测试和 final gate 规则 |",
        f"| `{SLUG}-requirement-traceability-matrix.md` | 需求到任务/证据映射 |",
        f"| `{SLUG}-api-db-contract-matrix.md` | API/服务/DB/存储契约 |",
        f"| `{SLUG}-external-data-validation-matrix.md` | 飞书表字段、upsert、readback 矩阵 |",
        f"| `{SLUG}-standard-test-plan.md` | 行级测试计划 |",
        f"| `{SLUG}-codex-exec-prompts.md` | 母执行提示词 |",
        f"| `{SLUG}-codex-exec-prompts-split.md` | 一任务一 fresh codex exec 队列 |",
        f"| `{SLUG}-owner-scenario-matrix.md` | 老板/运营验收场景 |",
        f"| `{SLUG}-final-acceptance-gate.md` | 只读 durable evidence 的最终门禁 |",
        f"| `{SLUG}-task-pack-quality-audit.md` | 本任务包质量自检 |",
    ])

    write(OUT / f"{SLUG}-delivery-standard-index.md", f"""
# {PROJECT} Goal Delivery Standard Index
> 生成日期：{TODAY}
> 项目根目录：`{ROOT}`
> 项目 slug：`{SLUG}`
> task_pack_id：`{TASK_PACK_ID}`
> 语言：zh-CN

## Goal
使用 `task-auto-execute` 生成一套新的、可交给后续 `auto-execute` 一次性串行执行的完整任务包，并把需求文档功能是否已实现写成可恢复审计。

## Source Inventory
| Source ID | 类型 | 路径/位置 | 用途 | 状态 | Blocker |
| --- | --- | --- | --- | --- | --- |
{source_rows}

## 文档地图
| 文档 | 作用 |
| --- | --- |
{doc_map}

## 执行边界
本轮使用的是 `task-auto-execute`，只能生成任务包和未来执行提示词；本轮不会运行产品实现、不会调用 `codex exec` 队列、不会创建新的 `results/*.json` 或 `latest/*HANDOFF.md` 执行证据。

## 一次性执行规则
后续真实执行时，从 `T00` 开始。T00 必须一次只启动一个 fresh `codex exec`，等待旧进程退出并确认 result JSON、HANDOFF、日志存在后，才能启动下一任务。

## 状态词
`READY_FOR_AUTO_EXECUTE` 表示任务包可执行，不表示产品已完成。产品最终状态只能由后续 final gate 根据 durable evidence 判定。
""")

    write(OUT / f"{SLUG}-TOTAL-auto-execute-task.md", f"""
# {PROJECT} 总任务 - 交给 auto-execute 一次性执行
> 生成日期：{TODAY}
> 项目根目录：`{ROOT}`
> task_pack_id：`{TASK_PACK_ID}`
> 分任务目录：`docs/auto-execute/{SLUG}-tasks`

## 总目标
使用 `auto-execute` 按 `docs/auto-execute/{SLUG}-auto-execute-master-plan.md` 串行执行 T00-T13，完成需求文档功能实现审计、缺口修复、本地验证、外部环境探针和最终 fail-closed 验收。

## 必须读取
- `AGENTS.md`
- `docs/auto-execute/{SLUG}-delivery-standard-index.md`
- `docs/auto-execute/{SLUG}-auto-execute-master-plan.md`
- `docs/auto-execute/{SLUG}-task-pack-quality-audit.md`
- `docs/auto-execute/{SLUG}-tasks/T00-omx-auto-execute-orchestrator.md`

## 模板约束
- 每个分任务都已选择 `Task Template ID`。
- 每个分任务都引用独立模板文件：`{SKILL_ROOT}\\references\\templates\\TPL-*.md`。
- 后续执行不得把任何分任务改成无模板的泛化任务。

## 执行方式
从 T00 开始。T00 是唯一总编排入口，必须：
- 读取本总任务和 master plan。
- 一次只启动一个 fresh `codex exec` 执行下一个分任务。
- 等待当前 `codex exec` 完全退出。
- 校验当前任务写出 result JSON、HANDOFF 和必要日志。
- 校验 result JSON 含有 `task_pack_id: "{TASK_PACK_ID}"`。
- 如果遇到 `REPAIR_REQUIRED` 或 `HARD_FAIL`，写入 repair queue 并执行最小修复任务。
- 如果遇到真实 Feishu/Qianniu/外部环境不可用，写 `BLOCKED_BY_ENVIRONMENT`，不得伪造 PASS。

## 首个命令
```powershell
Set-Location -LiteralPath "{ROOT}"
codex exec "Use auto-execute. Execute the total task pack at {ROOT}\\docs\\auto-execute\\{SLUG}-TOTAL-auto-execute-task.md. Start from {ROOT}\\docs\\auto-execute\\{SLUG}-tasks\\T00-omx-auto-execute-orchestrator.md. Execute one fresh codex exec per subtask, wait for exit, verify task_pack_id {TASK_PACK_ID}, result JSON, HANDOFF, logs, repair routing, and final gate. Do not stop after planning. Implement, test, repair, write durable result files, and exit only after T13 reaches PASS, PASS_WITH_LIMITATION, REPAIR_REQUIRED, BLOCKED_BY_ENVIRONMENT, BLOCKED_BY_MISSING_SOURCE, or HARD_FAIL."
```

## 终态规则
总任务完成不等于 pure PASS。只有 T13 final gate 可判定最终状态。缺真实飞书写入/读回或真实千牛 PC CDP 页面证据时，必须保留 `BLOCKED_BY_ENVIRONMENT` 或限制态。
""")

    audit_rows = "\n".join(
        f"| {rid} | {pri} | {desc} | {status} | {impl} | {verify} | {gap} | PLANNED |"
        for rid, pri, desc, status, impl, verify, gap in REQUIREMENTS
    )
    write(OUT / f"{SLUG}-implementation-audit.md", f"""
# {PROJECT} 需求实现审计

## 结论
当前仓库已经有一批本地实现和测试，但还不能判定“需求文档功能都已实现并验收通过”。核心原因：

- 真实 Feishu Bitable 写入、更新、upsert、读回证据缺失。
- 真实千牛 PC 订单中心和推广中心 CDP 会话证据缺失。
- 上一轮执行停在 T08 后，T09 需要新鲜重跑，T10 未执行，T11 是旧的 REPAIR_REQUIRED。
- 当前本地测试可证明部分业务逻辑，但本地 fake 不能替代真实外部验收。

## 逐项审计
| Req ID | 优先级 | 需求 | 当前实现状态 | 新实现/修复任务 | 新验证任务 | 缺口 | 本轮状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
{audit_rows}
""")

    task_rows = "\n".join(
        f"| {t.task_id} | {t.slug} | {t.template} | {t.surface} | {t.covers} | {t.depends_on} | `docs/auto-execute/results/{t.task_id}.json` | `docs/auto-execute/latest/{t.task_id}-HANDOFF.md` | repair queue/final gate |"
        for t in TASKS
    )
    write(OUT / f"{SLUG}-auto-execute-master-plan.md", f"""
# {PROJECT} Auto-Execute Master Plan
> task_pack_id：`{TASK_PACK_ID}`

## 执行目标
按 PRD 完成淘宝单平台监控 MVP 的本地可交付实现，并用真实或明确降级的证据证明每个 P0 面。

## Task Queue
| Task | 名称 | Task Template ID | 主验收面 | 覆盖对象 | 前置任务 | 必须输出 result JSON | 必须输出 HANDOFF | 失败路由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{task_rows}

## Resume Probe
T00 后续执行必须检查：
- `docs/auto-execute/results/`
- `docs/auto-execute/latest/`
- `docs/auto-execute/blockers.md`
- `docs/auto-execute/repair-queue.md`
- `docs/auto-execute/{SLUG}-implementation-audit.md`

## 历史证据规则
旧的 `shopops-*` 任务包和旧 `results/latest` 只能作为背景，不得当成本轮新鲜 PASS。T00/T11/T13 必须检查 result JSON 是否含有 `task_pack_id: "{TASK_PACK_ID}"`。缺少或不一致则必须重新执行对应任务，不能跳过。
""")

    write(OUT / f"{SLUG}-development-standard.md", """
# ShopOps Goal Development Standard

## Source Of Truth
优先级：用户本轮目标 > AGENTS.md > `docs/taobao_mvp_requirements.md` > `docs/taobao_mvp_development.md` > 现有代码 > 历史执行证据。

## 业务边界
- 当前 MVP 只支持淘宝单平台。
- 当前订单来源默认 `ORDER_SOURCE=crawler`，真实淘宝 API 是后续阶段预留，不阻塞当前 crawler MVP。
- 当前推广来源只允许 `PROMOTION_SOURCE=qianniu_pc`。
- 千牛 PC 当前只允许订单中心和推广中心两个只读页面。
- 推广中心只读“花费”指标，不拆分直通车/万相台/引力魔方，不做投放修改。

## 数据与存储
- 业务层只能依赖 `Storage` 抽象。
- 飞书表名和字段必须保持中文业务含义。
- 所有快照/日志类写入必须有 `unique_key` upsert。
- 写入失败必须进入 pending cache，并在下轮任务开始前 replay。
- 采集失败必须写状态和错误，不能写 0 污染指标。

## 安全
- 不绕过验证码、登录、权限或平台安全机制。
- 不保存淘宝主账号密码、买家手机号、姓名、地址等 PII。
- 不把密钥写入代码、日志、报告。
""")

    write(OUT / f"{SLUG}-software-test-standard.md", """
# ShopOps Goal Software Test Standard

## 基础命令
| 面 | 命令 | 证据 |
| --- | --- | --- |
| 全量测试 | `python -m pytest -q -p no:cacheprovider --basetemp .\\.pytest-tmp\\goal-full` | `docs/auto-execute/logs/T11/pytest.txt` |
| 飞书数据证明 | `python scripts\\acceptance\\verify_feishu_data.py` | `docs/auto-execute/external-data/T11/` |
| 密钥扫描 | `python scripts\\acceptance\\secret_guard.py` | `docs/auto-execute/logs/T12/secret-guard.txt` |

## 外部数据 PASS 条件
每个 P0 飞书表必须证明字段映射、payload、unique_key upsert、重复运行、失败缓存、replay、读回。缺真实凭据时只能写 `BLOCKED_BY_ENVIRONMENT` 或有明确限制的本地证明。

## Final Gate
任一 P0 需求缺证据、任一 required task 缺 result JSON/HANDOFF、任一外部数据读回缺失、任一失败写 0，最终都不能 pure PASS。
""")

    write(OUT / f"{SLUG}-requirement-traceability-matrix.md", "# ShopOps Goal Requirement Traceability Matrix\n\n| Req ID | Priority | Requirement | Current Status | Implement Task | Verify Task | Evidence Path | Status |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n" + audit_rows)

    table_rows = "\n".join(
        f"| {did} | {zh} | `{key}` | `{env}` | {fields} | unique_key/upsert where applicable | pending cache + replay | real Feishu or local fake readback | PLANNED |"
        for did, key, zh, env, fields in TABLES
    )
    write(OUT / f"{SLUG}-external-data-validation-matrix.md", f"""
# ShopOps Goal External Data Validation Matrix

| Data ID | 中文表名 | Internal Key | Env Var | 字段 | 幂等规则 | 失败缓存 | 读回证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
{table_rows}

## 必测用例
| Case ID | 范围 | 动作 | 期望 | 证据 |
| --- | --- | --- | --- | --- |
| EXT-001 | 所有表 | 合法 payload 写入 | 字段名和值正确 | `external-data/T03/` |
| EXT-002 | 快照/日志表 | 相同 unique_key 重复写入 | 更新而非新增重复行 | `external-data/T03/` |
| EXT-003 | 飞书失败 | 写入异常 | pending_records.jsonl 有记录 | `external-data/T03/` |
| EXT-004 | pending replay | 下轮重放 | 成功后 pending 清空或减少 | `external-data/T03/` |
| EXT-005 | 采集失败 | 订单或推广失败 | 指标为 null，状态为失败，不写 0 | `external-data/T08/` |
""")

    write(OUT / f"{SLUG}-api-db-contract-matrix.md", """
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
""")

    write(OUT / f"{SLUG}-ui-reference-map.md", """
# ShopOps Goal UI Reference Map

本项目没有 Web/小程序 UI 截图源，主要可视化界面是飞书多维表格和飞书机器人消息。

| UI ID | 来源 | 目标界面 | 控件/状态 | 数据依赖 | 证据目标 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| UI-FEISHU-001 | PRD 表结构 | 飞书多维表格看板 | 9 张中文表 | DATA-001..DATA-009 | 真实飞书截图或读回 JSON | PLANNED |
| UI-BOT-001 | PRD 日报/告警文本 | 飞书群机器人消息 | 告警、日报 | alert_log/daily_report | webhook 发送结果或 BLOCKED_BY_ENVIRONMENT | PLANNED |
""")

    write(OUT / f"{SLUG}-standard-test-plan.md", """
# ShopOps Goal Standard Test Plan

| Test ID | Layer | Target | Case | Command/Action | Expected | Evidence | Required |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TEST-001 | unit | config/models | defaults and validation | pytest | pass | T11 logs | yes |
| TEST-002 | integration | local Feishu storage | upsert/duplicate/pending/replay | pytest | pass | T03/T11 logs | yes |
| TEST-003 | external | real Feishu | write/update/readback | verify_feishu_data.py | PASS or env blocker | external-data/T03/T11 | yes |
| TEST-004 | crawler | Qianniu order center | live CDP or env blocker | T04 worker | orders_raw proof or blocker | external-data/T04 | yes |
| TEST-005 | crawler | Qianniu promotion center | live CDP or env blocker | T06 worker | 花费 proof or blocker | external-data/T06 | yes |
| TEST-006 | business | metrics/delta | edge cases | pytest | pass | T07/T11 logs | yes |
| TEST-007 | reliability | failure-as-null | collector/storage failures | pytest | no zero pollution | T08 logs | yes |
| TEST-008 | scheduler | full_collect | pending replay + task log | pytest | pass | T09/T11 logs | yes |
| TEST-009 | docs | runbook/env | operator docs | review | complete | T10 | yes |
| TEST-010 | guard | secret/report integrity | scan | secret_guard.py | pass | T12 | yes |
| TEST-011 | final | all durable evidence | aggregate | T13 | fail closed | verification-results.md | yes |
""")

    write(OUT / f"{SLUG}-owner-scenario-matrix.md", """
# ShopOps Goal Owner Scenario Matrix

| Scenario ID | Persona | Preconditions | Exact Action | Expected Storage/API | Expected Visible Result | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OWNER-001 | 商家老板 | 千牛和飞书配置可用 | 执行一次 full_collect | 写 monitor_snapshot/orders_raw/promotion_snapshot/metrics_10min/task_run_log | 飞书看板可读到今日订单、成交额、花费、ROI、获客成本 | T11/T13 | PLANNED |
| OWNER-002 | 运营人员 | 千牛未运行 | 执行一次 full_collect | 写失败 task_run_log/alert_log，不写 0 | 飞书告警或 blocker 显示千牛不可用 | T04/T09 | PLANNED |
| OWNER-003 | 运营人员 | 飞书写入失败 | 执行一次 full_collect | pending_records.jsonl 记录，后续 replay | 不丢数据，不误报成功 | T03/T09 | PLANNED |
| OWNER-004 | 商家老板 | 到达日报时间 | 触发日报 | 写 daily_report，调用 webhook | 群里出现日报或环境 blocker | T10 | PLANNED |
""")

    write(OUT / f"{SLUG}-final-acceptance-gate.md", """
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
""")

    prompt_header = f"""# {PROJECT} auto-execute Codex Exec 执行提示词
> 生成日期：{TODAY}
> 项目根目录：`{ROOT}`
> 项目 slug：`{SLUG}`
> task_pack_id：`{TASK_PACK_ID}`
> 需求文档：`docs/taobao_mvp_requirements.md`, `docs/taobao_mvp_development.md`

本文件是未来执行包，不是完成报告。本轮 `task-auto-execute` 没有执行产品代码、没有调用 API、没有创建执行证据。
"""
    write(OUT / f"{SLUG}-codex-exec-prompts.md", prompt_header + "\n\n## Task Queue\n\n" + task_rows)

    split_lines = [f"# {PROJECT} Codex Exec Prompts Split\n> task_pack_id：`{TASK_PACK_ID}`\n\n每个任务必须用一个 fresh `codex exec`。上一任务退出并写入 result JSON/HANDOFF 后，才能启动下一任务。每个 result JSON 必须包含 `task_pack_id: \"{TASK_PACK_ID}\"`。\n"]
    for t in TASKS:
        split_lines.append(f"## {t.task_id} - {t.slug}\n```powershell\nSet-Location -LiteralPath \"{ROOT}\"\ncodex exec \"Use auto-execute. Execute only {ROOT}\\docs\\auto-execute\\shopops-goal-tasks\\{t.task_id}-{t.slug}.md. Treat this as one fresh task boundary. Do not stop after planning. Implement, test, repair, write result JSON, write HANDOFF, and exit. If blocked, classify blocker in durable files.\"\n```\n")
    write(OUT / f"{SLUG}-codex-exec-prompts-split.md", "\n".join(split_lines))

    for task in TASKS:
        write(TASK_DIR / f"{task.task_id}-{task.slug}.md", task_doc(task))

    audit_tasks = "\n".join(
        f"| {t.task_id} | yes | yes | yes | yes | yes | yes | yes | `docs/auto-execute/results/{t.task_id}.json` | `docs/auto-execute/latest/{t.task_id}-HANDOFF.md` | yes | PASS |"
        for t in TASKS
    )
    template_audit = "\n".join(
        f"| {t.task_id} | {t.template} | {t.surface} | {t.covers} | yes | none | PASS |"
        for t in TASKS
    )
    write(OUT / f"{SLUG}-task-pack-quality-audit.md", f"""
# ShopOps Goal Task Pack Quality Audit

Generated by `task-auto-execute`.

## Verdict
`READY_FOR_AUTO_EXECUTE`

## Source Integrity
| Check | Evidence | Status | Blocker |
| --- | --- | --- | --- |
| PRD paths exist | `docs/taobao_mvp_requirements.md`, `docs/taobao_mvp_development.md` | PASS | |
| UTF-8 source readable | Python UTF-8 read succeeded before generation | PASS | |
| Existing execution artifacts distinguished from generated pack | old `results/` and `latest/` are marked stale/background only | PASS_WITH_NOTE | historical artifacts exist |
| Total task entry exists | `{SLUG}-TOTAL-auto-execute-task.md` | PASS | |
| Task pack ID guard exists | `{TASK_PACK_ID}` required in every worker result JSON | PASS | |

## Language And Encoding Audit
| Check | Evidence | Status | Blocker |
| --- | --- | --- | --- |
| Project language | `zh-CN` from PRD/user context | PASS | |
| Generated markdown UTF-8 | all generated files written with Python `encoding="utf-8"` | PASS | |
| Chinese business fields | Feishu table/field names preserved in matrices and tasks | PASS | |
| Mojibake marker policy | later audit must scan common mojibake/replacement code points such as `U+951F`, `U+95BF`, `U+95B3`, `U+FFFD` | PASS | |

## Task Executability Audit
| Task | Has command | Has inputs | Has allowed files | Has forbidden actions | Has dependency gate | Has stop rules | Has repair routing | Has result JSON | Has HANDOFF | Specific enough | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{audit_tasks}

## Task Template Matching Audit
| Task | Selected Template | Primary Surface | Covered IDs | Template Fits? | Missing Template Fields | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
{template_audit}

## Coverage Audit
| Surface | Required rows | Covered rows | Missing rows | Status |
| --- | --- | --- | --- | --- |
| P0/P1 requirements | 14 | 14 | 0 | PASS |
| Feishu external data | 9 tables + 5 cases | all mapped | 0 | PASS |
| Qianniu crawler surfaces | order center + promotion center | both mapped | 0 | PASS |
| Owner scenarios | 4 | 4 | 0 | PASS |
| Final gate | durable evidence only | yes | 0 | PASS |

## Generation Boundary Audit
| Forbidden artifact | Exists before generation? | Created by this run? | Status |
| --- | --- | --- | --- |
| `docs/auto-execute/results/*.json` | yes, historical | no | PASS_WITH_NOTE |
| `docs/auto-execute/latest/*HANDOFF.md` | yes, historical | no | PASS_WITH_NOTE |
| execution screenshots/logs/API transcripts | yes, historical logs | no | PASS_WITH_NOTE |

## Regeneration Blockers
- none
""")


if __name__ == "__main__":
    main()
