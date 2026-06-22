# 达人 ROI 自动筛选 Pipeline 运行手册

本文档给后续接手的模型或人工使用，用于低 token、可续跑地完成：

```text
搜索达人 -> 抓真实评论 -> 写入飞书 -> ROI/注水筛选 -> 输出 S/A/B/C/D 名单
```

## 1. 推荐启动命令

从头跑 50 个达人：

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts\run_douyin_creator_roi_pipeline.py --target 50 --round-timeout-seconds 900 --max-rounds 5
```

使用已有 partial 继续补齐 50 个达人：

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts\run_douyin_creator_roi_pipeline.py --target 50 --seed-rows docs\live-evidence\creator-comment-fast-batch-20260621-152223\rows.partial.json --round-timeout-seconds 900 --max-rounds 5
```

## 2. 低 token 监控方式

不要读取完整 `rows.json` 或完整评论 JSON。

只看 pipeline 摘要：

```powershell
Get-ChildItem docs\live-evidence -Directory |
  Where-Object { $_.Name -like 'creator-roi-pipeline-*' } |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 FullName
```

然后读取：

```powershell
Get-Content <pipeline_dir>\pipeline-summary.json -Encoding UTF8
```

重点看：

```text
status
target
collected
total_real_comments
roi_outputs.report
roi_outputs.csv
upload_summary.feishu.readback_count
upload_summary.feishu.missing_unique_keys
```

## 3. 输出文件

每次 pipeline 会生成一个目录：

```text
docs/live-evidence/creator-roi-pipeline-YYYYMMDD-HHMMSS
```

核心文件：

```text
pipeline-summary.json
master-rows.json
roi-screening/roi-screening-report.md
roi-screening/roi-screened-candidates.csv
roi-screening/roi-screened-candidates.json
logs/round-01.log
logs/upload.log
logs/roi-screening.log
```

## 4. 状态判断

成功：

```text
pipeline-summary.json.status = success
collected >= 50
upload_summary.feishu.missing_unique_keys = []
roi_outputs.report 存在
```

部分完成：

```text
status = partial
```

常见原因：

```text
采集不足 50 条
飞书写入或读回失败
ROI 筛选脚本失败
```

## 5. 设计原则

这套代码为了准确和低 token 做了这些处理：

```text
1. 只保留真实评论条数 > 0 的达人。
2. 每轮有超时，避免单个搜索页长期卡死。
3. 超时后会保留 partial rows，下一轮可自动续跑。
4. master-rows.json 会合并去重后的有效达人。
5. 飞书写入时会先读回 existing unique_key，只补写缺失记录，避免重复写入。
6. 最后自动执行 ROI 筛选，输出 S/A/B/C/D。
7. 大评论 JSON 保存在文件里，不需要在对话里展开。
```

## 6. 当前已知 partial

本轮已有一个 partial 可作为续跑种子：

```text
docs/live-evidence/creator-comment-fast-batch-20260621-152223/rows.partial.json
```

当时已采：

```text
28 个达人
28 个都有真实评论
402 条真实评论
```

继续跑时建议使用 `--seed-rows`，避免重复消耗采集时间。
