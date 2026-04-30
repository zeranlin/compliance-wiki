"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from schemas import CANDIDATE_SET_SCHEMA, CANDIDATE_WINDOW_SCHEMA, CandidateWindow, DocumentBlock, NBDItem, SECTION_ROLE_PRIORITY
from utils import compact, looks_like_heading, normalize_key, read_text, relative_path, run_path, write_text

SUPPORT_SECTION_ROLES = {"catalog", "common_terms", "bid_format", "contract_template", "template_support", "policy_support"}
PRIMARY_BOOST_SECTION_ROLES = {
    "user_requirement",
    "technical_primary",
    "business_terms",
    "business_primary",
    "qualification",
    "qualification_primary",
    "scoring",
    "scoring_primary",
    "announcement",
    "contract_primary",
    "sample_requirement",
}
QUALIFICATION_SECTION_ROLES = {"announcement", "qualification", "qualification_primary"}
SCORING_SECTION_ROLES = {"scoring", "scoring_primary"}
BUSINESS_SECTION_ROLES = {"business_terms", "business_primary", "contract_primary"}

def group_words(keyword_groups: dict[str, list[str]], *parts: str) -> list[str]:
    words: list[str] = []
    for group_name, values in keyword_groups.items():
        if any(part in group_name for part in parts):
            words.extend(values)
    return words


def hit_words(text: str, words: list[str]) -> list[str]:
    ctext = compact(text)
    return sorted({word for word in words if word and word in ctext})


def score_block(block: DocumentBlock, item: NBDItem) -> tuple[float, dict[str, list[str]], list[str]]:
    groups = item.keyword_groups
    ctext = compact(block.text)
    hits = {name: hit_words(block.text, words) for name, words in groups.items()}
    total_hits = sum(len(values) for values in hits.values())
    if not total_hits:
        return 0.0, hits, []

    object_hits = hit_words(block.text, group_words(groups, "对象", "审查对象"))
    action_hits = hit_words(block.text, group_words(groups, "行为", "限制", "门槛", "模式"))
    consequence_hits = hit_words(block.text, group_words(groups, "后果"))
    section_hits = hit_words(block.text, group_words(groups, "章节", "角色", "必召"))

    synthetic_hits: list[str] = []
    if re.search(r"得\d+(?:\.\d+)?分|不得分|加\d+(?:\.\d+)?分|权重", ctext):
        synthetic_hits.append("评分/权重结构")
    if re.search(r"投标无效|资格审查不通过|响应无效", ctext):
        synthetic_hits.append("资格/响应后果")
    if synthetic_hits:
        hits["结构后果词"] = synthetic_hits

    score = float(total_hits)
    has_object_profile = bool(group_words(groups, "对象", "审查对象"))
    if has_object_profile and not object_hits and total_hits <= 2:
        return 0.0, hits, []
    if has_object_profile and not object_hits:
        score -= 5
    if object_hits and action_hits:
        score += 8
    if object_hits and consequence_hits:
        score += 8
    if object_hits and synthetic_hits:
        score += 8
    if section_hits and object_hits:
        score += 5
    if block.section_role == "qualification_primary" and object_hits:
        score += 14
        if action_hits or consequence_hits:
            score += 8
    if block.section_role == "scoring_primary" and object_hits:
        score += 6
    if block.block_type == "table":
        score += 2
    score += SECTION_ROLE_PRIORITY.get(block.section_role, 3) * max(block.section_role_confidence, 0.2)
    if block.section_role in SUPPORT_SECTION_ROLES:
        score -= 4 if block.section_role == "catalog" else 2

    reasons = []
    for name, values in hits.items():
        if values:
            reasons.append(f"{name}=" + "、".join(values[:8]))
    if block.section_role != "unknown":
        reasons.append(f"section_role={block.section_role}({block.section_role_confidence})")
    return max(score, 0.0), hits, reasons


def profile_hits(block: DocumentBlock, item: NBDItem) -> list[str]:
    profile = item.recall_profile
    if not profile or not profile.get("enabled", True):
        return []
    ctext = compact(block.text)
    return sorted({term for term in profile.get("terms", []) if term and term in ctext})


def profile_score(block: DocumentBlock, item: NBDItem, hits: list[str], reason: str) -> float:
    profile = item.recall_profile or {}
    score = 6.0 + min(len(hits), 5)
    score += SECTION_ROLE_PRIORITY.get(block.section_role, 3) * max(block.section_role_confidence, 0.2) * 0.8
    if block.section_role in PRIMARY_BOOST_SECTION_ROLES:
        score += 5
    if block.section_role == "qualification_primary":
        score += 10
    if block.section_role == "scoring_primary":
        score += 6
    if block.section_role in SUPPORT_SECTION_ROLES:
        score -= 2
    formal_hits = [term for term in profile.get("formal_terms", []) if term in hits]
    noise_hits = [term for term in profile.get("noise_terms", []) if term and term in compact(block.text)]
    if formal_hits:
        max_formal_len = max((len(term) for term in formal_hits), default=0)
        score += 24 + min(len(formal_hits), 4) * 4 + min(max_formal_len, 20) * 0.4
    if noise_hits and not formal_hits:
        score -= 8 + min(len(noise_hits), 3) * 2
    if any(term in hits for term in profile.get("formal_terms", [])):
        score += 4
    return max(score, 1.0)


def expanded_window_blocks(blocks: list[DocumentBlock], block: DocumentBlock, item: NBDItem) -> list[DocumentBlock]:
    """Expand a selected short heading into the following content as one evidence window."""
    profile = item.recall_profile
    if not profile or not profile.get("enabled", True):
        return [block]
    if not looks_like_heading(block.lines[0].strip() if block.lines else block.text.strip()) and len(compact(block.text)) > 30:
        return [block]
    try:
        idx = next(i for i, candidate in enumerate(blocks) if candidate.block_id == block.block_id)
    except StopIteration:
        return [block]
    neighbor_after = int(profile.get("neighbor_after", 1))
    result = [block]
    for candidate in blocks[idx + 1 : min(len(blocks), idx + 1 + neighbor_after)]:
        first_line = candidate.lines[0].strip() if candidate.lines else candidate.text.strip()
        if looks_like_heading(first_line):
            break
        result.append(candidate)
    return result


def add_profile_recall_rows(
    rows: list[tuple[float, DocumentBlock, dict[str, list[str]], list[str]]],
    blocks: list[DocumentBlock],
    item: NBDItem,
) -> None:
    profile = item.recall_profile
    if not profile or not profile.get("enabled", True):
        return
    added_keys: set[str] = set()
    neighbor_after = int(profile.get("neighbor_after", 1))
    reason_label = str(profile.get("reason") or "通用反证召回")
    for idx, block in enumerate(blocks):
        hits = profile_hits(block, item)
        if not hits:
            continue
        candidate_indices = [idx]
        if looks_like_heading(block.lines[0].strip() if block.lines else block.text.strip()) or len(compact(block.text)) <= 30:
            candidate_indices.extend(range(idx + 1, min(len(blocks), idx + 1 + neighbor_after)))
        for candidate_idx in candidate_indices:
            candidate = blocks[candidate_idx]
            key = f"{candidate.block_id}:{reason_label}"
            if key in added_keys:
                continue
            added_keys.add(key)
            candidate_hits = profile_hits(candidate, item) or hits
            score = profile_score(candidate, item, candidate_hits, reason_label)
            rows.append(
                (
                    score,
                    candidate,
                    {reason_label: candidate_hits},
                    [f"{reason_label}=" + "、".join(candidate_hits[:8]), f"source_block={block.block_id}"],
                )
            )


def configured_completeness_for(blocks: list[DocumentBlock], item: NBDItem) -> dict[str, bool]:
    profile = item.recall_profile or {}
    configured = profile.get("completeness_terms") or {}
    if not isinstance(configured, dict) or not configured:
        return {}
    ctext = compact("\n".join(block.text for block in blocks))
    result: dict[str, bool] = {}
    for label, terms in configured.items():
        values = [str(term) for term in terms if str(term)]
        result[str(label)] = any(term in ctext for term in values)
    return result


def completeness_for(blocks: list[DocumentBlock], item: NBDItem) -> dict[str, bool]:
    configured = configured_completeness_for(blocks, item)
    if configured:
        return configured
    text = "\n".join(block.text for block in blocks)
    role = blocks[0].section_role if blocks else "unknown"
    ctext = compact(text)
    if role in SCORING_SECTION_ROLES or any(word in ctext for word in ["评审因素", "评分准则", "权重"]):
        return {
            "评分项名称": bool(re.search(r"评审因素|评分项|评分内容|供应商|方案|业绩|服务", ctext)),
            "权重": "权重" in ctext or bool(re.search(r"\t\d+(?:\.\d+)?\t", text)),
            "评分内容": "评分内容" in ctext or "得" in ctext,
            "评分依据": "评分依据" in ctext or "提供" in ctext or "证明" in ctext,
        }
    if role in QUALIFICATION_SECTION_ROLES:
        return {
            "项目基本情况": any(word in ctext for word in ["项目名称", "项目编号", "项目类型"]),
            "资格要求": any(word in ctext for word in ["资格要求", "申请人的资格要求", "投标人资格"]),
            "联合体/进口产品": any(word in ctext for word in ["联合体", "进口产品"]),
        }
    if role in BUSINESS_SECTION_ROLES:
        return {
            "条款标题": bool(blocks[0].section_path),
            "条款正文": len(ctext) > 20,
            "地点/期限/付款/验收": any(word in ctext for word in ["地点", "期限", "付款", "验收"]),
        }
    if role == "sample_requirement":
        return {
            "样品对象": "样品" in ctext,
            "提交/制作要求": any(word in ctext for word in ["提交", "递交", "制作", "提供"]),
            "评价/后果": any(word in ctext for word in ["评分", "评审", "得分", "不得分", "无效"]),
        }
    return {"候选文本": bool(ctext)}


def quality_from(completeness: dict[str, bool], primary_count: int, support_count: int) -> str:
    if primary_count == 0 and support_count == 0:
        return "miss"
    if primary_count == 0:
        return "noisy"
    if completeness and all(completeness.values()):
        return "good"
    return "partial"


def window_type_for(block: DocumentBlock, score: float) -> str:
    if block.section_role in SUPPORT_SECTION_ROLES:
        return "support"
    if score <= 3:
        return "support"
    return "primary"


def trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[候选窗口已截断]"


def window_table_scoring(blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for block in blocks:
        table = block.table or {}
        scoring = table.get("scoring") or {}
        if not scoring.get("is_scoring_like"):
            continue
        summaries.append(
            {
                "block_id": block.block_id,
                "weight_columns": table.get("weight_columns") or [],
                "item_columns": table.get("item_columns") or [],
                "weight_sum": scoring.get("weight_sum"),
                "weight_count": scoring.get("weight_count"),
                "structure_warnings": scoring.get("structure_warnings") or [],
                "rows": scoring.get("rows") or [],
            }
        )
    return summaries


def _terms_in_window(window: CandidateWindow, terms: list[str]) -> list[str]:
    ctext = compact(window.text)
    hit_values = [value for values in window.hit_words.values() for value in values]
    return sorted({term for term in terms if term and (term in ctext or term in hit_values)})


def recall_diagnostics(item: NBDItem, windows: list[CandidateWindow], primary_count: int) -> dict[str, Any]:
    formal_terms = list(item.recall_profile.get("formal_terms", []) if item.recall_profile else [])
    noise_terms = list(item.recall_profile.get("noise_terms", []) if item.recall_profile else [])
    conflict_terms = list(item.recall_profile.get("conflict_terms", []) if item.recall_profile else [])
    formal_count = sum(1 for window in windows if _terms_in_window(window, formal_terms))
    noise_count = sum(1 for window in windows if _terms_in_window(window, noise_terms))
    conflict_count = sum(1 for window in windows if _terms_in_window(window, conflict_terms))
    template_count = sum(1 for window in windows if window.section_role in SUPPORT_SECTION_ROLES)
    primary_windows = [window for window in windows if window.window_type == "primary"]
    missing_reasons: list[str] = []
    if not windows:
        missing_reasons.append("no_candidate")
    if windows and primary_count == 0:
        missing_reasons.append("no_primary_window")
    if formal_terms and formal_count == 0:
        missing_reasons.append("formal_evidence_not_recalled")
    if primary_windows and template_count >= len(primary_windows):
        missing_reasons.append("template_or_common_terms_dominant")
    return {
        "formal_evidence_window_count": formal_count,
        "noise_window_count": noise_count,
        "template_window_count": template_count,
        "conflict_window_count": conflict_count,
        "formal_evidence_ratio": round(formal_count / len(windows), 4) if windows else 0.0,
        "template_noise_ratio": round((noise_count + template_count) / len(windows), 4) if windows else 0.0,
        "missing_reason": "、".join(missing_reasons),
    }


def candidate_set_payload(item: NBDItem, windows: list[CandidateWindow], recall_stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": CANDIDATE_SET_SCHEMA,
        "nbd_id": item.nbd_id,
        "nbd_title": item.title,
        "nbd_ir": f"nbd-ir/{item.nbd_id}.json",
        "document_ir": "document-ir.json",
        "candidate_count": len(windows),
        "recall_stats": recall_stats,
        "windows": [asdict(window) for window in windows],
    }


def load_candidate_set(output_dir: Path, item: NBDItem) -> tuple[list[CandidateWindow], dict[str, Any]]:
    path = output_dir / "candidates" / f"{item.nbd_id}.json"
    if not path.exists():
        raise RuntimeError(f"缺少 CandidateSet：{run_path(output_dir, path)}")
    payload = json.loads(read_text(path))
    if payload.get("schema_version") != CANDIDATE_SET_SCHEMA:
        raise RuntimeError(f"CandidateSet schema 不匹配：{run_path(output_dir, path)}")
    windows = [CandidateWindow(**window) for window in payload.get("windows", [])]
    return windows, payload.get("recall_stats") or {}


def build_candidate_windows(
    blocks: list[DocumentBlock],
    item: NBDItem,
    *,
    max_primary: int,
    max_support: int,
    max_window_chars: int,
) -> tuple[list[CandidateWindow], dict[str, Any]]:
    scored: list[tuple[float, DocumentBlock, dict[str, list[str]], list[str]]] = []
    raw_hit_count = 0
    for block in blocks:
        score, hits, reasons = score_block(block, item)
        if score <= 0:
            continue
        raw_hit_count += 1
        if score >= 3:
            scored.append((score, block, hits, reasons))
    before_profile_count = len(scored)
    add_profile_recall_rows(scored, blocks, item)
    profile_added_count = len(scored) - before_profile_count

    scored.sort(key=lambda row: (row[0], SECTION_ROLE_PRIORITY.get(row[1].section_role, 3), -row[1].line_start), reverse=True)
    selected_primary: list[tuple[float, DocumentBlock, dict[str, list[str]], list[str]]] = []
    selected_support: list[tuple[float, DocumentBlock, dict[str, list[str]], list[str]]] = []
    seen_keys: set[str] = set()
    duplicate_skipped = 0
    for row in scored:
        _, block, _, _ = row
        key = normalize_key(block.text)
        overlap = any(block.line_start <= old.line_end and block.line_end >= old.line_start for _, old, _, _ in selected_primary + selected_support)
        if key and key in seen_keys:
            duplicate_skipped += 1
            continue
        target = selected_primary if window_type_for(block, row[0]) == "primary" else selected_support
        limit = max_primary if target is selected_primary else max_support
        if len(target) >= limit:
            continue
        target.append(row)
        if key:
            seen_keys.add(key)
        if overlap:
            duplicate_skipped += 1
    selected = sorted(selected_primary + selected_support, key=lambda row: row[1].line_start)

    windows: list[CandidateWindow] = []
    primary_count = sum(1 for score, block, _, _ in selected if window_type_for(block, score) == "primary")
    support_count = len(selected) - primary_count
    for idx, (score, block, hits, reasons) in enumerate(selected, start=1):
        wtype = window_type_for(block, score)
        window_blocks = expanded_window_blocks(blocks, block, item)
        comp = completeness_for(window_blocks, item)
        quality = quality_from(comp, 1 if wtype == "primary" else 0, 1 if wtype == "support" else 0)
        line_start = min(b.line_start for b in window_blocks)
        line_end = max(b.line_end for b in window_blocks)
        window_text = "\n".join(b.text for b in window_blocks)
        table_scoring = window_table_scoring(window_blocks)
        windows.append(
            CandidateWindow(
                schema_version=CANDIDATE_WINDOW_SCHEMA,
                nbd_id=item.nbd_id,
                window_id=f"W{idx:02d}",
                window_type=wtype,
                section_role=block.section_role,
                section_role_confidence=block.section_role_confidence,
                section_path=block.section_path,
                line_anchor=f"{line_start:04d}-{line_end:04d}",
                score=round(score, 2),
                recall_reason=reasons,
                recall_quality=quality,
                completeness=comp,
                text=trim_text(window_text, max_window_chars),
                block_ids=[b.block_id for b in window_blocks],
                hit_words={name: values for name, values in hits.items() if values},
                source={
                    "document_ir": "document-ir.json",
                    "nbd_ir": f"nbd-ir/{item.nbd_id}.json",
                    "nbd_recall_config": bool(item.recall_profile),
                    "source_block_id": block.block_id,
                    "table_scoring": table_scoring,
                },
            )
        )
    matrix_quality = quality_from(
        windows[0].completeness if windows else {},
        primary_count,
        support_count,
    )
    stats = {
        "raw_hit_count": raw_hit_count,
        "profile_added_count": profile_added_count,
        "filtered_hit_count": len(scored),
        "primary_count": primary_count,
        "support_count": support_count,
        "duplicate_skipped": duplicate_skipped,
        "recall_quality": matrix_quality,
        "max_score": max([row[0] for row in selected] or [0]),
        "top_role": selected[0][1].section_role if selected else "",
    }
    stats.update(recall_diagnostics(item, windows, primary_count))
    return windows, stats



def write_recall_matrix(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    write_text(output_dir / "recall_matrix.json", json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# NBD 候选窗口召回矩阵",
        "",
        "| NBD | 标题 | quality | candidates | primary | support | profile added | formal evidence % | template/noise % | top role | max score | duplicate skipped | missing reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        stats = row.get("recall_stats", {})
        lines.append(
            f"| {row.get('nbd_id')} | {row.get('title')} | {stats.get('recall_quality', '')} | "
            f"{row.get('candidate_count', 0)} | {stats.get('primary_count', 0)} | {stats.get('support_count', 0)} | "
            f"{stats.get('profile_added_count', 0)} | {float(stats.get('formal_evidence_ratio', 0)):.2f} | "
            f"{float(stats.get('template_noise_ratio', 0)):.2f} | {stats.get('top_role', '')} | "
            f"{float(stats.get('max_score', 0)):.1f} | {stats.get('duplicate_skipped', 0)} | {stats.get('missing_reason', '')} |"
        )
    write_text(output_dir / "recall_matrix.md", "\n".join(lines) + "\n")


def write_candidate_artifacts(output_dir: Path, blocks: list[DocumentBlock], items: list[NBDItem], args: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        windows, recall_stats = build_candidate_windows(
            blocks,
            item,
            max_primary=args.max_primary_windows,
            max_support=args.max_support_windows,
            max_window_chars=args.max_window_chars,
        )
        candidate_file = output_dir / "candidates" / f"{item.nbd_id}.json"
        write_text(candidate_file, json.dumps(candidate_set_payload(item, windows, recall_stats), ensure_ascii=False, indent=2) + "\n")
        rows.append(
            {
                "nbd_id": item.nbd_id,
                "title": item.title,
                "nbd_path": relative_path(item.path),
                "candidate_file": run_path(output_dir, candidate_file),
                "candidate_count": len(windows),
                "recall_stats": recall_stats,
                "windows": [asdict(window) for window in windows],
            }
        )
    write_recall_matrix(output_dir, rows)
    return rows
