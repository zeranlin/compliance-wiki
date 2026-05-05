#!/usr/bin/env python3
"""Diagnose false negatives across Document IR, candidates, prompt, and model output."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from quality_eval.evaluate_f1 import GoldItem, load_gold, name_match_info, normalize_name, parse_line_anchor


@dataclass
class NBDRun:
    nbd_id: str
    title: str
    result_file: str
    prompt_file: str
    candidate_file: str
    verdict: str
    windows: list[dict[str, Any]]
    model_candidates: list[dict[str, Any]]


def compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def compact_evidence(value: str) -> str:
    text = compact(value)
    text = re.sub(r"实质性条款具体内容[:：]?", "", text)
    text = re.sub(r"风险原文[:：]?", "", text)
    return re.sub(r"[，。、；;：:“”‘’（）()\[\]【】《》<>.,\-_/…]+", "", text)


def text_coverage(needle: str, haystack: str) -> float:
    needle_text = compact_evidence(needle)
    haystack_text = compact_evidence(haystack)
    if not needle_text or not haystack_text:
        return 0.0
    if needle_text in haystack_text:
        return 1.0
    if haystack_text in needle_text:
        shorter = len(haystack_text)
        ratio = shorter / len(needle_text)
        if shorter >= 8 and ratio >= 0.35:
            return max(0.85, ratio)
        return ratio
    chunks = [chunk for chunk in re.split(r"[，。、；;：:“”‘’（）()\[\]【】《》<>.,\-_/…]+", str(needle or "")) if len(compact_evidence(chunk)) >= 6]
    if chunks:
        chunk_hits = sum(1 for chunk in chunks if compact_evidence(chunk) in haystack_text)
        if chunk_hits:
            return max(chunk_hits / len(chunks), 0.65 if "…" in str(needle) else 0.0)
    return sum(1 for char in needle_text if char in haystack_text) / len(needle_text)


def document_match(gold: GoldItem, blocks_by_line: dict[int, dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for offset in (0, -1, 1, -2, 2):
        line = gold.line + offset
        block = blocks_by_line.get(line)
        if not block:
            continue
        coverage = text_coverage(gold.text, str(block.get("text") or ""))
        candidates.append({"line": line, "offset": offset, "block": block, "coverage": coverage})
    if not candidates:
        return {"status": "missing_line", "coverage": 0.0, "line": gold.line, "block": None, "matched_line": None}
    candidates.sort(key=lambda item: (item["coverage"], item["offset"] == 0), reverse=True)
    best = candidates[0]
    status = "weak_text_match"
    if best["coverage"] >= 0.8:
        status = "ok" if best["offset"] == 0 else "neighbor_text_match"
    elif "…" in gold.text and best["coverage"] >= 0.55:
        status = "summary_text_match"
    elif best["coverage"] >= 0.5:
        status = "partial_text_match"
    return {
        "status": status,
        "coverage": best["coverage"],
        "line": gold.line,
        "matched_line": best["line"],
        "block": best["block"],
    }


def line_in_anchor(line: int, anchor: Any) -> bool:
    line_range = parse_line_anchor(anchor)
    if not line_range:
        return False
    start, end = line_range
    return start <= line <= end


def resolve_run_path(run_dir: Path, value: str) -> Path:
    path = Path(str(value or ""))
    if path.is_absolute():
        return path
    return run_dir / path


def load_document_blocks(run_dir: Path) -> dict[int, dict[str, Any]]:
    document_ir = run_dir / "document-ir.json"
    payload = json.loads(document_ir.read_text(encoding="utf-8"))
    blocks: dict[int, dict[str, Any]] = {}
    for block in payload.get("blocks", []):
        try:
            start = int(block.get("line_start"))
            end = int(block.get("line_end") or start)
        except (TypeError, ValueError):
            continue
        for line in range(start, end + 1):
            blocks[line] = block
    return blocks


def load_nbd_runs(run_dir: Path) -> list[NBDRun]:
    runs: list[NBDRun] = []
    for result_file in sorted((run_dir / "items").glob("*/result.json")):
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        nbd_meta = payload.get("nbd") or {}
        model_result = payload.get("model_result") or {}
        nbd_id = str(model_result.get("nbd_id") or nbd_meta.get("id") or result_file.parent.name)
        title = str(model_result.get("nbd_title") or model_result.get("checkpoint_title") or nbd_meta.get("title") or "")
        prompt_file = str(payload.get("prompt_file") or "")
        candidate_file = str(payload.get("candidate_file") or "")
        windows = payload.get("windows") if isinstance(payload.get("windows"), list) else []
        candidates = model_result.get("candidates") if isinstance(model_result.get("candidates"), list) else []
        runs.append(
            NBDRun(
                nbd_id=nbd_id,
                title=title,
                result_file=str(result_file),
                prompt_file=str(resolve_run_path(run_dir, prompt_file)) if prompt_file else "",
                candidate_file=str(resolve_run_path(run_dir, candidate_file)) if candidate_file else "",
                verdict=str(model_result.get("verdict") or ""),
                windows=windows,
                model_candidates=candidates,
            )
        )
    return runs


def nbd_match_score(gold_name: str, title: str) -> tuple[float, str]:
    is_match, match_type, score = name_match_info(gold_name, title)
    if is_match:
        return score, match_type
    gold_norm = normalize_name(gold_name)
    title_norm = normalize_name(title)
    if not gold_norm or not title_norm:
        return 0.0, "none"
    if gold_norm == title_norm:
        return 1.0, "exact"
    if gold_norm in title_norm or title_norm in gold_norm:
        shorter = min(len(gold_norm), len(title_norm))
        longer = max(len(gold_norm), len(title_norm))
        return 0.72 + 0.2 * (shorter / longer), "contains"
    gold_chars = set(gold_norm)
    title_chars = set(title_norm)
    union = gold_chars | title_chars
    if not union:
        return 0.0, "none"
    return len(gold_chars & title_chars) / len(union), "fuzzy"


def target_runs_for_gold(gold: GoldItem, runs: list[NBDRun]) -> list[dict[str, Any]]:
    scored = []
    for run in runs:
        score, match_type = nbd_match_score(gold.checkpoint_name, run.title)
        if match_type in {"exact", "contains"} or score >= 0.45:
            scored.append({"run": run, "score": score, "match_type": match_type})
    scored.sort(key=lambda item: (item["score"], item["run"].nbd_id), reverse=True)
    exact = [item for item in scored if item["match_type"] == "exact"]
    if exact:
        return exact
    contains = [item for item in scored if item["match_type"] == "contains"]
    if contains:
        return contains[:3]
    return scored[:3]


def prompt_contains(run: NBDRun, gold: GoldItem, document_text: str) -> dict[str, Any]:
    if not run.prompt_file:
        return {"available": False, "contains_line_anchor": False, "contains_text": False}
    path = Path(run.prompt_file)
    if not path.exists():
        return {"available": False, "contains_line_anchor": False, "contains_text": False, "path": str(path)}
    text = path.read_text(encoding="utf-8")
    anchors = {f"{gold.line:04d}", f"{gold.line:04d}-{gold.line:04d}", str(gold.line)}
    contains_anchor = any(anchor in text for anchor in anchors)
    contains_text = text_coverage(gold.text, text) >= 0.8 or text_coverage(document_text, text) >= 0.8
    return {"available": True, "contains_line_anchor": contains_anchor, "contains_text": contains_text, "path": str(path)}


def candidate_windows_for_line(run: NBDRun, line: int) -> list[dict[str, Any]]:
    return [
        window for window in run.windows
        if isinstance(window, dict) and line_in_anchor(line, window.get("line_anchor") or window.get("line"))
    ]


def model_candidates_for_line(run: NBDRun, line: int) -> list[dict[str, Any]]:
    return [
        candidate for candidate in run.model_candidates
        if isinstance(candidate, dict) and line_in_anchor(line, candidate.get("line_anchor") or candidate.get("line"))
    ]


def has_prompt_target(prompt_statuses: list[dict[str, Any]], key: str) -> bool:
    return any(bool(item.get("prompt", {}).get(key)) for item in prompt_statuses)


def primary_reason(
    document_status: str,
    target_runs: list[dict[str, Any]],
    candidate_hits: list[dict[str, Any]],
    prompt_statuses: list[dict[str, Any]],
    model_hits: list[dict[str, Any]],
) -> str:
    if document_status not in {"ok", "neighbor_text_match", "summary_text_match", "partial_text_match"}:
        return "document_ir_missing"
    if not target_runs:
        return "name_mapping_missing"
    if not candidate_hits:
        return "candidate_missing"
    if prompt_statuses and not any(
        item.get("prompt", {}).get("contains_line_anchor") or item.get("prompt", {}).get("contains_text")
        for item in prompt_statuses
    ):
        return "prompt_missing"
    if not model_hits:
        return "postprocess_or_output_issue"
    verdicts = {str(item.get("candidate", {}).get("candidate_verdict") or "") for item in model_hits}
    if "命中" not in verdicts:
        return "model_conservative"
    return "evaluation_matching_granularity"


def secondary_reason(
    primary: str,
    candidate_hits: list[dict[str, Any]],
    prompt_statuses: list[dict[str, Any]],
    model_hits: list[dict[str, Any]],
) -> str:
    if primary == "candidate_missing":
        if has_prompt_target(prompt_statuses, "contains_line_anchor"):
            return "prompt_contains_line_but_not_candidate"
        if has_prompt_target(prompt_statuses, "contains_text"):
            return "prompt_contains_text_but_not_candidate"
        return "no_candidate_window_for_target_line"
    if primary == "prompt_missing":
        if candidate_hits and not any(hit.get("window_type") == "primary" for hit in candidate_hits):
            return "candidate_only_support_or_noisy"
        return "candidate_not_in_prompt"
    if primary == "postprocess_or_output_issue":
        if candidate_hits and not any(hit.get("window_type") == "primary" for hit in candidate_hits):
            return "candidate_not_primary"
        return "candidate_not_in_model_output"
    if primary == "model_conservative":
        verdicts = {str(item.get("candidate", {}).get("candidate_verdict") or "") for item in model_hits}
        if "待人工复核" in verdicts:
            return "model_candidate_review_required"
        if "不命中" in verdicts:
            return "model_candidate_negative"
        return "model_result_not_positive"
    if primary == "document_ir_missing":
        return "document_line_missing_or_weak"
    if primary == "name_mapping_missing":
        return "checkpoint_name_not_mapped"
    if primary == "evaluation_matching_granularity":
        return "positive_model_output_not_counted_by_f1"
    return "unknown"


def diagnose_false_negative(gold: GoldItem, blocks_by_line: dict[int, dict[str, Any]], runs: list[NBDRun]) -> dict[str, Any]:
    document = document_match(gold, blocks_by_line)
    block = document.get("block") if isinstance(document.get("block"), dict) else None
    document_text = str((block or {}).get("text") or "")
    coverage = float(document.get("coverage") or 0.0)
    document_status = str(document.get("status") or "missing_line")
    targets = target_runs_for_gold(gold, runs)

    candidate_hits: list[dict[str, Any]] = []
    prompt_statuses: list[dict[str, Any]] = []
    model_hits: list[dict[str, Any]] = []
    target_summaries: list[dict[str, Any]] = []
    for target in targets:
        run: NBDRun = target["run"]
        windows = candidate_windows_for_line(run, gold.line)
        model_candidates = model_candidates_for_line(run, gold.line)
        prompt_status = prompt_contains(run, gold, document_text)
        target_summaries.append(
            {
                "nbd_id": run.nbd_id,
                "title": run.title,
                "match_type": target["match_type"],
                "match_score": round(float(target["score"]), 4),
                "verdict": run.verdict,
                "candidate_window_count": len(run.windows),
                "target_line_in_candidates": bool(windows),
                "target_line_in_model_candidates": bool(model_candidates),
                "prompt": prompt_status,
            }
        )
        for window in windows:
            source = window.get("source") if isinstance(window.get("source"), dict) else {}
            candidate_hits.append(
                {
                    "nbd_id": run.nbd_id,
                    "title": run.title,
                    "window_id": window.get("window_id"),
                    "line_anchor": window.get("line_anchor"),
                    "window_type": window.get("window_type"),
                    "section_role": window.get("section_role"),
                    "score": window.get("score"),
                    "rank": source.get("selection_rank"),
                    "recall_quality": window.get("recall_quality"),
                    "recall_reason": window.get("recall_reason"),
                    "hit_words": window.get("hit_words"),
                    "excerpt": str(window.get("text") or "")[:240],
                }
            )
        for candidate in model_candidates:
            model_hits.append(
                {
                    "nbd_id": run.nbd_id,
                    "title": run.title,
                    "candidate": {
                        "line_anchor": candidate.get("line_anchor"),
                        "candidate_verdict": candidate.get("candidate_verdict"),
                        "reason": candidate.get("reason"),
                        "excerpt": str(candidate.get("excerpt") or "")[:240],
                    },
                }
            )
        prompt_statuses.append({"nbd_id": run.nbd_id, "prompt": prompt_status})

    reason = primary_reason(document_status, targets, candidate_hits, prompt_statuses, model_hits)
    secondary = secondary_reason(reason, candidate_hits, prompt_statuses, model_hits)
    return {
        "gold": asdict(gold),
        "primary_reason": reason,
        "secondary_reason": secondary,
        "document_ir": {
            "status": document_status,
            "coverage": round(coverage, 4),
            "line": gold.line,
            "matched_line": document.get("matched_line"),
            "block_id": (block or {}).get("block_id"),
            "block_type": (block or {}).get("block_type"),
            "section_role": (block or {}).get("section_role"),
            "text": document_text[:500],
        },
        "target_nbds": target_summaries,
        "candidate_hits": candidate_hits,
        "model_hits": model_hits,
    }


def load_false_negatives(metrics_path: Path) -> list[GoldItem]:
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    items: list[GoldItem] = []
    for row in payload.get("false_negatives", []):
        items.append(
            GoldItem(
                checkpoint_name=str(row.get("checkpoint_name") or ""),
                line=int(row.get("line") or 0),
                source_index=int(row.get("source_index") or 0),
                text=str(row.get("text") or ""),
            )
        )
    return items


def reason_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        reason = str(item.get("primary_reason") or "unknown")
        summary[reason] = summary.get(reason, 0) + 1
    return dict(sorted(summary.items()))


def secondary_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        reason = str(item.get("secondary_reason") or "unknown")
        summary[reason] = summary.get(reason, 0) + 1
    return dict(sorted(summary.items()))


def grouped_summary(items: list[dict[str, Any]], key_path: tuple[str, ...]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        value: Any = item
        for key in key_path:
            if not isinstance(value, dict):
                value = ""
                break
            value = value.get(key)
        label = str(value or "unknown")
        summary[label] = summary.get(label, 0) + 1
    return dict(sorted(summary.items(), key=lambda pair: (-pair[1], pair[0])))


def nbd_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        targets = item.get("target_nbds") or []
        if not targets:
            summary["unknown"] = summary.get("unknown", 0) + 1
            continue
        for target in targets:
            label = f"{target.get('nbd_id')} {target.get('title')}"
            summary[label] = summary.get(label, 0) + 1
    return dict(sorted(summary.items(), key=lambda pair: (-pair[1], pair[0])))


def line_bucket_summary(items: list[dict[str, Any]], bucket_size: int = 50) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        line = int((item.get("gold") or {}).get("line") or 0)
        start = ((line - 1) // bucket_size) * bucket_size + 1 if line > 0 else 0
        end = start + bucket_size - 1 if start else 0
        label = f"{start:04d}-{end:04d}" if start else "unknown"
        summary[label] = summary.get(label, 0) + 1
    return dict(sorted(summary.items(), key=lambda pair: pair[0]))


def write_markdown(path: Path, run_dir: Path, gold_path: Path, items: list[dict[str, Any]]) -> None:
    summary = reason_summary(items)
    secondary = secondary_summary(items)
    by_nbd = nbd_summary(items)
    by_role = grouped_summary(items, ("document_ir", "section_role"))
    by_bucket = line_bucket_summary(items)
    lines = [
        "# NBD F1 漏报归因诊断报告",
        "",
        f"- 运行目录：`{run_dir}`",
        f"- 标准答案：`{gold_path}`",
        f"- 漏报数量：{len(items)}",
        "",
        "## 归因统计",
        "",
        "| 归因类型 | 数量 |",
        "|---|---:|",
    ]
    for reason, count in summary.items():
        lines.append(f"| {reason} | {count} |")
    lines.extend(["", "## 二级归因统计", "", "| 二级归因 | 数量 |", "|---|---:|"])
    for reason, count in secondary.items():
        lines.append(f"| {reason} | {count} |")
    lines.extend(["", "## 按 NBD 聚合", "", "| NBD | 漏报数 |", "|---|---:|"])
    for label, count in list(by_nbd.items())[:30]:
        lines.append(f"| {label} | {count} |")
    lines.extend(["", "## 按 Document IR section_role 聚合", "", "| section_role | 漏报数 |", "|---|---:|"])
    for label, count in by_role.items():
        lines.append(f"| {label} | {count} |")
    lines.extend(["", "## 按行号区间聚合", "", "| 行号区间 | 漏报数 |", "|---|---:|"])
    for label, count in by_bucket.items():
        lines.append(f"| {label} | {count} |")
    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| # | 主归因 | 二级归因 | 审查点 | 行号 | Document IR | 目标 NBD | 候选 | 模型候选 |",
            "|---:|---|---|---|---:|---|---|---|---|",
        ]
    )
    for index, item in enumerate(items, start=1):
        gold = item["gold"]
        doc = item["document_ir"]
        targets = item.get("target_nbds") or []
        target_text = "<br>".join(
            f"{target['nbd_id']} {target['title']} ({target['match_type']}, {target['verdict']})"
            for target in targets[:3]
        ) or "未找到"
        candidate_text = "<br>".join(
            f"{hit['nbd_id']} {hit.get('line_anchor')} {hit.get('window_type')} {hit.get('section_role')} score={hit.get('score')} rank={hit.get('rank')} quality={hit.get('recall_quality')}"
            for hit in item.get("candidate_hits", [])[:3]
        ) or "未包含目标行"
        model_text = "<br>".join(
            f"{hit['nbd_id']} {hit['candidate'].get('line_anchor')} {hit['candidate'].get('candidate_verdict')}"
            for hit in item.get("model_hits", [])[:3]
        ) or "无目标行模型候选"
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    str(item.get("primary_reason")),
                    str(item.get("secondary_reason")),
                    str(gold.get("checkpoint_name")),
                    str(gold.get("line")),
                    f"{doc.get('status')} / {doc.get('coverage')}",
                    target_text,
                    candidate_text,
                    model_text,
                ]
            )
            + " |"
        )
    lines.extend(["", "## 下一步建议", ""])
    if summary.get("candidate_missing"):
        lines.append("- `candidate_missing`：先按二级归因处理。`no_candidate_window_for_target_line` 需要补 NBD recall；`prompt_contains_*_but_not_candidate` 需要检查候选分层、prompt 拼装和评测读取口径。")
    if summary.get("model_conservative"):
        lines.append("- `model_conservative`：优先补强 NBD SOP 和 prompt 判定边界。")
    if summary.get("name_mapping_missing"):
        lines.append("- `name_mapping_missing`：进入评测别名层处理，不进入 runtime。")
    if summary.get("document_ir_missing") or summary.get("weak_text_match"):
        lines.append("- `document_ir_missing` / `weak_text_match`：进入 document_compiler 回归。")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="诊断 NBD F1 漏报卡在 Document IR、候选窗口、prompt 还是模型判定")
    parser.add_argument("--gold-json", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--metrics-json", type=Path, help="默认读取 run-dir/evaluation/metrics.json")
    parser.add_argument("--output-dir", type=Path, help="默认写入 run-dir/evaluation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_diagnosis(args)


def run_diagnosis(args: argparse.Namespace) -> None:
    run_dir = args.run_dir.resolve()
    gold_path = args.gold_json.resolve()
    metrics_path = (args.metrics_json or (run_dir / "evaluation" / "metrics.json")).resolve()
    output_dir = (args.output_dir or (run_dir / "evaluation")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Validate the gold can be loaded even though false negatives come from metrics.json.
    load_gold(gold_path)
    blocks = load_document_blocks(run_dir)
    runs = load_nbd_runs(run_dir)
    false_negatives = load_false_negatives(metrics_path)
    diagnoses = [diagnose_false_negative(item, blocks, runs) for item in false_negatives]
    payload = {
        "gold_file": str(gold_path),
        "run_dir": str(run_dir),
        "metrics_file": str(metrics_path),
        "false_negative_total": len(diagnoses),
        "reason_summary": reason_summary(diagnoses),
        "secondary_reason_summary": secondary_summary(diagnoses),
        "nbd_summary": nbd_summary(diagnoses),
        "section_role_summary": grouped_summary(diagnoses, ("document_ir", "section_role")),
        "line_bucket_summary": line_bucket_summary(diagnoses),
        "items": diagnoses,
    }
    (output_dir / "diagnosis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(output_dir / "diagnosis.md", run_dir, gold_path, diagnoses)
    print(f"false_negative_total={len(diagnoses)}")
    for reason, count in payload["reason_summary"].items():
        print(f"{reason}={count}")
    for reason, count in payload["secondary_reason_summary"].items():
        print(f"secondary.{reason}={count}")
    print(output_dir)


if __name__ == "__main__":
    main()
