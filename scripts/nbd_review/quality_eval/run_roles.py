"""Quality-layer role metadata for NBD runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shared.utils import relative_path, write_text


VALID_ROLES = {"baseline", "targeted", "final-full", "final-hybrid"}


def split_csv(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for item in str(value or "").split(","):
            text = item.strip()
            if text:
                result.append(text)
    return result


def run_role_payload(
    run_dir: Path,
    role: str,
    case_no: int | None = None,
    sample_name: str = "",
    item_category: str = "",
    base_run: Path | None = None,
    targeted_runs: list[Path] | None = None,
    related_nbds: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    if role not in VALID_ROLES:
        raise ValueError(f"unknown run role: {role}")
    return {
        "schema_version": "nbd-run-role/v1",
        "created_by_layer": "quality_eval",
        "role": role,
        "case_no": case_no,
        "sample_name": sample_name,
        "item_category": item_category,
        "run_dir": str(run_dir),
        "base_run": str(base_run) if base_run else "",
        "targeted_runs": [str(path) for path in targeted_runs or []],
        "related_nbds": related_nbds or [],
        "notes": notes,
    }


def render_role_markdown(payload: dict[str, Any]) -> str:
    targeted_runs = payload.get("targeted_runs") or []
    related_nbds = payload.get("related_nbds") or []
    lines = [
        "# NBD Run 评测角色",
        "",
        f"- 角色：`{payload.get('role', '')}`",
        f"- 案例编号：{payload.get('case_no') or ''}",
        f"- 样本名称：{payload.get('sample_name') or ''}",
        f"- 品目：{payload.get('item_category') or ''}",
        f"- run：`{payload.get('run_dir', '')}`",
        f"- base run：`{payload.get('base_run', '')}`",
        f"- 备注：{payload.get('notes') or ''}",
        "",
        "## Targeted Runs",
        "",
    ]
    lines.extend(f"- `{item}`" for item in targeted_runs)
    if not targeted_runs:
        lines.append("- 无")
    lines.extend(["", "## Related NBDs", ""])
    lines.extend(f"- `{item}`" for item in related_nbds)
    if not related_nbds:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def write_run_role(
    run_dir: Path,
    role: str,
    case_no: int | None = None,
    sample_name: str = "",
    item_category: str = "",
    base_run: Path | None = None,
    targeted_runs: list[Path] | None = None,
    related_nbds: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    payload = run_role_payload(
        run_dir=run_dir,
        role=role,
        case_no=case_no,
        sample_name=sample_name,
        item_category=item_category,
        base_run=base_run,
        targeted_runs=targeted_runs,
        related_nbds=related_nbds,
        notes=notes,
    )
    write_text(run_dir / "run-role.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text(run_dir / "run-role.md", render_role_markdown(payload))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="标记 NBD run 在质量评测层中的角色")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--role", required=True, choices=sorted(VALID_ROLES))
    parser.add_argument("--case-no", type=int)
    parser.add_argument("--sample-name", default="")
    parser.add_argument("--item-category", default="")
    parser.add_argument("--base-run", type=Path)
    parser.add_argument("--targeted-run", action="append", default=[])
    parser.add_argument("--nbd", action="append", default=[], help="相关 NBD，可重复；也可逗号分隔")
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = write_run_role(
        run_dir=args.run_dir.resolve(),
        role=args.role,
        case_no=args.case_no,
        sample_name=args.sample_name,
        item_category=args.item_category,
        base_run=args.base_run.resolve() if args.base_run else None,
        targeted_runs=[path.resolve() for path in args.targeted_run],
        related_nbds=split_csv(args.nbd),
        notes=args.notes,
    )
    print(relative_path(args.run_dir.resolve() / "run-role.json"))
    print(f"role={payload['role']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
