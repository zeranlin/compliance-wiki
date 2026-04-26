#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


ROOT = Path("/Users/linzeran/code/2026-zn/test_target/compliance-wiki")
RAW = ROOT / "raw"
SOURCE_DIR = RAW / "source-files" / "深圳10个品目批注文件"
MANIFEST_DIR = RAW / "manifests"
SCAN_DIR = RAW / "full-risk-scans"
COMMENT_DIR = RAW / "extracted-comments"
NUMBERED_DIR = RAW / "numbered-text"
AUDIT_DIR = ROOT / "wiki" / "audits"
WIKI_DIR = ROOT / "wiki"

LEGAL_ROOT = ROOT / "law-wiki"
LEGAL_REFS = {
    "gov_law": LEGAL_ROOT / "sources" / "中华人民共和国政府采购法.md",
    "reg_impl": LEGAL_ROOT / "sources" / "中华人民共和国政府采购法实施条例.md",
    "bid_measure": LEGAL_ROOT / "sources" / "政府采购货物和服务招标投标管理办法.md",
    "topic_bidding": LEGAL_ROOT / "topics" / "招标投标.md",
    "concept_need": LEGAL_ROOT / "concepts" / "采购需求.md",
    "concept_qualification": LEGAL_ROOT / "concepts" / "资格审查.md",
}

TODAY = date(2026, 4, 20).isoformat()
GOODS_TYPES = {"信息化设备", "医疗设备", "家具", "教学仪器", "用具", "装具"}
SERVICE_TYPES = {"信息技术服务", "其他服务", "物业管理", "社会治理服务"}
PROOF_MATERIAL_FINDINGS = {
    "检测报告要求与评审必要性不匹配",
    "原件备查与评审可操作性不足",
    "原厂授权或厂家证明要求过严",
    "查询截图或平台核验要求过细",
}


def obsidian_link_target(path_like: str | Path) -> str:
    path = Path(path_like)
    try:
        rel = path.resolve().relative_to(ROOT.resolve())
    except Exception:
        return str(path_like)
    return str(rel.with_suffix("")).replace("\\", "/")


def resolve_vault_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return ROOT / path


def vault_metadata_path(path_like: str | Path) -> str:
    path = resolve_vault_path(path_like)
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path_like)


def render_obsidian_link(path_like: str | Path, alias: str | None = None) -> str:
    target = obsidian_link_target(path_like)
    if alias:
        return f"[[{target}|{alias}]]"
    return f"[[{target}]]"


def normalize_source_file(source_file: str) -> str:
    path = resolve_vault_path(source_file)
    if path.exists() and str(path.resolve()).startswith(str(SOURCE_DIR.resolve())):
        return str(path.resolve())
    basename_matches = list(SOURCE_DIR.rglob(path.name))
    if len(basename_matches) == 1:
        return str(basename_matches[0].resolve())
    stem_matches = [
        candidate
        for candidate in SOURCE_DIR.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in {".doc", ".docx"} and candidate.stem == path.stem
    ]
    if len(stem_matches) == 1:
        return str(stem_matches[0].resolve())
    return str(path)


def sanitize_page_name(name: str) -> str:
    return re.sub(r"[\\/:\*\?\"<>\|#\^\[\]]", "_", name).strip() or "未命名项目"


def parse_project_pages() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_source: dict[str, dict[str, str]] = {}
    by_scan: dict[str, dict[str, str]] = {}
    project_dir = WIKI_DIR / "projects"
    if not project_dir.exists():
        return by_source, by_scan
    for path in project_dir.glob("*.md"):
        meta: dict[str, str] = {}
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            _, fm, _ = text.split("---", 2)
            for raw in fm.splitlines():
                if ":" not in raw:
                    continue
                key, value = raw.split(":", 1)
                meta[key.strip()] = value.strip()
        source_file = meta.get("source_file", "")
        scan_file = meta.get("scan_file", "")
        page_name = meta.get("page_name") or path.stem
        title = meta.get("title") or path.stem
        record = {
            "page_name": page_name,
            "title": title,
            "project_code": meta.get("project_code", ""),
            "procurement_type": meta.get("procurement_type", ""),
            "status": meta.get("status", ""),
        }
        if source_file:
            by_source[normalize_source_file(source_file)] = record
        if scan_file:
            by_scan[str(resolve_vault_path(scan_file))] = record
    return by_source, by_scan


def clean_text(text: str) -> str:
    for ch in ("\u200f", "\ufeff", "\u202a", "\u202c", "\u2066", "\u2067", "\u2068", "\u2069"):
        text = text.replace(ch, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def run_textutil(path: Path) -> list[str]:
    proc = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    text = clean_text(proc.stdout)
    return [line.strip() for line in text.splitlines()]


def parse_frontmatter_bullets(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- ([a-zA-Z0-9_]+):\s*(.+)", line)
        if m:
            data[m.group(1)] = m.group(2)
    return data


def parse_bullet_metadata(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list_key = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        scalar_match = re.match(r"^- ([a-zA-Z0-9_]+):\s*(.*)$", line)
        if scalar_match:
            key = scalar_match.group(1)
            value = scalar_match.group(2).strip()
            scalars[key] = value
            current_list_key = key if not value else ""
            if current_list_key:
                lists.setdefault(current_list_key, [])
            continue
        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if list_match and current_list_key:
            lists.setdefault(current_list_key, []).append(list_match.group(1).strip())
        elif line.strip():
            current_list_key = ""
    return scalars, lists


def extract_comment_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    start = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line == "## comments":
            start = True
            continue
        if not start or not line:
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"^\d+\.\s*", "", line)
        if "未抽取到批注内容" in line:
            continue
        lines.append(line)
    return lines


COMMENT_RISK_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("评分项未细化量化", ("量化", "分项得分", "按项扣分", "主观分", "分开设置分值", "阶梯给分", "最高得", "如何得分")),
    ("法定资格条件进入评分", ("资格要求", "独立承担民事责任", "重大违法记录", "不应作为评审项", "不应作为评分项")),
    ("特定许可证或准入资质进入评分", ("许可证", "备案凭证", "经营许可", "生产许可", "强制性资质")),
    ("证书设置与项目相关性不足", ("证书", "软考", "高级", "中级", "颁发机构", "专业方向", "认证", "奖项")),
    ("固定月份社保作为评分条件", ("社保", "时间点", "近3个月", "连续缴纳")),
    ("自有员工或社保绑定评分条件", ("自有员工", "以社保为准", "本单位缴纳社保")),
    ("检测报告要求与评审必要性不匹配", ("检测报告", "CNAS", "CMA", "检验报告")),
    ("原件备查与评审可操作性不足", ("原件备查", "无法判断", "不清晰导致", "不得分")),
    ("原厂授权或厂家证明要求过严", ("原厂授权", "厂家授权", "授权书", "厂商证明")),
    ("查询截图或平台核验要求过细", ("查询截图", "认e云", "学信网", "官网截图", "网站信息")),
    ("中小企业政策口径与所属行业需明确", ("中小企业", "所属行业", "行业选项", "中小企业促进法")),
    ("荣誉或评级级别要求过高且口径不清", ("评级", "奖项", "级别", "国务院奖项", "省级奖项", "市级奖项")),
]


FOCUS_SUMMARY_MAP = {
    "评分项未细化量化": "评分标准、扣分逻辑或主观分写法未形成可稳定复核的量化闭环。",
    "法定资格条件进入评分": "法定资格条件应留在资格审查阶段，不宜再进入评分。",
    "特定许可证或准入资质进入评分": "准入性许可证或备案凭证不宜再作为评分条件。",
    "证书设置与项目相关性不足": "证书、认证、软著或奖项与采购标的质量、履约能力的关联性不足。",
    "固定月份社保作为评分条件": "固定月份或连续月数社保若进入评分，存在差别待遇风险。",
    "自有员工或社保绑定评分条件": "自有员工或社保绑定评分容易把组织方式要求放大为竞争门槛。",
    "检测报告要求与评审必要性不匹配": "检测报告或原材料检验报告要求可能超出本项目评审必要范围。",
    "原件备查与评审可操作性不足": "原件备查和无法判断即不得分的写法会削弱评审稳定性。",
    "原厂授权或厂家证明要求过严": "原厂授权、厂家背书或厂商证明要求可能形成渠道限制。",
    "查询截图或平台核验要求过细": "多平台查询截图或网站状态截图容易把形式核验放大为评分障碍。",
    "中小企业政策口径与所属行业需明确": "中小企业政策适用主体、所属行业和价格扣除口径需保持一致。",
    "荣誉或评级级别要求过高且口径不清": "荣誉、评级或示范单位加分可能构成与项目无关的存量资源倾斜。",
    "服务采购不宜按买人或无关资历堆砌逻辑组织评分": "服务采购评分不宜堆砌人数、学历、职称等与真实履约弱相关因素。",
    "特定组织形态或评级要求可能构成差别待遇": "组织形态、社会组织评级或特定主体身份要求可能形成差别待遇。",
    "不得设置特定金额业绩门槛": "业绩金额门槛可能超出项目合理履约需要。",
    "现场踏勘或样品要求不宜直接进入评分": "现场踏勘、样品或演示安排不宜直接作为评分条件。",
    "采购清单与技术参数表达不闭环": "采购清单、参数、偏离和验收要求之间需形成闭环。",
    "格式性事项不得作为评分条件": "装订、盖章、排序等格式性事项不宜纳入评分。",
    "服务网点或经营场地要求与项目相关性不足": "服务网点、办公场地或经营地点要求需与履约必要性相匹配。",
    "货物项目价格分设置过低": "货物项目价格分低于法定下限会直接影响综合评分法结构。",
    "评标方法模板切换不完整": "采购方式、评标方法或模板条款之间存在冲突残留。",
}


def infer_comment_risk_hints(comment: str) -> list[str]:
    hits: list[str] = []
    for risk_title, keywords in COMMENT_RISK_HINTS:
        if any(keyword in comment for keyword in keywords):
            hits.append(risk_title)
    return hits


def classify_comment_signal(comment: str) -> dict[str, object]:
    if any(keyword in comment for keyword in ("证明材料", "检测报告", "CNAS", "CMA", "授权", "原件", "截图")):
        signal_type = "证明材料审查"
    elif any(keyword in comment for keyword in ("不应", "不得", "过高", "倾向性", "无直接关联", "限定特定行业")):
        signal_type = "风险判断"
    elif any(keyword in comment for keyword in ("建议", "删除", "增加", "补充", "改为")):
        signal_type = "修改建议"
    elif any(keyword in comment for keyword in ("请确认", "是否", "准确")):
        signal_type = "口径确认"
    else:
        signal_type = "一般批注"

    risk_hints = infer_comment_risk_hints(comment)
    if risk_hints and signal_type in {"风险判断", "证明材料审查"}:
        confidence = "high"
    elif risk_hints:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "signal_type": signal_type,
        "risk_hints": risk_hints,
        "confidence": confidence,
        "needs_manual_review": "yes",
        "source_comment": comment,
    }


def comment_signal_strength(comment_count: int) -> str:
    if comment_count == 0:
        return "none"
    if comment_count <= 2:
        return "light"
    if comment_count <= 6:
        return "medium"
    return "high"


def ingest_priority(risk_count: int, comment_count: int) -> str:
    if risk_count >= 12 or comment_count >= 8:
        return "P1"
    if risk_count >= 8 or comment_count >= 3:
        return "P2"
    return "P3"


def normalize_manifest_scalar(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned or cleaned == "unknown":
        return "unknown"
    if cleaned.endswith("：") or cleaned in {"项目名称", "项目名称：", "项目编号", "项目编号：", "项目类型", "项目类型："}:
        return "unknown"
    if field == "procurement_type" and cleaned not in {"货物", "服务"}:
        return "unknown"
    return cleaned


def build_focus_items(risk_titles: list[str], legacy_focus: list[str], legacy_notes: list[str]) -> list[str]:
    items: list[str] = []
    for title in risk_titles[:5]:
        summary = FOCUS_SUMMARY_MAP.get(title, "")
        if summary and summary not in items:
            items.append(summary)
    for item in legacy_focus + legacy_notes:
        if item not in items:
            items.append(item)
    return items[:6]


def render_manifest_page(
    title: str,
    item_type: str,
    source_file: str,
    review_basis: str,
    project_page: dict[str, str] | None,
    scan_stem: str,
    risk_titles: list[str],
    comment_count: int,
    legacy_focus: list[str],
    legacy_notes: list[str],
) -> str:
    project_link = f"[[projects/{project_page['page_name']}|{project_page['title']}]]" if project_page else "待补建"
    focus_items = build_focus_items(risk_titles, legacy_focus, legacy_notes)
    project_code = normalize_manifest_scalar(project_page.get("project_code", "") if project_page else "", "project_code")
    procurement_type = normalize_manifest_scalar(project_page.get("procurement_type", "") if project_page else "", "procurement_type")
    status = project_page.get("status", "") if project_page else ""
    lines = [
        f"# {title}",
        "",
        f"- source_file: {vault_metadata_path(source_file)}",
        f"- item_type: {item_type}",
        f"- project_page: {project_link}",
        f"- full_risk_scan: [[raw/full-risk-scans/{scan_stem}|scan]]",
        f"- numbered_text: [[raw/numbered-text/{scan_stem}|numbered]]",
        f"- review_basis: {review_basis}",
        f"- project_code: {project_code or 'unknown'}",
        f"- procurement_type: {procurement_type or 'unknown'}",
        f"- has_comments: {'yes' if comment_count else 'no'}",
        f"- comment_count: {comment_count}",
        f"- risk_count: {len(risk_titles)}",
        f"- priority: {ingest_priority(len(risk_titles), comment_count)}",
        "- evidence_status: numbered-text + full-risk-scan",
        f"- scan_status: {status or ('reviewed' if risk_titles else 'needs-review')}",
        "",
        "## top_findings",
    ]
    lines.extend([f"- {title}" for title in risk_titles[:8]] or ["- 待人工复核"])
    lines.extend(["", "## current_focus"])
    lines.extend([f"- {item}" for item in focus_items] or ["- 待补充"])
    if legacy_notes:
        lines.extend(["", "## legacy_notes"])
        lines.extend([f"- {item}" for item in legacy_notes])
    return "\n".join(lines)


def render_comment_page(
    title: str,
    source_file: str,
    comments: list[str],
    project_page: dict[str, str] | None,
    scan_stem: str,
) -> str:
    structured = [classify_comment_signal(comment) for comment in comments]
    hint_titles: list[str] = []
    for item in structured:
        for hint in item["risk_hints"]:
            if hint not in hint_titles:
                hint_titles.append(hint)
    project_link = f"[[projects/{project_page['page_name']}|{project_page['title']}]]" if project_page else "待补建"
    lines = [
        f"# {title} 批注摘录",
        "",
        f"- source_file: {vault_metadata_path(source_file)}",
        f"- project_page: {project_link}",
        f"- full_risk_scan: [[raw/full-risk-scans/{scan_stem}|scan]]",
        f"- has_comments: {'yes' if comments else 'no'}",
        f"- comment_count: {len(comments)}",
        f"- signal_strength: {comment_signal_strength(len(comments))}",
        f"- suggested_findings_count: {len(hint_titles)}",
        "- evidence_role: 人工埋点辅助层",
        "",
        "## suggested_findings",
    ]
    lines.extend([f"- {title}" for title in hint_titles] or ["- 当前未形成稳定的标准风险提示。"])
    lines.extend(["", "## structured_signals"])
    if structured:
        for idx, item in enumerate(structured, start=1):
            lines.extend(
                [
                    f"### {idx}. {item['signal_type']}",
                    f"- risk_hints: {'、'.join(item['risk_hints']) if item['risk_hints'] else 'none'}",
                    f"- confidence: {item['confidence']}",
                    f"- needs_manual_review: {item['needs_manual_review']}",
                    f"- source_comment: {item['source_comment']}",
                    "",
                ]
            )
    else:
        lines.extend(["- 当前文件未抽取到有效批注信号，风险识别以 `full-risk-scan` 为准。", ""])
    lines.append("## comments")
    if comments:
        lines.extend([f"{idx}. {comment}" for idx, comment in enumerate(comments, start=1)])
    else:
        lines.append("- 当前文件未抽取到批注内容，已基于正文执行风险扫描。")
    return "\n".join(lines)


def quote_line(line: str, limit: int = 120) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    if len(line) <= limit:
        return line
    return f"{line[:limit-3]}..."


def find_heading(lines: list[str], idx: int) -> str:
    heading_patterns = (
        "技术部分",
        "商务部分",
        "诚信情况",
        "价格",
        "评标信息",
        "资格性审查表",
        "符合性审查表",
        "评分标准",
        "评分准则",
        "项目需求",
        "商务要求",
        "技术要求",
        "采购需求",
        "服务需求",
        "服务方案",
    )
    for back in range(idx, max(-1, idx - 25), -1):
        line = lines[back].strip()
        if not line:
            continue
        if any(p in line for p in heading_patterns):
            return line
        if len(line) <= 24 and ("部分" in line or "表" in line or "要求" in line or "信息" in line):
            return line
    return "正文相关段落"


@dataclass
class Evidence:
    line_no: int
    trigger_text: str
    section: str
    note: str = ""


@dataclass
class Risk:
    title: str
    level: str
    reason: str
    analysis: str
    legal_basis: list[str]
    legal_refs: list[Path]
    confidence: str
    evidences: list[Evidence] = field(default_factory=list)
    comment_support: list[str] = field(default_factory=list)

    def add_evidence(self, evidence: Evidence) -> None:
        if any(abs(e.line_no - evidence.line_no) <= 1 and e.trigger_text == evidence.trigger_text for e in self.evidences):
            return
        self.evidences.append(evidence)
        self.evidences.sort(key=lambda x: x.line_no)


RISK_TEMPLATES: dict[str, dict[str, object]] = {
    "评分项未细化量化": {
        "level": "高",
        "reason": "评分标准存在“优良中差”“横向比较”或专家自由裁量较大的表达，难以形成可复核、可重复的量化闭环。",
        "analysis": "此类写法容易导致不同评审专家对同一投标文件给出差异较大的分值，也会弱化投标人事先预判得分区间的能力，属于评审标准可执行性和透明度不足的典型风险。",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应当细化和量化，且与相应的商务条件和采购需求对应。",
            "《中华人民共和国政府采购法实施条例》第十五条：除技术复杂或者性质特殊外，采购需求应当完整、明确。",
        ],
        "legal_refs": [LEGAL_REFS["bid_measure"], LEGAL_REFS["reg_impl"], LEGAL_REFS["concept_need"]],
        "confidence": "high",
    },
    "法定资格条件进入评分": {
        "level": "高",
        "reason": "将独立承担民事责任、无重大违法记录、依法缴纳税收和社保等法定资格条件再次放入评分，容易形成重复审查或变相门槛。",
        "analysis": "法定资格应当先做有无判断，不宜再转化为分值竞争；否则会把资格审查与评审因素边界打乱。",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：资格条件不得作为评审因素。",
            "《中华人民共和国政府采购法》第二十二条、第二十三条：资格条件和资格审查应依法设置并进行审查。",
        ],
        "legal_refs": [LEGAL_REFS["bid_measure"], LEGAL_REFS["gov_law"], LEGAL_REFS["concept_qualification"]],
        "confidence": "medium",
    },
    "特定许可证或准入资质进入评分": {
        "level": "高",
        "reason": "将许可证、备案凭证、行业准入资质等本应先核验是否具备的准入条件写入评分，容易形成边界错位。",
        "analysis": "准入许可通常属于能否参与的前置条件，不宜再通过分值高低区分供应商竞争地位。",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：资格条件不得作为评审因素。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与项目特点和实际需要相适应。",
        ],
        "legal_refs": [LEGAL_REFS["bid_measure"], LEGAL_REFS["reg_impl"], LEGAL_REFS["concept_qualification"]],
        "confidence": "medium",
    },
    "证书设置与项目相关性不足": {
        "level": "中高",
        "reason": "对证书、认证、体系、软著或特定专业证照赋予分值，但与采购标的性能、服务质量或履约能力之间的关联度不足。",
        "analysis": "如果证书只是供应商一般性能力展示，而不能直接证明本项目交付质量，就可能构成对特定供应商的倾斜。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：设定的资格、技术、商务条件应与项目特点和实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与货物服务质量、履约能力等相关。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["topic_bidding"]],
        "confidence": "medium",
    },
    "荣誉或评级级别要求过高且口径不清": {
        "level": "中高",
        "reason": "以国家级、省级、市级荣誉、评级、示范单位或试点单位作为加分依据，且层级、认定机关或边界口径不够清楚。",
        "analysis": "荣誉、评级、奖项本身容易形成存量资源优势，如果与采购标的关联性弱、口径又不清晰，通常会放大差别待遇风险。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（四）项：不得以特定行政区域或者特定行业的业绩、奖项作为加分条件。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应细化量化并与采购需求对应。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"]],
        "confidence": "medium",
    },
    "固定月份社保作为评分条件": {
        "level": "中高",
        "reason": "在评分因素中直接要求固定月份、连续月数或特定时间段社保证明，容易形成对供应商的不合理限制。",
        "analysis": "社保材料可以用于辅助核验劳动关系真实性，但若直接绑定固定月份或连续时长要求，就会显著抬高投标门槛。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：设定条件应与项目特点和实际需要相适应，不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"]],
        "confidence": "medium",
    },
    "自有员工或社保绑定评分条件": {
        "level": "中高",
        "reason": "要求拟派人员必须为投标人自有员工，且以社保作为直接得分前提，容易把用工组织方式放大为竞争门槛。",
        "analysis": "团队稳定性可以关注，但若直接以自有员工或社保绑定得分，会对不同组织方式的供应商形成不必要限制。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：设定条件应与项目特点和实际需要相适应，不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与服务水平、履约能力等相关。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"]],
        "confidence": "medium",
    },
    "服务网点或经营场地要求与项目相关性不足": {
        "level": "中",
        "reason": "要求供应商在特定地域设常驻机构、办公场所或服务网点，容易形成地域性门槛。",
        "analysis": "服务便利性可以关注响应时效和履约能力，但不宜直接等同于本地设点；更稳妥的做法通常是写成中标后响应时效或服务承诺。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：与实际需要不相适应或其他不合理条件均构成差别待遇风险。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["topic_bidding"]],
        "confidence": "medium",
    },
    "现场踏勘或样品要求不宜直接进入评分": {
        "level": "中",
        "reason": "将现场踏勘、样品、演示、答辩等安排直接作为评分点，容易放大程序性条件对竞争结果的影响。",
        "analysis": "只有在书面方式确实不能准确描述采购需求时，样品等要求才有必要，且其标准、方法、条件必须事先明确。",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第二十二条：一般不得要求投标人提供样品，特殊情形下也应明确评审方法和标准。",
            "《政府采购货物和服务招标投标管理办法》第二十六条：现场考察、答疑应统一组织，不宜异化为隐性评分门槛。",
        ],
        "legal_refs": [LEGAL_REFS["bid_measure"], LEGAL_REFS["topic_bidding"]],
        "confidence": "medium",
    },
    "服务采购不宜按买人或无关资历堆砌逻辑组织评分": {
        "level": "中高",
        "reason": "服务项目大量围绕人员学历、职称、培训证书、团队人数等堆砌分值，容易把服务能力评价异化为“买人头”或“拼证书”。",
        "analysis": "服务采购更应围绕服务方案、服务流程、响应机制和履约结果设计评分；若将大量无关资历堆砌进评分，会削弱对真实服务能力的判断。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购需求应当完整、明确。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：评分条件应与项目特点和履约需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与服务水平、履约能力等相关。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["concept_need"]],
        "confidence": "medium",
    },
    "特定组织形态或评级要求可能构成差别待遇": {
        "level": "中高",
        "reason": "将社会组织评估等级、协会登记状态、特定组织身份等作为得分前提，可能对供应商组织形态形成差别待遇。",
        "analysis": "除确属法律法规明确要求外，组织形态本身通常不当然代表履约能力；若直接加分或设门槛，容易压缩非对应组织的参与空间。",
        "legal_basis": [
            "《中华人民共和国政府采购法》第二十二条：特定条件不得以不合理的条件对供应商实行差别待遇或者歧视待遇。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：不合理条件限制或者排斥潜在供应商。",
        ],
        "legal_refs": [LEGAL_REFS["gov_law"], LEGAL_REFS["reg_impl"]],
        "confidence": "medium",
    },
    "不得设置特定金额业绩门槛": {
        "level": "中高",
        "reason": "将单个项目合同金额、累计业绩规模或高额金额阈值作为评分或准入前提，可能放大对既有大项目供应商的偏好。",
        "analysis": "业绩可以作为履约能力参考，但如果直接以高额金额门槛区分得分，通常需要非常强的项目必要性论证，否则容易构成差别待遇。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：设定条件应与项目实际需要相适应，不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"]],
        "confidence": "medium",
    },
    "检测报告要求与评审必要性不匹配": {
        "level": "中",
        "reason": "要求提交大量检测报告、原材料检验报告或指定标识检测报告，但未充分说明其与本项目评审必要性的关系。",
        "analysis": "检测报告要求如果超出核心功能、安全或验收需要，就容易把技术证明扩张为普遍性投标门槛。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购需求应完整明确，并符合技术、服务、安全等要求。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第二十二条：样品和检测报告要求需有明确必要性与标准。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["concept_need"]],
        "confidence": "medium",
    },
    "原件备查与评审可操作性不足": {
        "level": "中",
        "reason": "大量使用原件备查、专家无法判断即不得分、不清晰即不得分等写法，会削弱评审可操作性。",
        "analysis": "这类写法容易把形式性瑕疵放大为分值损失，且会显著提高评审对临场判断的依赖。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应细化量化并与采购需求对应。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["concept_need"]],
        "confidence": "medium",
    },
    "原厂授权或厂家证明要求过严": {
        "level": "中高",
        "reason": "以原厂授权、厂家证明、厂商背书等作为评分或普遍性证明要求，可能形成渠道和品牌限制。",
        "analysis": "若采购目标可以通过功能响应、兼容承诺和履约责任实现，就不宜普遍要求原厂背书文件。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["concept_need"]],
        "confidence": "medium",
    },
    "查询截图或平台核验要求过细": {
        "level": "中",
        "reason": "要求提供多平台查询截图、网站状态截图或特定页面截图，容易把形式核验放大为评分门槛。",
        "analysis": "若采购人或评审系统本可自行核验，就不宜把截图形式要求普遍转化为供应商举证负担。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["concept_need"]],
        "confidence": "medium",
    },
    "中小企业政策口径与所属行业需明确": {
        "level": "中",
        "reason": "中小企业声明、所属行业、价格扣除口径如果写法不完整或前后不一致，会影响政策适用和价格评审。",
        "analysis": "此类问题往往不一定直接导致违法，但会增加投标人理解偏差和评审执行分歧，需要在招标文件中写清行业口径、适用对象和计算方式。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第六条：政府采购应落实促进中小企业发展等政策。",
            "《政府采购货物和服务招标投标管理办法》第五条：招标投标活动中应落实促进中小企业发展等政府采购政策。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"], LEGAL_REFS["topic_bidding"]],
        "confidence": "low",
    },
    "货物项目价格分设置过低": {
        "level": "高",
        "reason": "货物项目价格分低于法定最低比例，会直接触及综合评分法价格权重底线。",
        "analysis": "货物项目价格分设置过低，会弱化价格竞争，改变综合评分法的法定结构。",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：货物项目价格分值占总分值的比重不得低于30%。",
        ],
        "legal_refs": [LEGAL_REFS["bid_measure"], LEGAL_REFS["topic_bidding"]],
        "confidence": "high",
    },
    "评标方法模板切换不完整": {
        "level": "中",
        "reason": "同一文件中出现互相冲突的评标方法、采购方式或模板残留条款，可能导致评审依据不一致。",
        "analysis": "模板切换不完整会直接影响投标人理解、投标文件编制和评审委员会适用标准，属于招标文件完整性风险。",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购文件应围绕完整、明确的采购需求编制。",
            "《政府采购货物和服务招标投标管理办法》第二十条：招标文件应载明评标方法、评标标准和投标无效情形等主要内容。",
        ],
        "legal_refs": [LEGAL_REFS["reg_impl"], LEGAL_REFS["bid_measure"]],
        "confidence": "medium",
    },
}


def ensure_risk(risks: dict[str, Risk], title: str) -> Risk:
    if title not in risks:
        tpl = RISK_TEMPLATES[title]
        risks[title] = Risk(
            title=title,
            level=tpl["level"],
            reason=tpl["reason"],
            analysis=tpl["analysis"],
            legal_basis=list(tpl["legal_basis"]),
            legal_refs=list(tpl["legal_refs"]),
            confidence=str(tpl["confidence"]),
        )
    return risks[title]


def add_match(
    risks: dict[str, Risk],
    title: str,
    lines: list[str],
    idx: int,
    note: str = "",
) -> None:
    risk = ensure_risk(risks, title)
    risk.add_evidence(
        Evidence(
            line_no=idx + 1,
            trigger_text=quote_line(lines[idx]),
            section=find_heading(lines, idx),
            note=note,
        )
    )


def has_score_context(window: str, tokens: tuple[str, ...]) -> bool:
    return any(token in window for token in tokens)


def is_generic_mixed_review_clause(line: str) -> bool:
    if re.search(r"质疑|投诉", line) and re.search(r"原件|核查", line):
        return True
    mixed_tokens = ("资格性审查表", "符合性审查表", "投标无效处理", "投标无效", "各自审查范围", "核查和判定")
    return "评标信息" in line and any(token in line for token in mixed_tokens)


def build_risks(item_type: str, lines: list[str], comments: list[str], old_titles: list[str]) -> dict[str, Risk]:
    risks: dict[str, Risk] = {}
    proof_score_tokens = ("评分", "得分", "不得分", "评审", "评分因素", "评分准则", "证明文件", "考察内容")

    for idx, line in enumerate(lines):
        prev_window = " ".join(lines[max(0, idx - 3): idx + 1])
        next_window = " ".join(lines[idx: min(len(lines), idx + 3)])
        score_window = f"{prev_window} {next_window}"
        score_context = has_score_context(score_window, proof_score_tokens)

        if re.search(r"优加|良加|中加|差不加分|横向比较|综合评价|由专家组进一步评审|由评审委员会进行评价", line):
            add_match(risks, "评分项未细化量化", lines, idx)
        elif re.search(r"优秀|良好|一般|较差|评审为优|评审为良|评审为中|评审为差", line) and ("评分" in prev_window or "评审" in prev_window):
            add_match(risks, "评分项未细化量化", lines, idx)

        if ("社保" in line or "养老保险" in line) and re.search(r"\d{4}年\d{1,2}月|\d+个月|前[一二三四五六七八九十\d]+个月|近\d+个月", line):
            add_match(risks, "固定月份社保作为评分条件", lines, idx)
        if re.search(r"自有员工|以社保为准|投标人为其购买的社保|投标企业缴纳的近\d+个月|须为投标人自有员工", line):
            if any(token in score_window for token in ("评分", "得分", "不得分", "证明文件", "评分因素", "考察内容")):
                add_match(risks, "自有员工或社保绑定评分条件", lines, idx)

        if re.search(r"体系认证|认证证书|ISO/?IEC|CISP|CISAW|CISE|软件开发工程师|信息安全工程师|软著|著作权", line):
            add_match(risks, "证书设置与项目相关性不足", lines, idx)

        if re.search(r"国家级|省级|市级|副省级|示范单位|试点单位|一等奖|二等奖|三等奖|评级|等级", line):
            if "服务经验" in prev_window or "评审" in prev_window or "考察内容" in prev_window or "标准化" in prev_window:
                add_match(risks, "荣誉或评级级别要求过高且口径不清", lines, idx)

        if re.search(r"常驻服务机构|办公场所|租赁合同|深圳市内设有|服务机构", line):
            add_match(risks, "服务网点或经营场地要求与项目相关性不足", lines, idx)

        if re.search(r"现场踏勘|现场考察|样品|演示|答辩|讲标|述标", line):
            add_match(risks, "现场踏勘或样品要求不宜直接进入评分", lines, idx)

        if re.search(r"重大违法记录|独立承担民事责任|良好的商业信誉|依法缴纳税收|社会保障资金", line):
            if has_score_context(score_window, ("评分", "评审", "不得分", "评分因素", "评分准则", "考察内容")):
                add_match(risks, "法定资格条件进入评分", lines, idx)
        if re.search(r"许可证|备案凭证|经营许可证|生产许可证|资质证书", line):
            if has_score_context(score_window, ("评分", "评审", "不得分", "评分因素", "评分准则", "考察内容")):
                add_match(risks, "特定许可证或准入资质进入评分", lines, idx)

        if item_type in SERVICE_TYPES and re.search(r"至少\d+人|不少于\d+人|项目负责人|团队成员|研究生|本科|副高|督导|岗前培训|自有员工", line):
            if "评分" in prev_window or "考察内容" in prev_window or "证明文件" in prev_window:
                add_match(risks, "服务采购不宜按买人或无关资历堆砌逻辑组织评分", lines, idx)

        if re.search(r"社会组织|民办非企业|协会|合法登记且状态正常|评估认证|4A|5A", line):
            add_match(risks, "特定组织形态或评级要求可能构成差别待遇", lines, idx)

        if re.search(r"业绩", line) and re.search(r"金额|不低于|不少于|以上", line):
            add_match(risks, "不得设置特定金额业绩门槛", lines, idx)

        if re.search(r"检测报告|检验报告|CNAS|CMA", line):
            if score_context and not re.search(r"虚假|核实真实性|履约验收环节|验收环节", line):
                add_match(risks, "检测报告要求与评审必要性不匹配", lines, idx)
        if "原件备查" in line or re.search(r"无法判断|不清晰导致.*不得分|专家无法.*判断.*得分", line):
            if score_context and not is_generic_mixed_review_clause(line):
                add_match(risks, "原件备查与评审可操作性不足", lines, idx)
        if re.search(r"原厂授权|厂家授权|厂商证明|厂家证明|背书", line) or (("授权书" in line) and not re.search(r"评标授权书|授权代表|法定代表人授权", line)):
            if score_context and not re.search(r"评审授权书|采购人代表须持|采购人代表.*授权书", line):
                add_match(risks, "原厂授权或厂家证明要求过严", lines, idx)
        if re.search(r"查询截图|认e云|学信网|官网查询|网站信息|状态为有效", line):
            if score_context:
                add_match(risks, "查询截图或平台核验要求过细", lines, idx)

        if re.search(r"中小企业|小微企业|所属行业|声明函|监狱企业|残疾人福利性单位", line):
            add_match(risks, "中小企业政策口径与所属行业需明确", lines, idx)

    if item_type in GOODS_TYPES:
        for idx, line in enumerate(lines):
            if line == "价格":
                for ahead in range(idx + 1, min(len(lines), idx + 6)):
                    if re.fullmatch(r"\d+", lines[ahead]):
                        weight = int(lines[ahead])
                        if weight < 30:
                            add_match(
                                risks,
                                "货物项目价格分设置过低",
                                lines,
                                ahead,
                                note=f"价格权重识别为 {weight}%",
                            )
                        break

    text_all = "\n".join(lines)
    if ("综合评分法" in text_all and "最低评标价法" in text_all) or ("公开招标" in text_all and "竞争性谈判" in text_all):
        idx = next((i for i, line in enumerate(lines) if "综合评分法" in line or "最低评标价法" in line or "竞争性谈判" in line), 0)
        add_match(risks, "评标方法模板切换不完整", lines, idx)

    comment_text = " ".join(comments)
    comment_map = {
        "评分项未细化量化": ["优", "良", "中", "差", "量化", "删除“至少”", "删除,评分项不应出现"],
        "法定资格条件进入评分": ["资格要求", "不应作为评审项", "不应作为评分项", "法定资格"],
        "特定许可证或准入资质进入评分": ["许可证", "备案凭证", "强制性资质", "准入资质"],
        "证书设置与项目相关性不足": ["证书", "与项目无关", "有什么关联", "无关"],
        "固定月份社保作为评分条件": ["社保", "近3个月", "连续缴纳", "时间点"],
        "自有员工或社保绑定评分条件": ["自有员工", "以社保为准", "购买的社保"],
        "检测报告要求与评审必要性不匹配": ["检测报告", "CNAS", "CMA", "检验报告"],
        "原件备查与评审可操作性不足": ["原件备查", "无法判断", "不清晰", "不得分"],
        "原厂授权或厂家证明要求过严": ["原厂授权", "厂家授权", "授权书", "厂商证明"],
        "查询截图或平台核验要求过细": ["查询截图", "认e云", "学信网", "官网截图"],
        "荣誉或评级级别要求过高且口径不清": ["国家级", "省级", "副省级", "满分要求过高", "档次分级"],
        "服务采购不宜按买人或无关资历堆砌逻辑组织评分": ["明确人数", "按人得分", "需要那么多人", "项目需要出书吗"],
        "特定组织形态或评级要求可能构成差别待遇": ["社会组织", "评估", "评级"],
    }
    for title, keys in comment_map.items():
        matched = [c for c in comments if any(k in c for k in keys)]
        if matched:
            risk = ensure_risk(risks, title)
            risk.comment_support.extend(matched[:4])

    for old_title in old_titles:
        if old_title in PROOF_MATERIAL_FINDINGS:
            continue
        if old_title in RISK_TEMPLATES and old_title not in risks:
            risk = ensure_risk(risks, old_title)
            # 兜底挂在第一个“评分因素/考察内容”附近，至少确保有行号入口。
            idx = next(
                (
                    i
                    for i, line in enumerate(lines)
                    if any(token in line for token in ("评分因素", "评分准则", "考察内容", "证明文件", "评标信息"))
                ),
                0,
            )
            risk.add_evidence(
                Evidence(
                    line_no=idx + 1,
                    trigger_text=quote_line(lines[idx]) if lines else "正文抽取为空，需人工复核。",
                    section=find_heading(lines, idx) if lines else "正文相关段落",
                    note="该风险来自首轮扫描主题回填，当前批次未命中更具体的自动化证据，建议后续人工复核。",
                )
            )

    return risks


def read_old_titles(path: Path) -> list[str]:
    if not path.exists():
        return []
    titles = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"###\s+\d+\.\s+(.+)", line.strip())
        if m:
            titles.append(m.group(1).strip())
    return titles


def write_numbered_snapshot(title: str, source_file: str, lines: list[str], out_path: Path) -> None:
    body = [
        f"# {title} 带行号全文快照",
        "",
        f"- source_file: {vault_metadata_path(source_file)}",
        f"- generated_at: {TODAY}",
        "- line_numbering_basis: textutil 文本抽取后逐行编号",
        "",
        "## numbered_text",
    ]
    for idx, line in enumerate(lines, start=1):
        body.append(f"{idx:04d}: {line}")
    out_path.write_text("\n".join(body) + "\n", encoding="utf-8")


def render_scan(
    title: str,
    item_type: str,
    source_file: str,
    numbered_path: Path,
    risks: dict[str, Risk],
    comments: list[str],
    project_page: dict[str, str] | None = None,
) -> str:
    ordered = sorted(risks.values(), key=lambda r: ({"高": 0, "中高": 1, "中": 2}.get(r.level, 3), r.evidences[0].line_no if r.evidences else 9999, r.title))
    risk_titles = [risk.title for risk in ordered]
    lines = [
        f"# {title} 全风险点扫描（第二轮增强）",
        "",
        f"- source_file: {vault_metadata_path(source_file)}",
        f"- item_type: {item_type}",
        f"- scan_date: {TODAY}",
        "- scan_basis: 全文抽取 + 行号定位 + 人工批注辅助 + 政府采购法规映射",
        f"- numbered_snapshot: {vault_metadata_path(numbered_path)}",
        "",
        "## 扫描结论",
        f"- 本文件当前识别到 {len(ordered)} 类政府采购合规风险。",
        f"- 主风险主题：{'、'.join(risk_titles[:5]) if risk_titles else '本轮未命中明确规则，需人工复核。'}",
        "- 行号为 `textutil` 抽取文本后的稳定引用行，不等同于原始 Word 页码。",
        "",
    ]
    if comments:
        lines.extend(
            [
                "## 人工批注提示",
                *[f"- {comment}" for comment in comments[:10]],
                "",
            ]
        )

    lines.append("## 已识别风险点")
    if not ordered:
        lines.extend(
            [
                "### 1. 待人工复核",
                "- 风险等级：待复核",
                "- 风险原因：当前文本抽取未命中规则，但首轮扫描或文件属性表明仍需复核。",
                "- 风险分析总结：建议人工优先查看评分表、资格要求、证明材料和政策条款。",
                "",
            ]
        )
    for idx, risk in enumerate(ordered, start=1):
        lines.extend(
            [
                f"### {idx}. {risk.title}",
                f"- 风险等级：{risk.level}",
                f"- 风险原因：{risk.reason}",
                f"- 风险分析总结：{risk.analysis}",
                f"- 置信度：{risk.confidence}",
                "- 法规依据：",
                *[f"  - {basis}" for basis in risk.legal_basis],
                "- 法规基础库：",
                *[f"  - {render_obsidian_link(ref, Path(ref).stem)}" for ref in dict.fromkeys(risk.legal_refs)],
            ]
        )
        if risk.comment_support:
            lines.append("- 人工批注补强：")
            for comment in risk.comment_support[:4]:
                lines.append(f"  - {comment}")
        lines.append("- 证据定位：")
        for ev_idx, evidence in enumerate(risk.evidences[:5], start=1):
            line = f"  - 证据{ev_idx} | 位置：{evidence.section} | 行号：{evidence.line_no} | 触发文本：{evidence.trigger_text}"
            if evidence.note:
                line += f" | 备注：{evidence.note}"
            lines.append(line)
        lines.append("")

    lines.extend(["## 关联入口"])
    if project_page:
        lines.append(f"- [[projects/{project_page['page_name']}|project-entry]]")
    lines.append(f"- [[{obsidian_link_target(numbered_path)}|numbered-text]]")
    for risk_title in risk_titles:
        lines.append(f"- [[findings/{risk_title}|{risk_title}]]")
    lines.append("")

    lines.extend(
        [
            "## 风险主题索引",
            *[f"- [[{risk_title}]]" for risk_title in risk_titles],
            "",
            "## 证据边界 / 不确定点",
            "- 本页为规则识别与批注辅助后的第二轮增强结果，适合做批量检索和线索回溯。",
            "- 若需要形成确定违法判断，仍应结合完整招标文件上下文、答疑澄清和适用法规版本进行人工复核。",
            "",
        ]
    )
    return "\n".join(lines)


def build_audit(records: list[dict[str, object]]) -> str:
    total = len(records)
    corpus_sources = len([p for p in SOURCE_DIR.rglob("*") if p.is_file() and p.suffix.lower() in {".doc", ".docx"}])
    counter = Counter()
    for record in records:
        counter.update(record["risk_titles"])

    lines = [
        "# full-risk-scan-second-pass-index",
        "",
        "## 说明",
        "- 本页汇总第二轮增强版逐文件风险扫描结果，重点提供文件级风险数、主要风险和证据快照入口。",
        "- 所有行号均来自 `raw/numbered-text/` 下的带行号全文快照。",
        "",
        "## 总体状态",
        f"- 已增强扫描入口数：{total}",
        f"- 源目录文件数：{corpus_sources}",
        f"- 风险主题总命中次数：{sum(counter.values())}",
        "",
        "## 高频风险主题",
    ]
    for title, count in counter.most_common(15):
        lines.append(f"- {title}：{count}")
    lines.append("")

    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record["item_type"])].append(record)

    for item_type in sorted(grouped):
        lines.extend([f"## {item_type}"])
        for record in sorted(grouped[item_type], key=lambda r: str(r["title"])):
            top_titles = "、".join(record["risk_titles"][:3]) if record["risk_titles"] else "待人工复核"
            display_title = str(record["title"])
            lines.append(
                f"- 文件：{display_title} | [[raw/full-risk-scans/{record['scan_stem']}|scan]] | [[raw/numbered-text/{record['scan_stem']}|numbered]] | 风险数：{record['risk_count']} | 主要风险：{top_titles}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    NUMBERED_DIR.mkdir(parents=True, exist_ok=True)
    project_by_source, _project_by_scan = parse_project_pages()

    records: list[dict[str, object]] = []
    for manifest_path in sorted(MANIFEST_DIR.glob("*.md")):
        stem = manifest_path.stem
        scan_path = SCAN_DIR / f"{stem}.md"
        comment_path = COMMENT_DIR / f"{stem}.md"

        meta, list_blocks = parse_bullet_metadata(manifest_path)
        title = manifest_path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        source_file = meta.get("source_file")
        item_type = meta.get("item_type", stem.split("-", 1)[0])
        if not source_file:
            continue
        source_file = normalize_source_file(source_file)

        lines = run_textutil(Path(source_file))
        comments = extract_comment_lines(comment_path)
        old_titles = read_old_titles(scan_path)
        risks = build_risks(item_type, lines, comments, old_titles)

        numbered_path = NUMBERED_DIR / f"{stem}.md"
        write_numbered_snapshot(title, source_file, lines, numbered_path)
        project_page = project_by_source.get(source_file)
        if not project_page:
            project_page = {"page_name": sanitize_page_name(title), "title": title}
        scan_body = render_scan(title, item_type, source_file, numbered_path, risks, comments, project_page)
        scan_path.write_text(scan_body + "\n", encoding="utf-8")

        ordered_titles = [risk.title for risk in sorted(risks.values(), key=lambda r: ({"高": 0, "中高": 1, "中": 2}.get(r.level, 3), r.evidences[0].line_no if r.evidences else 9999, r.title))]
        review_basis = meta.get("review_basis") or ("带批注招标文件" if comments else "无批注或批注不可抽取文件，已先做单文件全风险点扫描")
        manifest_body = render_manifest_page(
            title=title,
            item_type=item_type,
            source_file=source_file,
            review_basis=review_basis,
            project_page=project_page,
            scan_stem=stem,
            risk_titles=ordered_titles,
            comment_count=len(comments),
            legacy_focus=list_blocks.get("current_focus", []),
            legacy_notes=list_blocks.get("notes", []),
        )
        manifest_path.write_text(manifest_body + "\n", encoding="utf-8")

        comment_body = render_comment_page(
            title=title,
            source_file=source_file,
            comments=comments,
            project_page=project_page,
            scan_stem=stem,
        )
        comment_path.write_text(comment_body + "\n", encoding="utf-8")
        records.append(
            {
                "title": title,
                "item_type": item_type,
                "risk_count": len(risks),
                "risk_titles": ordered_titles,
                "scan_stem": stem,
                "source_file": source_file,
                "comment_count": len(comments),
            }
        )

    audit_path = AUDIT_DIR / "full-risk-scan-second-pass-index.md"
    audit_path.write_text(build_audit(records) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
