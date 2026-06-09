from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "docs" / "auto-execute" / "logs" / "T09" / "secret-guard.txt"
SECRET_KEYS = {"FEISHU_APP_SECRET", "TAOBAO_APP_SECRET", "TAOBAO_SESSION_KEY"}
PLACEHOLDERS = {"", "xxx", "missing", "your_app_secret", "your_session_key", "your_feishu_app_secret"}
SKIP_DIRS = {".git", ".omx", ".codex", ".pytest_cache", "__pycache__"}
SKIP_FILES = {
    ".env.example",
    "taobao_mvp_requirements.md",
    "taobao_mvp_development.md",
}


def main() -> int:
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_dir() or path.suffix.lower() in {".pyc", ".png", ".jpg", ".jpeg", ".gif"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.name in SKIP_FILES:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key in SECRET_KEYS and value.lower() not in PLACEHOLDERS:
                hits.append(f"{path.relative_to(ROOT)}:{line_no}")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if hits:
        LOG.write_text("SECRET_GUARD: FAIL\n" + "\n".join(hits), encoding="utf-8")
        return 1
    LOG.write_text("SECRET_GUARD: PASS\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
