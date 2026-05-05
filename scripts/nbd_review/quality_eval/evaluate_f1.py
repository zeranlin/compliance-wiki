#!/usr/bin/env python3
"""Evaluate NBD run output against line/checkpoint gold answers."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


POSITIVE_VERDICTS = {"命中"}
NEW_CHECKPOINT_RE = re.compile(r"[（(]\s*新增\s*[）)]")
CHECKPOINT_TITLE_CACHE: list[str] | None = None
CHECKPOINT_SEPARATOR_CHARS = set(",，;；、")
BLOCKING_QUALITY_CODES = {
    "invalid_json_recovered",
    "positive_verdict_without_candidate",
    "candidate_id_missing",
    "candidate_id_not_found",
    "candidate_line_anchor_missing",
    "candidate_line_anchor_not_found",
    "candidate_excerpt_missing",
}


@dataclass(frozen=True)
class GoldItem:
    checkpoint_name: str
    line: int
    source_index: int
    text: str = ""


@dataclass(frozen=True)
class PredItem:
    checkpoint_name: str
    line_anchor: str
    source_file: str
    nbd_id: str = ""
    verdict: str = ""
    excerpt: str = ""

    @property
    def line_range(self) -> tuple[int, int] | None:
        return parse_line_anchor(self.line_anchor)


@dataclass
class MatchItem:
    checkpoint_name: str
    gold_line: int
    pred_line_anchor: str
    pred_source_file: str
    nbd_id: str = ""
    pred_checkpoint_name: str = ""
    name_match_type: str = ""
    name_match_score: float = 0.0


def normalize_name(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"^NBD\d{2}-\d{3}\s*", "", text)
    text = text.replace("/", "-")
    text = text.replace("必须", "需").replace("须", "需")
    return re.sub(r"[\s，。、；;：:“”‘’（）()\[\]【】《》<>.,\-_/]+", "", text)


def name_match_info(gold_name: str, pred_name: str) -> tuple[bool, str, float]:
    """Return evaluation-only checkpoint title matching result.

    The gold JSON sometimes splits one NBD title into two short names, while
    the runtime output keeps the full NBD title.  Only exact and containment
    matching are accepted here; broader fuzzy matching stays in diagnosis.
    """
    gold = normalize_name(gold_name)
    pred = normalize_name(pred_name)
    if not gold or not pred:
        return False, "none", 0.0
    if gold == pred:
        return True, "exact", 1.0
    if gold in pred or pred in gold:
        shorter = min(len(gold), len(pred))
        longer = max(len(gold), len(pred))
        score = 0.72 + 0.2 * (shorter / longer)
        return True, "contains", round(score, 4)
    return False, "none", 0.0


def default_checkpoint_title_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "wiki" / "bd-review-points" / "items"


def load_checkpoint_titles(title_dir: Path | None = None) -> list[str]:
    global CHECKPOINT_TITLE_CACHE
    if title_dir is None and CHECKPOINT_TITLE_CACHE is not None:
        return CHECKPOINT_TITLE_CACHE
    base = title_dir or default_checkpoint_title_dir()
    titles: list[str] = []
    if base.exists():
        for path in sorted(base.glob("NBD*.md")):
            text = path.read_text(encoding="utf-8")
            match = re.search(r"^title:\s*(.+)$", text, flags=re.M)
            if match:
                title = match.group(1).strip().strip('"')
                if title:
                    titles.append(title)
    titles = sorted(set(titles), key=len, reverse=True)
    if title_dir is None:
        CHECKPOINT_TITLE_CACHE = titles
    return titles


def split_checkpoint_names_by_titles(value: str, titles: list[str]) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    names: list[str] = []
    pos = 0
    while pos < len(text):
        while pos < len(text) and (text[pos].isspace() or text[pos] in CHECKPOINT_SEPARATOR_CHARS):
            pos += 1
        if pos >= len(text):
            break
        matched = next((title for title in titles if text.startswith(title, pos)), "")
        if matched:
            names.append(matched)
            pos += len(matched)
            continue
        next_start = len(text)
        for idx in range(pos + 1, len(text)):
            if text[idx] not in CHECKPOINT_SEPARATOR_CHARS:
                continue
            probe = idx + 1
            while probe < len(text) and (text[probe].isspace() or text[probe] in CHECKPOINT_SEPARATOR_CHARS):
                probe += 1
            if any(text.startswith(title, probe) for title in titles):
                next_start = idx
                break
        segment = text[pos:next_start].strip(" \t\r\n,，;；、")
        if segment:
            names.append(segment)
        pos = next_start + 1 if next_start < len(text) else next_start
    return names or [text]


def split_checkpoint_names(value: str) -> list[str]:
    titles = load_checkpoint_titles()
    if titles:
        return split_checkpoint_names_by_titles(value, titles)
    text = str(value or "").strip()
    return [text] if text else []


def is_ignored_gold_checkpoint(value: str) -> bool:
    return bool(NEW_CHECKPOINT_RE.search(str(value or "")))


def parse_line_anchor(value: Any) -> tuple[int, int] | None:
    if isinstance(value, int):
        return value, value
    text = str(value or "").strip()
    if not text:
        return None
    numbers = [int(item) for item in re.findall(r"\d+", text)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    start, end = numbers[0], numbers[1]
    if start > end:
        start, end = end, start
    return start, end


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def has_blocking_quality_flag(data: dict[str, Any], model_result: dict[str, Any]) -> bool:
    """Skip structurally invalid positive outputs in F1.

    F1 evaluates line-level findings. A positive verdict that the runtime has
    already flagged as invalid JSON, missing candidate, missing line anchor, or
    otherwise non-actionable should not enter the precision denominator as a
    business hit. This is a generic output-quality gate, not an NBD rule.
    """
    flags = data.get("quality_flags")
    if not isinstance(flags, list):
        flags = model_result.get("quality_flags")
    if not isinstance(flags, list):
        return False
    return any(isinstance(flag, dict) and flag.get("code") in BLOCKING_QUALITY_CODES for flag in flags)


def load_gold_with_ignored(path: Path) -> tuple[list[GoldItem], list[GoldItem]]:
    data = load_json(path)
    rows = data.get("检查结果") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"cannot find gold list in {path}")
    items: list[GoldItem] = []
    ignored_items: list[GoldItem] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("审查点名称") or row.get("checkpoint_name") or "").strip()
        line_range = parse_line_anchor(row.get("行号") or row.get("line") or row.get("line_no"))
        if not raw_name or not line_range:
            continue
        line = line_range[0]
        text = str(row.get("风险原文") or row.get("text") or "")
        for name in split_checkpoint_names(raw_name):
            item = GoldItem(checkpoint_name=name, line=line, source_index=index, text=text)
            if is_ignored_gold_checkpoint(name):
                ignored_items.append(item)
            else:
                items.append(item)
    return items, ignored_items


def load_gold(path: Path) -> list[GoldItem]:
    items, _ignored_items = load_gold_with_ignored(path)
    return items


def normalize_evidence_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def load_document_line_texts(run_dir: Path) -> dict[int, str]:
    document_ir = run_dir / "document-ir.json"
    if not document_ir.exists():
        return {}
    payload = load_json(document_ir)
    blocks = payload.get("blocks") if isinstance(payload, dict) else []
    if not isinstance(blocks, list):
        return {}
    lines: dict[int, str] = {}
    for block in blocks:
        if not isinstance(block, dict):
            continue
        start = block.get("line_start")
        end = block.get("line_end")
        text = str(block.get("text") or "")
        if not isinstance(start, int) or not isinstance(end, int) or not text:
            continue
        for line_no in range(start, end + 1):
            lines.setdefault(line_no, text)
    return lines


def text_matches_gold(gold_text: str, document_text: str) -> bool:
    gold = normalize_evidence_text(gold_text)
    document = normalize_evidence_text(document_text)
    if not gold or not document:
        return False
    if gold in document or document in gold:
        return True
    if len(gold) >= 12 and gold[:12] in document:
        return True
    return len(gold) >= 16 and gold[-16:] in document


def gold_line_health(gold_items: list[GoldItem], run_dir: Path, radius: int = 3) -> dict[str, Any]:
    document_lines = load_document_line_texts(run_dir)
    text_items = [item for item in gold_items if item.text.strip()]
    if not document_lines or not text_items:
        return {"available": False, "reason": "document_ir_or_gold_text_missing", "checked_total": len(text_items)}

    exact = 0
    offset_hits: dict[int, int] = {offset: 0 for offset in range(-radius, radius + 1) if offset}
    missing = 0
    examples: list[dict[str, Any]] = []
    for item in text_items:
        if text_matches_gold(item.text, document_lines.get(item.line, "")):
            exact += 1
            continue
        matched_offset: int | None = None
        for offset in range(-radius, radius + 1):
            if offset == 0:
                continue
            if text_matches_gold(item.text, document_lines.get(item.line + offset, "")):
                matched_offset = offset
                offset_hits[offset] += 1
                break
        if matched_offset is None:
            missing += 1
            if len(examples) < 8:
                examples.append(
                    {
                        "checkpoint_name": item.checkpoint_name,
                        "gold_line": item.line,
                        "status": "not_found_nearby",
                    }
                )
        elif len(examples) < 8:
            examples.append(
                {
                    "checkpoint_name": item.checkpoint_name,
                    "gold_line": item.line,
                    "matched_document_line": item.line + matched_offset,
                    "offset": matched_offset,
                    "status": "offset_match",
                }
            )

    checked_total = len(text_items)
    dominant_offset = 0
    dominant_count = 0
    if offset_hits:
        dominant_offset, dominant_count = max(offset_hits.items(), key=lambda pair: pair[1])
        if dominant_count == 0:
            dominant_offset = 0
    exact_ratio = exact / checked_total if checked_total else 0.0
    dominant_offset_ratio = dominant_count / checked_total if checked_total else 0.0
    status = "ok"
    if exact_ratio < 0.6 and dominant_offset_ratio >= 0.3:
        status = "suspected_global_offset"
    elif exact_ratio < 0.6:
        status = "weak_alignment"
    return {
        "available": True,
        "status": status,
        "checked_total": checked_total,
        "exact_text_match_total": exact,
        "exact_text_match_ratio": exact_ratio,
        "offset_hits": {str(key): value for key, value in offset_hits.items() if value},
        "dominant_offset": dominant_offset,
        "dominant_offset_match_total": dominant_count,
        "dominant_offset_match_ratio": dominant_offset_ratio,
        "not_found_nearby_total": missing,
        "examples": examples,
    }


def iter_result_files(run_dir: Path) -> list[Path]:
    items_dir = run_dir / "items"
    if items_dir.exists():
        return sorted(items_dir.glob("*/result.json"))
    return sorted(run_dir.glob("**/result.json"))


def candidate_to_pred(
    result_file: Path,
    model_result: dict[str, Any],
    nbd_meta: dict[str, Any],
    candidate: dict[str, Any],
) -> PredItem | None:
    line_anchor = str(candidate.get("line_anchor") or candidate.get("line") or "").strip()
    if not line_anchor:
        return None
    title = (
        model_result.get("nbd_title")
        or model_result.get("checkpoint_title")
        or nbd_meta.get("title")
        or ""
    )
    return PredItem(
        checkpoint_name=str(title),
        line_anchor=line_anchor,
        source_file=str(result_file),
        nbd_id=str(model_result.get("nbd_id") or nbd_meta.get("id") or ""),
        verdict=str(candidate.get("candidate_verdict") or model_result.get("verdict") or ""),
        excerpt=str(candidate.get("excerpt") or ""),
    )


def load_predictions(run_dir: Path, positive_verdicts: set[str]) -> tuple[list[PredItem], list[PredItem]]:
    predictions: list[PredItem] = []
    no_line_predictions: list[PredItem] = []
    for result_file in iter_result_files(run_dir):
        data = load_json(result_file)
        if not isinstance(data, dict):
            continue
        model_result = data.get("model_result") or {}
        nbd_meta = data.get("nbd") or {}
        if not isinstance(model_result, dict):
            continue
        verdict = str(model_result.get("verdict") or "").strip()
        if verdict not in positive_verdicts:
            continue
        if has_blocking_quality_flag(data, model_result):
            continue
        candidates = model_result.get("candidates")
        hit_candidates = []
        if isinstance(candidates, list):
            hit_candidates = [
                item for item in candidates
                if isinstance(item, dict)
                and str(item.get("candidate_verdict") or verdict).strip() in positive_verdicts
            ]
        for candidate in hit_candidates:
            pred = candidate_to_pred(result_file, model_result, nbd_meta, candidate)
            if pred:
                predictions.append(pred)
        if not hit_candidates:
            title = model_result.get("nbd_title") or model_result.get("checkpoint_title") or nbd_meta.get("title") or ""
            no_line_predictions.append(
                PredItem(
                    checkpoint_name=str(title),
                    line_anchor="",
                    source_file=str(result_file),
                    nbd_id=str(model_result.get("nbd_id") or nbd_meta.get("id") or ""),
                    verdict=verdict,
                    excerpt=str(model_result.get("summary") or ""),
                )
            )
    return predictions, no_line_predictions


def is_line_match(gold: GoldItem, pred: PredItem, line_match: str) -> bool:
    pred_range = pred.line_range
    if not pred_range:
        return False
    start, end = pred_range
    if line_match == "exact":
        return start == end == gold.line
    return start <= gold.line <= end


def match_items(gold_items: list[GoldItem], pred_items: list[PredItem], line_match: str) -> list[MatchItem]:
    used_pred: set[int] = set()
    matches: list[MatchItem] = []
    for gold in gold_items:
        best_index: int | None = None
        best_width: int | None = None
        best_name_match: tuple[str, float] = ("", 0.0)
        for index, pred in enumerate(pred_items):
            if index in used_pred:
                continue
            is_name_match, name_match_type, name_score = name_match_info(gold.checkpoint_name, pred.checkpoint_name)
            if not is_name_match:
                continue
            if not is_line_match(gold, pred, line_match):
                continue
            start, end = pred.line_range or (0, 0)
            width = end - start
            if best_width is None or width < best_width or (width == best_width and name_score > best_name_match[1]):
                best_index = index
                best_width = width
                best_name_match = (name_match_type, name_score)
        if best_index is None:
            continue
        used_pred.add(best_index)
        pred = pred_items[best_index]
        matches.append(
            MatchItem(
                checkpoint_name=gold.checkpoint_name,
                gold_line=gold.line,
                pred_line_anchor=pred.line_anchor,
                pred_source_file=pred.source_file,
                nbd_id=pred.nbd_id,
                pred_checkpoint_name=pred.checkpoint_name,
                name_match_type=best_name_match[0],
                name_match_score=best_name_match[1],
            )
        )
    return matches


def compute_metrics(gold_total: int, pred_total: int, match_total: int) -> dict[str, float]:
    recall = match_total / gold_total if gold_total else 0.0
    precision = match_total / pred_total if pred_total else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    return {"recall": recall, "precision": precision, "f1": f1}


def write_report(
    output_dir: Path,
    gold_path: Path,
    run_dir: Path,
    gold_items: list[GoldItem],
    pred_items: list[PredItem],
    no_line_predictions: list[PredItem],
    matches: list[MatchItem],
    line_match: str,
    ignored_gold_items: list[GoldItem] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ignored_gold_items = ignored_gold_items or []
    matched_gold = {(item.checkpoint_name, item.gold_line) for item in matches}
    matched_pred_sources = {(item.pred_source_file, item.pred_line_anchor, item.nbd_id) for item in matches}
    false_negatives = [
        item for item in gold_items
        if (item.checkpoint_name, item.line) not in matched_gold
    ]
    false_positives = [
        item for item in pred_items
        if (item.source_file, item.line_anchor, item.nbd_id) not in matched_pred_sources
    ]
    pred_total = len(pred_items) + len(no_line_predictions)
    metrics = compute_metrics(len(gold_items), pred_total, len(matches))
    health = gold_line_health(gold_items, run_dir)
    summary = {
        "gold_file": str(gold_path),
        "run_dir": str(run_dir),
        "line_match": line_match,
        "gold_line_health": health,
        "gold_total": len(gold_items),
        "ignored_gold_total": len(ignored_gold_items),
        "pred_total": pred_total,
        "pred_with_line": len(pred_items),
        "pred_without_line": len(no_line_predictions),
        "match_total": len(matches),
        **metrics,
        "matches": [asdict(item) for item in matches],
        "false_negatives": [asdict(item) for item in false_negatives],
        "false_positives": [asdict(item) for item in false_positives],
        "no_line_predictions": [asdict(item) for item in no_line_predictions],
        "ignored_gold_items": [asdict(item) for item in ignored_gold_items],
    }
    (output_dir / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    recall = metrics["recall"]
    precision = metrics["precision"]
    f1 = metrics["f1"]
    lines = [
        "# NBD F1 评测报告",
        "",
        f"- 标准答案：`{gold_path}`",
        f"- 工程结果：`{run_dir}`",
        f"- 行号匹配：`{line_match}`",
        f"- F1 标准答案数：{len(gold_items)}。过滤掉名称中带“（新增）”或“(新增)”的审查点后，当前评测共有 {len(gold_items)} 个标准答案 `(审查点名称, 行号)` 对参与评测。",
        f"- F1 忽略新增审查点数：{len(ignored_gold_items)}。该 {len(ignored_gold_items)} 项不属于当前 NBD 覆盖范围，按评测口径视为标准答案中没有这些记录。",
        f"- F1 工程命中输出数：{pred_total}。模型输出并进入精确率分母的命中结果共 {pred_total} 条；该指标只统计“命中”结果，不统计“待人工复核”。",
        f"- F1 带行号命中输出数：{len(pred_items)}。该 {len(pred_items)} 条可直接参与行号匹配。",
        f"- F1 缺少行号命中输出数：{len(no_line_predictions)}。该 {len(no_line_predictions)} 条虽然模型判定为命中，但没有结构化行号，不能与标准答案形成行号级匹配。",
        f"- F1 匹配成功数：{len(matches)}。共有 {len(matches)} 条工程输出与标准答案在审查点名称和行号范围上匹配成功。",
        f"- 召回率：{recall:.4f}。计算公式为 `F1 匹配成功数 / F1 标准答案数 = {len(matches)} / {len(gold_items)} = {recall:.4f}`，表示标准答案中的风险点找回了 {recall:.2%}。",
        f"- 精确率：{precision:.4f}。计算公式为 `F1 匹配成功数 / F1 工程命中输出数 = {len(matches)} / {pred_total} = {precision:.4f}`，表示工程输出的命中结果中有 {precision:.2%} 与标准答案一致。",
        f"- F1 值：{f1:.4f}。计算公式为 `2 * 召回率 * 精确率 / (召回率 + 精确率) = 2 * {recall:.4f} * {precision:.4f} / ({recall:.4f} + {precision:.4f}) = {f1:.4f}`，表示召回率和精确率的综合水平。",
        "",
        "## 金标行号健康检查",
        "",
    ]
    if not health.get("available"):
        lines.append("- 未执行：缺少 Document IR 或标准答案风险原文，无法判断金标行号是否与当前 Document IR 对齐。")
    else:
        lines.extend(
            [
                f"- 检查条数：{health['checked_total']}。",
                f"- 原行号文本匹配数：{health['exact_text_match_total']}，匹配率：{health['exact_text_match_ratio']:.4f}。",
                f"- 主偏移量：{health['dominant_offset']}，偏移匹配数：{health['dominant_offset_match_total']}，偏移匹配率：{health['dominant_offset_match_ratio']:.4f}。",
                f"- 附近未找到原文数：{health['not_found_nearby_total']}。",
            ]
        )
        if health.get("status") == "suspected_global_offset":
            lines.append("- 结论：疑似金标行号与当前 Document IR 存在整体偏移；本轮 F1 可能低估工程效果，应优先校准金标或使用已校准 V2。")
        elif health.get("status") == "weak_alignment":
            lines.append("- 结论：金标行号与当前 Document IR 对齐较弱；需人工复核金标行号口径。")
        else:
            lines.append("- 结论：金标行号与当前 Document IR 基本对齐。")
        examples = health.get("examples") or []
        if examples:
            lines.extend(["", "| 审查点名称 | 标准行号 | 匹配行号 | 偏移 | 状态 |", "|---|---:|---:|---:|---|"])
            for item in examples[:8]:
                lines.append(
                    f"| {item.get('checkpoint_name', '')} | {item.get('gold_line', '')} | {item.get('matched_document_line', '')} | {item.get('offset', '')} | {item.get('status', '')} |"
                )
    lines.extend([
        "",
        "## 指标结论",
        "",
        f"当前评测 F1 标准答案数为 {len(gold_items)}，工程命中输出数为 {pred_total}，匹配成功数为 {len(matches)}。召回率为 {recall:.4f}，精确率为 {precision:.4f}，F1 值为 {f1:.4f}。",
        "",
        "## 匹配项",
        "",
        "| 审查点名称 | 标准行号 | 预测行号 | NBD |",
        "|---|---:|---|---|",
    ])
    for item in matches:
        lines.append(f"| {item.checkpoint_name} | {item.gold_line} | {item.pred_line_anchor} | {item.nbd_id} |")
    lines.extend(["", "## 漏报", "", "| 审查点名称 | 标准行号 |", "|---|---:|"])
    for item in false_negatives:
        lines.append(f"| {item.checkpoint_name} | {item.line} |")
    lines.extend(["", "## 误报", "", "| 审查点名称 | 预测行号 | NBD |", "|---|---|---|"])
    for item in false_positives:
        lines.append(f"| {item.checkpoint_name} | {item.line_anchor} | {item.nbd_id} |")
    if no_line_predictions:
        lines.extend(["", "## 缺少行号的命中输出", "", "| 审查点名称 | NBD |", "|---|---|"])
        for item in no_line_predictions:
            lines.append(f"| {item.checkpoint_name} | {item.nbd_id} |")
    if ignored_gold_items:
        lines.extend(["", "## 已忽略的新增审查点", "", "| 审查点名称 | 标准行号 |", "|---|---:|"])
        for item in ignored_gold_items:
            lines.append(f"| {item.checkpoint_name} | {item.line} |")
    (output_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="统计 NBD 审查结果相对标准答案的召回率、精确率和 F1")
    parser.add_argument("--gold-json", required=True, type=Path, help="标准答案 JSON")
    parser.add_argument("--run-dir", required=True, type=Path, help="NBD CLI 输出目录")
    parser.add_argument("--output-dir", type=Path, help="评测结果输出目录")
    parser.add_argument("--line-match", choices=["range", "exact"], default="range", help="预测为范围行号时的匹配方式")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold_path = args.gold_json.resolve()
    run_dir = args.run_dir.resolve()
    output_dir = (args.output_dir or (run_dir / "evaluation")).resolve()
    gold_items, ignored_gold_items = load_gold_with_ignored(gold_path)
    pred_items, no_line_predictions = load_predictions(run_dir, POSITIVE_VERDICTS)
    matches = match_items(gold_items, pred_items, args.line_match)
    write_report(output_dir, gold_path, run_dir, gold_items, pred_items, no_line_predictions, matches, args.line_match, ignored_gold_items)
    pred_total = len(pred_items) + len(no_line_predictions)
    metrics = compute_metrics(len(gold_items), pred_total, len(matches))
    print(f"gold_total={len(gold_items)}")
    print(f"ignored_gold_total={len(ignored_gold_items)}")
    print(f"pred_total={pred_total}")
    print(f"match_total={len(matches)}")
    print(f"recall={metrics['recall']:.4f}")
    print(f"precision={metrics['precision']:.4f}")
    print(f"f1={metrics['f1']:.4f}")
    print(output_dir)


if __name__ == "__main__":
    main()
