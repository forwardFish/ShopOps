param(
  [string]$ProjectRoot = "D:\lyh\agent\agent-frame\ShopOps",
  [string[]]$TaskIds = @("T01","T02","T03","T04","T05","T06","T07","T08","T09","T10","T11"),
  [switch]$Force,
  [int]$MaxRepairAttempts = 1
)

$ErrorActionPreference = "Continue"
Set-Location -Path $ProjectRoot

$taskFiles = [ordered]@{
  T01 = "docs/auto-execute/shopops-tasks/T01-python-scaffold-config-models.md"
  T02 = "docs/auto-execute/shopops-tasks/T02-real-feishu-bitable-storage.md"
  T03 = "docs/auto-execute/shopops-tasks/T03-order-collectors-api-crawler.md"
  T04 = "docs/auto-execute/shopops-tasks/T04-promotion-crawler-qianniu-safety.md"
  T05 = "docs/auto-execute/shopops-tasks/T05-metric-snapshot-delta-engine.md"
  T06 = "docs/auto-execute/shopops-tasks/T06-alerts-task-log-daily-report.md"
  T07 = "docs/auto-execute/shopops-tasks/T07-scheduler-full-collect-pending-replay.md"
  T08 = "docs/auto-execute/shopops-tasks/T08-real-feishu-data-correctness-verification.md"
  T09 = "docs/auto-execute/shopops-tasks/T09-local-test-suite-and-secret-guard.md"
  T10 = "docs/auto-execute/shopops-tasks/T10-operator-runbook-env-docs.md"
  T11 = "docs/auto-execute/shopops-tasks/T11-final-acceptance-gate.md"
}

$acceptable = @("PASS", "PASS_WITH_LIMITATION", "PASS_NEEDS_MANUAL_UI_REVIEW", "BLOCKED_BY_ENVIRONMENT", "DOCUMENTED_BLOCKER")
$bad = @("REPAIR_REQUIRED", "HARD_FAIL", "FAIL", "IN_SCOPE_GAP")
$orchestrator = Join-Path $ProjectRoot "docs/auto-execute/shopops-tasks/T00-omx-auto-execute-orchestrator.md"
$relayLogDir = Join-Path $ProjectRoot "docs/auto-execute/logs/relay-orchestrator"
New-Item -ItemType Directory -Force -Path $relayLogDir | Out-Null

function Get-TaskStatus {
  param([string]$TaskId)
  $resultPath = Join-Path $ProjectRoot "docs/auto-execute/results/$TaskId.json"
  $handoffPath = Join-Path $ProjectRoot "docs/auto-execute/latest/$TaskId-HANDOFF.md"
  if (-not (Test-Path $resultPath) -or -not (Test-Path $handoffPath)) {
    return [pscustomobject]@{ exists = $false; status = $null; resultPath = $resultPath; handoffPath = $handoffPath }
  }
  try {
    $json = Get-Content -Raw -Encoding UTF8 -Path $resultPath | ConvertFrom-Json
    return [pscustomobject]@{ exists = $true; status = [string]$json.status; resultPath = $resultPath; handoffPath = $handoffPath }
  } catch {
    return [pscustomobject]@{ exists = $true; status = "INVALID_JSON"; resultPath = $resultPath; handoffPath = $handoffPath }
  }
}

function Invoke-FreshCodexTask {
  param([string]$TaskId, [int]$Attempt, [string]$Reason)
  $relativeTaskPath = $taskFiles[$TaskId]
  if (-not $relativeTaskPath) { throw "Unknown task id: $TaskId" }
  $taskPath = Join-Path $ProjectRoot $relativeTaskPath
  if (-not (Test-Path $taskPath)) { throw "Missing task file: $taskPath" }

  $taskLogDir = Join-Path $ProjectRoot "docs/auto-execute/logs/$TaskId"
  New-Item -ItemType Directory -Force -Path $taskLogDir | Out-Null
  $runStamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $eventLog = Join-Path $taskLogDir "codex-exec-$runStamp-attempt-$Attempt.jsonl"
  $lastMessage = Join-Path $taskLogDir "last-message-$runStamp-attempt-$Attempt.txt"
  $checkPath = Join-Path $taskLogDir "orchestrator-check-$runStamp-attempt-$Attempt.json"

  $prompt = @"
Use the auto-execute skill in Relay Worker mode. Execute exactly one task and then exit.
Project root: $ProjectRoot
Task file: $taskPath
Global orchestrator: $orchestrator
Relay reason: $Reason
Rules:
- This fresh codex exec may execute only $TaskId. Do not execute any other Txx task.
- Read AGENTS.md, the T00 orchestrator, this task markdown, and required source docs named by the task.
- Respect the current MVP scope: ORDER_SOURCE=crawler; Taobao API credentials are future-stage only; no real Taobao Open Platform API calls; only Qianniu PC order center and promotion center cost collection are in scope.
- Implement/verify the task, or truthfully classify BLOCKED_BY_ENVIRONMENT when real Feishu credentials or Qianniu PC session are missing.
- Write docs/auto-execute/results/$TaskId.json and docs/auto-execute/latest/$TaskId-HANDOFF.md before exiting.
- If running pytest, prefer: python -m pytest -q -p no:cacheprovider --basetemp .\.pytest-tmp\$TaskId . Do not recursively delete temp directories.
- Update relevant docs/auto-execute logs, verification notes, blocker notes, and repair notes if needed.
- Do not ask for ordinary confirmation. Stop only for destructive/irreversible actions, credentials, production deployment/data, or payment.
"@

  Write-Host "[$(Get-Date -Format o)] START $TaskId attempt $Attempt ($Reason)"
  $started = Get-Date
  $oldEap = $ErrorActionPreference; $ErrorActionPreference = "Continue"; & codex exec -C $ProjectRoot --sandbox workspace-write --output-last-message $lastMessage --json $prompt 2>&1 | Out-File -FilePath $eventLog -Encoding utf8; $ErrorActionPreference = $oldEap
  $exit = $LASTEXITCODE
  $ended = Get-Date
  $status = Get-TaskStatus -TaskId $TaskId
  $record = [pscustomobject]@{
    task = $TaskId
    attempt = $Attempt
    reason = $Reason
    exitCode = $exit
    started = $started.ToString("o")
    ended = $ended.ToString("o")
    resultExists = [bool](Test-Path $status.resultPath)
    handoffExists = [bool](Test-Path $status.handoffPath)
    status = $status.status
    eventLog = $eventLog
    lastMessage = $lastMessage
  }
  $record | ConvertTo-Json -Depth 6 | Out-File -FilePath $checkPath -Encoding utf8
  Write-Host "[$(Get-Date -Format o)] END $TaskId attempt $Attempt exit=$exit status=$($status.status) result=$($record.resultExists) handoff=$($record.handoffExists)"
  return $record
}

$summary = @()
foreach ($taskId in $TaskIds) {
  if (-not $taskFiles.Contains($taskId)) { throw "Unknown task id in TaskIds: $taskId" }
  $current = Get-TaskStatus -TaskId $taskId
  if (-not $Force -and $current.exists -and ($acceptable -contains $current.status)) {
    Write-Host "[$(Get-Date -Format o)] SKIP $taskId existing acceptable status=$($current.status)"
    $summary += [pscustomobject]@{ task=$taskId; action="skip"; status=$current.status; attempts=0; reason="existing acceptable result+handoff" }
    continue
  }

  $attempt = 1
  $reason = if ($current.exists) { "missing/invalid/unacceptable existing status '$($current.status)'" } else { "missing result or handoff" }
  $record = Invoke-FreshCodexTask -TaskId $taskId -Attempt $attempt -Reason $reason
  $current = Get-TaskStatus -TaskId $taskId

  while ((-not $current.exists -or $bad -contains $current.status -or $current.status -eq "INVALID_JSON" -or [string]::IsNullOrWhiteSpace($current.status)) -and $attempt -le $MaxRepairAttempts) {
    $attempt++
    $reason = "fresh repair worker for status '$($current.status)' or missing artifacts"
    $record = Invoke-FreshCodexTask -TaskId $taskId -Attempt $attempt -Reason $reason
    $current = Get-TaskStatus -TaskId $taskId
  }

  $summary += [pscustomobject]@{ task=$taskId; action="run"; status=$current.status; attempts=$attempt; resultExists=$current.exists; resultPath=$current.resultPath; handoffPath=$current.handoffPath }

  if (-not $current.exists -or [string]::IsNullOrWhiteSpace($current.status)) {
    throw "$taskId did not produce required result JSON + HANDOFF with a status. Stop before launching next task."
  }
  if ($bad -contains $current.status -or $current.status -eq "INVALID_JSON") {
    throw "$taskId ended with $($current.status) after $attempt attempts. Stop before launching next task."
  }
}

$summaryPath = Join-Path $relayLogDir ("summary-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
$summary | ConvertTo-Json -Depth 8 | Out-File -FilePath $summaryPath -Encoding utf8
Write-Host "Relay summary: $summaryPath"
$summary | Format-Table -AutoSize


