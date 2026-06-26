# Douyin creator ROI screening pipeline

Chrome only: this workflow uses Google Chrome/CDP, not Edge.

The default keyword is `洗面奶`. The full workflow collects real public comments, creator profile data, and up to 30 normal non-pinned profile videos, writes the records to Feishu Bitable, and produces an ROI screening report.

## 1. Start Chrome/CDP

Run this in a normal unrestricted PowerShell terminal:

```powershell
./scripts/start_douyin_creator_cdp_browser.ps1 -Port 9224 -Keyword 洗面奶
```

Keep the visible Chrome window open. Complete login or verification in that window if Douyin asks for it.

The launcher uses:

- CDP URL: `http://127.0.0.1:9224`
- dedicated profile: `D:/tmp/ShopOpsCreatorChromeProfiles/douyin-creator-9224`
- Douyin search page for the configured keyword

Verify the browser before starting collection:

```powershell
python scripts/check_douyin_creator_chrome_cdp.py --cdp-url http://127.0.0.1:9224
```

A sandbox error such as `spawn EPERM`, `CreateFile: Access denied (0x5)`, or `platform_channel.cc:108` means the current agent process is not allowed to create Chrome child processes. Start the launcher from a normal desktop terminal, then let the collector reuse that CDP session.

## 2. Run the full 50-creator job

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/run_douyin_creator_roi_pipeline.py --target 50 --keywords 洗面奶 --collection-mode profile --comments-per-creator 50 --profile-video-limit 30 --direct-cdp --cdp-url http://127.0.0.1:9224 --round-timeout-seconds 7200 --max-rounds 3
```

To let the pipeline launch Chrome itself from an unrestricted terminal:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/run_douyin_creator_roi_pipeline.py --target 50 --keywords 洗面奶 --collection-mode profile --comments-per-creator 50 --profile-video-limit 30 --direct-cdp --launch-cdp-browser --cdp-port 9224 --round-timeout-seconds 7200 --max-rounds 3
```

## 3. Backfill existing real-comment records

When Chrome is temporarily unavailable, existing Feishu rows with real public comment JSON can still be deduplicated, rescored, and written back safely:

```powershell
$env:PYTHONIOENCODING='utf-8'
python scripts/backfill_douyin_creator_roi_to_feishu.py --target 50 --min-comments 5
```

The command:

- requires at least 5 parsed comment texts per selected creator by default
- deduplicates by creator name and keeps the strongest record
- prefers non-D creators, while preserving an explicit D/rejected sample only if fewer than 50 non-D records meet the comment threshold
- writes ROI score, tier, interaction stability, water-risk score, mismatch risk, first-test advice, scoring basis, and manual-review status
- reads all 50 records back from Feishu before returning success
- does not invent missing profile URLs, Douyin IDs, followers, or 30-video samples

## 4. What gets collected

Each full-profile creator row keeps:

- search keyword and source
- creator name, Douyin ID, followers, total likes, following, identity, and signature
- homepage URL and screenshot
- real public comment JSON, with up to 50 comments per creator when the platform returns them
- comment quality metrics: meaningful comments, purchase intent, usage questions, doubts, low-value rate, and duplicate rate
- up to 30 normal profile videos, excluding visibly pinned videos
- video heat summary: sample count, average, median, low-video rate, and max/median ratio
- follower/video mismatch diagnosis
- ROI score, tier, blockers, and recommended action

## 5. Scoring logic

The ROI score favors product relevance, useful real comments, stable ordinary-video interaction, and lower suspected water risk.

Main risk checks:

- high follower count with low median ordinary-video heat
- excessive follower-to-median-video-heat ratio
- most ordinary videos have weak interaction
- one top video is much stronger than ordinary videos
- repetitive or low-value comments
- brand, official shop, live-room, or product-only account patterns

Tier interpretation:

- `S`: prioritize outreach; negotiate sample plus low base fee plus commission
- `A`: request a quote and recent ordinary-video proof
- `B`: promising but incomplete; collect more evidence first
- `C`: do not include in the first paid test
- `D`: reject from the creator pool

Missing profile or 30-video evidence is always written as a data limitation. A comment-only score is a first-pass ranking, not a final investment decision.

## 6. Time and token estimate

Local Python, Chrome/CDP collection, and Feishu API calls do not consume model tokens. Model tokens are consumed only when an agent inspects logs, reasons over results, or summarizes progress.

Expected runtime with a stable visible Chrome session:

- fast mode, 50 creators with comments: about 15-35 minutes
- full profile mode, 50 creators plus up to 30 normal videos each: about 60-120 minutes
- Feishu backfill/readback for 50 existing creators: usually under 1 minute

For low-token monitoring, read only:

```text
docs/live-evidence/creator-roi-pipeline-*/pipeline-summary.json
docs/live-evidence/creator-feishu-roi-backfill-*/summary.json
```

## 7. Outputs

The full pipeline writes a timestamped folder under `docs/live-evidence` containing:

- `master-rows.json`
- `pipeline-summary.json`
- `roi-screening/summary.json`
- `roi-screening/roi-screened-candidates.json`
- `roi-screening/roi-screened-candidates.csv`
- `roi-screening/roi-screening-report.md`

The backfill command writes:

- `selected-50-index.json`
- `summary.json`
- an independent readback file can be saved beside those artifacts for audit

The Feishu target is the table configured by `FEISHU_APP_TOKEN` and `FEISHU_TABLE_CREATOR_SCREENING`.
