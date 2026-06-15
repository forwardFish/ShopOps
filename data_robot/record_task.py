from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from data_robot.common import PROFILE_ROOT
from data_robot.tasks import TASKS


def main() -> int:
    parser = argparse.ArgumentParser(description="Open Playwright codegen for one ShopOps data task.")
    parser.add_argument("task", choices=sorted(TASKS))
    parser.add_argument("--output", default="", help="Recording output path. Defaults to data_robot/recordings/<task>.py.")
    args = parser.parse_args()

    task = TASKS[args.task]
    output = Path(args.output) if args.output else Path(__file__).resolve().parent / "recordings" / f"{task.key}.py"
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = PROFILE_ROOT / task.profile
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "playwright",
        "codegen",
        "--target",
        "python",
        "-o",
        str(output),
        "--user-data-dir",
        str(profile),
        task.url,
    ]
    print(" ".join(command), flush=True)
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
