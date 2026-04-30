"""Postprocess normalized model results into business issue groups.

This module only groups and selects evidence emitted by recall/model stages. It must not
create new risk verdicts, infer business rules from keywords, or override model output.
"""

from __future__ import annotations

import re
from typing import Any

from utils import normalize_key

CONTRADICTION_TERMS = [
    "已明确",
    "已满足",
    "已载明",
    "不构成风险",
    "不构成",
    "符合规定",
    "不属于风险",
    "无需整改",
    "不存在风险",
]

SUPPORT_SECTION_ROLES = {"catalog", "common_terms", "bid_format", "contract_template", "template_support", "policy_support"}
NUMERIC_TERMS = ["权重", "总和", "分值", "比例", "金额", "期限", "数量", "超过", "不得低于", "不得超过", "计算"]


def first_text(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""


def _result_text(result: dict[str, Any]) -> str:
    parts = [
        str(result.get("summary") or ""),
        str(result.get("risk_tip") or ""),
        str(result.get("revision_suggestion") or ""),
    ]
    trace = result.get("execution_trace") or {}
    if isinstance(trace, dict):
        parts.append(str(trace))
    candidates = result.get("candidates") or []
    if isinstance(candidates, list):
        parts.extend(str(candidate) for candidate in candidates[:8])
    return " ".join(parts)


def model_quality_flags(row: dict[str, Any]) -> list[dict[str, str]]:
    """Add generic model-output quality markers without changing model verdict."""
    result = row.get("model_result", {}) or {}
    verdict = result.get("verdict")
    flags: list[dict[str, str]] = []
    text = _result_text(result)
    meta = row.get("nbd", {}) or {}
    nbd_text = " ".join([str(meta.get("title") or ""), str(meta.get("risk_tip") or ""), str(meta.get("revision_suggestion") or "")])
    combined_text = f"{nbd_text} {text}"
    if verdict == "命中":
        terms = [term for term in CONTRADICTION_TERMS if term in text]
        if re.search(r"(?<!不)(?<!未)(?<!无)符合要求", text):
            terms.append("符合要求")
        if terms:
            flags.append(
                {
                    "code": "verdict_contradiction",
                    "level": "review_required",
                    "message": "模型 verdict 为命中，但说明中出现反证语义：" + "、".join(terms[:5]),
                }
            )
        windows = row.get("windows") or []
        if windows:
            primary_windows = [window for window in windows if window.get("window_type") == "primary"]
            support_like = [
                window
                for window in windows
                if window.get("window_type") == "support" or window.get("section_role") in SUPPORT_SECTION_ROLES
            ]
            if not primary_windows and support_like:
                flags.append(
                    {
                        "code": "primary_window_missing",
                        "level": "review_required",
                        "message": "命中结果缺少 primary 候选窗口，仅有 support 类证据。",
                    }
                )
            if support_like and len(support_like) == len(windows):
                flags.append(
                    {
                        "code": "template_only_hit",
                        "level": "review_required",
                        "message": "命中结果的候选窗口全部为模板、格式、目录、通用条款或政策支持类证据。",
                    }
                )
            primary_lines = [
                str(window.get("line_anchor") or "")
                for window in primary_windows
                if str(window.get("line_anchor") or "")
            ]
            if len(primary_lines) != len(set(primary_lines)):
                flags.append(
                    {
                        "code": "duplicate_same_evidence",
                        "level": "review_required",
                        "message": "命中结果存在重复 primary 证据位置，需确认是否重复引用同一段原文。",
                    }
                )
        if any(term in combined_text for term in NUMERIC_TERMS):
            has_formula = bool(re.search(r"\d+(?:\.\d+)?\s*[+＋\-—–]\s*\d+|\d+(?:\.\d+)?\s*[×x*/÷]\s*\d+|=\s*\d+|\d+(?:\.\d+)?\s*(?:%|分|元|万元).{0,20}(?:不等于|等于|超过|低于|大于|小于)", text))
            if not has_formula:
                flags.append(
                    {
                        "code": "missing_calculation",
                        "level": "review_required",
                        "message": "命中结果涉及数值/权重/金额/比例/期限判断，但未展示可复盘的计算过程。",
                    }
                )
        table_warnings: list[str] = []
        for window in row.get("windows") or []:
            for table_summary in ((window.get("source") or {}).get("table_scoring") or []):
                table_warnings.extend(str(value) for value in table_summary.get("structure_warnings") or [])
        if table_warnings and any(term in combined_text for term in ["权重", "分值", "评分", "总和"]):
            flags.append(
                {
                    "code": "scoring_table_structure_uncertain",
                    "level": "review_required",
                    "message": "候选评分表存在结构不确定信号：" + "、".join(list(dict.fromkeys(table_warnings))[:5]),
                }
            )
    return flags


def row_quality_flags(row: dict[str, Any]) -> list[dict[str, str]]:
    flags = row.get("quality_flags")
    if isinstance(flags, list):
        return [flag for flag in flags if isinstance(flag, dict)]
    result_flags = (row.get("model_result") or {}).get("quality_flags")
    if isinstance(result_flags, list):
        return [flag for flag in result_flags if isinstance(flag, dict)]
    return []


def has_blocking_quality_flag(row: dict[str, Any]) -> bool:
    return any(
        flag.get("code")
        in {"verdict_contradiction", "template_only_hit", "primary_window_missing", "missing_calculation"}
        for flag in row_quality_flags(row)
    )


def clean_inline(text: Any, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def candidate_evidence(row: dict[str, Any]) -> dict[str, Any]:
    result = row.get("model_result", {}) or {}
    candidates = result.get("candidates") or []
    preferred = ["命中", "待人工复核", ""]
    for verdict in preferred:
        for candidate in candidates:
            if verdict and candidate.get("candidate_verdict") != verdict:
                continue
            excerpt = clean_inline(candidate.get("excerpt"), 900)
            if excerpt:
                return {
                    "line_anchor": candidate.get("line_anchor") or "",
                    "excerpt": excerpt,
                    "clause_type": candidate.get("clause_type") or "",
                    "reason": candidate.get("reason") or result.get("summary") or "",
                    "source": "model_candidate",
                }
    windows = row.get("windows") or []
    primary = [window for window in windows if window.get("window_type") == "primary"]
    for window in primary + windows:
        excerpt = clean_inline(window.get("text"), 900)
        if excerpt:
            return {
                "line_anchor": window.get("line_anchor") or "",
                "excerpt": excerpt,
                "clause_type": window.get("section_role") or "",
                "reason": result.get("summary") or "",
                "source": "candidate_window",
            }
    return {"line_anchor": "", "excerpt": "", "clause_type": "", "reason": result.get("summary") or "", "source": ""}


def issue_family(row: dict[str, Any], evidence: dict[str, Any]) -> str:
    # Postprocessor must not infer business families from keywords.
    # Group only by structural evidence emitted by recall/model stages.
    line_anchor = str(evidence.get("line_anchor") or "").strip()
    clause_type = str(evidence.get("clause_type") or "").strip()
    excerpt_key = normalize_key(str(evidence.get("excerpt") or ""))[:120]
    if line_anchor:
        return f"evidence:{line_anchor}:{clause_type}:{excerpt_key}"
    result = row.get("model_result", {}) or {}
    summary_key = normalize_key(str(result.get("summary") or ""))[:120]
    if summary_key:
        return f"summary:{summary_key}"
    meta = row.get("nbd", {}) or {}
    title_key = normalize_key(str(meta.get("title") or ""))[:120]
    return f"title:{title_key or 'unknown'}"


def issue_title(rows: list[dict[str, Any]], family: str) -> str:
    hit = next((row for row in rows if row.get("model_result", {}).get("verdict") == "命中"), rows[0])
    summary = clean_inline(hit.get("model_result", {}).get("summary"), 80)
    if summary:
        return summary
    meta = hit.get("nbd", {})
    title = str(meta.get("title") or "").strip()
    return title or "业务风险事项"


def risk_level(rows: list[dict[str, Any]]) -> str:
    if any(row.get("model_result", {}).get("verdict") == "命中" for row in rows):
        return "高"
    return "待人工复核"


def issue_status(rows: list[dict[str, Any]]) -> str:
    return "命中" if any(row.get("model_result", {}).get("verdict") == "命中" for row in rows) else "待人工复核"


def issue_types(rows: list[dict[str, Any]], evidence: dict[str, Any]) -> str:
    values: list[str] = []
    for row in rows:
        meta = row.get("nbd", {}) or {}
        if meta.get("finding_type"):
            values.append(str(meta.get("finding_type")))
        if meta.get("item_scope"):
            values.append(str(meta.get("item_scope")))
    clause_type = evidence.get("clause_type")
    if clause_type:
        values.append(str(clause_type))
    deduped = list(dict.fromkeys([value for value in values if value]))
    return "、".join(deduped[:5]) or "其他"


def business_family_label(row: dict[str, Any], evidence: dict[str, Any]) -> str:
    """Presentation-only family labels; does not affect verdicts or evidence selection."""
    meta = row.get("nbd", {}) or {}
    title = str(meta.get("title") or "")
    text = " ".join([title, str(evidence.get("clause_type") or ""), str(evidence.get("excerpt") or "")])
    if any(word in text for word in ["资格", "供应商", "投标人资格"]):
        return "资格条件"
    if any(word in text for word in ["评分", "评审", "权重", "分值", "得分", "不得分"]):
        return "评分规则"
    if any(word in text for word in ["样品", "检测报告", "检验报告", "CMA", "标准", "检测"]):
        return "样品检测"
    if any(word in text for word in ["技术", "参数", "规格", "采购需求", "货物清单"]):
        return "技术参数"
    if any(word in text for word in ["合同", "付款", "履约", "验收", "保证金", "交货", "服务期"]):
        return "商务合同"
    if any(word in text for word in ["中小企业", "节能", "环保", "政府采购政策", "进口产品", "联合体"]):
        return "政府采购政策"
    return "其他"


def business_issue_rank(rows: list[dict[str, Any]]) -> int:
    """Presentation priority for business reports, based on issue family only."""
    if not rows:
        return 99
    evidence = best_group_evidence(rows)
    label = business_family_label(rows[0], evidence)
    clause_type = str(evidence.get("clause_type") or "")
    if label == "资格条件" and ("qualification" in clause_type or "资格" in clause_type):
        return 0
    order = {
        "资格条件": 1,
        "评分规则": 2,
        "样品检测": 3,
        "技术参数": 4,
        "商务合同": 5,
        "政府采购政策": 6,
        "其他": 9,
    }
    return order.get(label, 9)


def best_group_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evidences = [candidate_evidence(row) for row in rows]
    for row, evidence in zip(rows, evidences):
        if row.get("model_result", {}).get("verdict") == "命中" and evidence.get("excerpt"):
            return evidence
    return next((evidence for evidence in evidences if evidence.get("excerpt")), evidences[0] if evidences else {})


def group_business_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        evidence = candidate_evidence(row)
        family = issue_family(row, evidence)
        if family not in buckets:
            buckets[family] = {"family": family, "rows": [], "evidences": []}
            order.append(family)
        buckets[family]["rows"].append(row)
        buckets[family]["evidences"].append(evidence)
    grouped = [buckets[key] for key in order]
    grouped.sort(
        key=lambda item: (
            0 if issue_status(item["rows"]) == "命中" else 1,
            business_issue_rank(item["rows"]),
            str((best_group_evidence(item["rows"]) or {}).get("line_anchor", "")),
            item["family"],
        )
    )
    return grouped
