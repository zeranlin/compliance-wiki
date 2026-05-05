"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
from pathlib import Path
from typing import Any

from shared.schemas import RUNTIME_SCHEMA
from business_review.document_compiler import load_document_ir, write_document_artifacts
from business_review.model_runner import run_one_item, write_model_result_artifact
from business_review.nbd_compiler import expand_nbd_files, load_items_from_nbd_ir, parse_nbd_file, write_nbd_ir_artifacts, write_nbd_lint_report
from business_review.prompt_runner import write_prompt_artifacts
from business_review.recall_runner import write_candidate_artifacts
from business_review.reporters import write_report_artifacts
from shared.utils import ensure_output_dir, relative_path, write_text


COMPACT_REMOVED_PATHS = [
    "nbd-ir",
    "prompts",
    "nbd-ir-lint.json",
    "nbd-ir-lint.md",
]


def artifact_mode(args: Any) -> str:
    return str(getattr(args, "artifact_mode", "") or "compact").strip()


def write_artifact_manifest(output_dir: Path, mode: str, removed: list[str]) -> None:
    payload = {
        "artifact_mode": mode,
        "kept": [
            "run.json",
            "document-ir.json",
            "candidates/",
            "model-results/",
            "recall_matrix.json",
            "recall_matrix.md",
            "nbd-results.json",
            "业务审查报告.md",
        ],
        "removed": removed,
        "note": "compact 模式保留业务报告、结构化结果、Document IR、CandidateWindow 和模型结果；调试 prompt 或 NBD IR 时请使用 --artifact-mode full。",
    }
    write_text(output_dir / "artifacts.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# 运行产物清单",
        "",
        f"- 产物模式：`{mode}`",
        "- 说明：compact 模式保留业务复盘和 F1 评测所需文件，清理可重新生成的 prompt 明细和重复 NBD IR。",
        "",
        "## 保留",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["kept"])
    lines.extend(["", "## 清理", ""])
    lines.extend(f"- `{item}`" for item in removed)
    write_text(output_dir / "artifacts.md", "\n".join(lines) + "\n")


def compact_run_artifacts(output_dir: Path, args: Any) -> None:
    mode = artifact_mode(args)
    removed: list[str] = []
    if mode == "compact":
        for rel_path in COMPACT_REMOVED_PATHS:
            path = output_dir / rel_path
            if not path.exists():
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(rel_path)
    write_artifact_manifest(output_dir, mode, removed)

def run_preflight(args: Any) -> int:
    review_file = args.review_file.resolve()
    output_dir = ensure_output_dir(args, "nbd-preflight")
    blocks, stats, facts, extractor = write_document_artifacts(output_dir, review_file)
    nbd_files = expand_nbd_files(args)
    items = [parse_nbd_file(path) for path in nbd_files]
    write_nbd_ir_artifacts(output_dir, items)
    write_candidate_artifacts(output_dir, blocks, items, args)
    write_text(output_dir / "run.json", json.dumps({"schema_version": RUNTIME_SCHEMA, "review_file": str(review_file), "extractor": extractor, "stats": stats}, ensure_ascii=False, indent=2) + "\n")
    print(relative_path(output_dir / "recall_matrix.md"))
    return 0


def run_compile_document(args: Any) -> int:
    review_file = args.review_file.resolve()
    output_dir = ensure_output_dir(args, "nbd-stage")
    blocks, stats, _, extractor = write_document_artifacts(output_dir, review_file)
    write_text(
        output_dir / "run.json",
        json.dumps({"schema_version": RUNTIME_SCHEMA, "review_file": str(review_file), "extractor": extractor, "stats": stats}, ensure_ascii=False, indent=2) + "\n",
    )
    print(relative_path(output_dir / "document-ir.json"))
    print(f"blocks={len(blocks)}")
    return 0


def run_compile_nbd(args: Any) -> int:
    output_dir = ensure_output_dir(args, "nbd-stage")
    items = [parse_nbd_file(path) for path in expand_nbd_files(args)]
    write_nbd_ir_artifacts(output_dir, items)
    report = write_nbd_lint_report(output_dir, items)
    print(relative_path(output_dir / "nbd-ir"))
    print(relative_path(output_dir / "nbd-ir-lint.md"))
    print(f"nbd_count={len(items)}")
    print(f"lint_errors={report.get('error_count', 0)} lint_warnings={report.get('warning_count', 0)}")
    return 1 if int(report.get("error_count") or 0) else 0


def run_recall_stage(args: Any) -> int:
    output_dir = ensure_output_dir(args, "nbd-stage")
    _, blocks, _, _, _ = load_document_ir(output_dir)
    items = load_items_from_nbd_ir(output_dir, list(args.nbd or []))
    write_candidate_artifacts(output_dir, blocks, items, args)
    print(relative_path(output_dir / "recall_matrix.md"))
    return 0


def run_build_prompt_stage(args: Any) -> int:
    output_dir = ensure_output_dir(args, "nbd-stage")
    review_file, _, _, facts, _ = load_document_ir(output_dir)
    items = load_items_from_nbd_ir(output_dir, list(args.nbd or []))
    write_prompt_artifacts(output_dir, review_file.name, facts, items, args)
    print(relative_path(output_dir / "prompts"))
    print(f"prompt_count={len(items)}")
    return 0


def run_model_stage(args: Any) -> int:
    output_dir = ensure_output_dir(args, "nbd-stage")
    review_file, _, _, facts, _ = load_document_ir(output_dir)
    items = load_items_from_nbd_ir(output_dir, list(args.nbd or []))
    results: list[dict[str, Any]] = []
    failures = 0
    jobs = max(1, int(args.jobs or 1))
    if jobs == 1:
        for item in items:
            try:
                results.append(write_model_result_artifact(output_dir, review_file, facts, item, args))
            except Exception as exc:
                failures += 1
                print(f"error {item.nbd_id}: {exc}", flush=True)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(write_model_result_artifact, output_dir, review_file, facts, item, args): item for item in items}
            for future in concurrent.futures.as_completed(future_map):
                item = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    failures += 1
                    print(f"error {item.nbd_id}: {exc}", flush=True)
    print(f"model stage done output={relative_path(output_dir)} failures={failures}", flush=True)
    return 1 if failures else 0


def run_report_stage(args: Any) -> int:
    output_dir = ensure_output_dir(args, "nbd-stage")
    results = write_report_artifacts(output_dir)
    print(relative_path(output_dir / "业务审查报告.md"))
    print(f"result_count={len(results)}")
    return 0


def run_review(args: Any) -> int:
    review_file = args.review_file.resolve()
    output_dir = ensure_output_dir(args, "nbd-review")
    blocks, stats, facts, extractor = write_document_artifacts(output_dir, review_file)
    nbd_files = expand_nbd_files(args)
    items = [parse_nbd_file(path) for path in nbd_files]
    write_nbd_ir_artifacts(output_dir, items)
    write_text(output_dir / "run.json", json.dumps({"schema_version": RUNTIME_SCHEMA, "review_file": str(review_file), "extractor": extractor, "stats": stats, "nbd_count": len(items)}, ensure_ascii=False, indent=2) + "\n")

    results: list[dict[str, Any]] = []
    failures = 0
    jobs = max(1, int(args.jobs or 1))
    if jobs == 1:
        for item in items:
            try:
                results.append(run_one_item(args, review_file, output_dir, blocks, facts, item))
            except Exception as exc:
                failures += 1
                print(f"error {item.nbd_id}: {exc}", flush=True)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(run_one_item, args, review_file, output_dir, blocks, facts, item): item for item in items}
            for future in concurrent.futures.as_completed(future_map):
                item = future_map[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    failures += 1
                    print(f"error {item.nbd_id}: {exc}", flush=True)
    write_report_artifacts(output_dir, results)
    compact_run_artifacts(output_dir, args)
    print(f"nbd review done output={relative_path(output_dir)} failures={failures}", flush=True)
    return 1 if failures else 0
