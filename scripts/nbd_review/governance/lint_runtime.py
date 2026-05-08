"""Runtime hygiene checks for the NBD CLI."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from shared.utils import WORKSPACE_ROOT, read_text, relative_path


def run_lint_runtime(args: Any) -> int:
    """Prevent NBD-specific business knowledge from creeping into runtime."""
    target = Path(args.path).resolve() if args.path else WORKSPACE_ROOT / "scripts" / "nbd_review" / "business_review"
    nbd_id_pattern = re.compile("NBD" + r"\d{2}-\d{3}")
    forbidden_literals = [
        "RECALL" + "_PROFILES",
        "checkpoint" + "_profiles",
        "statistical" + "_review",
        "STATISTICAL" + "_REVIEW",
        "REPORT" + "_OBJECT",
    ]
    forbidden_business_terms = [
        "家具",
        "物业",
        "信息技术",
        "信息化设备",
        "检测报告",
        "检验报告",
        "检验检测报告",
    ]
    findings: list[str] = []
    for path in sorted(target.rglob("*.py") if target.is_dir() else [target]):
        text = read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if nbd_id_pattern.search(line):
                findings.append(f"{relative_path(path)}:{lineno}: runtime contains concrete NBD id")
            if any(value in line for value in forbidden_literals):
                findings.append(f"{relative_path(path)}:{lineno}: runtime contains forbidden profile registry")
            if any(value in line for value in forbidden_business_terms):
                findings.append(f"{relative_path(path)}:{lineno}: runtime contains hard-coded business object/item term")
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print(f"runtime lint ok: {relative_path(target)}")
    return 0
