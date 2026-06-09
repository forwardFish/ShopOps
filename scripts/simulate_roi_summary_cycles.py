from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.services.roi_summary_simulation import simulate_roi_cycles, write_simulation_to_feishu


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate ShopOps ROI summaries every 5 minutes.")
    parser.add_argument("--start-at", default="2026-06-04 10:00:00", help="Simulation base time. First summary is start + interval.")
    parser.add_argument("--cycles", type=int, default=6, help="Number of summary cycles to generate.")
    parser.add_argument("--interval-minutes", type=int, default=5, help="Minutes between summary cycles.")
    parser.add_argument("--evidence-dir", default="docs/live-evidence/roi-5min-6cycles", help="Output directory for local Feishu JSON evidence.")
    parser.add_argument("--write-feishu", action="store_true", help="Also create/reuse real Feishu Bitable tables and upsert the simulated rows.")
    args = parser.parse_args()

    start_at = datetime.strptime(args.start_at, "%Y-%m-%d %H:%M:%S")
    settings = load_settings()
    result = simulate_roi_cycles(
        settings,
        start_at=start_at,
        cycles=args.cycles,
        interval_minutes=args.interval_minutes,
        evidence_dir=args.evidence_dir,
    )
    output = {"simulation": asdict(result)}
    if args.write_feishu:
        output["feishu"] = asdict(write_simulation_to_feishu(settings, result.local_path))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
