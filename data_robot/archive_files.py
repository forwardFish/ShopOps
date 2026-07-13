from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from data_robot.common import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_EVIDENCE_ROOT,
    add_batch_layout_args,
    archive_downloads,
    evidence_token,
    hourly_batch_token,
    print_json,
    write_archive_manifest,
    write_json,
)
from data_robot.tasks import TASKS


def candidate_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            for child in sorted(path.iterdir()):
                if child.is_file() and child.suffix.lower() in {".csv", ".xls", ".xlsx", ".zip"}:
                    files.append(child)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive already-downloaded ShopOps source files.")
    parser.add_argument("task", choices=sorted(TASKS), help="Task that identifies platform and data kind.")
    parser.add_argument("paths", nargs="+", help="Downloaded files or folders containing csv/xls/xlsx/zip files.")
    parser.add_argument("--date-token", default="", help="Archive date directory, e.g. 0611. Defaults to today.")
    add_batch_layout_args(parser)
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    args = parser.parse_args()

    task = TASKS[args.task]
    date_token = args.date_token or datetime.now().strftime("%m%d")
    batch_token = date_token if args.flat_date_folder else hourly_batch_token(date_token, args.batch_hour)
    run_token = datetime.now().strftime("%Y%m%d-%H%M%S")
    sources = candidate_files([Path(item) for item in args.paths])
    archived = archive_downloads(task, sources, Path(args.archive_root), date_token=batch_token, run_token=run_token)
    manifest = write_archive_manifest(
        task,
        archived,
        Path(args.archive_root),
        date_token=batch_token,
        run_token=run_token,
        downloaded=sources,
    )

    summary = {
        "task": task.key,
        "status": "archived" if archived else "no_files_archived",
        "date_token": date_token,
        "batch_token": batch_token,
        "batch_dir": str(Path(args.archive_root) / batch_token),
        "sources": [str(path) for path in sources],
        "archived": [str(item.archived) for item in archived],
        "manifest": str(manifest) if manifest else "",
    }
    evidence_root = Path(args.evidence_root)
    evidence = evidence_root / f"archive-files-{task.key}-{evidence_token(batch_token)}-{datetime.now().strftime('%H%M%S')}.json"
    write_json(evidence, summary)
    print_json({**summary, "evidence": str(evidence)})
    return 0 if archived else 2


if __name__ == "__main__":
    raise SystemExit(main())
