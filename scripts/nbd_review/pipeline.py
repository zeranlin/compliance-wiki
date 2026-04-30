"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from pathlib import Path
from typing import Any

from schemas import RUNTIME_SCHEMA
from document_compiler import load_document_ir, write_document_artifacts
from model_runner import run_one_item, write_model_result_artifact
from nbd_compiler import expand_nbd_files, load_items_from_nbd_ir, parse_nbd_file, write_nbd_ir_artifacts, write_nbd_lint_report
from prompt_runner import write_prompt_artifacts
from recall_runner import write_candidate_artifacts
from reporters import write_report_artifacts
from utils import WORKSPACE_ROOT, ensure_output_dir, read_text, relative_path, write_text

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


def run_lint_runtime(args: Any) -> int:
    """Prevent NBD-specific business knowledge from creeping into runtime."""
    target = Path(args.path or WORKSPACE_ROOT / "scripts" / "nbd_review").resolve()
    nbd_id_pattern = re.compile("NBD" + r"\d{2}-\d{3}")
    forbidden_literals = ["RECALL" + "_PROFILES", "checkpoint" + "_profiles"]
    findings: list[str] = []
    for path in sorted(target.rglob("*.py") if target.is_dir() else [target]):
        text = read_text(path)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if nbd_id_pattern.search(line):
                findings.append(f"{relative_path(path)}:{lineno}: runtime contains concrete NBD id")
            if any(value in line for value in forbidden_literals):
                findings.append(f"{relative_path(path)}:{lineno}: runtime contains forbidden profile registry")
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print(f"runtime lint ok: {relative_path(target)}")
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
    print(f"nbd review done output={relative_path(output_dir)} failures={failures}", flush=True)
    return 1 if failures else 0
