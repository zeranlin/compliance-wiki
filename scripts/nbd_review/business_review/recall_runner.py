"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from shared.schemas import CANDIDATE_SET_SCHEMA, CANDIDATE_WINDOW_SCHEMA, CandidateWindow, DocumentBlock, NBDItem, SECTION_ROLE_PRIORITY
from shared.utils import compact, looks_like_heading, normalize_key, read_text, relative_path, run_path, write_text

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
GENERIC_RECALL_TERMS = {
    "要求",
    "提供",
    "具备",
    "具有",
    "满足",
    "服务内容",
    "采购需求",
    "技术要求",
    "货物清单",
    "品目事实",
    "品目",
    "出具",
    "应",
    "须",
    "必须",
    "得分",
    "不得分",
}
TEMPLATE_TEXT_PATTERNS = [
    r"投标人认为需要加以说明的其他内容",
    r"按项目实际勾选填写",
    r"空白待填",
    r"_{4,}|…{2,}|\.{6,}",
    r"详见本项目招标公告",
]


@dataclass
class ScoredRow:
    score: float
    block: DocumentBlock
    hits: dict[str, list[str]]
    reasons: list[str]
    source: str = "keyword"


CHINESE_DIGITS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
STATISTICAL_REVIEW_TRIGGERS = ["数量", "份数", "累计", "统计", "超过", "不得超过", "原则上"]
STATISTICAL_REVIEW_DECLARATIONS = ["全文统计型审查", "统计型单一风险", "统计型审查"]
REPORT_OBJECT_TERMS = ["检验检测报告", "检测报告", "检验报告"]


def group_words(keyword_groups: dict[str, list[str]], *parts: str) -> list[str]:
    words: list[str] = []
    for group_name, values in keyword_groups.items():
        if any(part in group_name for part in parts):
            words.extend(values)
    return words


def hit_words(text: str, words: list[str]) -> list[str]:
    ctext = compact(text)
    return sorted({word for word in words if word and word in ctext})


def is_generic_recall_term(term: str) -> bool:
    value = compact(term)
    return len(value) <= 1 or value in GENERIC_RECALL_TERMS


def specific_terms(terms: list[str]) -> list[str]:
    return [term for term in terms if not is_generic_recall_term(term)]


def item_prefers_qualification(item: NBDItem) -> bool:
    text = compact(
        " ".join(
            [
                item.title,
                " ".join(item.keyword_groups.get("章节角色词", [])),
                " ".join(item.keyword_groups.get("对象词簇", [])),
            ]
        )
    )
    return any(term in text for term in ["资格", "资质", "证照", "资格审查", "申请人的资格要求", "投标人资格"])


def evidence_shape_hits(block: DocumentBlock) -> list[str]:
    text = block.text
    ctext = compact(text)
    hits: list[str] = []
    if "\t" in text and re.search(r"\t\d+[、.．]?", text):
        hits.append("表格证据行")
    if re.search(r"[▲★]", text):
        hits.append("重点条款标识")
    if re.search(r"证明|证书|报告|扫描件|关键页|原件|发票", ctext):
        hits.append("证明材料要求")
    if re.search(r"[≥≤<>]|不低于|不高于|不少于|不超过|以上|以内|工作日|%", ctext):
        hits.append("数值约束")
    if re.search(r"投标无效|响应无效|资格审查不通过|不得分|扣\d+(?:\.\d+)?分", ctext):
        hits.append("审查后果")
    return hits


def template_noise_hits(block: DocumentBlock, profile: dict[str, Any] | None = None) -> list[str]:
    ctext = compact(block.text)
    hits: list[str] = []
    if block.section_role in SUPPORT_SECTION_ROLES:
        hits.append(f"section_role:{block.section_role}")
    for pattern in TEMPLATE_TEXT_PATTERNS:
        if re.search(pattern, block.text):
            hits.append(f"template_pattern:{pattern}")
    for term in (profile or {}).get("noise_terms", []):
        if term and term in ctext:
            hits.append(f"noise_term:{term}")
    return hits


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
    shape_hits = evidence_shape_hits(block)
    if shape_hits:
        hits["证据形态"] = shape_hits

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
    if object_hits and shape_hits:
        score += min(len(shape_hits), 3) * 3
    if section_hits and object_hits:
        score += 5
    if block.section_role == "qualification_primary" and object_hits and item_prefers_qualification(item):
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
    noise_hits = template_noise_hits(block, item.recall_profile)
    if noise_hits:
        score -= 6 + min(len(noise_hits), 3) * 2

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
    conflict_hits = [term for term in profile.get("conflict_terms", []) if term and term in ctext]
    if conflict_hits:
        return []
    hits = {term for term in profile.get("terms", []) if term and term in ctext}
    for pattern in profile.get("regex_terms", []):
        if not pattern:
            continue
        try:
            if re.search(pattern, block.text, flags=re.IGNORECASE):
                hits.add(pattern)
        except re.error:
            continue
    return sorted(hits)


def profile_score(block: DocumentBlock, item: NBDItem, hits: list[str], reason: str) -> float:
    profile = item.recall_profile or {}
    score = 6.0 + min(len(hits), 5)
    score += SECTION_ROLE_PRIORITY.get(block.section_role, 3) * max(block.section_role_confidence, 0.2) * 0.8
    if block.section_role in PRIMARY_BOOST_SECTION_ROLES:
        score += 5
    if block.section_role == "qualification_primary" and item_prefers_qualification(item):
        score += 10
    if block.section_role == "scoring_primary":
        score += 6
    if block.section_role in SUPPORT_SECTION_ROLES:
        score -= 2
    formal_hits = [term for term in profile.get("formal_terms", []) if term in hits]
    formal_specific_hits = specific_terms(formal_hits)
    non_generic_hits = specific_terms(hits)
    shape_hits = evidence_shape_hits(block)
    noise_hits = template_noise_hits(block, profile)
    if formal_hits:
        max_formal_len = max((len(compact(term)) for term in formal_specific_hits or formal_hits), default=0)
        if formal_specific_hits:
            score += 24 + min(len(formal_specific_hits), 4) * 4 + min(max_formal_len, 20) * 0.4
        else:
            score += 6 + min(len(formal_hits), 3)
    if non_generic_hits and shape_hits:
        score += min(len(shape_hits), 3) * 3
    if noise_hits and not formal_specific_hits:
        score -= 10 + min(len(noise_hits), 4) * 3
    if formal_specific_hits:
        score += 4
    return max(score, 1.0)


def can_expand_as_similar_evidence(base: DocumentBlock, candidate: DocumentBlock, item: NBDItem) -> bool:
    if candidate.section_role in SUPPORT_SECTION_ROLES or looks_like_heading(candidate.lines[0].strip() if candidate.lines else candidate.text.strip()):
        return False
    if base.section_role != candidate.section_role:
        return False
    base_hits = set(specific_terms(profile_hits(base, item)))
    candidate_hits = set(specific_terms(profile_hits(candidate, item)))
    if not base_hits or not candidate_hits:
        return False
    shared_hits = base_hits & candidate_hits
    if not shared_hits:
        return False
    return bool(evidence_shape_hits(candidate))


def similar_evidence_window_blocks(blocks: list[DocumentBlock], block: DocumentBlock, item: NBDItem) -> list[DocumentBlock]:
    profile = item.recall_profile or {}
    before = int(profile.get("similar_before") or 0)
    after = int(profile.get("similar_after") or 0)
    if before <= 0 and after <= 0:
        return []
    try:
        idx = next(i for i, candidate in enumerate(blocks) if candidate.block_id == block.block_id)
    except StopIteration:
        return []
    selected_indices = {idx}
    for candidate_idx in range(max(0, idx - before), idx):
        if can_expand_as_similar_evidence(block, blocks[candidate_idx], item):
            selected_indices.add(candidate_idx)
    for candidate_idx in range(idx + 1, min(len(blocks), idx + 1 + after)):
        if can_expand_as_similar_evidence(block, blocks[candidate_idx], item):
            selected_indices.add(candidate_idx)
    if len(selected_indices) <= 1:
        return []
    start = min(selected_indices)
    end = max(selected_indices)
    return blocks[start : end + 1]


def expanded_window_blocks(blocks: list[DocumentBlock], block: DocumentBlock, item: NBDItem) -> list[DocumentBlock]:
    """Expand a selected short heading into the following content as one evidence window."""
    profile = item.recall_profile
    if not profile or not profile.get("enabled", True):
        return [block]
    similar_blocks = similar_evidence_window_blocks(blocks, block, item)
    if similar_blocks:
        return similar_blocks
    try:
        idx = next(i for i, candidate in enumerate(blocks) if candidate.block_id == block.block_id)
    except StopIteration:
        return [block]
    neighbor_before = int(profile.get("neighbor_before", 0))
    neighbor_after = int(profile.get("neighbor_after", 1))
    result = [block]
    for candidate in reversed(blocks[max(0, idx - neighbor_before) : idx]):
        first_line = candidate.lines[0].strip() if candidate.lines else candidate.text.strip()
        if looks_like_heading(first_line) or candidate.section_role == block.section_role:
            result.insert(0, candidate)
            continue
        break
    if not looks_like_heading(block.lines[0].strip() if block.lines else block.text.strip()):
        return result
    for candidate in blocks[idx + 1 : min(len(blocks), idx + 1 + neighbor_after)]:
        first_line = candidate.lines[0].strip() if candidate.lines else candidate.text.strip()
        if looks_like_heading(first_line):
            break
        result.append(candidate)
    return result


def add_profile_recall_rows(
    rows: list[ScoredRow],
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
        if looks_like_heading(block.lines[0].strip() if block.lines else block.text.strip()):
            for candidate_idx in range(idx + 1, min(len(blocks), idx + 1 + neighbor_after)):
                candidate = blocks[candidate_idx]
                first_line = candidate.lines[0].strip() if candidate.lines else candidate.text.strip()
                if looks_like_heading(first_line):
                    break
                candidate_indices.append(candidate_idx)
        for candidate_idx in candidate_indices:
            candidate = blocks[candidate_idx]
            key = f"{candidate.block_id}:{reason_label}"
            if key in added_keys:
                continue
            added_keys.add(key)
            candidate_hits = profile_hits(candidate, item) or hits
            score = profile_score(candidate, item, candidate_hits, reason_label)
            noise_hits = template_noise_hits(candidate, profile)
            reasons = [f"{reason_label}=" + "、".join(candidate_hits[:8]), f"source_block={block.block_id}"]
            if noise_hits:
                reasons.append("降权噪声=" + "、".join(noise_hits[:5]))
            rows.append(
                ScoredRow(
                    score=score,
                    block=candidate,
                    hits={reason_label: candidate_hits},
                    reasons=reasons,
                    source="machine_recall",
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


def selection_span(blocks: list[DocumentBlock], row: ScoredRow, item: NBDItem) -> tuple[int, int]:
    window_blocks = expanded_window_blocks(blocks, row.block, item)
    return min(block.line_start for block in window_blocks), max(block.line_end for block in window_blocks)


def trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[候选窗口已截断]"


def window_table_scoring(blocks: list[DocumentBlock]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for block in blocks:
        table = block.table or {}
        row_analysis = table.get("row_scoring_analysis") or {}
        table = table.get("full_table") or table
        scoring = table.get("scoring") or {}
        if not scoring.get("is_scoring_like") and not row_analysis:
            continue
        summary = {
            "block_id": block.block_id,
            "line_anchor": f"{block.line_start:04d}-{block.line_end:04d}",
            "table_id": (block.table or {}).get("table_id"),
            "row_number": (block.table or {}).get("row_number"),
            "weight_columns": table.get("weight_columns") or [],
            "item_columns": table.get("item_columns") or [],
            "weight_sum": scoring.get("weight_sum"),
            "weight_count": scoring.get("weight_count"),
            "structure_warnings": scoring.get("structure_warnings") or [],
            "row_scoring_analysis": row_analysis,
            "rows": scoring.get("rows") or [],
        }
        summaries.append(summary)
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


def statistical_review_profile(item: NBDItem) -> dict[str, Any]:
    """Infer generic counting needs from NBD runnable knowledge.

    The runtime only discovers that a NBD asks for object counting. It does not
    decide whether the count is compliant; that decision remains in the NBD SOP
    and model execution.
    """
    text = compact(f"{item.title}\n{item.compact_text}")
    if not any(term in text for term in STATISTICAL_REVIEW_DECLARATIONS):
        return {"enabled": False}
    if not any(term in text for term in STATISTICAL_REVIEW_TRIGGERS):
        return {"enabled": False}

    object_terms: list[str] = []
    if any(term in text for term in REPORT_OBJECT_TERMS):
        object_terms = REPORT_OBJECT_TERMS
    if not object_terms:
        return {"enabled": False}

    threshold = statistical_threshold_from_text(text)
    return {
        "enabled": True,
        "object_family": "报告",
        "object_terms": object_terms,
        "threshold": threshold,
        "reason": "NBD 文本包含数量统计触发词和可统计对象词",
    }


def statistical_threshold_from_text(text: str) -> int | None:
    for pattern in [r"不得超过(\d+)份", r"超过(\d+)份", r"原则上不得超过(\d+)份"]:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    for pattern in [r"不得超过([一二两三四五六七八九十])份", r"超过([一二两三四五六七八九十])份", r"原则上不得超过([一二两三四五六七八九十])份"]:
        match = re.search(pattern, text)
        if match:
            return CHINESE_DIGITS.get(match.group(1))
    return None


def normalized_object_key(name: str, object_term: str) -> str:
    value = re.sub(r"[\s\t，,。；;：:（）()《》“”\"'、]+", "", name)
    value = re.sub(r"^(需提供|提供|出具|由|具备|相关资质的|第三方|检验检测机构|检测机构)+", "", value)
    value = re.sub(r"(依据|按照|满足|符合).*$", "", value)
    return normalize_key(f"{value}:{object_term}")[:120]


def clean_statistical_object_name(raw: str) -> str:
    value = re.sub(r"\s+", "", raw)
    value = re.sub(r"^[，,。；;：:、（）()《》]+|[，,。；;：:、（）()《》]+$", "", value)
    value = re.sub(r"^(需提供|提供|出具|由|具备|相关资质的|第三方|检验检测机构|检测机构|带有CMA或CNAS标识的)+", "", value)
    value = re.sub(r"(需提供|提供|出具|检测合格|均检测合格|以佐证|报告查询截图).*$", "", value)
    if len(value) > 36:
        value = value[-36:]
    return value or "未能稳定抽取对象名称"


def infer_object_name_before(text: str, position: int) -> str:
    prefix = text[max(0, position - 500) : position]
    quoted_name_matches = re.findall(r"[“\"]([^”\"]{1,40})[”\"]\s*的\s*$", prefix)
    if quoted_name_matches:
        return quoted_name_matches[-1]
    quoted_name_matches = re.findall(r"[“\"]([^”\"]{1,40})[”\"]\s*的\s*(?:检验)?检测?$", prefix)
    if quoted_name_matches:
        return quoted_name_matches[-1]
    label_matches = re.findall(r"(?:^|[;；。\t\n])\s*▲?\d+[\.、\s]*([^：:；;。()（）]{2,40})[：:]", prefix)
    if label_matches:
        return label_matches[-1]
    short_label_matches = re.findall(r"(?:^|[;；。\t\n])\s*▲?\d+[\.、\s]*([^，,；;。()（）]{2,24})", prefix)
    if short_label_matches:
        return short_label_matches[-1]
    quoted = re.findall(r"《([^》]{1,40})》", prefix)
    if quoted:
        return quoted[-1]
    material_matches = re.findall(r"(?:所使用|采用|提供|关于)([^，,；;。()（）]{2,40})(?:依据|的|检测|检验)", prefix)
    material_matches = [value for value in material_matches if "机构" not in value and "资质" not in value]
    if material_matches:
        return material_matches[-1]
    chunks = re.split(r"[。；;，,\t()（）]", prefix)
    return chunks[-1] if chunks else ""


def is_countable_statistical_occurrence(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 180) : start]
    after = text[end : min(len(text), end + 80)]
    nearby = before + text[start:end] + after
    after_stripped = after.lstrip()
    if after_stripped.startswith(("名称", "封面", "查询截图")):
        return False
    has_submit_verb = bool(re.search(r"需提供|须提供|应提供|提供|提供由|出具|检测合格|检验合格|以佐证", before))
    if re.search(r"报告编号|查询截图|应与检测报告一致|与检测报告一致", nearby):
        return False
    if "报告名称" in nearby and not has_submit_verb:
        return False
    if "该份报告" in before[-30:]:
        return False
    return has_submit_verb


def extract_statistical_objects_from_window(window: CandidateWindow, object_terms: list[str]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for object_term in object_terms:
        for match in re.finditer(re.escape(object_term), window.text):
            if not is_countable_statistical_occurrence(window.text, match.start(), match.end()):
                continue
            name = clean_statistical_object_name(infer_object_name_before(window.text, match.start()))
            evidence_start = max(0, match.start() - 80)
            evidence_end = min(len(window.text), match.end() + 80)
            evidence = window.text[evidence_start:evidence_end].strip()
            objects.append(
                {
                    "object_name": name,
                    "object_term": object_term,
                    "line_anchor": window.line_anchor,
                    "window_id": window.window_id,
                    "dedupe_key": normalized_object_key(name, object_term),
                    "evidence_text": evidence[:220],
                }
            )
    return objects


def build_statistical_review(item: NBDItem, windows: list[CandidateWindow]) -> dict[str, Any]:
    profile = statistical_review_profile(item)
    if not profile.get("enabled"):
        return {"enabled": False}
    objects: list[dict[str, Any]] = []
    seen: set[str] = set()
    for window in windows:
        for obj in extract_statistical_objects_from_window(window, list(profile.get("object_terms") or [])):
            key = str(obj.get("dedupe_key") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            obj["ordinal"] = len(objects) + 1
            objects.append(obj)
    return {
        **profile,
        "object_count": len(objects),
        "objects": objects[:24],
        "omitted_object_count": max(0, len(objects) - 24),
        "representative_lines": sorted({obj["line_anchor"] for obj in objects})[:12],
    }


def candidate_set_payload(item: NBDItem, windows: list[CandidateWindow], recall_stats: dict[str, Any]) -> dict[str, Any]:
    statistical_review = build_statistical_review(item, windows)
    return {
        "schema_version": CANDIDATE_SET_SCHEMA,
        "nbd_id": item.nbd_id,
        "nbd_title": item.title,
        "nbd_ir": f"nbd-ir/{item.nbd_id}.json",
        "document_ir": "document-ir.json",
        "candidate_count": len(windows),
        "recall_stats": recall_stats,
        "statistical_review": statistical_review,
        "windows": [asdict(window) for window in windows],
    }


def load_candidate_set_payload(output_dir: Path, item: NBDItem) -> dict[str, Any]:
    path = output_dir / "candidates" / f"{item.nbd_id}.json"
    if not path.exists():
        raise RuntimeError(f"缺少 CandidateSet：{run_path(output_dir, path)}")
    payload = json.loads(read_text(path))
    if payload.get("schema_version") != CANDIDATE_SET_SCHEMA:
        raise RuntimeError(f"CandidateSet schema 不匹配：{run_path(output_dir, path)}")
    return payload


def load_candidate_set(output_dir: Path, item: NBDItem) -> tuple[list[CandidateWindow], dict[str, Any]]:
    payload = load_candidate_set_payload(output_dir, item)
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
    profile = item.recall_profile or {}
    profile_max_primary = int(profile.get("max_primary_windows") or 0)
    profile_max_support = int(profile.get("max_support_windows") or 0)
    effective_max_primary = max(max_primary, profile_max_primary)
    effective_max_support = max(max_support, profile_max_support)

    scored: list[ScoredRow] = []
    raw_hit_count = 0
    for block in blocks:
        score, hits, reasons = score_block(block, item)
        if score <= 0:
            continue
        raw_hit_count += 1
        if score >= 3:
            scored.append(ScoredRow(score=score, block=block, hits=hits, reasons=reasons))
    before_profile_count = len(scored)
    add_profile_recall_rows(scored, blocks, item)
    profile_added_count = len(scored) - before_profile_count

    scored.sort(key=lambda row: (row.score, SECTION_ROLE_PRIORITY.get(row.block.section_role, 3), -row.block.line_start), reverse=True)
    selected_primary: list[ScoredRow] = []
    selected_support: list[ScoredRow] = []
    seen_keys: set[str] = set()
    duplicate_skipped = 0
    overlap_skipped = 0
    support_noise_skipped = 0
    span_cache: dict[str, tuple[int, int]] = {}

    def cached_span(row: ScoredRow) -> tuple[int, int]:
        if row.block.block_id not in span_cache:
            span_cache[row.block.block_id] = selection_span(blocks, row, item)
        return span_cache[row.block.block_id]

    for row in scored:
        block = row.block
        key = f"{block.block_id}:{normalize_key(block.text)}"
        line_start, line_end = cached_span(row)
        overlap = any(
            line_start <= old_end and line_end >= old_start
            for old_start, old_end in [cached_span(old) for old in selected_primary + selected_support]
        )
        if key and key in seen_keys:
            duplicate_skipped += 1
            continue
        if overlap:
            overlap_skipped += 1
            continue
        target = selected_primary if window_type_for(block, row.score) == "primary" else selected_support
        if (
            target is selected_support
            and selected_primary
            and block.section_role in SUPPORT_SECTION_ROLES
            and profile_max_support <= 0
        ):
            support_noise_skipped += 1
            continue
        limit = effective_max_primary if target is selected_primary else effective_max_support
        if len(target) >= limit:
            continue
        target.append(row)
        if key:
            seen_keys.add(key)
    selected = selected_primary + sorted(selected_support, key=lambda row: row.block.line_start)

    windows: list[CandidateWindow] = []
    primary_count = sum(1 for row in selected if window_type_for(row.block, row.score) == "primary")
    support_count = len(selected) - primary_count
    for idx, row in enumerate(selected, start=1):
        score = row.score
        block = row.block
        hits = row.hits
        reasons = row.reasons
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
                    "recall_source": row.source,
                    "selection_rank": idx,
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
        "max_primary_windows": effective_max_primary,
        "max_support_windows": effective_max_support,
        "profile_max_primary_windows": profile_max_primary,
        "profile_max_support_windows": profile_max_support,
        "duplicate_skipped": duplicate_skipped,
        "overlap_skipped": overlap_skipped,
        "support_noise_skipped": support_noise_skipped,
        "recall_quality": matrix_quality,
        "max_score": max([row.score for row in selected] or [0]),
        "top_role": selected[0].block.section_role if selected else "",
        "top_primary_anchors": [window.line_anchor for window in windows if window.window_type == "primary"][:5],
    }
    stats.update(recall_diagnostics(item, windows, primary_count))
    return windows, stats



def write_recall_matrix(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    write_text(output_dir / "recall_matrix.json", json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# NBD 候选窗口召回矩阵",
        "",
        "| NBD | 标题 | quality | candidates | primary | support | profile added | formal evidence % | template/noise % | top role | top primary anchors | max score | duplicate skipped | overlap skipped | support noise skipped | missing reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        stats = row.get("recall_stats", {})
        top_anchors = "、".join(str(anchor) for anchor in (stats.get("top_primary_anchors") or [])[:5])
        lines.append(
            f"| {row.get('nbd_id')} | {row.get('title')} | {stats.get('recall_quality', '')} | "
            f"{row.get('candidate_count', 0)} | {stats.get('primary_count', 0)} | {stats.get('support_count', 0)} | "
            f"{stats.get('profile_added_count', 0)} | {float(stats.get('formal_evidence_ratio', 0)):.2f} | "
            f"{float(stats.get('template_noise_ratio', 0)):.2f} | {stats.get('top_role', '')} | {top_anchors} | "
            f"{float(stats.get('max_score', 0)):.1f} | {stats.get('duplicate_skipped', 0)} | "
            f"{stats.get('overlap_skipped', 0)} | {stats.get('support_noise_skipped', 0)} | {stats.get('missing_reason', '')} |"
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
