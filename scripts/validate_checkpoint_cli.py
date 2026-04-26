#!/usr/bin/env python3
"""用 OpenAI 兼容小模型验证 1 个 BD 检查点执行说明书 + 1 份待审文件。"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import re
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path.cwd()
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "validation" / "cli-runs"
DEFAULT_BASE_URL = os.environ.get("CHECKPOINT_LLM_BASE_URL", "http://112.111.54.86:10011/v1")
DEFAULT_MODEL = os.environ.get("CHECKPOINT_LLM_MODEL", "qwen3.5-27b")
DEFAULT_API_KEY = os.environ.get("CHECKPOINT_LLM_API_KEY", "bssc")

MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "quick": {
        "jobs": 10,
        "max_tokens": 3072,
        "fast_skip": True,
        "two_stage": True,
        "stage1_min_score": 8,
    },
    "standard": {
        "jobs": 10,
        "max_tokens": 4096,
        "fast_skip": True,
        "two_stage": True,
        "stage1_min_score": 6,
    },
    "strict": {
        "jobs": 8,
        "max_tokens": 6144,
        "fast_skip": True,
        "two_stage": True,
        "stage1_min_score": 5,
    },
    "sop-validation": {
        "jobs": 8,
        "max_tokens": 6144,
        "fast_skip": False,
        "two_stage": False,
        "stage1_min_score": 0,
    },
}

DOMAIN_STAGE1_THRESHOLDS: dict[str, dict[str, int]] = {
    "quick": {
        "BD01": 8,
        "BD02": 8,
        "BD03": 7,
        "BD04": 7,
        "BD05": 7,
        "BD06": 6,
        "BD07": 6,
        "BD08": 7,
        "BD09": 6,
        "BD10": 7,
        "BD11": 7,
        "BD12": 6,
        "BD13": 7,
    },
    "standard": {
        "BD01": 8,
        "BD02": 8,
        "BD03": 6,
        "BD04": 6,
        "BD05": 6,
        "BD06": 5,
        "BD07": 5,
        "BD08": 6,
        "BD09": 5,
        "BD10": 6,
        "BD11": 6,
        "BD12": 5,
        "BD13": 6,
    },
    "strict": {
        "BD01": 6,
        "BD02": 6,
        "BD03": 5,
        "BD04": 5,
        "BD05": 5,
        "BD06": 4,
        "BD07": 4,
        "BD08": 5,
        "BD09": 4,
        "BD10": 5,
        "BD11": 5,
        "BD12": 4,
        "BD13": 5,
    },
    "sop-validation": {},
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def slugify_filename(name: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "-", name).strip()
    return sanitized or "unknown"


def relative_path(path: Path) -> str:
    try:
        return os.path.relpath(path, WORKSPACE_ROOT)
    except Exception:
        return str(path)


def under_path(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def validate_output_dir(output_dir: Path) -> None:
    forbidden = WORKSPACE_ROOT / "wiki" / "audits"
    if under_path(output_dir, forbidden):
        raise RuntimeError("checkpoint CLI 输出不得写入 wiki/audits，请使用 validation/cli-runs。")


def extract_text_from_docx(path: Path) -> tuple[str, str]:
    textutil = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if textutil.returncode == 0 and textutil.stdout.strip():
        return textutil.stdout, "textutil"

    try:
        import docx  # type: ignore
    except ImportError as exc:
        raise RuntimeError(f"无法提取 {path.name}，textutil 失败且 python-docx 不可用") from exc

    document = docx.Document(str(path))
    lines = [para.text for para in document.paragraphs]
    text = "\n".join(lines).strip()
    if text:
        return text, "python-docx"
    raise RuntimeError(f"无法提取 {path.name}，docx 内容为空")


def extract_text_from_doc(path: Path) -> tuple[str, str]:
    antiword = subprocess.run(
        ["antiword", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if antiword.returncode == 0 and antiword.stdout.strip():
        return antiword.stdout, "antiword"

    textutil = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if textutil.returncode == 0 and textutil.stdout.strip():
        return textutil.stdout, "textutil"

    error_text = antiword.stderr.strip() or textutil.stderr.strip() or "未知错误"
    raise RuntimeError(f"无法提取 {path.name}：{error_text}")


def load_review_file(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return read_text(path), "plain-text"
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".doc":
        return extract_text_from_doc(path)
    raise RuntimeError(f"暂不支持的待审文件类型：{path.suffix}")


def parse_frontmatter(markdown: str) -> dict[str, Any]:
    match = re.match(r"(?ms)^---\n(.*?)\n---", markdown)
    if not match:
        return {}
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if key_match:
            current_key = key_match.group(1)
            value = key_match.group(2).strip()
            data[current_key] = value if value else []
            continue
        list_match = re.match(r"^\s*-\s*(.+)$", line)
        if list_match and current_key:
            value = data.setdefault(current_key, [])
            if isinstance(value, list):
                value.append(list_match.group(1).strip())
    return data


def source_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def extract_title(markdown: str) -> str:
    frontmatter = parse_frontmatter(markdown)
    title = frontmatter.get("title")
    if isinstance(title, str) and title:
        return title
    match = re.search(r"^#\s+(.+)$", markdown, re.M)
    return match.group(1).strip() if match else "unknown-checkpoint"


def extract_checkpoint_id(markdown: str) -> str:
    frontmatter = parse_frontmatter(markdown)
    checkpoint_id = frontmatter.get("id")
    if isinstance(checkpoint_id, str) and checkpoint_id:
        return checkpoint_id
    return "unknown-id"


def extract_section(markdown: str, heading: str) -> str:
    pattern = re.compile(rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)")
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def compact_checkpoint_text(markdown: str, max_chars: int) -> str:
    headings = [
        "标准检查点",
        "检查点定义",
        "审查问题句",
        "定位关键词",
        "候选召回规则",
        "上下文读取规则",
        "条款属性判断",
        "相关性判断尺子",
        "专用 SOP 边界",
        "基础命中条件",
        "命中条件",
        "排除条件",
        "判断结果分流",
        "正例",
        "反例",
        "审查步骤",
        "结论表达",
    ]
    chunks: list[str] = []
    included_headings: set[str] = set()
    for heading in headings:
        section = extract_section(markdown, heading)
        if section:
            chunks.append(f"## {heading}\n{section}")
            included_headings.add(heading)
    for match in re.finditer(r"^##\s+(.+?判断尺子)\s*$", markdown, re.M):
        heading = match.group(1).strip()
        if heading in included_headings:
            continue
        section = extract_section(markdown, heading)
        if section:
            chunks.append(f"## {heading}\n{section}")
            included_headings.add(heading)
    text = "\n\n".join(chunks).strip()
    if not text:
        text = markdown
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[已按 max-checkpoint-chars 截断]"
    return text


def parse_keyword_groups(markdown: str) -> dict[str, list[str]]:
    section = extract_section(markdown, "定位关键词")
    groups: dict[str, list[str]] = {}
    current_group = "关键词"
    groups[current_group] = []
    for line in section.splitlines():
        heading = re.match(r"^###\s+(.+?)\s*$", line)
        if heading:
            current_group = heading.group(1).strip()
            groups.setdefault(current_group, [])
            continue
        item = re.match(r"^-\s+(.+?)\s*$", line)
        if item:
            word = item.group(1).strip().rstrip("。；;")
            if word:
                groups.setdefault(current_group, []).append(word)
    return {key: value for key, value in groups.items() if value}


def numbered_lines(text: str) -> list[str]:
    return [f"{idx:04d}: {line}" for idx, line in enumerate(source_lines(text), start=1)]


def line_has_any(line: str, words: list[str]) -> list[str]:
    return [word for word in words if word and word in line]


def checkpoint_required_pattern_groups(checkpoint_id: str, checkpoint_title: str) -> list[list[str]]:
    """Return AND groups used to suppress noisy one-word recalls."""
    title = f"{checkpoint_id} {checkpoint_title}"
    bd01_groups = {
        "BD01-001": [["注册地", "住所地", "经营地", "本地", "当地", "深圳", "宝安"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
        "BD01-002": [["分支机构", "办事处", "服务点", "本地服务", "售后服务点"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
        "BD01-003": [["距离", "车程", "响应半径", "公里", "分钟", "小时内", "到达"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
        "BD01-004": [["登记", "注册", "备案", "入库", "报名"], ["采购活动前", "投标前", "参与", "资格", "评分", "无效", "必须", "须"]],
        "BD01-005": [["平台", "系统", "入驻", "账号", "软件"], ["提前", "投标前", "参与", "资格", "评分", "无效", "必须", "须", "购买"]],
        "BD01-006": [["备选库", "名录库", "资格库", "供应商库", "库内"], ["准入", "资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD01-007": [["指定软件", "软件", "客户端", "系统", "平台", "工具"], ["购买", "安装", "使用", "参与", "投标", "资格", "评分", "无效", "必须", "须"]],
        "BD01-008": [["国有", "民营", "外资", "中外合资", "所有制"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
        "BD01-009": [["组织形式", "法人", "事业单位", "社会组织", "企业"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
        "BD01-010": [["股权", "控股", "参股", "股东", "出资"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
        "BD01-011": [["内资", "外资", "国别", "投资者", "境外"], ["资格", "评分", "得分", "加分", "无效", "必须", "须", "不得"]],
    }
    if checkpoint_id in bd01_groups:
        return bd01_groups[checkpoint_id]

    bd02_groups = {
        "BD02-001": [["经营年限", "成立年限", "成立时间", "注册年限", "不少于", "满"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-002": [["注册资本", "注册资金", "实缴资本"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-003": [["资产总额", "净资产", "总资产"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-004": [["营业收入", "销售额", "销售收入", "年收入"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-005": [["利润", "净利润", "利润率", "盈利"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-006": [["纳税额", "税收", "纳税证明", "税收贡献"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-007": [["从业人员", "团队规模", "员工人数", "人员数量"], ["企业规模", "资格", "评分", "得分", "加分", "无效", "必须", "须"]],
        "BD02-008": [["经营范围", "营业执照", "特定字样", "包含"], ["资格", "评分", "得分", "加分", "无效", "必须", "须"]],
    }
    if checkpoint_id in bd02_groups:
        return bd02_groups[checkpoint_id]

    bd04_groups = {
        "BD04-001": [["采购需求", "需求", "服务内容", "技术要求", "商务要求"], ["不完整", "矛盾", "歧义", "不一致", "缺少", "未明确", "详见附件"]],
        "BD04-002": [["采购标的", "功能", "目标", "应用场景", "服务内容"], ["未明确", "缺少", "不清", "详见附件", "需求"]],
        "BD04-003": [["标准", "规范", "执行标准", "国家标准", "行业标准", "技术标准"], ["未明确", "缺少", "不清", "应符合", "验收", "检测"]],
        "BD04-004": [["技术要求", "技术参数", "指标", "参数", "性能"], ["未明确", "缺少", "不低于", "不少于", "优于", "满足", "评分", "负偏离"]],
        "BD04-005": [["商务要求", "履约", "服务期限", "交付", "付款", "验收"], ["未明确", "缺少", "不清", "条件", "责任"]],
        "BD04-006": [["采购需求", "项目特点", "实际需要", "服务内容", "设备"], ["不符合", "超出", "无关", "不必要", "不合理"]],
        "BD04-007": [["预算", "资产配置", "办公需要", "配置标准", "数量", "金额"], ["超出", "高于", "超过", "不合理", "不必要"]],
        "BD04-008": [["分包", "转包", "分包内容", "分包金额", "分包比例"], ["允许", "未明确", "缺少", "比例", "金额"]],
    }
    if checkpoint_id in bd04_groups:
        return bd04_groups[checkpoint_id]

    bd05_groups = {
        "BD05-001": [["特定供应商", "唯一", "指定", "原厂", "厂家", "品牌", "型号"], ["技术", "商务", "资格", "评分", "参数", "必须", "须", "无效"]],
        "BD05-002": [["技术参数", "参数组合", "规格", "型号", "配置"], ["唯一", "特定", "指向", "品牌", "厂家", "满足", "负偏离"]],
        "BD05-003": [["品牌", "型号", "商标", "制造商", "厂家"], ["指定", "限定", "唯一", "相当于", "参考", "或同等"]],
        "BD05-004": [["专利", "专有技术", "著作权", "软著"], ["指定", "必须", "须", "评分", "得分", "加分", "无效"]],
        "BD05-005": [["参数", "指标", "规格", "配置", "组合"], ["唯一", "特定", "指向", "同时满足", "全部满足", "负偏离"]],
        "BD05-006": [["原厂授权", "制造商授权", "厂家授权", "原厂证明", "制造商证明"], ["资格", "评分", "得分", "无效", "必须", "须", "门槛"]],
        "BD05-007": [["厂家彩页", "说明书", "检测报告", "技术参数证明", "截图", "证明材料"], ["参数", "负偏离", "不得分", "无效", "必须", "须", "过密", "过细"]],
    }
    if checkpoint_id in bd05_groups:
        return bd05_groups[checkpoint_id]

    if checkpoint_id == "BD11-003":
        return [
            ["澄清", "修改", "更正", "答疑", "补遗"],
            ["顺延", "延期", "截止", "开标", "提交", "影响投标文件编制", "不足十五", "不足15"],
        ]
    if checkpoint_id == "BD11-001":
        return [
            ["公告", "更正公告", "投标邀请", "采购文件", "投标人须知", "前附表"],
            ["预算", "最高限价", "资格", "评标方法", "采购方式", "截止", "开标", "项目名称", "项目编号"],
        ]
    if checkpoint_id == "BD11-002":
        return [
            ["项目名称", "项目编号", "预算", "最高限价", "采购需求", "资格要求", "获取采购文件", "提交截止", "开标", "联系人", "联系方式", "公告期限"],
            ["空白", "缺失", "未明确", "另行通知", "详见公告", "详见附件", "待定"],
        ]
    if checkpoint_id == "BD13-002":
        return [
            ["检测报告", "认证证书", "合同业绩", "验收报告", "发票", "查询截图", "第三方证明", "原件", "证书"],
            ["高分", "得分", "不得分", "缺一", "必须", "须", "无效", "截图", "协会", "平台", "原件备查", "特定"],
        ]
    if checkpoint_id in {"BD13-004", "BD13-005", "BD13-006", "BD13-007"}:
        return [
            ["不同投标", "供应商", "投标人", "报价", "账户", "机器码", "创建标识码", "文件作者", "保证金"],
            ["一致", "相同", "同一", "规律", "异常", "转出"],
        ]
    if "澄清修改" in title:
        return [["澄清", "修改", "更正", "答疑", "补遗"], ["顺延", "截止", "开标", "提交"]]
    return []


def line_matches_required_groups(line: str, required_groups: list[list[str]]) -> bool:
    if not required_groups:
        return True
    return all(any(word in line for word in group) for group in required_groups)


def is_response_format_line(line: str) -> bool:
    return any(
        word in line
        for word in [
            "投标函",
            "声明函",
            "授权委托书",
            "承诺函",
            "报价表",
            "格式自拟",
            "单位名称",
            "项目名称）",
            "（项目名称）",
            "（标的名称）",
        ]
    )


def is_static_warning_line(line: str) -> bool:
    return any(
        phrase in line
        for phrase in [
            "如有虚假，将依法承担相应责任",
            "提供虚假材料谋取中标",
            "追究相应责任",
            "不得提供虚假材料",
            "法律法规规定追究",
        ]
    )


def needs_scoring_weight_context(checkpoint_id: str, checkpoint_title: str) -> bool:
    if checkpoint_id.startswith(("BD03", "BD06", "BD07", "BD09", "BD13")):
        return True
    return any(word in checkpoint_title for word in ["评分", "得分", "认证", "证书", "业绩", "荣誉", "软著"])


def collect_scoring_weight_context(raw_lines: list[str], max_chars: int = 12000) -> str:
    ranges: list[tuple[int, int]] = []
    for idx, line in enumerate(raw_lines):
        if any(phrase in line for phrase in ["评标总得分", "F1、F2", "权重(A1", "评分项"]):
            ranges.append((max(0, idx - 6), min(len(raw_lines), idx + 36)))
        if "权重(%)" in line or line.strip() == "权重":
            ranges.append((max(0, idx - 8), min(len(raw_lines), idx + 90)))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    lines: list[str] = []
    for start, end in merged[:6]:
        for line_no in range(start + 1, end + 1):
            lines.append(f"{line_no:04d}: {raw_lines[line_no - 1]}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[评分折算上下文已截断]"
    return text


def collect_candidate_windows(
    review_text: str,
    keyword_groups: dict[str, list[str]],
    checkpoint_id: str,
    checkpoint_title: str,
    context_before: int,
    context_after: int,
    max_windows: int,
    max_line_chars: int,
    max_excerpt_chars: int,
    min_candidate_score: int,
) -> tuple[str, int, dict[str, Any]]:
    raw_lines = source_lines(review_text)
    stats: dict[str, Any] = {
        "raw_hit_count": 0,
        "filtered_hit_count": 0,
        "selected_scores": [],
        "max_score": 0,
        "skip_reason": "",
    }
    if not raw_lines:
        stats["skip_reason"] = "待审文件文本为空"
        return "", 0, stats

    def words_from_named_groups(*name_parts: str) -> list[str]:
        words: list[str] = []
        for group_name, group_words in keyword_groups.items():
            if any(part in group_name for part in name_parts):
                words.extend(group_words)
        return words

    table_words = keyword_groups.get("表头词", []) + words_from_named_groups("表头", "评分")
    object_words = (
        keyword_groups.get("对象词", [])
        + words_from_named_groups("对象", "方案", "演示", "样品", "比较", "人员", "证书", "产品", "参数")
    )
    limit_words = keyword_groups.get("限制词", []) + words_from_named_groups("限制")
    consequence_words = (
        keyword_groups.get("后果词", [])
        + words_from_named_groups("后果", "评分", "分档", "缺失信号")
        + ["得分", "加分", "满分", "不得分", "扣分", "评分", "评审"]
    )
    required_groups = checkpoint_required_pattern_groups(checkpoint_id, checkpoint_title)

    scored: list[tuple[int, int, int, dict[str, list[str]]]] = []
    for idx, line in enumerate(raw_lines):
        hits = {group: line_has_any(line, words) for group, words in keyword_groups.items()}
        total_hits = sum(len(words) for words in hits.values())
        if total_hits == 0:
            continue
        stats["raw_hit_count"] += 1
        if not line_matches_required_groups(line, required_groups):
            continue
        if checkpoint_id == "BD11-002" and is_response_format_line(line):
            continue
        if checkpoint_id == "BD13-002" and is_static_warning_line(line):
            continue

        has_table = bool(line_has_any(line, table_words))
        has_object = bool(line_has_any(line, object_words))
        has_limit = bool(line_has_any(line, limit_words))
        has_consequence = bool(line_has_any(line, consequence_words))

        score = total_hits
        line_has_score_signal = bool(re.search(r"(得|加|扣)?\d+(\.\d+)?\s*分|得分|加分|满分|不得分|扣分|评分|评审", line))
        if has_object and has_consequence:
            score += 8
        if has_table and has_object and has_consequence:
            score += 10
        if has_object and has_limit and has_consequence:
            score += 10
        if has_object and ("资格" in line or "符合性" in line or "实质性" in line):
            score += 6
        if has_object and line_has_score_signal:
            score += 8
        if has_consequence and line_has_score_signal:
            score += 4
        if has_table and line_has_score_signal:
            score += 4
        if not has_object and total_hits:
            score -= 1

        if checkpoint_id == "BD11-003" and "修改" in line and not any(word in line for word in ["澄清", "更正", "答疑", "补遗", "顺延", "延期"]):
            score -= 10
        if checkpoint_id == "BD11-003" and any(word in line for word in ["开标后", "评审过程中", "评审委员会"]) and not any(word in line for word in ["招标文件的澄清", "招标文件的修改", "更正公告", "投标截止"]):
            score -= 10
        if checkpoint_id == "BD13-002" and is_response_format_line(line) and not any(word in line for word in ["高分", "不得分", "缺一", "原件备查", "查询截图"]):
            score -= 8
        if score < min_candidate_score:
            continue

        stats["filtered_hit_count"] += 1
        start = max(0, idx - context_before)
        end = min(len(raw_lines), idx + context_after + 1)
        start = expand_template_context_start(raw_lines, start, end)
        scored.append((score, start, end, hits))

    if not scored:
        if stats["raw_hit_count"]:
            stats["skip_reason"] = "仅命中弱关键词或被专用召回边界排除"
        else:
            stats["skip_reason"] = "未命中检查点关键词"
        return "", 0, stats

    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    selected = scored[:max_windows]
    selected.sort(key=lambda item: item[1])
    stats["selected_scores"] = [item[0] for item in selected]
    stats["max_score"] = max(stats["selected_scores"] or [0])

    merged: list[tuple[int, int, int, dict[str, list[str]]]] = []
    for score, start, end, hits in selected:
        if not merged or start > merged[-1][2]:
            merged.append((score, start, end, hits))
            continue
        prev_score, prev_start, prev_end, prev_hits = merged[-1]
        merged_hits = {
            group: sorted(set(prev_hits.get(group, [])) | set(hits.get(group, [])))
            for group in set(prev_hits) | set(hits)
        }
        merged[-1] = (max(prev_score, score), prev_start, max(prev_end, end), merged_hits)

    chunks: list[str] = []
    for idx, (score, start, end, hits) in enumerate(merged, start=1):
        hit_parts = []
        for group, words in hits.items():
            if words:
                hit_parts.append(f"{group}=" + "、".join(words))
        chunk_lines = []
        for line_no in range(start + 1, end + 1):
            line = raw_lines[line_no - 1]
            if len(line) > max_line_chars:
                line = line[:max_line_chars] + "……[本行已截断]"
            chunk_lines.append(f"{line_no:04d}: {line}")
        if needs_scoring_weight_context(checkpoint_id, checkpoint_title):
            chunk_lines.append("")
            chunk_lines.append(
                "评分折算提示：若本窗口表头包含“评分因素 / 权重(%) / 评分准则”，"
                "评分因素名称后的数字通常是该评分因素权重；"
                "条款中的“得N分、优得N分、最高得N分、满分N分”通常是该因素内部得分，"
                "必须结合权重折算后再评价实际总分影响。"
            )
        chunks.append(
            f"[候选窗口 {idx}] score={score}; " + "；".join(hit_parts) + "\n" + "\n".join(chunk_lines)
        )
    if needs_scoring_weight_context(checkpoint_id, checkpoint_title):
        scoring_context = collect_scoring_weight_context(raw_lines)
        if scoring_context:
            chunks.insert(
                0,
                "[评分折算上下文]\n"
                "以下内容用于判断“内部满分”和“实际总分权重”的关系；"
                "审查评分项时必须优先读取。\n"
                + scoring_context,
            )
    excerpt = "\n\n".join(chunks)
    if len(excerpt) > max_excerpt_chars:
        excerpt = excerpt[:max_excerpt_chars] + "\n\n[候选窗口已按 max-review-excerpt-chars 截断]"
    return excerpt, len(merged), stats


def build_messages(
    checkpoint_id: str,
    checkpoint_title: str,
    checkpoint_text: str,
    review_name: str,
    review_excerpt: str,
) -> list[dict[str, str]]:
    system = (
        "/no_think\n"
        "你是政府采购招标文件合规审查小模型。"
        "你只能根据给定的 BD 检查点执行说明书和待审文件候选窗口进行审查。"
        "你必须按检查点中的流程执行：候选召回、上下文读取、条款属性判断、相关性三问、基础命中条件、排除条件、核心条件计数、结果分流。"
        "你不能发明未出现在原文中的证据，不能只因关键词命中就输出命中。"
        "不要输出思考过程，不要输出解释性前言，输出必须是 JSON。"
    )
    user = textwrap.dedent(
        f"""
        目标检查点：{checkpoint_id} {checkpoint_title}
        待审文件：{review_name}

        执行要求：
        1. 只能根据下方 BD 检查点执行说明书审查。
        2. 必须先列出候选条款，再逐条执行三问、A/B/C 基础命中、排除条件和核心条件计数。
        3. 最终结论只能是：命中 / 待人工复核 / 不命中。
        4. 如果证据不足，必须输出待人工复核，不能强行命中。
        5. 证据摘录必须来自待审文件候选窗口，不得改写原文。
        6. 必须返回严格合法 JSON：所有字符串内部禁止出现未转义的英文双引号，不要在字符串中用英文双引号列举关键词。
        7. 如果没有候选条款，candidates 必须返回空数组 []，candidate_count 填 0，各步骤 summary 控制在 80 个汉字以内。
        8. 不要复制大段关键词清单，不要输出制表符、异常空白、重复占位符或超长空白。
        9. 审查评分项时，必须区分“评分因素内部得分”和“折算后的评标总分影响”。
        10. 如果原文存在“评标总得分=F×A”或“权重(%)”，不得把“得N分、优得N分、最高得N分、满分N分”直接表述为总分高或分值占比高；必须先读取对应权重。
        11. 无法确认权重时，只能表述为“该评分因素内部得分为 N 分，实际总分影响需结合权重折算”，不得使用“分值高达、分值极高、完全决定评标结果”等表达。
        12. 审查合同或商务条款留白时，必须先判断该条款是正式专用条款，还是“合同条款及格式、合同模板、合同范本、示范文本、仅供参考”类文本。
        13. 如果留白位于仅供参考的合同格式或模板范文中，且采购需求、专用条款或其他正式章节可能补足，不得直接输出命中；应输出待人工复核，并说明需核对正式专用条款或最终签署合同。

        输出 JSON 结构：
        {{
          "checkpoint_id": "{checkpoint_id}",
          "checkpoint_title": "{checkpoint_title}",
          "verdict": "命中|待人工复核|不命中",
          "summary": "一句话总结审查结论",
          "execution_trace": {{
            "candidate_recall": {{"status": "已执行", "summary": "...", "candidate_count": 0}},
            "context_reading": {{"status": "已执行", "summary": "..."}},
            "clause_classification": {{"status": "已执行", "summary": "...", "clause_types": []}},
            "relevance_three_questions": {{"status": "已执行", "summary": "..."}},
            "basic_hit_abc": {{"status": "已执行", "A": false, "B": false, "C": false, "summary": "..."}},
            "exclusion_checks": {{"status": "已执行", "triggered": [], "not_triggered": []}},
            "core_condition_count": {{"status": "已执行", "count": 0, "summary": "..."}},
            "result_branch": {{"status": "已执行", "branch": "命中|待人工复核|不命中", "reason": "..."}}
          }},
          "candidates": [
            {{
              "line_anchor": "行号范围，例如 0123-0128",
              "excerpt": "原文证据摘录",
              "matched_keyword_groups": {{"表头词": [], "对象词": [], "限制词": [], "后果词": []}},
              "clause_type": "评分项|资格条件|符合性审查|实质性响应|证明材料|履约能力说明|模板残留|其他",
              "three_questions": {{
                "certificate_capability": "...",
                "same_capability_in_demand": "是|否|不确定",
                "direct_effect_on_performance": "是|否|不确定"
              }},
              "basic_hit_abc": {{"A": false, "B": false, "C": false}},
              "triggered_exclusions": [],
              "core_conditions_met": [],
              "core_condition_count": 0,
              "candidate_verdict": "命中|待人工复核|不命中",
              "reason": "..."
            }}
          ]
        }}

        【BD 检查点执行说明书】
        {checkpoint_text}

        【待审文件候选窗口】
        {review_excerpt}
        """
    ).strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def post_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout_seconds: int,
    max_tokens: int,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
        "enable_thinking": False,
    }
    command = [
        "curl",
        "-sS",
        "--max-time",
        str(timeout_seconds),
        "-H",
        "Content-Type: application/json",
        "-H",
        f"Authorization: Bearer {api_key}",
        "--data",
        json.dumps(payload, ensure_ascii=False),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"接口未返回合法 JSON：{result.stdout[:1000]}") from exc


def parse_model_json(response: dict[str, Any]) -> dict[str, Any]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"模型响应结构异常：{response}") from exc
    if content is None:
        message = response.get("choices", [{}])[0].get("message", {})
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip().startswith("{"):
            content = reasoning
        else:
            raise RuntimeError("模型返回 content 为空；可能仍在输出 reasoning，请降低 max_tokens 或关闭 thinking")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"模型未返回合法 JSON：{content[:1000]}") from exc


def normalize_result(result: dict[str, Any], checkpoint_id: str, checkpoint_title: str) -> dict[str, Any]:
    result.setdefault("checkpoint_id", checkpoint_id)
    result.setdefault("checkpoint_title", checkpoint_title)
    if result.get("verdict") not in {"命中", "待人工复核", "不命中"}:
        result["verdict"] = "待人工复核"
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        result["candidates"] = []
    trace = result.get("execution_trace")
    if not isinstance(trace, dict):
        trace = {}
    required_steps = [
        "candidate_recall",
        "context_reading",
        "clause_classification",
        "relevance_three_questions",
        "basic_hit_abc",
        "exclusion_checks",
        "core_condition_count",
        "result_branch",
    ]
    for step in required_steps:
        current = trace.get(step)
        if not isinstance(current, dict):
            current = {}
        current.setdefault("status", "已执行")
        current.setdefault("summary", "")
        trace[step] = current
    result["execution_trace"] = trace
    return result


def build_fast_skip_result(checkpoint_id: str, checkpoint_title: str, reason: str) -> dict[str, Any]:
    summary = reason or "未召回有效候选条款，按 fast-skip 判定不命中。"
    return normalize_result(
        {
            "checkpoint_id": checkpoint_id,
            "checkpoint_title": checkpoint_title,
            "verdict": "不命中",
            "summary": summary,
            "execution_trace": {
                "candidate_recall": {"status": "已执行", "summary": summary, "candidate_count": 0},
                "context_reading": {"status": "已跳过", "summary": "无有效候选窗口，未调用小模型。"},
                "clause_classification": {"status": "已跳过", "summary": "无候选条款。", "clause_types": []},
                "relevance_three_questions": {"status": "已跳过", "summary": "无候选条款。"},
                "basic_hit_abc": {"status": "已执行", "A": False, "B": False, "C": False, "summary": "无有效候选条款。"},
                "exclusion_checks": {"status": "已执行", "triggered": ["fast-skip：无有效候选"], "not_triggered": []},
                "core_condition_count": {"status": "已执行", "count": 0, "summary": "核心条件未成立。"},
                "result_branch": {"status": "已执行", "branch": "不命中", "reason": summary},
            },
            "candidates": [],
        },
        checkpoint_id,
        checkpoint_title,
    )


def should_two_stage_skip(recall_stats: dict[str, Any], stage1_min_score: int) -> tuple[bool, str]:
    max_score = int(recall_stats.get("max_score") or 0)
    filtered_hits = int(recall_stats.get("filtered_hit_count") or 0)
    if max_score <= 0:
        return True, str(recall_stats.get("skip_reason") or "两阶段预筛未召回有效候选。")
    if max_score < stage1_min_score:
        return True, f"两阶段预筛最高风险分 {max_score} 低于阈值 {stage1_min_score}，仅作弱候选记录。"
    if filtered_hits == 0:
        return True, "两阶段预筛无过滤后候选。"
    return False, ""


def stage1_threshold_for_checkpoint(args: argparse.Namespace, checkpoint_id: str) -> int:
    domain = checkpoint_id.split("-")[0]
    mode_thresholds = DOMAIN_STAGE1_THRESHOLDS.get(args.mode, {})
    return int(mode_thresholds.get(domain, args.stage1_min_score))


def apply_mode_defaults(args: argparse.Namespace) -> None:
    defaults = MODE_DEFAULTS[args.mode]
    for key, value in defaults.items():
        if getattr(args, key) is None:
            setattr(args, key, value)


def normalize_evidence_line(line: str) -> str:
    line = re.sub(r"^\s*\d{1,5}\s*[:：]\s*", "", line)
    line = re.sub(r"\s+", " ", line.strip())
    return line


def compact_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text)


def extract_evidence_lines(excerpt: str) -> list[str]:
    lines: list[str] = []
    for line in source_lines(excerpt):
        normalized = normalize_evidence_line(line)
        if not normalized:
            continue
        if re.fullmatch(r"\d+", normalized):
            continue
        if len(normalized) <= 2:
            continue
        if normalized in {"```", "```text", "证据摘录："}:
            continue
        if normalized.startswith("……") or normalized.startswith("["):
            continue
        lines.append(normalized)
    return lines


def find_line_anchor_from_excerpt(excerpt: str, review_text: str) -> str | None:
    numbered = []
    for line in source_lines(excerpt):
        match = re.match(r"^\s*(\d{1,5})\s*[:：]", line)
        if match:
            numbered.append(int(match.group(1)))
    if numbered:
        return f"{min(numbered):04d}-{max(numbered):04d}"

    evidence_lines = extract_evidence_lines(excerpt)
    if len(evidence_lines) == 1 and len(evidence_lines[0]) > 80:
        fragments = [
            normalize_evidence_line(fragment)
            for fragment in re.split(r"[；;。]", evidence_lines[0])
        ]
        evidence_lines = [fragment for fragment in fragments if len(fragment) > 8 and not re.fullmatch(r"\d+", fragment)]
    evidence_lines = evidence_lines[:8]
    if not evidence_lines:
        return None

    raw_lines = [normalize_evidence_line(line) for line in source_lines(review_text)]
    best: tuple[int, int, int] | None = None
    for start_idx, raw_line in enumerate(raw_lines):
        if not raw_line:
            continue
        evidence_idx = 0
        matched: list[int] = []
        for raw_idx in range(start_idx, len(raw_lines)):
            if evidence_idx >= len(evidence_lines):
                break
            current_raw = raw_lines[raw_idx]
            current_evidence = evidence_lines[evidence_idx]
            if not current_raw:
                continue
            raw_compact = compact_for_match(current_raw)
            evidence_compact = compact_for_match(current_evidence)
            raw_in_evidence = len(current_raw) > 8 and current_raw in current_evidence
            compact_match = (
                raw_compact == evidence_compact
                or evidence_compact in raw_compact
                or (len(raw_compact) > 8 and raw_compact in evidence_compact)
            )
            if current_raw == current_evidence or current_evidence in current_raw or raw_in_evidence or compact_match:
                matched.append(raw_idx + 1)
                evidence_idx += 1
        if not matched:
            continue
        score = len(matched)
        span = matched[-1] - matched[0]
        if best is None or score > best[0] or (score == best[0] and span < best[2] - best[1]):
            best = (score, matched[0], matched[-1])
        if score == len(evidence_lines):
            break

    if best and best[0] >= 2:
        return f"{best[1]:04d}-{best[2]:04d}"
    return None


def repair_candidate_line_anchors(result: dict[str, Any], review_text: str) -> None:
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        excerpt = str(candidate.get("excerpt", "")).strip()
        repaired = find_line_anchor_from_excerpt(excerpt, review_text)
        if not repaired:
            continue
        original = str(candidate.get("line_anchor", "")).strip()
        if original and original != repaired:
            candidate["original_line_anchor"] = original
        candidate["line_anchor"] = repaired


def trace_step_summary(key: str, step: dict[str, Any]) -> str:
    summary = str(step.get("summary", "")).strip()
    if summary:
        return summary
    if key == "exclusion_checks":
        triggered = step.get("triggered")
        not_triggered = step.get("not_triggered")
        parts: list[str] = []
        if isinstance(triggered, list) and triggered:
            parts.append("触发：" + "；".join(str(item) for item in triggered))
        else:
            parts.append("未触发排除条件")
        if isinstance(not_triggered, list) and not_triggered:
            parts.append("未触发项：" + "；".join(str(item) for item in not_triggered))
        return "；".join(parts)
    if key == "result_branch":
        branch = str(step.get("branch", "")).strip()
        reason = str(step.get("reason", "")).strip()
        if branch and reason:
            return f"{branch}：{reason}"
        return branch or reason
    if key == "basic_hit_abc":
        flags = []
        for name in ["A", "B", "C"]:
            if name in step:
                flags.append(f"{name}={step.get(name)}")
        return "，".join(flags)
    return ""


def markdown_report(report: dict[str, Any]) -> str:
    result = report["model_result"]
    candidates = result.get("candidates", [])
    lines = [
        f"# {report['checkpoint_id']} {report['checkpoint_title']} 验证报告",
        "",
        "## 运行信息",
        f"- 开始时间：{report['started_at']}",
        f"- 结束时间：{report['ended_at']}",
        f"- 模型：{report['model']}",
        f"- 检查点：{report['checkpoint_path']}",
        f"- 待审文件：{report['review_file']}",
        f"- 文本抽取方式：{report['text_extractor']}",
        "",
        "## 结论",
        f"- 结果：{result.get('verdict', '待人工复核')}",
        f"- 摘要：{result.get('summary', '')}",
        "",
        "## 执行过程",
    ]
    trace = result.get("execution_trace", {})
    for key, label in [
        ("candidate_recall", "候选召回"),
        ("context_reading", "上下文读取"),
        ("clause_classification", "条款属性判断"),
        ("relevance_three_questions", "相关性三问"),
        ("basic_hit_abc", "基础命中 A/B/C"),
        ("exclusion_checks", "排除条件"),
        ("core_condition_count", "核心条件计数"),
        ("result_branch", "结果分流"),
    ]:
        step = trace.get(key, {})
        lines.append(f"- {label}：{trace_step_summary(key, step)}")
    lines.extend(["", "## 候选条款"])
    if not candidates:
        lines.append("- 未召回候选条款。")
    for idx, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"### 候选 {idx}",
                f"- 行号：{candidate.get('line_anchor', '')}",
                f"- 条款属性：{candidate.get('clause_type', '')}",
                f"- 候选结论：{candidate.get('candidate_verdict', '')}",
                f"- 理由：{candidate.get('reason', '')}",
                "",
                "证据摘录：",
                "",
                "```text",
                str(candidate.get("excerpt", "")).strip(),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## 机器可读结果",
            "",
            "```json",
            json.dumps(result, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def summary_markdown(report: dict[str, Any]) -> str:
    result = report["model_result"]
    return "\n".join(
        [
            f"# {report['checkpoint_id']} 验证摘要",
            "",
            f"- 检查点：{report['checkpoint_title']}",
            f"- 待审文件：{report['review_file']}",
            f"- 结果：{result.get('verdict', '待人工复核')}",
            f"- 摘要：{result.get('summary', '')}",
            f"- 开始时间：{report['started_at']}",
            f"- 结束时间：{report['ended_at']}",
            f"- 报告：[[{Path(report['report_file']).name}]]",
            "",
        ]
    )


def verdict_rank(verdict: str) -> int:
    return {"命中": 0, "待人工复核": 1, "不命中": 2}.get(verdict, 3)


def load_batch_results(run_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for result_file in sorted(run_dir.glob("**/result.json")):
        try:
            data = json.loads(read_text(result_file))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"无法读取结果文件：{relative_path(result_file)}") from exc
        data["_result_file"] = relative_path(result_file)
        results.append(data)
    if not results:
        raise RuntimeError(f"未在批次目录中找到 result.json：{relative_path(run_dir)}")
    results.sort(
        key=lambda item: (
            verdict_rank(item.get("model_result", {}).get("verdict", "")),
            item.get("checkpoint_id", ""),
        )
    )
    return results


def candidate_summary(candidate: dict[str, Any]) -> str:
    reason = str(candidate.get("reason", "")).strip()
    if reason:
        return reason
    verdict = str(candidate.get("candidate_verdict", "")).strip()
    return f"候选条款结论为{verdict}" if verdict else "模型未提供候选理由。"


def format_candidate_evidence(candidate: dict[str, Any]) -> list[str]:
    lines = [
        f"- 行号证据：`{candidate.get('line_anchor', '')}`",
        f"- 条款属性：{candidate.get('clause_type', '')}",
        f"- 候选结论：{candidate.get('candidate_verdict', '')}",
        f"- 风险原因：{candidate_summary(candidate)}",
    ]
    three_questions = candidate.get("three_questions")
    if isinstance(three_questions, dict):
        lines.extend(
            [
                "- 相关性三问：",
                f"  - 证明能力：{three_questions.get('certificate_capability', '')}",
                f"  - 需求中是否存在同一能力：{three_questions.get('same_capability_in_demand', '')}",
                f"  - 是否直接影响履约：{three_questions.get('direct_effect_on_performance', '')}",
            ]
        )
    basic_hit = candidate.get("basic_hit_abc")
    if isinstance(basic_hit, dict):
        lines.append(
            "- 基础命中 A/B/C："
            f"A={basic_hit.get('A')}, B={basic_hit.get('B')}, C={basic_hit.get('C')}"
        )
    exclusions = candidate.get("triggered_exclusions")
    if isinstance(exclusions, list) and exclusions:
        lines.append("- 触发排除条件：" + "；".join(str(item) for item in exclusions))
    core_conditions = candidate.get("core_conditions_met")
    if isinstance(core_conditions, list) and core_conditions:
        lines.append("- 已满足核心条件：" + "；".join(str(item) for item in core_conditions))
    excerpt = str(candidate.get("excerpt", "")).strip()
    if excerpt:
        lines.extend(["- 证据摘录：", "", "```text", excerpt, "```"])
    return lines


def batch_audit_report_markdown(run_dir: Path, results: list[dict[str, Any]]) -> str:
    started_values = [item.get("started_at", "") for item in results if item.get("started_at")]
    ended_values = [item.get("ended_at", "") for item in results if item.get("ended_at")]
    review_files = sorted({item.get("review_file", "") for item in results if item.get("review_file")})
    models = sorted({item.get("model", "") for item in results if item.get("model")})
    hit_items = [item for item in results if item.get("model_result", {}).get("verdict") == "命中"]
    review_items = [item for item in results if item.get("model_result", {}).get("verdict") == "待人工复核"]
    clean_items = [item for item in results if item.get("model_result", {}).get("verdict") == "不命中"]

    title_review_file = Path(review_files[0]).name if review_files else "未知待审文件"
    lines = [
        "---",
        f"title: {title_review_file} 小模型检查点审查报告",
        "page_type: checkpoint-cli-audit-report",
        f"run_dir: {relative_path(run_dir)}",
        f"generated_at: {now_text()}",
        "---",
        "",
        f"# {title_review_file} 小模型检查点审查报告",
        "",
        "## 运行信息",
        f"- 批次目录：{relative_path(run_dir)}",
        f"- 待审文件：{review_files[0] if review_files else ''}",
        f"- 模型：{', '.join(models)}",
        f"- 开始时间：{min(started_values) if started_values else ''}",
        f"- 结束时间：{max(ended_values) if ended_values else ''}",
        f"- 检查点数量：{len(results)}",
        f"- 命中数量：{len(hit_items)}",
        f"- 待人工复核数量：{len(review_items)}",
        f"- 不命中数量：{len(clean_items)}",
        "",
        "## 主审查结论",
    ]
    if hit_items:
        hit_titles = "、".join(f"{item.get('checkpoint_id')} {item.get('checkpoint_title')}" for item in hit_items)
        lines.append(f"本次小模型按检查点 SOP 执行后，认定存在 {len(hit_items)} 项命中风险：{hit_titles}。")
    else:
        lines.append("本次小模型按检查点 SOP 执行后，未输出明确命中风险。")
    if review_items:
        review_titles = "、".join(f"{item.get('checkpoint_id')} {item.get('checkpoint_title')}" for item in review_items)
        lines.append(f"另有 {len(review_items)} 项输出为待人工复核：{review_titles}。这些事项已召回候选证据，但模型认为相关性、必要性、替代路径或排除条件仍需人工确认。")
    if clean_items:
        lines.append(f"其余 {len(clean_items)} 项暂未发现命中情形，列入未命中事项备查。")
    lines.extend(
        [
            "",
            "说明：本报告是业务系统调用检查点 SOP 后的小模型审查产物，作用类似 `full-risk-scan` 的审查结果页；正式定性仍应结合原文、法规依据和人工复核。",
            "",
        ]
    )

    issue_no = 1
    if hit_items:
        lines.append("## 命中风险点")
        for item in hit_items:
            result = item["model_result"]
            candidates = [
                candidate
                for candidate in result.get("candidates", [])
                if candidate.get("candidate_verdict") in {"命中", "待人工复核"}
            ]
            lines.extend(
                [
                    "",
                    f"## 风险点 {issue_no}：{item.get('checkpoint_title')}（{result.get('verdict')}）",
                    "",
                    "- 风险等级：高",
                    f"- 检查点：`{item.get('checkpoint_id')} {item.get('checkpoint_title')}`",
                    f"- 检查点文件：{item.get('checkpoint_path', '')}",
                    f"- 审查结论：{result.get('summary', '')}",
                    "- 项目具体风险：",
                    f"  - {result.get('summary', '')}",
                    "- 风险原因：",
                ]
            )
            if candidates:
                lines.append(f"  - 模型在候选条款中发现 {len(candidates)} 处与该检查点相关的风险或需复核事项。")
            else:
                lines.append("  - 模型未返回可展开候选条款，需回看单点报告。")
            lines.append("- 行号证据：")
            if candidates:
                for candidate in candidates:
                    lines.append(f"  - `{candidate.get('line_anchor', '')}`：{candidate_summary(candidate)}")
            else:
                lines.append("  - 暂无候选行号。")
            lines.extend(["- 候选条款明细：", ""])
            if candidates:
                for candidate_index, candidate in enumerate(candidates, start=1):
                    lines.append(f"### 候选 {candidate_index}")
                    lines.extend(format_candidate_evidence(candidate))
                    lines.append("")
            else:
                lines.append("- 未返回候选条款。")
            lines.extend(
                [
                    "- 回链：",
                    f"  - 单点报告：{item.get('report_file', '')}",
                    f"  - 机器结果：{item.get('_result_file', '')}",
                ]
            )
            issue_no += 1
        lines.append("")

    if review_items:
        lines.append("## 待人工复核事项")
        for item in review_items:
            result = item["model_result"]
            candidates = [
                candidate
                for candidate in result.get("candidates", [])
                if candidate.get("candidate_verdict") in {"命中", "待人工复核"}
            ]
            lines.extend(
                [
                    "",
                    f"## 复核点 {issue_no}：{item.get('checkpoint_title')}（{result.get('verdict')}）",
                    "",
                    "- 风险等级：待人工复核",
                    f"- 检查点：`{item.get('checkpoint_id')} {item.get('checkpoint_title')}`",
                    f"- 检查点文件：{item.get('checkpoint_path', '')}",
                    f"- 审查结论：{result.get('summary', '')}",
                    "- 复核原因：",
                    f"  - {result.get('summary', '')}",
                    "- 行号证据：",
                ]
            )
            if candidates:
                for candidate in candidates:
                    lines.append(f"  - `{candidate.get('line_anchor', '')}`：{candidate_summary(candidate)}")
            else:
                lines.append("  - 暂无候选行号。")
            lines.extend(["- 候选条款明细：", ""])
            if candidates:
                for candidate_index, candidate in enumerate(candidates, start=1):
                    lines.append(f"### 候选 {candidate_index}")
                    lines.extend(format_candidate_evidence(candidate))
                    lines.append("")
            else:
                lines.append("- 未返回候选条款。")
            lines.extend(
                [
                    "- 回链：",
                    f"  - 单点报告：{item.get('report_file', '')}",
                    f"  - 机器结果：{item.get('_result_file', '')}",
                ]
            )
            issue_no += 1
        lines.append("")

    lines.append("## 未命中事项")
    if clean_items:
        for item in clean_items:
            result = item["model_result"]
            lines.extend(
                [
                    f"- `{item.get('checkpoint_id')} {item.get('checkpoint_title')}`：{result.get('summary', '')}",
                    f"  - 单点报告：{item.get('report_file', '')}",
                ]
            )
    else:
        lines.append("- 无。")

    lines.extend(["", "## 回链", f"- 批次日志：{relative_path(run_dir / 'batch.log')}", f"- 结果表：{relative_path(run_dir / 'results.tsv')}"])
    return "\n".join(lines) + "\n"


def parse_line_anchor(anchor: str) -> tuple[int | None, int | None]:
    numbers = [int(item) for item in re.findall(r"\d{1,6}", str(anchor))]
    if not numbers:
        return None, None
    return min(numbers), max(numbers)


def normalize_excerpt_key(excerpt: str) -> str:
    text = re.sub(r"\s+", "", str(excerpt))
    text = re.sub(r"^\d{1,6}[:：]", "", text)
    return text[:160]


def evidence_group_key(candidate: dict[str, Any]) -> str:
    start, end = parse_line_anchor(str(candidate.get("line_anchor", "")))
    if start is not None and end is not None:
        # 适度按行号分桶，避免同一长条款在不同 BD 中因行号略有差异而重复。
        return f"line:{start // 5}-{end // 5}"
    excerpt_key = normalize_excerpt_key(str(candidate.get("excerpt", "")))
    return f"excerpt:{excerpt_key}" if excerpt_key else "unknown"


def risk_level_for_verdict(verdict: str) -> str:
    if verdict == "命中":
        return "高"
    if verdict == "待人工复核":
        return "待人工复核"
    return "低"


def compact_text_value(value: Any, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= max_chars else text[:max_chars] + "……"


def normalize_score_risk_language(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"该评分项分值高达\s*(\d+(?:\.\d+)?)\s*分",
        r"该评分项内部得分为 \1 分，需结合上级权重折算实际总分影响",
        text,
    )
    text = re.sub(
        r"分值高达\s*(\d+(?:\.\d+)?)\s*分",
        r"内部得分为 \1 分，需结合上级权重折算实际总分影响",
        text,
    )
    text = re.sub(
        r"分值极高[（(](\d+(?:\.\d+)?)\s*分[）)]",
        r"内部得分为 \1 分，需结合上级权重折算实际总分影响",
        text,
    )
    text = re.sub(
        r"分值占比极高",
        "需结合上级权重折算实际总分占比",
        text,
    )
    return text


TEMPLATE_REFERENCE_PHRASES = [
    "仅供参考",
    "具体以项目需求及采购结果为准",
    "以最终签订",
    "最终签署",
    "合同模板",
    "合同范本",
    "示范文本",
    "参考文本",
    "参考格式",
]

TEMPLATE_SECTION_PHRASES = [
    "合同条款及格式",
    "合同条款格式",
    "合同格式",
    "合同草案格式",
    "合同文本格式",
]


def has_placeholder_blank(text: str) -> bool:
    if re.search(r"_{3,}|＿{3,}|…{2,}|\.{4,}", text):
        return True
    return bool(re.search(r"后\s{4,}(?:个工作日|日|天)|前\s{4,}(?:个工作日|日|天)|\s{4,}(?:元|%|％|天|日|个工作日)", text))


def expand_template_context_start(raw_lines: list[str], start: int, end: int) -> int:
    """模板留白候选必须带上方章节标题，否则小模型容易把范本误当正式条款。"""
    window_text = "\n".join(raw_lines[start:end])
    if not has_placeholder_blank(window_text):
        return start
    lookback_start = max(0, start - 60)
    for idx in range(start - 1, lookback_start - 1, -1):
        line = raw_lines[idx]
        if any(phrase in line for phrase in TEMPLATE_REFERENCE_PHRASES + TEMPLATE_SECTION_PHRASES):
            return min(max(0, idx - 2), start)
    return start


def resolve_review_file_path(value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    try:
        return path.resolve()
    except Exception:
        return path


def load_review_lines_for_results(results: list[dict[str, Any]]) -> list[str]:
    review_files = sorted({str(item.get("review_file", "")) for item in results if item.get("review_file")})
    if len(review_files) != 1:
        return []
    review_path = resolve_review_file_path(review_files[0])
    if not review_path or not review_path.exists():
        return []
    try:
        review_text, _ = load_review_file(review_path)
    except Exception:
        return []
    return source_lines(review_text)


def template_context_for_candidate(candidate: dict[str, Any], review_lines: list[str]) -> dict[str, Any]:
    start, end = parse_line_anchor(str(candidate.get("line_anchor", "")))
    excerpt = str(candidate.get("excerpt", "") or "")
    reason = candidate_summary(candidate)
    if start is None or end is None or not review_lines:
        context_text = "\n".join([excerpt, reason])
    else:
        lookback_start = max(1, start - 80)
        lookahead_end = min(len(review_lines), end + 5)
        context_text = "\n".join(review_lines[lookback_start - 1 : lookahead_end])
    has_reference = any(phrase in context_text for phrase in TEMPLATE_REFERENCE_PHRASES)
    has_section = any(phrase in context_text for phrase in TEMPLATE_SECTION_PHRASES)
    # 只因候选证据自身存在待填空白才按“模板留白”降级，避免同一合同格式章节内
    # 其他非留白条款被上方模板说明误伤。
    has_blank = has_placeholder_blank(excerpt)
    is_template_blank = has_blank and (has_reference or has_section or "模板" in reason or "最终签署" in reason)
    return {
        "is_template_blank": is_template_blank,
        "has_reference": has_reference,
        "has_section": has_section,
        "has_blank": has_blank,
        "note": "该证据位于合同条款及格式、合同模板或仅供参考文本，且存在待填写空白，不能直接认定为正式商务要求缺失。"
        if is_template_blank
        else "",
    }


def context_text_for_candidate(candidate: dict[str, Any], review_lines: list[str], before: int = 80, after: int = 8) -> str:
    start, end = parse_line_anchor(str(candidate.get("line_anchor", "")))
    excerpt = str(candidate.get("excerpt", "") or "")
    if start is None or end is None or not review_lines:
        return excerpt
    lookback_start = max(1, start - before)
    lookahead_end = min(len(review_lines), end + after)
    return "\n".join(review_lines[lookback_start - 1 : lookahead_end])


def should_suppress_business_candidate(checkpoint_id: str, candidate: dict[str, Any], reason: str) -> bool:
    """业务报告只展示有可比证据的风险，不把缺少外部资料本身包装成问题。"""
    if checkpoint_id != "BD11-001":
        return False
    text = "\n".join([str(candidate.get("excerpt", "")), reason])
    missing_comparator = any(
        phrase in text
        for phrase in [
            "无公告原文",
            "缺少公告原文",
            "缺公告原文",
            "无法比对",
            "无法确认口径一致性",
            "无法执行比对",
        ]
    )
    only_reference = any(phrase in text for phrase in ["详见公告", "详见招标公告", "引用公告", "按本招标文件第一册第一章招标公告"])
    return missing_comparator or only_reference


def common_clause_context_for_candidate(candidate: dict[str, Any], review_lines: list[str]) -> dict[str, Any]:
    context_text = context_text_for_candidate(candidate, review_lines)
    excerpt = str(candidate.get("excerpt", "") or "")
    is_common_terms = (
        "通用条款" in context_text
        and any(phrase in context_text for phrase in ["具有普遍性和通用性", "以专用条款为准", "专用条款”和“通用条款"])
    )
    is_generic_standard = any(
        phrase in excerpt
        for phrase in [
            "设计、制造生产标准及行业标准",
            "符合国家强制性标准要求",
            "符合相关行业标准",
            "符合中华人民共和国的设计、制造生产标准及行业标准",
        ]
    )
    is_common_generic_standard = is_common_terms and is_generic_standard
    return {
        "is_common_generic_standard": is_common_generic_standard,
        "is_common_terms": is_common_terms,
        "is_generic_standard": is_generic_standard,
        "note": "该证据位于第二册通用条款，属于货物质量和标准的通用兜底表述；不能单独认定为项目专用执行标准缺失。"
        if is_common_generic_standard
        else "",
    }


def build_business_issues(results: list[dict[str, Any]], review_lines: list[str] | None = None) -> list[dict[str, Any]]:
    review_lines = review_lines or []
    entries: list[dict[str, Any]] = []
    for item in results:
        result = item.get("model_result", {})
        verdict = str(result.get("verdict", ""))
        if verdict not in {"命中", "待人工复核"}:
            continue
        candidates = result.get("candidates", [])
        if not isinstance(candidates, list):
            candidates = []
        relevant_candidates = [
            candidate
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("candidate_verdict") in {"命中", "待人工复核"}
        ]
        if not relevant_candidates:
            # 没有候选证据的待复核只保留在检查点报告，不进入证据视角业务报告。
            continue
        for candidate in relevant_candidates:
            start, end = parse_line_anchor(str(candidate.get("line_anchor", "")))
            reason = normalize_score_risk_language(candidate_summary(candidate))
            checkpoint_id = str(item.get("checkpoint_id", ""))
            if should_suppress_business_candidate(checkpoint_id, candidate, reason):
                continue
            template_context = template_context_for_candidate(candidate, review_lines)
            common_clause_context = common_clause_context_for_candidate(candidate, review_lines)
            effective_verdict = (
                "待人工复核"
                if template_context.get("is_template_blank") or common_clause_context.get("is_common_generic_standard")
                else verdict
            )
            effective_candidate_verdict = (
                "待人工复核"
                if template_context.get("is_template_blank") or common_clause_context.get("is_common_generic_standard")
                else str(candidate.get("candidate_verdict", ""))
            )
            if template_context.get("note"):
                reason = (
                    template_context["note"]
                    + "候选条款存在待填写空白，仅作为复核线索；"
                    + "需核对项目专用条款、采购需求书、补充条款或最终签署合同是否已补足。"
                )
            if common_clause_context.get("note"):
                reason = (
                    common_clause_context["note"]
                    + "需核对第一册专用条款、用户需求书、技术参数表或附件是否已经列明本项目适用的具体标准、规范、检测或验收依据。"
                )
            entries.append(
                {
                    "start": start,
                    "end": end,
                    "line_anchor": str(candidate.get("line_anchor", "")).strip(),
                    "excerpt": str(candidate.get("excerpt", "")).strip(),
                    "excerpt_key": normalize_excerpt_key(str(candidate.get("excerpt", ""))),
                    "verdict": effective_verdict,
                    "clause_type": str(candidate.get("clause_type", "")).strip(),
                    "reason": reason,
                    "template_context": template_context,
                    "common_clause_context": common_clause_context,
                    "checkpoint_item": {
                        "id": checkpoint_id,
                        "title": item.get("checkpoint_title", ""),
                        "verdict": effective_verdict,
                        "summary": normalize_score_risk_language(result.get("summary", "")),
                        "candidate_verdict": effective_candidate_verdict,
                        "reason": reason,
                        "report_file": item.get("report_file", ""),
                        "result_file": item.get("_result_file", ""),
                    },
                }
            )

    groups: list[dict[str, Any]] = []
    anchored = [entry for entry in entries if entry["start"] is not None and entry["end"] is not None]
    unanchored = [entry for entry in entries if entry["start"] is None or entry["end"] is None]
    anchored.sort(key=lambda entry: (entry["start"], entry["end"]))

    def new_group(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "start": entry["start"],
            "end": entry["end"],
            "line_anchor": entry["line_anchor"],
            "excerpt": entry["excerpt"],
            "verdicts": {entry["verdict"]},
            "checkpoint_items": [entry["checkpoint_item"]],
            "candidate_reasons": [entry["reason"]] if entry["reason"] else [],
            "clause_types": {entry["clause_type"]} if entry["clause_type"] else set(),
            "excerpt_keys": {entry["excerpt_key"]} if entry["excerpt_key"] else set(),
            "template_contexts": [entry["template_context"]] if entry.get("template_context") else [],
            "common_clause_contexts": [entry["common_clause_context"]] if entry.get("common_clause_context") else [],
        }

    for entry in anchored:
        if not groups:
            groups.append(new_group(entry))
            continue
        last = groups[-1]
        same_neighborhood = entry["start"] <= (last["end"] or entry["start"]) + 1
        same_excerpt = bool(entry["excerpt_key"] and entry["excerpt_key"] in last.get("excerpt_keys", set()))
        if same_neighborhood or same_excerpt:
            last["start"] = min(int(last["start"]), int(entry["start"]))
            last["end"] = max(int(last["end"]), int(entry["end"]))
            last["line_anchor"] = f"{int(last['start']):04d}-{int(last['end']):04d}"
            if len(entry["excerpt"]) > len(str(last.get("excerpt", ""))):
                last["excerpt"] = entry["excerpt"]
            last["verdicts"].add(entry["verdict"])
            last["checkpoint_items"].append(entry["checkpoint_item"])
            if entry["reason"]:
                last["candidate_reasons"].append(entry["reason"])
            if entry["clause_type"]:
                last["clause_types"].add(entry["clause_type"])
            if entry["excerpt_key"]:
                last["excerpt_keys"].add(entry["excerpt_key"])
            if entry.get("template_context"):
                last.setdefault("template_contexts", []).append(entry["template_context"])
            if entry.get("common_clause_context"):
                last.setdefault("common_clause_contexts", []).append(entry["common_clause_context"])
        else:
            groups.append(new_group(entry))

    by_excerpt: dict[str, dict[str, Any]] = {}
    for entry in unanchored:
        key = entry["excerpt_key"] or f"unanchored:{len(by_excerpt)}"
        if key not in by_excerpt:
            by_excerpt[key] = new_group(entry)
            continue
        group = by_excerpt[key]
        group["verdicts"].add(entry["verdict"])
        group["checkpoint_items"].append(entry["checkpoint_item"])
        if entry["reason"]:
            group["candidate_reasons"].append(entry["reason"])
        if entry["clause_type"]:
            group["clause_types"].add(entry["clause_type"])
        if entry.get("template_context"):
            group.setdefault("template_contexts", []).append(entry["template_context"])
        if entry.get("common_clause_context"):
            group.setdefault("common_clause_contexts", []).append(entry["common_clause_context"])
    groups.extend(by_excerpt.values())

    issues: list[dict[str, Any]] = []
    sorted_groups = sorted(
        groups,
        key=lambda group: (
            0 if "命中" in group["verdicts"] else 1,
            parse_line_anchor(group.get("line_anchor", ""))[0] or 10**9,
            group.get("line_anchor", ""),
        ),
    )
    for index, group in enumerate(sorted_groups, start=1):
        checkpoint_items_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for checkpoint_item in group["checkpoint_items"]:
            key = (
                str(checkpoint_item.get("id", "")),
                str(checkpoint_item.get("title", "")),
            )
            existing = checkpoint_items_by_key.get(key)
            if existing is None:
                checkpoint_items_by_key[key] = dict(checkpoint_item)
                continue
            if existing.get("verdict") != "命中" and checkpoint_item.get("verdict") == "命中":
                existing["verdict"] = checkpoint_item.get("verdict", "")
                existing["candidate_verdict"] = checkpoint_item.get("candidate_verdict", "")
            existing_reason = compact_text_value(existing.get("reason", ""), 160)
            new_reason = compact_text_value(checkpoint_item.get("reason", ""), 160)
            if new_reason and new_reason != existing_reason:
                existing["reason"] = "；".join([part for part in [existing_reason, new_reason] if part])
        checkpoint_items = list(checkpoint_items_by_key.values())
        verdict = "命中" if "命中" in group["verdicts"] else "待人工复核"
        template_contexts = group.get("template_contexts", [])
        template_blank = any(context.get("is_template_blank") for context in template_contexts if isinstance(context, dict))
        common_clause_contexts = group.get("common_clause_contexts", [])
        common_generic_standard = any(
            context.get("is_common_generic_standard") for context in common_clause_contexts if isinstance(context, dict)
        )
        first_checkpoint = checkpoint_items[0] if checkpoint_items else {}
        title = str(first_checkpoint.get("title") or "业务风险问题")
        if len(checkpoint_items) > 1:
            title = f"{title}等关联风险"
        reasons = []
        seen_reasons: set[str] = set()
        for reason in group["candidate_reasons"]:
            compact = compact_text_value(reason, 180)
            if compact and compact not in seen_reasons:
                reasons.append(compact)
                seen_reasons.add(compact)
        issues.append(
            {
                "issue_id": f"BI-{index:03d}" if verdict == "命中" else f"BR-{index:03d}",
                "title": title,
                "verdict": verdict,
                "risk_level": risk_level_for_verdict(verdict),
                "line_anchor": group.get("line_anchor", ""),
                "excerpt": group.get("excerpt", ""),
                "clause_types": sorted(group["clause_types"]),
                "triggered_checkpoints": checkpoint_items,
                "risk_analysis": "；".join(reasons[:4]) if reasons else compact_text_value(first_checkpoint.get("summary", "")),
                "manual_review_questions": [
                    "该证据可能位于合同条款及格式、合同模板或仅供参考文本，需先确认其是否属于本项目正式约束条款。",
                    "需核对项目专用条款、采购需求书、补充条款或最终签署合同是否已补足留白事项。",
                ]
                if template_blank
                else [
                    "该证据可能仅是第二册通用条款的兜底表述，需先确认第一册专用条款、用户需求书或技术附件是否已有项目专用标准。",
                    "只有项目专用需求也未列明必要标准、检测或验收依据时，才可进一步认定为采购需求不明确风险。",
                ]
                if common_generic_standard
                else [
                    "需结合采购文件完整上下文、项目实际需求和适用法规进行人工确认。"
                ]
                if verdict == "待人工复核"
                else [],
            }
        )
    return issues


def business_audit_report_data(run_dir: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    started_values = [item.get("started_at", "") for item in results if item.get("started_at")]
    ended_values = [item.get("ended_at", "") for item in results if item.get("ended_at")]
    review_files = sorted({item.get("review_file", "") for item in results if item.get("review_file")})
    models = sorted({item.get("model", "") for item in results if item.get("model")})
    review_lines = load_review_lines_for_results(results)
    issues = build_business_issues(results, review_lines)
    hit_issues = [issue for issue in issues if issue["verdict"] == "命中"]
    review_issues = [issue for issue in issues if issue["verdict"] == "待人工复核"]
    return {
        "report_type": "business_audit_report",
        "generated_at": now_text(),
        "run_dir": relative_path(run_dir),
        "review_file": review_files[0] if review_files else "",
        "models": models,
        "started_at": min(started_values) if started_values else "",
        "ended_at": max(ended_values) if ended_values else "",
        "checkpoint_count": len(results),
        "summary": {
            "business_issue_count": len(issues),
            "confirmed_issue_count": len(hit_issues),
            "manual_review_count": len(review_issues),
            "checkpoint_hit_count": sum(1 for item in results if item.get("model_result", {}).get("verdict") == "命中"),
            "checkpoint_manual_review_count": sum(1 for item in results if item.get("model_result", {}).get("verdict") == "待人工复核"),
        },
        "issues": issues,
    }


def business_audit_report_markdown(data: dict[str, Any]) -> str:
    review_file_name = Path(str(data.get("review_file", ""))).name or "未知待审文件"
    issues = data.get("issues", [])
    hit_issues = [issue for issue in issues if issue.get("verdict") == "命中"]
    review_issues = [issue for issue in issues if issue.get("verdict") == "待人工复核"]
    summary = data.get("summary", {})
    lines = [
        "---",
        f"title: {review_file_name} 业务审查报告",
        "page_type: business-audit-report",
        f"run_dir: {data.get('run_dir', '')}",
        f"generated_at: {data.get('generated_at', '')}",
        "---",
        "",
        f"# {review_file_name} 业务审查报告",
        "",
        "## 一、审查结论摘要",
        "",
        "本报告由 AI 审查生成，用于辅助识别政府采购文件中的合规风险。报告结论不替代采购人、采购代理机构、评审专家、法务人员或监管部门的人工判断。",
        "",
        f"- 审查方式：AI 自动审查",
        f"- 审查模型：{', '.join(data.get('models', []))}",
        f"- 待审文件：{data.get('review_file', '')}",
        f"- 开始时间：{data.get('started_at', '')}",
        f"- 结束时间：{data.get('ended_at', '')}",
        f"- 检查点数量：{data.get('checkpoint_count', 0)}",
        f"- 形成业务风险问题：{summary.get('confirmed_issue_count', 0)} 个",
        f"- 待人工复核事项：{summary.get('manual_review_count', 0)} 个",
        "",
    ]

    lines.extend(["", "## 二、问题明细", ""])
    if not hit_issues:
        lines.append("本次未形成明确命中的业务风险问题。")
    for index, issue in enumerate(hit_issues, start=1):
        lines.extend(render_business_issue_markdown(issue, f"问题 {index}"))

    lines.extend(["", "## 三、待人工复核事项", ""])
    if not review_issues:
        lines.append("本次未形成按证据聚合的待人工复核事项。")
    for index, issue in enumerate(review_issues, start=1):
        lines.extend(render_business_issue_markdown(issue, f"复核事项 {index}"))

    lines.extend(
        [
            "",
            "## 四、AI审查特别提醒说明",
            "",
            "本报告由 AI 根据标准检查点、待审文件文本和模型审查结果自动生成，主要用于辅助业务人员发现可能存在的风险线索。",
            "",
            "- AI 审查可能存在漏检、误判或对项目背景理解不足的情况。",
            "- 本报告中的“命中”表示 AI 认为存在较明确风险线索，不等同于监管部门的违法认定。",
            "- 本报告中的“待人工复核”表示 AI 发现疑点，但需要结合项目背景、采购需求、公告、更正公告、预算批复、合同附件、交易平台记录等进一步确认。",
            "- 对涉及法律责任、投诉处理、采购文件修改、废标或重新采购等事项，应由业务人员、法务人员或有权监管部门进一步判断。",
            "- 业务人员应结合原始采购文件、项目实际情况和适用法规，对本报告结论进行复核后再使用。",
            "",
        ]
    )
    return "\n".join(lines)


def render_business_issue_markdown(issue: dict[str, Any], label: str) -> list[str]:
    lines = [
        f"### {label}：{issue.get('title', '')}",
        "",
        f"- 风险等级：{issue.get('risk_level', '')}",
        f"- 问题类型：{', '.join(issue.get('clause_types', [])) or '未标注'}",
        f"- 证据位置：{issue.get('line_anchor', '')}",
        f"- 当前状态：{issue.get('verdict', '')}",
        "",
        "#### 原文摘录",
        "",
        "```text",
        str(issue.get("excerpt", "")).strip() or "未返回证据摘录。",
        "```",
        "",
        "#### 触发检查点",
        "",
        "| 检查点 | 结论 | 说明 |",
        "|---|---|---|",
    ]
    for item in issue.get("triggered_checkpoints", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{item.get('id')} {item.get('title')}",
                    str(item.get("verdict", "")),
                    compact_text_value(item.get("reason") or item.get("summary"), 180),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "#### 风险说明",
            "",
            issue.get("risk_analysis", "") or "AI 未返回进一步风险说明，需结合单点报告复核。",
            "",
        ]
    )
    if issue.get("manual_review_questions"):
        lines.extend(["#### 需人工确认事项", ""])
        for question in issue.get("manual_review_questions", []):
            lines.append(f"- {question}")
        lines.append("")
    return lines


def write_business_audit_report(run_dir: Path, results: list[dict[str, Any]]) -> tuple[Path, Path]:
    data = business_audit_report_data(run_dir, results)
    report_file = run_dir / "业务审查报告.md"
    data_file = run_dir / "业务审查报告.json"
    write_text(report_file, business_audit_report_markdown(data))
    write_text(data_file, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return report_file, data_file


def write_batch_audit_report(run_dir: Path) -> tuple[Path, Path]:
    validate_output_dir(run_dir)
    results = load_batch_results(run_dir)
    report_file = run_dir / "审查报告.md"
    data_file = run_dir / "审查报告.json"
    report_data = {
        "generated_at": now_text(),
        "run_dir": relative_path(run_dir),
        "result_count": len(results),
        "results": results,
    }
    write_text(report_file, batch_audit_report_markdown(run_dir, results))
    write_text(data_file, json.dumps(report_data, ensure_ascii=False, indent=2) + "\n")
    write_business_audit_report(run_dir, results)
    return report_file, data_file


def write_results_tsv(run_dir: Path) -> Path:
    results = load_batch_results(run_dir)
    lines = []
    for item in results:
        result = item.get("model_result", {})
        lines.append(
            "\t".join(
                [
                    str(item.get("checkpoint_id", "")),
                    str(result.get("verdict", "")),
                    str(result.get("summary", "")).replace("\n", " "),
                    str(item.get("_result_file", "")),
                ]
            )
        )
    output_file = run_dir / "results.tsv"
    write_text(output_file, "\n".join(lines) + ("\n" if lines else ""))
    return output_file


def default_output_dir(checkpoint_id: str, review_file: Path) -> Path:
    return DEFAULT_OUTPUT_ROOT / f"checkpoint-{checkpoint_id}-{slugify_filename(review_file.stem)}-{run_id()}"


def default_batch_output_dir(review_file: Path) -> Path:
    return DEFAULT_OUTPUT_ROOT / f"batch-{slugify_filename(review_file.stem)}-{run_id()}"


def expand_checkpoint_glob(pattern: str) -> list[Path]:
    matches = [Path(item).resolve() for item in glob.glob(pattern)]
    if not matches:
        matches = [Path(item).resolve() for item in glob.glob(str(WORKSPACE_ROOT / pattern))]
    checkpoint_paths = sorted({path for path in matches if path.is_file() and path.suffix == ".md"})
    if not checkpoint_paths:
        raise RuntimeError(f"未找到检查点文件：{pattern}")
    return checkpoint_paths


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="验证 1 个 BD 检查点执行说明书是否能约束小模型审查 1 份待审文件。"
    )
    parser.add_argument("--checkpoint", type=Path, help="BD 检查点 md 文件路径")
    parser.add_argument("--checkpoint-glob", help="批量验证检查点 glob，例如 'wiki/checkpoints/BD06-*.md'")
    parser.add_argument("--review-file", type=Path, help="待审文件，支持 md/txt/doc/docx")
    parser.add_argument("--aggregate-run-dir", type=Path, help="汇总批次目录下的 result.json，生成审查报告.md")
    parser.add_argument("--output-dir", type=Path, help="输出目录，默认 validation/cli-runs/checkpoint-...")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI 兼容接口 base_url")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="OpenAI 兼容接口密钥")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="模型名称")
    parser.add_argument(
        "--mode",
        choices=sorted(MODE_DEFAULTS),
        default="standard",
        help="运行模式：quick 快速初筛；standard 默认业务审查；strict 稳健复核；sop-validation SOP 验证",
    )
    parser.add_argument("--timeout", type=int, default=1800, help="接口超时秒数")
    parser.add_argument("--temperature", type=float, default=0.0, help="模型温度")
    parser.add_argument("--context-before", type=int, default=5, help="候选命中行前文行数")
    parser.add_argument("--context-after", type=int, default=10, help="候选命中行后文行数")
    parser.add_argument("--max-windows", type=int, default=12, help="最多提交候选窗口数")
    parser.add_argument("--max-line-chars", type=int, default=900, help="候选窗口中单行最大字符数")
    parser.add_argument("--max-review-excerpt-chars", type=int, default=12000, help="候选窗口总字符上限")
    parser.add_argument("--max-checkpoint-chars", type=int, default=18000, help="检查点执行说明书字符上限")
    parser.add_argument("--max-tokens", type=int, default=None, help="模型最大输出 token；默认由 --mode 决定")
    parser.add_argument("--min-candidate-score", type=int, default=3, help="低于该分数的弱候选不送入模型")
    parser.add_argument("--two-stage", action=argparse.BooleanOptionalAction, default=None, help="先用召回分数轻量预筛，疑似风险再调用模型生成完整报告；默认由 --mode 决定")
    parser.add_argument("--stage1-min-score", type=int, default=None, help="两阶段预筛进入模型审查的最低最高候选分；默认由 --mode 和 BD 域决定")
    parser.add_argument("--jobs", type=int, default=None, help="批量验证并发数；默认由 --mode 决定")
    parser.add_argument("--fast-skip", action=argparse.BooleanOptionalAction, default=None, help="无有效候选窗口时跳过模型调用并直接输出不命中；默认由 --mode 决定")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True, help="批量验证时跳过已有 result.json 的检查点")
    parser.add_argument("--repair-line-anchors", action=argparse.BooleanOptionalAction, default=False, help="是否用原文二次修复模型证据行号；默认关闭以提升性能")
    parser.add_argument("--reuse-raw-response", action=argparse.BooleanOptionalAction, default=True, help="续跑时复用已存在的 raw-response.json，避免重复请求模型")
    return parser


def run_single_validation(
    args: argparse.Namespace,
    checkpoint_path: Path,
    review_file: Path,
    output_dir_override: Path | None = None,
) -> int:
    checkpoint_path = checkpoint_path.resolve()
    review_file = review_file.resolve()
    checkpoint_text = read_text(checkpoint_path)
    compact_text = compact_checkpoint_text(checkpoint_text, args.max_checkpoint_chars)
    checkpoint_id = extract_checkpoint_id(checkpoint_text)
    checkpoint_title = extract_title(checkpoint_text)
    output_dir = (output_dir_override or args.output_dir or default_output_dir(checkpoint_id, review_file)).resolve()
    validate_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = now_text()
    print(f"start {started_at} checkpoint={checkpoint_id} file={review_file.name}", flush=True)

    try:
        review_text, extractor = load_review_file(review_file)
        keyword_groups = parse_keyword_groups(checkpoint_text)
        review_excerpt, window_count, recall_stats = collect_candidate_windows(
            review_text,
            keyword_groups,
            checkpoint_id,
            checkpoint_title,
            args.context_before,
            args.context_after,
            args.max_windows,
            args.max_line_chars,
            args.max_review_excerpt_chars,
            args.min_candidate_score,
        )
        prompt_file = output_dir / "prompt.md"
        write_text(
            prompt_file,
            "# Prompt Preview\n\n"
            + f"- checkpoint: {checkpoint_id} {checkpoint_title}\n"
            + f"- review_file: {relative_path(review_file)}\n"
            + f"- candidate_windows: {window_count}\n\n"
            + f"- checkpoint_chars: {len(compact_text)}\n"
            + f"- review_excerpt_chars: {len(review_excerpt)}\n\n"
            + f"- recall_stats: {json.dumps(recall_stats, ensure_ascii=False)}\n\n"
            + "## 检查点执行说明书\n\n"
            + compact_text
            + "\n\n"
            + "## 候选窗口\n\n"
            + (review_excerpt or "无有效候选窗口。")
            + "\n",
        )
        print(
            f"recall ok windows={window_count} raw_hits={recall_stats.get('raw_hit_count', 0)} "
            f"filtered_hits={recall_stats.get('filtered_hit_count', 0)} max_score={recall_stats.get('max_score', 0)}",
            flush=True,
        )

        if args.fast_skip and window_count == 0:
            ended_at = now_text()
            model_result = build_fast_skip_result(checkpoint_id, checkpoint_title, str(recall_stats.get("skip_reason", "")))
            report_file = output_dir / f"{checkpoint_id}-{slugify_filename(checkpoint_title)}.md"
            report = {
                "started_at": started_at,
                "ended_at": ended_at,
                "model": "fast-skip",
                "checkpoint_id": checkpoint_id,
                "checkpoint_title": checkpoint_title,
                "checkpoint_path": relative_path(checkpoint_path),
                "review_file": relative_path(review_file),
                "text_extractor": extractor,
                "candidate_window_count": window_count,
                "recall_stats": recall_stats,
                "prompt_file": relative_path(prompt_file),
                "report_file": relative_path(report_file),
                "raw_response_file": "",
                "model_result": model_result,
            }
            write_text(report_file, markdown_report(report))
            write_text(output_dir / "summary.md", summary_markdown(report))
            write_text(output_dir / "result.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(f"skip {ended_at} verdict=不命中 reason={recall_stats.get('skip_reason', '')} output={relative_path(report_file)}", flush=True)
            return 0

        if args.two_stage:
            stage1_min_score = stage1_threshold_for_checkpoint(args, checkpoint_id)
            recall_stats["stage1_min_score"] = stage1_min_score
            recall_stats["mode"] = args.mode
            skip_by_stage, stage_reason = should_two_stage_skip(recall_stats, stage1_min_score)
            if skip_by_stage:
                ended_at = now_text()
                recall_stats["skip_reason"] = stage_reason
                recall_stats["two_stage_skipped"] = True
                model_result = build_fast_skip_result(checkpoint_id, checkpoint_title, stage_reason)
                report_file = output_dir / f"{checkpoint_id}-{slugify_filename(checkpoint_title)}.md"
                report = {
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "model": "two-stage-fast-skip",
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_title": checkpoint_title,
                    "checkpoint_path": relative_path(checkpoint_path),
                    "review_file": relative_path(review_file),
                    "text_extractor": extractor,
                    "candidate_window_count": window_count,
                    "recall_stats": recall_stats,
                    "prompt_file": relative_path(prompt_file),
                    "report_file": relative_path(report_file),
                    "raw_response_file": "",
                    "model_result": model_result,
                }
                write_text(report_file, markdown_report(report))
                write_text(output_dir / "summary.md", summary_markdown(report))
                write_text(output_dir / "result.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                print(f"stage-skip {ended_at} verdict=不命中 reason={stage_reason} output={relative_path(report_file)}", flush=True)
                return 0

        messages = build_messages(
            checkpoint_id,
            checkpoint_title,
            compact_text,
            review_file.name,
            review_excerpt,
        )
        raw_response_file = output_dir / "raw-response.json"
        if args.reuse_raw_response and raw_response_file.exists():
            response = json.loads(read_text(raw_response_file))
            print(f"reuse raw-response {relative_path(raw_response_file)}", flush=True)
        else:
            response = post_openai_compatible(
                args.base_url,
                args.api_key,
                args.model,
                messages,
                args.temperature,
                args.timeout,
                args.max_tokens,
            )
            write_text(raw_response_file, json.dumps(response, ensure_ascii=False, indent=2) + "\n")
        model_result = normalize_result(parse_model_json(response), checkpoint_id, checkpoint_title)
        if args.repair_line_anchors:
            repair_candidate_line_anchors(model_result, review_text)
        ended_at = now_text()

        report_file = output_dir / f"{checkpoint_id}-{slugify_filename(checkpoint_title)}.md"
        report: dict[str, Any] = {
            "started_at": started_at,
            "ended_at": ended_at,
            "model": args.model,
            "checkpoint_id": checkpoint_id,
            "checkpoint_title": checkpoint_title,
            "checkpoint_path": relative_path(checkpoint_path),
            "review_file": relative_path(review_file),
            "text_extractor": extractor,
            "candidate_window_count": window_count,
            "recall_stats": recall_stats,
            "prompt_file": relative_path(prompt_file),
            "report_file": relative_path(report_file),
            "raw_response_file": relative_path(raw_response_file),
            "model_result": model_result,
        }
        write_text(report_file, markdown_report(report))
        write_text(output_dir / "summary.md", summary_markdown(report))
        write_text(output_dir / "result.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"ok {ended_at} verdict={model_result.get('verdict')} output={relative_path(report_file)}", flush=True)
        return 0
    except Exception as exc:
        ended_at = now_text()
        error_report = {
            "started_at": started_at,
            "ended_at": ended_at,
            "checkpoint_id": checkpoint_id,
            "checkpoint_title": checkpoint_title,
            "checkpoint_path": relative_path(checkpoint_path),
            "review_file": relative_path(review_file),
            "error": str(exc),
        }
        write_text(output_dir / "error.md", "# 运行失败\n\n```json\n" + json.dumps(error_report, ensure_ascii=False, indent=2) + "\n```\n")
        print(f"error {ended_at} {exc}", flush=True)
        return 1


def run_batch_validation(args: argparse.Namespace) -> int:
    if not args.review_file:
        raise SystemExit("批量验证必须提供 --review-file。")
    review_file = args.review_file.resolve()
    checkpoint_paths = expand_checkpoint_glob(args.checkpoint_glob)
    batch_dir = (args.output_dir or default_batch_output_dir(review_file)).resolve()
    validate_output_dir(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_log = batch_dir / "batch.log"
    write_text(
        batch_log,
        f"batch_dir={relative_path(batch_dir)}\n"
        f"review_file={relative_path(review_file)}\n"
        f"checkpoint_count={len(checkpoint_paths)}\n"
        f"mode={args.mode}\n"
        + f"jobs={args.jobs}\n"
        + f"max_tokens={args.max_tokens}\n"
        + f"fast_skip={args.fast_skip}\n"
        + f"two_stage={args.two_stage}\n",
    )
    failures = 0
    jobs = max(1, int(args.jobs or 1))

    def append_log(text: str) -> None:
        with batch_log.open("a", encoding="utf-8") as handle:
            handle.write(text)

    def run_one(checkpoint_path: Path) -> tuple[str, str, int]:
        checkpoint_text = read_text(checkpoint_path)
        checkpoint_id = extract_checkpoint_id(checkpoint_text)
        checkpoint_title = extract_title(checkpoint_text)
        output_dir = batch_dir / checkpoint_id
        if args.resume and (output_dir / "result.json").exists():
            line = f"\n=== {checkpoint_id} skip existing {now_text()} ===\n"
            append_log(line)
            print(line.strip(), flush=True)
            return checkpoint_id, checkpoint_title, 0
        line = f"\n=== {checkpoint_id} start {now_text()} ===\n"
        append_log(line)
        print(line.strip(), flush=True)
        status = run_single_validation(args, checkpoint_path, review_file, output_dir)
        end_line = f"=== {checkpoint_id} end status={status} {now_text()} ===\n"
        append_log(f"checkpoint_title={checkpoint_title}\n{end_line}")
        print(end_line.strip(), flush=True)
        return checkpoint_id, checkpoint_title, status

    if jobs == 1:
        for checkpoint_path in checkpoint_paths:
            _, _, status = run_one(checkpoint_path)
            if status != 0:
                failures += 1
    else:
        print(f"batch parallel jobs={jobs}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(run_one, checkpoint_path): checkpoint_path for checkpoint_path in checkpoint_paths}
            for future in concurrent.futures.as_completed(future_map):
                checkpoint_path = future_map[future]
                try:
                    _, _, status = future.result()
                except Exception as exc:
                    checkpoint_text = read_text(checkpoint_path)
                    checkpoint_id = extract_checkpoint_id(checkpoint_text)
                    append_log(f"=== {checkpoint_id} end status=1 {now_text()} exception={exc} ===\n")
                    print(f"error {checkpoint_id} {exc}", flush=True)
                    status = 1
                if status != 0:
                    failures += 1

    if failures != len(checkpoint_paths):
        results_file = write_results_tsv(batch_dir)
        report_file, data_file = write_batch_audit_report(batch_dir)
        print(
            f"batch report ok results={relative_path(results_file)} output={relative_path(report_file)} data={relative_path(data_file)}",
            flush=True,
        )
    print(f"batch done output={relative_path(batch_dir)} failures={failures}", flush=True)
    return 1 if failures else 0


def main() -> int:
    args = build_arg_parser().parse_args()
    apply_mode_defaults(args)
    if args.aggregate_run_dir:
        run_dir = args.aggregate_run_dir.resolve()
        report_file, data_file = write_batch_audit_report(run_dir)
        print(f"report ok output={relative_path(report_file)} data={relative_path(data_file)}", flush=True)
        return 0
    if args.checkpoint_glob:
        return run_batch_validation(args)
    if not args.checkpoint or not args.review_file:
        raise SystemExit("必须提供 --checkpoint 和 --review-file；或使用 --checkpoint-glob 批量验证；或使用 --aggregate-run-dir 汇总批次报告。")
    return run_single_validation(args, args.checkpoint, args.review_file)


if __name__ == "__main__":
    raise SystemExit(main())
