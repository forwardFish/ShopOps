from __future__ import annotations

import asyncio

from data_robot.common import parse_common_args, run_platform


def main() -> int:
    parser = parse_common_args("Collect Pinduoduo order and promotion exports.")
    args = parser.parse_args()
    asyncio.run(run_platform("pinduoduo", args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
