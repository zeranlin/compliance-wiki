"""Postprocess normalized model results into business issue groups.

This module only groups and selects evidence emitted by recall/model stages. It must not
create new risk verdicts or infer business rules from keywords. It may repair structural
inconsistencies inside the same model output when the model emitted positive candidates
but left the top-level verdict stale.
"""

from __future__ import annotations

import re
from typing import Any

from shared.utils import normalize_key

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
POSITIVE_VERDICTS = {"命中", "待人工复核"}
VERDICT_PRIORITY = {"命中": 2, "待人工复核": 1, "不命中": 0, "": 0}
SELF_REJECT_PATTERNS = [
    r"不命中",
    r"不得命中",
    r"不能(?:作为|输出|进入)?命中",
    r"不(?:构成|属于|进入).{0,12}(?:风险|命中|candidate|candidates)",
    r"按(?:照)?排除条件.{0,12}(?:不命中|排除)",
    r"需(?:重新检查|寻找其他命中项|寻找更明确)",
]


def _parse_line_anchor(value: Any) -> tuple[int, int] | None:
    numbers = [int(item) for item in re.findall(r"\d+", str(value or ""))]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    start, end = numbers[0], numbers[1]
    if start > end:
        start, end = end, start
    return start, end


def _line_anchor_overlaps_windows(line_anchor: str, window_line_anchors: set[str]) -> bool:
    target = _parse_line_anchor(line_anchor)
    if not target:
        return False
    target_start, target_end = target
    for window_anchor in window_line_anchors:
        window_range = _parse_line_anchor(window_anchor)
        if not window_range:
            continue
        window_start, window_end = window_range
        if target_start <= window_end and window_start <= target_end:
            return True
    return False


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


def _verdict_text(result: dict[str, Any]) -> str:
    trace = result.get("execution_trace") or {}
    branch_reason = ""
    if isinstance(trace, dict):
        branch = trace.get("result_branch") or {}
        if isinstance(branch, dict):
            branch_reason = str(branch.get("reason") or "")
    return " ".join(
        [
            str(result.get("summary") or ""),
            str(result.get("risk_tip") or ""),
            str(result.get("revision_suggestion") or ""),
            branch_reason,
        ]
    )


def _candidate_is_positive(candidate: dict[str, Any], fallback_verdict: str) -> bool:
    return str(candidate.get("candidate_verdict") or fallback_verdict).strip() in POSITIVE_VERDICTS


def _candidate_self_rejected(candidate: dict[str, Any]) -> bool:
    """Return true when the model's own candidate reason rejects the candidate.

    This is a generic JSON consistency check. It does not know any NBD business
    rules; it only prevents a candidate from being positive when the same reason
    text explicitly says the candidate should not be positive.
    """
    reason = str(candidate.get("reason") or "")
    if not reason:
        return False
    reason = re.sub(r"\s+", "", reason)
    reason = reason.replace("未命中排除条件", "")
    reason = reason.replace("没有命中排除条件", "")
    return any(re.search(pattern, reason) for pattern in SELF_REJECT_PATTERNS)


def prune_self_rejected_positive_candidates(row: dict[str, Any]) -> bool:
    """Prune positive candidates contradicted by their own reason text."""
    result = row.get("model_result")
    if not isinstance(result, dict):
        return False
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return False
    fallback_verdict = str(result.get("verdict") or "").strip()
    pruned: list[Any] = []
    rejected: list[dict[str, Any]] = []
    changed = False
    for candidate in candidates:
        if (
            isinstance(candidate, dict)
            and _candidate_is_positive(candidate, fallback_verdict)
            and _candidate_self_rejected(candidate)
        ):
            changed = True
            candidate = dict(candidate)
            candidate["candidate_verdict"] = "不命中"
            candidate["hit_condition_met"] = False
            rejected.append(candidate)
            continue
        pruned.append(candidate)
    if not changed:
        return False
    positive_left = [
        candidate
        for candidate in pruned
        if isinstance(candidate, dict) and _candidate_is_positive(candidate, fallback_verdict)
    ]
    if not positive_left:
        pruned.extend(rejected[:3])
        result["verdict"] = "不命中"
        trace = result.get("execution_trace")
        if isinstance(trace, dict):
            branch = trace.get("result_branch")
            if isinstance(branch, dict):
                branch["branch"] = "不命中"
                reason = str(branch.get("reason") or "").strip()
                branch["reason"] = (reason + "；" if reason else "") + "运行时发现全部正向候选的 reason 已自我排除，按结构一致性修正为不命中。"
    result["candidates"] = pruned
    result["candidate_count"] = len(pruned)
    repairs = [repair for repair in (row.get("runtime_repairs") or []) if isinstance(repair, dict)]
    repairs.append(
        {
            "code": "self_rejected_positive_candidate_pruned",
            "message": f"已移除 {len(rejected)} 条 reason 自我排除却标为正向的候选，保证候选结论与理由一致。",
        }
    )
    row["runtime_repairs"] = repairs
    return True


def prune_output_constraint_violations(row: dict[str, Any]) -> bool:
    """Apply generic output constraints compiled from an NBD page.

    The runtime does not know why a completeness key matters. It only enforces
    the NBD-declared structural contract against already recalled candidate
    windows and model-emitted candidates.
    """
    constraints = row.get("output_constraints")
    if not isinstance(constraints, dict) or not constraints:
        return False
    result = row.get("model_result")
    if not isinstance(result, dict):
        return False
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return False
    windows = row.get("windows")
    if not isinstance(windows, list):
        windows = []
    window_by_id = {
        str(window.get("window_id") or ""): window
        for window in windows
        if isinstance(window, dict) and str(window.get("window_id") or "")
    }
    fallback_verdict = str(result.get("verdict") or "").strip()
    allowed_roles = set(str(item) for item in constraints.get("allowed_section_roles") or [])
    excluded_roles = set(str(item) for item in constraints.get("excluded_section_roles") or [])
    required_completeness = [str(item) for item in constraints.get("required_completeness") or [] if str(item)]
    excluded_text_patterns = [str(item) for item in constraints.get("excluded_text_patterns") or [] if str(item)]
    selection_strategy = str(constraints.get("positive_selection_strategy") or "")
    max_positive = constraints.get("max_positive_candidates")
    candidate_entries = list(enumerate(candidates))
    if isinstance(max_positive, int) and max_positive >= 0 and "最早行号" in selection_strategy:
        candidate_entries.sort(key=lambda item: _parse_line_anchor(item[1].get("line_anchor")) or (10**9, 10**9) if isinstance(item[1], dict) else (10**9, 10**9))
    pruned: list[Any] = []
    rejected: list[dict[str, Any]] = []
    positive_seen = 0
    changed = False
    for _, candidate in candidate_entries:
        if not isinstance(candidate, dict) or not _candidate_is_positive(candidate, fallback_verdict):
            pruned.append(candidate)
            continue
        window = window_by_id.get(str(candidate.get("candidate_id") or ""))
        rejection_reason = output_constraint_rejection_reason(candidate, window, allowed_roles, excluded_roles, required_completeness, excluded_text_patterns)
        if isinstance(max_positive, int) and max_positive >= 0 and positive_seen >= max_positive:
            rejection_reason = rejection_reason or f"超过 NBD 声明的正向候选最多数量 {max_positive}"
        if rejection_reason:
            changed = True
            candidate = dict(candidate)
            candidate["candidate_verdict"] = "不命中"
            candidate["hit_condition_met"] = False
            candidate["exclusion_triggered"] = True
            reason = str(candidate.get("reason") or "").strip()
            candidate["reason"] = (reason + "；" if reason else "") + rejection_reason
            rejected.append(candidate)
            continue
        positive_seen += 1
        pruned.append(candidate)
    if not changed:
        return False
    positive_left = [
        candidate
        for candidate in pruned
        if isinstance(candidate, dict) and _candidate_is_positive(candidate, fallback_verdict)
    ]
    if not positive_left:
        pruned.extend(rejected[:3])
        result["verdict"] = "不命中"
        trace = result.get("execution_trace")
        if isinstance(trace, dict):
            branch = trace.get("result_branch")
            if isinstance(branch, dict):
                branch["branch"] = "不命中"
                reason = str(branch.get("reason") or "").strip()
                branch["reason"] = (reason + "；" if reason else "") + "运行时按 NBD 机器输出约束移除全部正向候选。"
    result["candidates"] = pruned
    result["candidate_count"] = len(pruned)
    repairs = [repair for repair in (row.get("runtime_repairs") or []) if isinstance(repair, dict)]
    repairs.append(
        {
            "code": "nbd_output_constraint_violation_pruned",
            "message": f"已按 NBD 机器输出约束移除 {len(rejected)} 条结构不合格的正向候选。",
        }
    )
    row["runtime_repairs"] = repairs
    return True


def output_constraint_rejection_reason(
    candidate: dict[str, Any],
    window: dict[str, Any] | None,
    allowed_roles: set[str],
    excluded_roles: set[str],
    required_completeness: list[str],
    excluded_text_patterns: list[str],
) -> str:
    role = str((window or {}).get("section_role") or "")
    if allowed_roles and role and role not in allowed_roles:
        return f"候选章节角色 {role} 不在 NBD 允许正向角色内"
    if excluded_roles and role in excluded_roles:
        return f"候选章节角色 {role} 属于 NBD 排除正向角色"
    completeness = (window or {}).get("completeness") or {}
    if required_completeness and isinstance(completeness, dict):
        missing = [key for key in required_completeness if not bool(completeness.get(key))]
        if missing:
            return "候选窗口缺少 NBD 要求的完整性要素：" + "、".join(missing)
    text = " ".join([str(candidate.get("excerpt") or ""), str(candidate.get("reason") or ""), str((window or {}).get("text") or "")])
    for pattern in excluded_text_patterns:
        try:
            if re.search(pattern, text):
                return f"候选文本命中 NBD 排除文本模式：{pattern}"
        except re.error:
            continue
    return ""


def repair_verdict_candidate_consistency(row: dict[str, Any]) -> bool:
    """Align top-level verdict with model-emitted positive candidates.

    This is a structural repair only: it never creates candidates and never reads
    keywords or NBD-specific business content. It trusts the model's own
    candidate_verdict values when they are more specific than the stale top-level
    verdict.
    """
    result = row.get("model_result")
    if not isinstance(result, dict) or result.get("recovered_from_invalid_json"):
        return False
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return False
    candidate_verdicts = [
        str(candidate.get("candidate_verdict") or "").strip()
        for candidate in candidates
        if isinstance(candidate, dict)
    ]
    if "命中" in candidate_verdicts:
        target = "命中"
    elif "待人工复核" in candidate_verdicts:
        target = "待人工复核"
    else:
        return False
    current = str(result.get("verdict") or "").strip()
    if VERDICT_PRIORITY.get(current, 0) >= VERDICT_PRIORITY[target]:
        return False
    result["verdict"] = target
    trace = result.get("execution_trace")
    if isinstance(trace, dict):
        branch = trace.get("result_branch")
        if isinstance(branch, dict):
            branch["branch"] = target
            reason = str(branch.get("reason") or "").strip()
            branch["reason"] = (reason + "；" if reason else "") + "运行时按模型已输出的正向 candidate_verdict 修正顶层 verdict。"
    repairs = [repair for repair in (row.get("runtime_repairs") or []) if isinstance(repair, dict)]
    repairs.append(
        {
            "code": "verdict_candidate_consistency_repaired",
            "message": f"模型候选结论包含“{target}”，顶层 verdict 已由“{current or '空'}”修正为“{target}”。",
        }
    )
    row["runtime_repairs"] = repairs
    return True


def prune_support_positive_candidates(row: dict[str, Any]) -> bool:
    """Remove support-only positive candidates when primary positive evidence exists.

    Support windows are context. If the model already selected primary evidence for
    the same NBD result, keeping additional support candidates inflates business
    findings and F1 predictions without adding a standalone risk fact.
    """
    result = row.get("model_result")
    if not isinstance(result, dict):
        return False
    verdict = str(result.get("verdict") or "").strip()
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return False
    positive = [candidate for candidate in candidates if isinstance(candidate, dict) and _candidate_is_positive(candidate, verdict)]
    if not positive:
        return False
    primary_positive = [
        candidate
        for candidate in positive
        if str(candidate.get("window_type") or "").strip() == "primary"
        or str(candidate.get("clause_type") or "").strip() not in SUPPORT_SECTION_ROLES
    ]
    if not primary_positive:
        return False
    pruned: list[dict[str, Any]] = []
    changed = False
    for candidate in candidates:
        if not isinstance(candidate, dict):
            pruned.append(candidate)
            continue
        if _candidate_is_positive(candidate, verdict) and str(candidate.get("window_type") or "").strip() == "support":
            changed = True
            continue
        pruned.append(candidate)
    if not changed:
        return False
    result["candidates"] = pruned
    result["candidate_count"] = len(pruned)
    repairs = [repair for repair in (row.get("runtime_repairs") or []) if isinstance(repair, dict)]
    repairs.append(
        {
            "code": "support_positive_candidate_pruned",
            "message": "已移除与 primary 命中并存的 support 正向候选，support 仅作为上下文，不作为独立风险输出。",
        }
    )
    row["runtime_repairs"] = repairs
    return True


def dedupe_model_candidates(row: dict[str, Any]) -> bool:
    """Remove exact duplicate model candidates without changing business rules.

    The runtime may validate model output, but it must not become a second rule
    library. This only removes repeated candidates that point to the same line,
    have the same verdict, and quote the same evidence text.
    """
    result = row.get("model_result")
    if not isinstance(result, dict):
        return False
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return False
    deduped: list[Any] = []
    seen: set[tuple[str, str, str]] = set()
    changed = False
    for candidate in candidates:
        if not isinstance(candidate, dict):
            deduped.append(candidate)
            continue
        key = (
            str(candidate.get("candidate_verdict") or result.get("verdict") or "").strip(),
            str(candidate.get("line_anchor") or candidate.get("line") or "").strip(),
            normalize_key(str(candidate.get("excerpt") or ""))[:160],
        )
        if key[1] and key[2] and key in seen:
            changed = True
            continue
        seen.add(key)
        deduped.append(candidate)
    if not changed:
        return False
    result["candidates"] = deduped
    result["candidate_count"] = len(deduped)
    repairs = [repair for repair in (row.get("runtime_repairs") or []) if isinstance(repair, dict)]
    repairs.append(
        {
            "code": "duplicate_model_candidate_pruned",
            "message": "已移除同一行号、同一结论、同一原文摘录的重复候选。",
        }
    )
    row["runtime_repairs"] = repairs
    return True


def _contradiction_terms(text: str) -> list[str]:
    terms: list[str] = []
    sentences = [sentence for sentence in re.split(r"[。；;！!\n]", text) if sentence.strip()]
    for term in CONTRADICTION_TERMS:
        matched = [
            sentence
            for sentence in sentences
            if term in sentence
            and not re.search(r"非本NBD|不构成本NBD|不按本NBD|不属于本NBD|由.+NBD承接|交由.+NBD|W\d", sentence)
            and not re.search(r"其他候选|其余候选|其他窗口|其余窗口|其他条款|其余条款", sentence)
        ]
        if term.startswith("已"):
            pattern = rf"(?<!未)(?<!没有)(?<!无){re.escape(term)}"
            if any(re.search(pattern, sentence) for sentence in matched) and not re.search(
                rf"{re.escape(term)}(涉及|出现|引用|提及|不接受|接受|要求|列出|设置|规定|统计|发现|检出)",
                text,
            ):
                terms.append(term)
        elif matched:
            terms.append(term)
    if re.search(r"(?<!不)(?<!未)(?<!无)符合要求", text):
        terms.append("符合要求")
    return terms


def model_quality_flags(row: dict[str, Any]) -> list[dict[str, str]]:
    """Add generic model-output quality markers without changing model verdict."""
    result = row.get("model_result", {}) or {}
    verdict = result.get("verdict")
    flags: list[dict[str, str]] = []
    if result.get("recovered_from_invalid_json"):
        flags.append(
            {
                "code": "invalid_json_recovered",
                "level": "structure_error",
                "message": "模型输出不是严格 JSON，运行时仅恢复了部分字段；该结果不得直接进入业务风险或 F1 命中。",
            }
        )
    text = _result_text(result)
    meta = row.get("nbd", {}) or {}
    nbd_text = " ".join([str(meta.get("title") or ""), str(meta.get("risk_tip") or ""), str(meta.get("revision_suggestion") or "")])
    combined_text = f"{nbd_text} {text}"
    windows = row.get("windows") or []
    window_by_id = {
        str(window.get("window_id") or ""): window
        for window in windows
        if isinstance(window, dict) and str(window.get("window_id") or "")
    }
    window_line_anchors = {
        str(window.get("line_anchor") or "")
        for window in windows
        if isinstance(window, dict) and str(window.get("line_anchor") or "")
    }
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
    positive_candidates = [
        candidate for candidate in candidates
        if isinstance(candidate, dict) and str(candidate.get("candidate_verdict") or verdict or "").strip() in POSITIVE_VERDICTS
    ]
    if verdict in POSITIVE_VERDICTS:
        if not positive_candidates:
            flags.append(
                {
                    "code": "positive_verdict_without_candidate",
                    "level": "structure_error",
                    "message": "模型输出为命中或待人工复核，但未提供对应的结构化候选证据。",
                }
            )
        for index, candidate in enumerate(positive_candidates, start=1):
            candidate_id = str(candidate.get("candidate_id") or candidate.get("window_id") or "").strip()
            line_anchor = str(candidate.get("line_anchor") or candidate.get("line") or "").strip()
            excerpt = str(candidate.get("excerpt") or "").strip()
            if not candidate_id:
                flags.append(
                    {
                        "code": "candidate_id_missing",
                        "level": "structure_error",
                        "message": f"第 {index} 个正向候选缺少 candidate_id，无法追溯到候选窗口。",
                    }
                )
            elif window_by_id and candidate_id not in window_by_id:
                flags.append(
                    {
                        "code": "candidate_id_not_found",
                        "level": "structure_error",
                        "message": f"第 {index} 个正向候选引用的 candidate_id 不存在：{candidate_id}。",
                    }
                )
            if not line_anchor:
                flags.append(
                    {
                        "code": "candidate_line_anchor_missing",
                        "level": "structure_error",
                        "message": f"第 {index} 个正向候选缺少 line_anchor，无法参与行号级评测。",
                    }
                )
            elif window_line_anchors and line_anchor not in window_line_anchors and not _line_anchor_overlaps_windows(line_anchor, window_line_anchors):
                flags.append(
                    {
                        "code": "candidate_line_anchor_not_found",
                        "level": "structure_error",
                        "message": f"第 {index} 个正向候选 line_anchor 未对应任何候选窗口：{line_anchor}。",
                    }
                )
            if not excerpt:
                flags.append(
                    {
                        "code": "candidate_excerpt_missing",
                        "level": "structure_error",
                        "message": f"第 {index} 个正向候选缺少原文摘录，无法复核证据。",
                    }
                )
    if verdict == "命中":
        verdict_text = _verdict_text(result)
        terms = _contradiction_terms(verdict_text)
        if terms:
            flags.append(
                {
                    "code": "verdict_contradiction",
                    "level": "review_required",
                    "message": "模型 verdict 为命中，但说明中出现反证语义：" + "、".join(terms[:5]),
                }
            )
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


def repair_positive_candidate_structure(row: dict[str, Any], max_candidates: int = 8) -> bool:
    """Do not synthesize positive evidence in the daily review runtime.

    A business hit must come from model-emitted structured candidates. The runtime may
    validate, prune, and flag model output, but it must not create candidate evidence
    from recalled windows after the model omitted it.
    """
    return False


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
        in {
            "verdict_contradiction",
            "template_only_hit",
            "primary_window_missing",
            "missing_calculation",
            "invalid_json_recovered",
            "positive_verdict_without_candidate",
            "candidate_id_missing",
            "candidate_id_not_found",
            "candidate_line_anchor_missing",
            "candidate_line_anchor_not_found",
            "candidate_excerpt_missing",
        }
        for flag in row_quality_flags(row)
    )


def clean_inline(text: Any, limit: int = 280) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def candidate_evidence(row: dict[str, Any]) -> dict[str, Any]:
    result = row.get("model_result", {}) or {}
    raw_candidates = result.get("candidates") or []
    candidates = [candidate for candidate in raw_candidates if isinstance(candidate, dict)]
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
    raw_windows = row.get("windows") or []
    windows = [window for window in raw_windows if isinstance(window, dict)]
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
    """Presentation-only labels based on structured metadata, not evidence keywords."""
    meta = row.get("nbd", {}) or {}
    for key in ("issue_family", "item_scope", "finding_type"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    clause_type = str(evidence.get("clause_type") or "").strip()
    return clause_type or "其他"


def business_issue_rank(rows: list[dict[str, Any]]) -> int:
    """Presentation priority for business reports, based on issue family only."""
    if not rows:
        return 99
    evidence = best_group_evidence(rows)
    label = business_family_label(rows[0], evidence)
    if label == "其他":
        return 9
    return 1


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
