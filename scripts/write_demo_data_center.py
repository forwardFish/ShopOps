from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.config import load_settings
from shopops.services.data_center_demo import write_data_center


def main() -> int:
    settings = load_settings()
    result = write_data_center(settings, allow_local_fallback=True)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.mode == "feishu" else 2


if __name__ == "__main__":
    raise SystemExit(main())
