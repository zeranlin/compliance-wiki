"""Build a lightweight index for NBD run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shared.utils import WORKSPACE_ROOT, relative_path, write_text


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_metrics(run_dir: Path, name: str) -> dict[str, Any]:
    data = load_json(run_dir / name / "metrics.json")
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else data
    return metrics if isinstance(metrics, dict) else {}


def run_row(run_dir: Path) -> dict[str, Any]:
    run_meta = load_json(run_dir / "run.json")
    artifacts = load_json(run_dir / "artifacts.json")
    run_role = load_json(run_dir / "run-role.json")
    hybrid_manifest = load_json(run_dir / "hybrid-manifest.json")
    model_results = sorted((run_dir / "model-results").glob("*.json")) if (run_dir / "model-results").exists() else []
    return {
        "run_id": run_dir.name,
        "path": relative_path(run_dir),
        "role": run_role.get("role", ""),
        "case_no": run_role.get("case_no", ""),
        "sample_name": run_role.get("sample_name", ""),
        "item_category": run_role.get("item_category", ""),
        "base_run": run_role.get("base_run", "") or hybrid_manifest.get("base_run", ""),
        "targeted_runs": run_role.get("targeted_runs", []) or hybrid_manifest.get("targeted_runs", []),
        "related_nbds": run_role.get("related_nbds", []) or hybrid_manifest.get("selected_nbds", []),
        "review_file": run_meta.get("review_file", ""),
        "nbd_count": run_meta.get("nbd_count", ""),
        "artifact_mode": artifacts.get("artifact_mode", ""),
        "model_result_count": len(model_results),
        "v1": load_metrics(run_dir, "evaluation-v1"),
        "v2": load_metrics(run_dir, "evaluation-v2"),
    }


def build_index(base_dir: Path) -> list[dict[str, Any]]:
    candidates = [path for path in base_dir.rglob("*") if path.is_dir() and (path / "run.json").exists()]
    return [run_row(path) for path in sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)]


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# NBD 运行产物索引",
        "",
        "| run | 角色 | 品目 | 案例 | 文件 | NBD | 模型结果 | 产物模式 | V1 F1 | V2 F1 | 路径 |",
        "|---|---|---|---:|---|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        v1 = row.get("v1") or {}
        v2 = row.get("v2") or {}
        sample = row.get("sample_name") or Path(str(row.get("review_file") or "")).name
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("run_id") or ""),
                    str(row.get("role") or ""),
                    str(row.get("item_category") or ""),
                    str(row.get("case_no") or ""),
                    str(sample),
                    str(row.get("nbd_count") or ""),
                    str(row.get("model_result_count") or 0),
                    str(row.get("artifact_mode") or ""),
                    f"{float(v1.get('f1', 0) or 0):.4f}" if v1 else "",
                    f"{float(v2.get('f1', 0) or 0):.4f}" if v2 else "",
                    str(row.get("path") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_run_index(base_dir: Path, output_dir: Path) -> tuple[Path, Path]:
    rows = build_index(base_dir)
    json_path = output_dir / "run-index.json"
    md_path = output_dir / "run-index.md"
    write_text(json_path, json.dumps({"runs": rows}, ensure_ascii=False, indent=2) + "\n")
    write_text(md_path, render_markdown(rows))
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 validation/nbd-runs 运行产物索引")
    parser.add_argument("--base-dir", type=Path, default=WORKSPACE_ROOT / "validation" / "nbd-runs")
    parser.add_argument("--output-dir", type=Path, default=WORKSPACE_ROOT / "validation" / "nbd-runs" / "governance")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    json_path, md_path = write_run_index(args.base_dir.resolve(), args.output_dir.resolve())
    print(relative_path(md_path))
    print(relative_path(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
