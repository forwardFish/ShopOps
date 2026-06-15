from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from data_robot.common import DEFAULT_ARCHIVE_ROOT, DEFAULT_EVIDENCE_ROOT, evidence_token, print_json, write_json
from data_robot.tasks import TASKS


TABULAR_SUFFIXES = {".csv", ".xls", ".xlsx"}
KIND_ALIASES = {
    "orders": "orders",
    "ads": "ads",
    "influencer": "influencer",
}


def task_files(batch_dir: Path, task_key: str) -> list[Path]:
    task = TASKS[task_key]
    platform_dir = batch_dir / task.platform
    if not platform_dir.exists():
        return []
    prefix = f"{task.platform_code}_{task.kind}_{task.slug}"
    return sorted(
        path
        for path in platform_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in TABULAR_SUFFIXES
        and prefix in path.name
    )


def task_manifests(batch_dir: Path, task_key: str) -> list[Path]:
    task = TASKS[task_key]
    platform_dir = batch_dir / task.platform
    if not platform_dir.exists():
        return []
    prefix = f"{task.platform_code}_{task.kind}_{task.slug}"
    return sorted(
        path
        for path in platform_dir.iterdir()
        if path.is_file()
        and path.name.endswith("_manifest.json")
        and prefix in path.name
    )


def legacy_task_files(batch_dir: Path, task_key: str) -> list[Path]:
    try:
        from scripts.import_daily_files_to_feishu import discover_daily_files
    except Exception:
        return []
    task = TASKS[task_key]
    try:
        discovered = discover_daily_files(batch_dir)
    except Exception:
        return []
    kinds = discovered.get(task.platform) or {}
    return sorted(Path(path) for path in kinds.get(KIND_ALIASES[task.kind], []))


def verify_batch(
    batch_dir: Path,
    task_keys: list[str] | None = None,
    *,
    include_legacy: bool = False,
) -> dict[str, Any]:
    selected = task_keys or list(TASKS)
    tasks: dict[str, Any] = {}
    for key in selected:
        files = task_files(batch_dir, key)
        manifests = task_manifests(batch_dir, key)
        legacy_files = legacy_task_files(batch_dir, key) if include_legacy else []
        status = "normalized" if files else "legacy_present" if legacy_files else "missing"
        tasks[key] = {
            "platform": TASKS[key].platform,
            "kind": TASKS[key].kind,
            "files": [str(path) for path in files],
            "legacy_files": [str(path) for path in legacy_files],
            "manifests": [str(path) for path in manifests],
            "status": status,
        }
    missing = [key for key, item in tasks.items() if item["status"] == "missing"]
    legacy_only = [key for key, item in tasks.items() if item["status"] == "legacy_present"]
    return {
        "status": "complete" if not missing and not legacy_only else "legacy_present" if not missing else "incomplete",
        "batch_dir": str(batch_dir),
        "checked_tasks": selected,
        "missing_tasks": missing,
        "legacy_only_tasks": legacy_only,
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a ShopOps data_robot daily archive folder.")
    parser.add_argument("--date-token", required=True, help="Daily folder such as 0611.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--task", action="append", choices=sorted(TASKS), help="Only verify selected task; repeatable.")
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Also scan older unnormalized files with the Feishu import classifier. This can open many Excel files.",
    )
    args = parser.parse_args()

    batch_dir = Path(args.archive_root) / args.date_token
    summary = verify_batch(batch_dir, args.task, include_legacy=args.include_legacy)
    evidence_root = Path(args.evidence_root)
    evidence = evidence_root / f"verify-batch-{evidence_token(args.date_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({**summary, "evidence": str(evidence)})
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
