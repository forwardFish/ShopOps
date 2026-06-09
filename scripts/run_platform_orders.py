from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shopops.collectors import create_order_collector
from shopops.config import load_settings
from shopops.models import model_dict


def main() -> int:
    settings = load_settings()
    collector = create_order_collector(settings)
    result = collector.fetch_today()
    print(json.dumps(model_dict(result), ensure_ascii=False, indent=2, default=str))
    return 0 if result.success else 2


if __name__ == "__main__":
    raise SystemExit(main())
