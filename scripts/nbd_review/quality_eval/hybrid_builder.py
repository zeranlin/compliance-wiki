"""Build final-hybrid evaluation runs from full and targeted runs."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from quality_eval.run_roles import split_csv, write_run_role
from shared.utils import relative_path, write_text


OVERLAY_DIRS = ["model-results", "candidates"]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def nbd_id_from_result(path: Path) -> str:
    data = load_json(path)
    model_result = data.get("model_result") if isinstance(data.get("model_result"), dict) else {}
    nbd_meta = data.get("nbd") if isinstance(data.get("nbd"), dict) else {}
    return str(model_result.get("nbd_id") or nbd_meta.get("id") or path.stem).strip()


def copy_selected_files(source_dir: Path, output_dir: Path, subdir: str, selected_nbds: set[str]) -> list[str]:
    src = source_dir / subdir
    dst = output_dir / subdir
    if not src.exists():
        return []
    copied: list[str] = []
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.glob("*.json")):
        nbd_id = nbd_id_from_result(path) if subdir == "model-results" else path.stem
        if selected_nbds and nbd_id not in selected_nbds:
            continue
        shutil.copy2(path, dst / path.name)
        copied.append(nbd_id)
    return sorted(set(copied))


def copy_selected_item_dirs(source_dir: Path, output_dir: Path, selected_nbds: set[str]) -> list[str]:
    src = source_dir / "items"
    dst = output_dir / "items"
    if not src.exists():
        return []
    copied: list[str] = []
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        if not path.is_dir():
            continue
        nbd_id = path.name
        if selected_nbds and nbd_id not in selected_nbds:
            continue
        target = dst / nbd_id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(path, target)
        copied.append(nbd_id)
    return copied


def remove_stale_evaluations(output_dir: Path) -> None:
    for path in output_dir.glob("evaluation*"):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def build_hybrid_run(
    base_run: Path,
    targeted_runs: list[Path],
    output_dir: Path,
    selected_nbds: set[str],
    case_no: int | None = None,
    sample_name: str = "",
    item_category: str = "",
    notes: str = "",
) -> dict[str, Any]:
    if not base_run.exists():
        raise FileNotFoundError(base_run)
    if output_dir.exists():
        raise FileExistsError(f"output already exists: {output_dir}")
    shutil.copytree(base_run, output_dir)
    remove_stale_evaluations(output_dir)
    overlays: list[dict[str, Any]] = []
    for targeted_run in targeted_runs:
        copied_by_dir: dict[str, list[str]] = {}
        for subdir in OVERLAY_DIRS:
            copied_by_dir[subdir] = copy_selected_files(targeted_run, output_dir, subdir, selected_nbds)
        copied_by_dir["items"] = copy_selected_item_dirs(targeted_run, output_dir, selected_nbds)
        overlays.append(
            {
                "targeted_run": str(targeted_run),
                "selected_nbds": sorted(selected_nbds),
                "copied": copied_by_dir,
            }
        )
    payload = {
        "schema_version": "nbd-final-hybrid/v1",
        "created_by_layer": "quality_eval",
        "base_run": str(base_run),
        "targeted_runs": [str(path) for path in targeted_runs],
        "selected_nbds": sorted(selected_nbds),
        "overlays": overlays,
        "notes": notes,
    }
    write_text(output_dir / "hybrid-manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "hybrid-manifest.md", render_hybrid_markdown(payload))
    write_run_role(
        run_dir=output_dir,
        role="final-hybrid",
        case_no=case_no,
        sample_name=sample_name,
        item_category=item_category,
        base_run=base_run,
        targeted_runs=targeted_runs,
        related_nbds=sorted(selected_nbds),
        notes=notes,
    )
    return payload


def render_hybrid_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Final-Hybrid 构造清单",
        "",
        f"- base run：`{payload.get('base_run', '')}`",
        f"- 备注：{payload.get('notes') or ''}",
        "",
        "## 合并 NBD",
        "",
    ]
    selected = payload.get("selected_nbds") or []
    lines.extend(f"- `{item}`" for item in selected)
    if not selected:
        lines.append("- 未限制 NBD，按 targeted run 可用结果合并。")
    lines.extend(["", "## Targeted Runs", ""])
    for overlay in payload.get("overlays") or []:
        lines.append(f"### `{overlay.get('targeted_run', '')}`")
        copied = overlay.get("copied") if isinstance(overlay.get("copied"), dict) else {}
        for name, items in copied.items():
            lines.append(f"- `{name}`：{len(items)} 个")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构造质量评测层 final-hybrid run")
    parser.add_argument("--base-run", required=True, type=Path)
    parser.add_argument("--targeted-run", required=True, action="append", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--nbd", action="append", default=[], help="只合并指定 NBD，可重复；也可逗号分隔")
    parser.add_argument("--case-no", type=int)
    parser.add_argument("--sample-name", default="")
    parser.add_argument("--item-category", default="")
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_hybrid_run(
        base_run=args.base_run.resolve(),
        targeted_runs=[path.resolve() for path in args.targeted_run],
        output_dir=args.output_dir.resolve(),
        selected_nbds=set(split_csv(args.nbd)),
        case_no=args.case_no,
        sample_name=args.sample_name,
        item_category=args.item_category,
        notes=args.notes,
    )
    print(relative_path(args.output_dir.resolve()))
    print(f"targeted_runs={len(payload['targeted_runs'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
