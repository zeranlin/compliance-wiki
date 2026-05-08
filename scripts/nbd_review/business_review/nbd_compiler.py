"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path
from typing import Any

from shared.schemas import NBD_GOVERNANCE_IR_SCHEMA, NBD_IR_SCHEMA, NBD_PROMPT_IR_SCHEMA, NBD_RECALL_IR_SCHEMA, NBDItem
from shared.utils import read_text, relative_path, run_path, vcc, write_text

PLACEHOLDER_TERMS = ["待 smoke", "待smoke", "待预检", "待验证", "待通过 fixture"]
PAGE_PLACEHOLDER_TERMS = [
    *PLACEHOLDER_TERMS,
    "待补充真实样例",
    "待通过 fixture 或真实样本",
    "示例：待补充",
    "反例：待补充",
]
GOVERNANCE_ONLY_SECTIONS = ["调试备注", "小模型可执行性自检"]

def parse_nbd_file(path: Path) -> NBDItem:
    markdown = read_text(path)
    meta = vcc.parse_frontmatter(markdown)
    nbd_id = str(meta.get("id") or vcc.extract_checkpoint_id(markdown)).strip()
    title = str(meta.get("title") or vcc.extract_title(markdown)).strip()
    keyword_groups = vcc.parse_keyword_groups(markdown)
    item = NBDItem(
        nbd_id=nbd_id,
        title=title,
        path=path,
        markdown=markdown,
        meta=meta,
        keyword_groups=keyword_groups,
        recall_profile=parse_recall_profile(markdown, keyword_groups),
        compact_text="",
    )
    item.compact_text = compact_text_from_prompt_ir(nbd_prompt_ir_from_item(item))
    return item


def nbd_ir_from_item(item: NBDItem) -> dict[str, Any]:
    sections = {
        "goal": vcc.extract_section(item.markdown, "审查目标"),
        "applicability": vcc.extract_section(item.markdown, "适用范围"),
        "review_steps": vcc.extract_section(item.markdown, "专项判断方法") or vcc.extract_section(item.markdown, "审查步骤"),
        "base_conditions": vcc.extract_section(item.markdown, "基础命中条件"),
        "hit_conditions": vcc.extract_section(item.markdown, "命中条件"),
        "exclusion_conditions": vcc.extract_section(item.markdown, "排除条件"),
        "verdict_policy": vcc.extract_section(item.markdown, "判断结果分流"),
        "manual_review_boundaries": vcc.extract_section(item.markdown, "待人工复核边界") or vcc.extract_section(item.markdown, "边界例"),
    }
    return {
        "schema_version": NBD_IR_SCHEMA,
        "id": item.nbd_id,
        "title": item.title,
        "status": item.meta.get("status", ""),
        "source_path": relative_path(item.path),
        "frontmatter": item.meta,
        "prompt_text": item.compact_text,
        "scope": {
            "item_scope": item.meta.get("item_scope", ""),
            "risk_level": item.meta.get("risk_level", ""),
            "finding_type": item.meta.get("finding_type", ""),
            "standard_scope": item.meta.get("standard_scope", ""),
            "source_region": item.meta.get("source_region", ""),
            "applicable_regions": item.meta.get("applicable_regions", []),
        },
        "recall": {
            "keyword_groups": item.keyword_groups,
            "machine_recall": item.recall_profile,
            "candidate_rules": vcc.extract_section(item.markdown, "候选召回规则"),
            "context_rules": vcc.extract_section(item.markdown, "上下文读取规则"),
        },
        "sop": sections,
        "output_constraints": parse_output_constraints(item.markdown),
        "output": {
            "risk_tip": vcc.extract_section(item.markdown, "风险提示"),
            "revision_suggestion": vcc.extract_section(item.markdown, "修改建议"),
            "legal_basis": vcc.extract_section(item.markdown, "审查依据"),
        },
        "lint": lint_nbd_ir(item, sections),
    }


def scope_from_item(item: NBDItem) -> dict[str, Any]:
    return {
        "item_scope": item.meta.get("item_scope", ""),
        "risk_level": item.meta.get("risk_level", ""),
        "finding_type": item.meta.get("finding_type", ""),
        "standard_scope": item.meta.get("standard_scope", ""),
        "source_region": item.meta.get("source_region", ""),
        "applicable_regions": item.meta.get("applicable_regions", []),
    }


def prompt_sections_from_item(item: NBDItem) -> dict[str, str]:
    return {
        "goal": vcc.extract_section(item.markdown, "审查目标"),
        "applicability": vcc.extract_section(item.markdown, "适用范围"),
        "not_applicable": vcc.extract_section(item.markdown, "不适用范围"),
        "preconditions": vcc.extract_section(item.markdown, "基础命中条件"),
        "review_steps": vcc.extract_section(item.markdown, "专项判断方法") or vcc.extract_section(item.markdown, "审查步骤"),
        "hit_conditions": vcc.extract_section(item.markdown, "命中条件"),
        "exclusion_conditions": vcc.extract_section(item.markdown, "排除条件"),
        "manual_review_boundaries": vcc.extract_section(item.markdown, "待人工复核边界") or vcc.extract_section(item.markdown, "边界例"),
        "verdict_policy": vcc.extract_section(item.markdown, "判断结果分流"),
    }


def nbd_recall_ir_from_item(item: NBDItem) -> dict[str, Any]:
    recall = item.recall_profile
    return {
        "schema_version": NBD_RECALL_IR_SCHEMA,
        "id": item.nbd_id,
        "title": item.title,
        "status": item.meta.get("status", ""),
        "source_path": relative_path(item.path),
        "terms": list(recall.get("terms") or []),
        "formal_terms": list(recall.get("formal_terms") or []),
        "noise_terms": list(recall.get("noise_terms") or []),
        "regex_terms": list(recall.get("regex_terms") or []),
        "conflict_terms": list(recall.get("conflict_terms") or []),
        "completeness_terms": dict(recall.get("completeness_terms") or {}),
        "candidate_rules": vcc.extract_section(item.markdown, "候选召回规则"),
        "context_rules": vcc.extract_section(item.markdown, "上下文读取规则"),
        "neighbor_before": int(recall.get("neighbor_before") or 0),
        "neighbor_after": int(recall.get("neighbor_after") or 0),
        "similar_before": int(recall.get("similar_before") or 0),
        "similar_after": int(recall.get("similar_after") or 0),
        "max_primary_windows": int(recall.get("max_primary_windows") or 0),
        "max_support_windows": int(recall.get("max_support_windows") or 0),
        "enabled": bool(recall.get("enabled")),
        "reason": str(recall.get("reason") or ""),
    }


def nbd_prompt_ir_from_item(item: NBDItem) -> dict[str, Any]:
    sections = prompt_sections_from_item(item)
    return {
        "schema_version": NBD_PROMPT_IR_SCHEMA,
        "id": item.nbd_id,
        "title": item.title,
        "status": item.meta.get("status", ""),
        "source_path": relative_path(item.path),
        "scope": scope_from_item(item),
        "goal": sections["goal"],
        "applicability": sections["applicability"],
        "not_applicable": sections["not_applicable"],
        "preconditions": sections["preconditions"],
        "review_steps": sections["review_steps"],
        "hit_conditions": sections["hit_conditions"],
        "exclusion_conditions": sections["exclusion_conditions"],
        "manual_review_boundaries": sections["manual_review_boundaries"],
        "verdict_policy": sections["verdict_policy"],
        "output_constraints": parse_output_constraints(item.markdown),
        "risk_tip": vcc.extract_section(item.markdown, "风险提示"),
        "revision_suggestion": vcc.extract_section(item.markdown, "修改建议"),
        "legal_basis": vcc.extract_section(item.markdown, "审查依据"),
    }


def nbd_governance_ir_from_item(item: NBDItem) -> dict[str, Any]:
    return {
        "schema_version": NBD_GOVERNANCE_IR_SCHEMA,
        "id": item.nbd_id,
        "title": item.title,
        "status": item.meta.get("status", ""),
        "version": item.meta.get("version", ""),
        "source_path": relative_path(item.path),
        "source_material": item.meta.get("source_material", ""),
        "source_row": item.meta.get("source_row", ""),
        "last_reviewed": item.meta.get("last_reviewed", ""),
        "validation_records": [],
        "related_audits": [],
        "change_log": vcc.extract_section(item.markdown, "调试备注"),
    }


def lint_required_fields(payload: dict[str, Any], required_fields: list[str]) -> list[str]:
    missing: list[str] = []
    for field in required_fields:
        if field not in payload:
            missing.append(field)
    return missing


def lint_split_ir(item: NBDItem) -> dict[str, Any]:
    recall_ir = nbd_recall_ir_from_item(item)
    prompt_ir = nbd_prompt_ir_from_item(item)
    governance_ir = nbd_governance_ir_from_item(item)
    categories = {
        "recall_ir": {"warnings": [], "errors": []},
        "prompt_ir": {"warnings": [], "errors": []},
        "governance_ir": {"warnings": [], "errors": []},
    }

    for field in lint_required_fields(
        recall_ir,
        [
            "id",
            "title",
            "source_path",
            "terms",
            "formal_terms",
            "noise_terms",
            "regex_terms",
            "conflict_terms",
            "completeness_terms",
            "candidate_rules",
            "context_rules",
            "neighbor_before",
            "neighbor_after",
        ],
    ):
        categories["recall_ir"]["errors"].append(f"Recall IR 缺少字段：{field}")
    for field in lint_required_fields(
        prompt_ir,
        [
            "id",
            "title",
            "goal",
            "applicability",
            "not_applicable",
            "preconditions",
            "hit_conditions",
            "exclusion_conditions",
            "manual_review_boundaries",
            "verdict_policy",
            "risk_tip",
            "revision_suggestion",
            "legal_basis",
        ],
    ):
        categories["prompt_ir"]["errors"].append(f"Prompt IR 缺少字段：{field}")
    for field in lint_required_fields(
        governance_ir,
        ["id", "title", "source_material", "source_row", "validation_records", "change_log", "related_audits"],
    ):
        categories["governance_ir"]["errors"].append(f"Governance IR 缺少字段：{field}")

    if not recall_ir.get("terms"):
        categories["recall_ir"]["errors"].append("Recall IR terms 为空")
    if not recall_ir.get("candidate_rules"):
        categories["recall_ir"]["warnings"].append("Recall IR candidate_rules 为空")
    if not recall_ir.get("context_rules"):
        categories["recall_ir"]["warnings"].append("Recall IR context_rules 为空")
    for field in ["goal", "hit_conditions", "exclusion_conditions", "verdict_policy"]:
        if not prompt_ir.get(field):
            categories["prompt_ir"]["warnings"].append(f"Prompt IR {field} 为空")
    prompt_text = json.dumps(prompt_ir, ensure_ascii=False)
    for term in PLACEHOLDER_TERMS:
        if term in prompt_text:
            categories["prompt_ir"]["warnings"].append(f"Prompt IR 含历史占位：{term}")
            break
    if "调试备注" in prompt_text or "小模型可执行性自检" in prompt_text:
        categories["prompt_ir"]["warnings"].append("Prompt IR 含治理段落文本")

    warnings: list[str] = []
    errors: list[str] = []
    for values in categories.values():
        warnings.extend(values["warnings"])
        errors.extend(values["errors"])
    return {"valid": not errors, "warnings": warnings, "errors": errors, "categories": categories}


def lint_nbd_ir(item: NBDItem, sections: dict[str, str]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    categories = {
        "recall": {"warnings": [], "errors": []},
        "sop": {"warnings": [], "errors": []},
        "verdict_policy": {"warnings": [], "errors": []},
        "evidence_policy": {"warnings": [], "errors": []},
        "output": {"warnings": [], "errors": []},
        "governance": {"warnings": [], "errors": []},
    }

    def warn(category: str, message: str) -> None:
        categories[category]["warnings"].append(message)
        warnings.append(message)

    def error(category: str, message: str) -> None:
        categories[category]["errors"].append(message)
        errors.append(message)

    if item.meta.get("status") == "maintained" and not item.recall_profile:
        warn("recall", "maintained NBD 缺少 ## 机器召回配置")
    if item.meta.get("status") == "maintained":
        for term in PAGE_PLACEHOLDER_TERMS:
            if term in item.markdown:
                error("governance", f"maintained NBD 含历史占位：{term}")
        for section_title in GOVERNANCE_ONLY_SECTIONS:
            if vcc.extract_section(item.markdown, section_title):
                error("governance", f"maintained NBD 含治理段落：{section_title}")
    if not item.keyword_groups and not item.recall_profile:
        error("recall", "recall 为空：缺少定位与召回剖面和机器召回配置")
    if item.recall_profile:
        if not item.recall_profile.get("terms"):
            error("recall", "machine_recall 缺少 terms")
        if not item.recall_profile.get("formal_terms"):
            warn("evidence_policy", "machine_recall 缺少正式证据词")
        if not item.recall_profile.get("noise_terms"):
            warn("evidence_policy", "machine_recall 缺少降权噪声词")
    if not vcc.extract_section(item.markdown, "候选召回规则"):
        warn("recall", "recall 缺少候选召回规则")
    if not vcc.extract_section(item.markdown, "上下文读取规则"):
        warn("evidence_policy", "evidence_policy 缺少上下文读取规则")
    if not sections.get("hit_conditions"):
        warn("sop", "sop 缺少命中条件")
    if not sections.get("exclusion_conditions"):
        warn("sop", "sop 缺少排除条件")
    if not sections.get("review_steps"):
        warn("sop", "sop 缺少专项判断方法/审查步骤")
    if not sections.get("base_conditions"):
        warn("sop", "sop 缺少基础命中条件")
    if not sections.get("verdict_policy"):
        warn("verdict_policy", "verdict_policy 缺少判断结果分流")
    else:
        verdict_text = sections.get("verdict_policy") or ""
        for verdict in ["命中", "待人工复核", "不命中"]:
            if verdict not in verdict_text:
                warn("verdict_policy", f"verdict_policy 缺少 {verdict} 分流说明")
    if not sections.get("manual_review_boundaries"):
        warn("verdict_policy", "verdict_policy 缺少待人工复核边界/边界例")
    if not vcc.extract_section(item.markdown, "风险提示"):
        warn("output", "output 缺少风险提示")
    if not vcc.extract_section(item.markdown, "修改建议"):
        warn("output", "output 缺少修改建议")
    if not vcc.extract_section(item.markdown, "易误报场景"):
        warn("evidence_policy", "evidence_policy 缺少易误报场景")
    return {"valid": not errors, "warnings": warnings, "errors": errors, "categories": categories}


def parse_recall_profile(markdown: str, keyword_groups: dict[str, list[str]]) -> dict[str, Any]:
    """Read machine-executable recall hints from the NBD itself.

    The engine owns only the interpreter. NBD-specific terms, evidence priority,
    noise terms, and heading expansion live in each NBD under ## 机器召回配置.
    """
    section = vcc.extract_section(markdown, "机器召回配置")
    if not section:
        return {}
    groups: dict[str, list[str]] = {}
    current_group = ""
    reason = ""
    neighbor_before = 0
    neighbor_after = 1
    similar_before = 0
    similar_after = 0
    max_primary_windows = 0
    max_support_windows = 0
    enabled = True
    for line in section.splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current_group = heading.group(1).strip()
            groups.setdefault(current_group, [])
            continue
        item = re.match(r"^-\s+(.+?)\s*$", line)
        if not item:
            continue
        value = item.group(1).strip().rstrip("。；;")
        if not value:
            continue
        key_value = re.match(r"^([^：:]+)[：:]\s*(.+?)\s*$", value)
        if key_value:
            key = key_value.group(1).strip()
            raw = key_value.group(2).strip()
            if key in {"召回原因", "reason"}:
                reason = raw
                continue
            if key in {"标题后继块数", "neighbor_after", "后继块数"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    neighbor_after = max(0, int(nums[0]))
                continue
            if key in {"标题前置块数", "neighbor_before", "前置块数"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    neighbor_before = max(0, int(nums[0]))
                continue
            if key in {"同类证据前置块数", "similar_before", "相邻同类前置块数"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    similar_before = max(0, int(nums[0]))
                continue
            if key in {"同类证据后继块数", "similar_after", "相邻同类后继块数"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    similar_after = max(0, int(nums[0]))
                continue
            if key in {"主候选保留数", "max_primary_windows", "primary_windows"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    max_primary_windows = max(0, int(nums[0]))
                continue
            if key in {"辅助候选保留数", "max_support_windows", "support_windows"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    max_support_windows = max(0, int(nums[0]))
                continue
            if key in {"启用", "enabled"}:
                enabled = raw.lower() not in {"false", "no", "0", "否", "不启用"}
                continue
        if current_group:
            groups.setdefault(current_group, []).append(value)

    terms = []
    formal_terms = []
    noise_terms = []
    regex_terms: list[str] = []
    conflict_terms: list[str] = []
    completeness_terms: dict[str, list[str]] = {}
    for name, values in groups.items():
        if any(part in name for part in ["主召回", "召回词", "对象", "支持", "章节", "冲突", "并列"]):
            terms.extend(values)
        if any(part in name for part in ["正式", "反证", "升权", "高价值"]):
            terms.extend(values)
            formal_terms.extend(values)
        if any(part in name for part in ["正则", "regex", "模式"]):
            regex_terms.extend(values)
        if any(part in name for part in ["冲突反证", "冲突排除", "互斥", "排斥"]):
            conflict_terms.extend(values)
        if any(part in name for part in ["完整性", "要素"]):
            label = re.sub(r"^(完整性|证据完整性|完整性要素)[-：: ]*", "", name).strip() or name
            completeness_terms[label] = list(dict.fromkeys(value for value in values if value))
        if any(part in name for part in ["降权", "噪声", "排除"]):
            noise_terms.extend(values)
    if not terms:
        terms.extend(group_words(keyword_groups, "对象", "支持", "章节"))
    terms = list(dict.fromkeys(term for term in terms if term))
    return {
        "enabled": enabled and bool(terms),
        "terms": terms,
        "formal_terms": list(dict.fromkeys(term for term in formal_terms if term)),
        "noise_terms": list(dict.fromkeys(term for term in noise_terms if term)),
        "regex_terms": list(dict.fromkeys(term for term in regex_terms if term)),
        "conflict_terms": list(dict.fromkeys(term for term in conflict_terms if term)),
        "completeness_terms": completeness_terms,
        "reason": reason or "NBD 机器召回配置",
        "neighbor_before": neighbor_before,
        "neighbor_after": neighbor_after,
        "similar_before": similar_before,
        "similar_after": similar_after,
        "max_primary_windows": max_primary_windows,
        "max_support_windows": max_support_windows,
    }


def parse_output_constraints(markdown: str) -> dict[str, Any]:
    """Parse generic model-output constraints declared by an NBD markdown page.

    These constraints are executable protocol hints, not business rules owned by
    the runtime. The runtime only interprets simple structural constraints such
    as candidate count, section role, and candidate-window completeness keys.
    """
    section = vcc.extract_section(markdown, "机器输出约束")
    if not section:
        return {}
    constraints: dict[str, Any] = {}
    current_group = ""
    groups: dict[str, list[str]] = {}
    for line in section.splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current_group = heading.group(1).strip()
            groups.setdefault(current_group, [])
            continue
        item = re.match(r"^-\s+(.+?)\s*$", line)
        if not item:
            continue
        value = item.group(1).strip().rstrip("。；;")
        if not value:
            continue
        key_value = re.match(r"^([^：:]+)[：:]\s*(.+?)\s*$", value)
        if key_value:
            key = key_value.group(1).strip()
            raw = key_value.group(2).strip()
            if key in {"正向候选最多数量", "max_positive_candidates"}:
                nums = re.findall(r"\d+", raw)
                if nums:
                    constraints["max_positive_candidates"] = max(0, int(nums[0]))
                continue
            if key in {"正向候选允许章节角色", "allowed_section_roles"}:
                constraints["allowed_section_roles"] = split_constraint_values(raw)
                continue
            if key in {"正向候选排除章节角色", "excluded_section_roles"}:
                constraints["excluded_section_roles"] = split_constraint_values(raw)
                continue
            if key in {"正向候选必备完整性", "required_completeness"}:
                constraints["required_completeness"] = split_constraint_values(raw)
                continue
            if key in {"正向候选排除文本模式", "excluded_text_patterns"}:
                constraints["excluded_text_patterns"] = split_constraint_patterns(raw)
                continue
            if key in {"正向候选选择策略", "positive_selection_strategy"}:
                constraints["positive_selection_strategy"] = raw
                continue
        if current_group:
            groups.setdefault(current_group, []).append(value)
    for name, values in groups.items():
        if "允许章节" in name:
            constraints["allowed_section_roles"] = list(dict.fromkeys(values))
        elif "排除章节" in name:
            constraints["excluded_section_roles"] = list(dict.fromkeys(values))
        elif "完整性" in name or "必备" in name:
            constraints["required_completeness"] = list(dict.fromkeys(values))
        elif "排除文本" in name or "排除模式" in name:
            constraints["excluded_text_patterns"] = list(dict.fromkeys(values))
        else:
            protocol_notes = constraints.setdefault("protocol_notes", [])
            protocol_notes.extend(values)
    if "protocol_notes" in constraints:
        constraints["protocol_notes"] = list(dict.fromkeys(constraints["protocol_notes"]))
    return {key: value for key, value in constraints.items() if value not in (None, [], {})}


def split_constraint_values(raw: str) -> list[str]:
    values = re.split(r"[,，、/|]\s*|\s+", raw)
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def split_constraint_patterns(raw: str) -> list[str]:
    values = re.split(r"[；;]\s*", raw)
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def parse_theme_ids(path: Path) -> list[str]:
    meta = vcc.parse_frontmatter(read_text(path))
    value = meta.get("nbd_ids")
    return [str(item).strip() for item in value] if isinstance(value, list) else []


def expand_nbd_files(args: Any) -> list[Path]:
    by_id: dict[str, Path] = {}
    all_files = [Path(p).resolve() for p in glob.glob(args.nbd_glob or "")]
    for path in all_files:
        if path.is_file():
            try:
                item = parse_nbd_file(path)
            except Exception:
                continue
            by_id[item.nbd_id] = path

    selected: list[Path] = []
    requested = list(args.nbd or [])
    if args.theme:
        requested.extend(parse_theme_ids(args.theme))
    if requested:
        for value in requested:
            path = Path(value)
            if path.exists():
                selected.append(path.resolve())
            elif value in by_id:
                selected.append(by_id[value])
            else:
                raise RuntimeError(f"未找到 NBD：{value}")
    else:
        selected = all_files

    seen: set[str] = set()
    result: list[Path] = []
    for path in selected:
        key = str(path)
        if path.is_file() and key not in seen:
            result.append(path)
            seen.add(key)
    return sorted(result)


def iter_nbd_ir_payloads(output_dir: Path, requested: list[str] | None = None) -> list[dict[str, Any]]:
    requested_values = [str(value).strip() for value in requested or [] if str(value).strip()]
    requested_ids = {Path(value).stem if value.endswith(".json") else Path(value).stem if Path(value).suffix else value for value in requested_values}
    payloads: list[dict[str, Any]] = []
    for path in sorted((output_dir / "nbd-ir").glob("*.json")):
        payload = json.loads(read_text(path))
        nbd_id = str(payload.get("id") or path.stem)
        if requested_ids and nbd_id not in requested_ids and path.name not in requested_ids:
            continue
        if payload.get("schema_version") != NBD_IR_SCHEMA:
            raise RuntimeError(f"NBD IR schema 不匹配：{run_path(output_dir, path)}")
        payloads.append(payload)
    if requested_ids and not payloads:
        raise RuntimeError("未在 nbd-ir/ 中找到请求的 NBD IR")
    return payloads


def compact_text_from_prompt_ir(payload: dict[str, Any]) -> str:
    lines = [f"# {payload.get('id', '')} {payload.get('title', '')}".strip()]
    sections = [
        ("审查目标", payload.get("goal")),
        ("适用范围", payload.get("applicability")),
        ("不适用范围", payload.get("not_applicable")),
        ("专项判断方法", payload.get("review_steps")),
        ("基础命中条件", payload.get("preconditions")),
        ("命中条件", payload.get("hit_conditions")),
        ("排除条件", payload.get("exclusion_conditions")),
        ("待人工复核边界", payload.get("manual_review_boundaries")),
        ("判断结果分流", payload.get("verdict_policy")),
        ("机器输出约束", render_output_constraints(payload.get("output_constraints"))),
        ("风险提示", payload.get("risk_tip")),
        ("修改建议", payload.get("revision_suggestion")),
        ("审查依据", payload.get("legal_basis")),
    ]
    for title, value in sections:
        if value:
            lines.extend([f"## {title}", str(value)])
    return "\n\n".join(lines)


def render_output_constraints(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    lines: list[str] = []
    if value.get("max_positive_candidates") is not None:
        lines.append(f"- 正向候选最多数量：{value.get('max_positive_candidates')}")
    if value.get("allowed_section_roles"):
        lines.append("- 正向候选允许章节角色：" + "、".join(str(item) for item in value.get("allowed_section_roles") or []))
    if value.get("excluded_section_roles"):
        lines.append("- 正向候选排除章节角色：" + "、".join(str(item) for item in value.get("excluded_section_roles") or []))
    if value.get("required_completeness"):
        lines.append("- 正向候选必备完整性：" + "、".join(str(item) for item in value.get("required_completeness") or []))
    if value.get("protocol_notes"):
        lines.append("### 正向候选代表行协议")
        lines.extend(f"- {str(item)}" for item in value.get("protocol_notes") or [])
    return "\n".join(lines)


def compact_text_from_nbd_ir(payload: dict[str, Any]) -> str:
    prompt_ir = payload.get("prompt_ir")
    if isinstance(prompt_ir, dict):
        return compact_text_from_prompt_ir(prompt_ir)
    legacy_prompt_ir = {
        "id": payload.get("id", ""),
        "title": payload.get("title", ""),
        "goal": (payload.get("sop") or {}).get("goal"),
        "applicability": (payload.get("sop") or {}).get("applicability"),
        "not_applicable": "",
        "review_steps": (payload.get("sop") or {}).get("review_steps"),
        "preconditions": (payload.get("sop") or {}).get("base_conditions"),
        "hit_conditions": (payload.get("sop") or {}).get("hit_conditions"),
        "exclusion_conditions": (payload.get("sop") or {}).get("exclusion_conditions"),
        "manual_review_boundaries": (payload.get("sop") or {}).get("manual_review_boundaries"),
        "verdict_policy": (payload.get("sop") or {}).get("verdict_policy"),
        "output_constraints": payload.get("output_constraints") or {},
        "risk_tip": (payload.get("output") or {}).get("risk_tip"),
        "revision_suggestion": (payload.get("output") or {}).get("revision_suggestion"),
        "legal_basis": (payload.get("output") or {}).get("legal_basis"),
    }
    return compact_text_from_prompt_ir(legacy_prompt_ir)


def prompt_ir_payload_for(output_dir: Path, nbd_id: str) -> dict[str, Any] | None:
    path = output_dir / "prompt-ir" / f"{nbd_id}.json"
    if not path.exists():
        return None
    return json.loads(read_text(path))


def item_from_nbd_ir(payload: dict[str, Any], prompt_ir: dict[str, Any] | None = None) -> NBDItem:
    if prompt_ir:
        payload = {**payload, "prompt_ir": prompt_ir}
    source_path = Path(str(payload.get("source_path") or ""))
    meta = dict(payload.get("frontmatter") or {})
    meta.setdefault("id", payload.get("id", ""))
    meta.setdefault("title", payload.get("title", ""))
    meta.setdefault("status", payload.get("status", ""))
    for key, value in (payload.get("scope") or {}).items():
        meta.setdefault(key, value)
    output_constraints = payload.get("output_constraints")
    if not output_constraints and isinstance(prompt_ir, dict):
        output_constraints = prompt_ir.get("output_constraints")
    if isinstance(output_constraints, dict) and output_constraints:
        meta["_output_constraints"] = output_constraints
    recall = payload.get("recall") or {}
    return NBDItem(
        nbd_id=str(payload.get("id") or ""),
        title=str(payload.get("title") or ""),
        path=source_path,
        markdown="",
        meta=meta,
        keyword_groups=dict(recall.get("keyword_groups") or {}),
        recall_profile=dict(recall.get("machine_recall") or {}),
        compact_text=compact_text_from_nbd_ir(payload),
    )


def load_items_from_nbd_ir(output_dir: Path, requested: list[str] | None = None) -> list[NBDItem]:
    items: list[NBDItem] = []
    for payload in iter_nbd_ir_payloads(output_dir, requested):
        nbd_id = str(payload.get("id") or "")
        items.append(item_from_nbd_ir(payload, prompt_ir_payload_for(output_dir, nbd_id)))
    return items


def nbd_lint_report_payload(items: list[NBDItem]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    category_summary: dict[str, dict[str, int]] = {}
    for item in items:
        payload = nbd_ir_from_item(item)
        lint = payload.get("lint") or {}
        split_lint = lint_split_ir(item)
        for category, values in (lint.get("categories") or {}).items():
            summary = category_summary.setdefault(category, {"warnings": 0, "errors": 0})
            summary["warnings"] += len(values.get("warnings") or [])
            summary["errors"] += len(values.get("errors") or [])
        for category, values in (split_lint.get("categories") or {}).items():
            summary = category_summary.setdefault(category, {"warnings": 0, "errors": 0})
            summary["warnings"] += len(values.get("warnings") or [])
            summary["errors"] += len(values.get("errors") or [])
        warnings = list(lint.get("warnings") or []) + list(split_lint.get("warnings") or [])
        errors = list(lint.get("errors") or []) + list(split_lint.get("errors") or [])
        records.append(
            {
                "id": payload.get("id"),
                "title": payload.get("title"),
                "status": payload.get("status"),
                "source_path": payload.get("source_path"),
                "valid": bool(lint.get("valid")) and bool(split_lint.get("valid")),
                "warning_count": len(warnings),
                "error_count": len(errors),
                "warnings": warnings,
                "errors": errors,
                "categories": {**(lint.get("categories") or {}), **(split_lint.get("categories") or {})},
            }
        )
    return {
        "schema_version": "nbd-ir-lint/v1",
        "nbd_count": len(records),
        "valid_count": sum(1 for record in records if record.get("valid")),
        "error_count": sum(int(record.get("error_count") or 0) for record in records),
        "warning_count": sum(int(record.get("warning_count") or 0) for record in records),
        "category_summary": category_summary,
        "records": records,
    }


def render_nbd_lint_report(report: dict[str, Any]) -> str:
    lines = [
        "# NBD IR Lint Report",
        "",
        f"- NBD 总数：{report.get('nbd_count', 0)}",
        f"- valid：{report.get('valid_count', 0)}",
        f"- error：{report.get('error_count', 0)}",
        f"- warning：{report.get('warning_count', 0)}",
        "",
        "## 分类统计",
        "",
        "| 分类 | warnings | errors |",
        "|---|---:|---:|",
    ]
    for category, summary in sorted((report.get("category_summary") or {}).items()):
        lines.append(f"| {category} | {summary.get('warnings', 0)} | {summary.get('errors', 0)} |")
    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| NBD | valid | warnings | errors | 主要问题 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for record in report.get("records") or []:
        issues = list(record.get("errors") or []) + list(record.get("warnings") or [])
        issue_text = "；".join(str(issue) for issue in issues[:5]).replace("|", "\\|")
        lines.append(
            f"| {record.get('id')} {record.get('title')} | {record.get('valid')} | "
            f"{record.get('warning_count', 0)} | {record.get('error_count', 0)} | {issue_text} |"
        )
    return "\n".join(lines) + "\n"


def write_nbd_lint_report(output_dir: Path, items: list[NBDItem]) -> dict[str, Any]:
    report = nbd_lint_report_payload(items)
    write_text(output_dir / "nbd-ir-lint.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "nbd-ir-lint.md", render_nbd_lint_report(report))
    return report



def write_nbd_ir_artifacts(output_dir: Path, items: list[NBDItem]) -> None:
    for item in items:
        write_text(output_dir / "nbd-ir" / f"{item.nbd_id}.json", json.dumps(nbd_ir_from_item(item), ensure_ascii=False, indent=2) + "\n")
        write_text(output_dir / "recall-ir" / f"{item.nbd_id}.json", json.dumps(nbd_recall_ir_from_item(item), ensure_ascii=False, indent=2) + "\n")
        write_text(output_dir / "prompt-ir" / f"{item.nbd_id}.json", json.dumps(nbd_prompt_ir_from_item(item), ensure_ascii=False, indent=2) + "\n")
        write_text(output_dir / "governance-ir" / f"{item.nbd_id}.json", json.dumps(nbd_governance_ir_from_item(item), ensure_ascii=False, indent=2) + "\n")
