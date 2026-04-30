"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path.cwd()
SCRIPTS_DIR = WORKSPACE_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate_checkpoint_cli as vcc  # noqa: E402

def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def default_output_dir(suffix: str) -> Path:
    return WORKSPACE_ROOT / "validation" / "nbd-runs" / f"{run_id()}-{suffix}"


def ensure_output_dir(args: Any, suffix: str) -> Path:
    output_dir = (args.output_dir or default_output_dir(suffix)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def relative_path(path: Path) -> str:
    try:
        return os.path.relpath(path, WORKSPACE_ROOT)
    except Exception:
        return str(path)


def run_path(output_dir: Path, path: Path) -> str:
    try:
        return os.path.relpath(path, output_dir)
    except Exception:
        return str(path)


def slugify(value: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "-", value).strip()
    return text or "unknown"


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def normalize_key(text: str) -> str:
    value = vcc.normalize_similarity_text(text)
    return value[:600]


def looks_like_heading(text: str) -> bool:
    value = text.strip()
    if not value or len(value) > 80 or "\t" in value:
        return False
    return bool(
        re.match(r"^(第[一二三四五六七八九十0-9]+[章节册部分]|[一二三四五六七八九十]+[、.．]|[0-9]+[.．、])", value)
        or value in {"评标信息", "商务要求", "用户需求书", "采购需求", "招标公告", "目录"}
    )
