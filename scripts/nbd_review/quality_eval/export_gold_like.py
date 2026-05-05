#!/usr/bin/env python3
"""Export NBD hit results in a gold-answer-like JSON shape."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quality_eval.evaluate_f1 import POSITIVE_VERDICTS, iter_result_files, parse_line_anchor


BLOCKING_QUALITY_CODES = {
    "invalid_json_recovered",
    "positive_verdict_without_candidate",
    "candidate_id_missing",
    "candidate_id_not_found",
    "candidate_line_anchor_missing",
    "candidate_line_anchor_not_found",
    "candidate_excerpt_missing",
}


def has_blocking_quality_flag(data: dict[str, Any], model_result: dict[str, Any]) -> bool:
    flags = data.get("quality_flags")
    if not isinstance(flags, list):
        flags = model_result.get("quality_flags")
    if not isinstance(flags, list):
        return False
    return any(isinstance(flag, dict) and flag.get("code") in BLOCKING_QUALITY_CODES for flag in flags)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_document_lines(run_dir: Path) -> dict[int, str]:
    document_ir = run_dir / "document-ir.json"
    if not document_ir.exists():
        return {}
    data = load_json(document_ir)
    lines: dict[int, str] = {}
    for block in data.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        start = block.get("line_start")
        end = block.get("line_end")
        text = str(block.get("text") or "").strip()
        if isinstance(start, int) and isinstance(end, int) and text:
            for line_no in range(start, end + 1):
                lines.setdefault(line_no, text)
    return lines


def load_source_file(run_dir: Path) -> str:
    document_ir = run_dir / "document-ir.json"
    if document_ir.exists():
        data = load_json(document_ir)
        source_file = data.get("source_file")
        if source_file:
            return str(source_file)
    run_json = run_dir / "run.json"
    if run_json.exists():
        data = load_json(run_json)
        source_file = data.get("review_file") or data.get("source_file")
        if source_file:
            return str(source_file)
    return ""


def candidate_rows(
    result_file: Path,
    model_result: dict[str, Any],
    nbd_meta: dict[str, Any],
    document_lines: dict[int, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    title = str(
        model_result.get("nbd_title")
        or model_result.get("checkpoint_title")
        or nbd_meta.get("title")
        or ""
    ).strip()
    nbd_id = str(model_result.get("nbd_id") or nbd_meta.get("id") or "").strip()
    candidates = model_result.get("candidates")
    hit_candidates = []
    if isinstance(candidates, list):
        hit_candidates = [
            item for item in candidates
            if isinstance(item, dict)
            and str(item.get("candidate_verdict") or model_result.get("verdict") or "").strip() in POSITIVE_VERDICTS
        ]

    for candidate in hit_candidates:
        line_anchor = str(candidate.get("line_anchor") or candidate.get("line") or "").strip()
        line_range = parse_line_anchor(line_anchor)
        line_no = line_range[0] if line_range else None
        excerpt = str(candidate.get("excerpt") or "").strip()
        rows.append(
            {
                "行号": line_no,
                "预测行号": line_anchor,
                "风险原文": excerpt or (document_lines.get(line_no or -1, "") if line_no is not None else ""),
                "审查点名称": title,
                "违规原因": str(candidate.get("reason") or model_result.get("summary") or "").strip(),
                "风险提示": str(model_result.get("risk_tip") or "").strip(),
                "修改建议": str(model_result.get("revision_suggestion") or "").strip(),
                "NBD": nbd_id,
                "结果来源": str(result_file),
            }
        )
    return rows


def no_line_row(result_file: Path, model_result: dict[str, Any], nbd_meta: dict[str, Any]) -> dict[str, Any]:
    title = str(
        model_result.get("nbd_title")
        or model_result.get("checkpoint_title")
        or nbd_meta.get("title")
        or ""
    ).strip()
    nbd_id = str(model_result.get("nbd_id") or nbd_meta.get("id") or "").strip()
    return {
        "行号": None,
        "预测行号": "",
        "风险原文": "",
        "审查点名称": title,
        "违规原因": str(model_result.get("summary") or "").strip(),
        "风险提示": str(model_result.get("risk_tip") or "").strip(),
        "修改建议": str(model_result.get("revision_suggestion") or "").strip(),
        "NBD": nbd_id,
        "结果来源": str(result_file),
    }


def build_gold_like(run_dir: Path, include_no_line: bool) -> dict[str, Any]:
    document_lines = load_document_lines(run_dir)
    rows: list[dict[str, Any]] = []
    for result_file in iter_result_files(run_dir):
        data = load_json(result_file)
        if not isinstance(data, dict):
            continue
        model_result = data.get("model_result") or {}
        nbd_meta = data.get("nbd") or {}
        if not isinstance(model_result, dict):
            continue
        verdict = str(model_result.get("verdict") or "").strip()
        if verdict not in POSITIVE_VERDICTS:
            continue
        if has_blocking_quality_flag(data, model_result):
            continue
        current_rows = candidate_rows(result_file, model_result, nbd_meta, document_lines)
        if current_rows:
            rows.extend(current_rows)
        elif include_no_line:
            rows.append(no_line_row(result_file, model_result, nbd_meta))

    rows.sort(key=lambda item: ((item.get("行号") is None), item.get("行号") or 10**9, item.get("NBD") or ""))
    return {
        "源文件": load_source_file(run_dir),
        "行号口径": "按 Document IR 行号导出；命中结果按候选窗口展开为行号级记录；仅关注行号和审查点名称时，可使用“行号/预测行号/审查点名称”字段对比。",
        "导出口径": {
            "结果范围": "仅导出模型结论为“命中”的 NBD 结果",
            "是否包含无行号命中": include_no_line,
            "记录粒度": "一个命中候选窗口导出一条记录",
        },
        "检查结果": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 NBD 命中结果导出为接近标准答案格式的 JSON")
    parser.add_argument("--run-dir", required=True, type=Path, help="NBD CLI 输出目录")
    parser.add_argument("--output", type=Path, help="输出 JSON 路径")
    parser.add_argument("--include-no-line", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    output = args.output or (run_dir / "evaluation" / "工程审查结果_按标准答案格式.json")
    data = build_gold_like(run_dir, include_no_line=args.include_no_line)
    write_json(output.resolve(), data)
    print(output.resolve())
    print(f"exported={len(data['检查结果'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
