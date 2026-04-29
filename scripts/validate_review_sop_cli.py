#!/usr/bin/env python3
"""验证 3+1 审查执行说明书 + 1 份待审文件。"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import re
import subprocess
import threading
import textwrap
import time
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path.cwd()
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "validation" / "review-sop-runs"
DEFAULT_JOBS = 8
DEFAULT_MAX_TOKENS = 6144
DEFAULT_MIN_CANDIDATE_SCORE = 3
ENV_BASE_URL = "REVIEW_SOP_LLM_BASE_URL"
ENV_MODEL = "REVIEW_SOP_LLM_MODEL"
ENV_API_KEY = "REVIEW_SOP_LLM_API_KEY"
LOG_LOCK = threading.Lock()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOG_LOCK:
        with path.open("a", encoding="utf-8") as file:
            file.write(text)


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def slugify_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "-", name).strip() or "unknown"


def safe_frontmatter_value(value: str) -> str:
    return str(value).replace("\n", " ").replace('"', '\\"')


def relative_path(path: Path) -> str:
    try:
        return os.path.relpath(path, WORKSPACE_ROOT)
    except Exception:
        return str(path)


def parse_frontmatter(markdown: str) -> dict[str, Any]:
    match = re.match(r"(?ms)^---\n(.*?)\n---", markdown)
    if not match:
        return {}
    data: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        item = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if item:
            data[item.group(1)] = item.group(2).strip()
    return data


def extract_title(markdown: str) -> str:
    frontmatter = parse_frontmatter(markdown)
    if frontmatter.get("title"):
        return str(frontmatter["title"])
    match = re.search(r"^#\s+(.+)$", markdown, re.M)
    return match.group(1).strip() if match else "unknown-review-sop"


def extract_id(markdown: str) -> str:
    frontmatter = parse_frontmatter(markdown)
    if frontmatter.get("id"):
        return str(frontmatter["id"])
    return "unknown-id"


def extract_section(markdown: str, heading: str, level: int = 2) -> str:
    marks = "#" * level
    next_marks = "#" * level
    pattern = re.compile(rf"(?ms)^{re.escape(marks)}\s+{re.escape(heading)}\s*$\n(.*?)(?=^{re.escape(next_marks)}\s+|\Z)")
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def extract_child_section(section: str, heading: str, level: int = 3) -> str:
    marks = "#" * level
    pattern = re.compile(rf"(?ms)^{re.escape(marks)}\s+{re.escape(heading)}\s*$\n(.*?)(?=^{re.escape(marks)}\s+|\Z)")
    match = pattern.search(section)
    return match.group(1).strip() if match else ""


def compact_sop_text(markdown: str, max_chars: int) -> str:
    chunks: list[str] = []
    for heading in ["标准检查点", "检查点定义", "权威依据", "适用边界", "审查执行说明书（3+1）"]:
        section = extract_section(markdown, heading)
        if section:
            chunks.append(f"## {heading}\n{section}")
    text = "\n\n".join(chunks).strip() or markdown
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[已按 max-sop-chars 截断]"
    return text


def parse_word_groups(markdown: str) -> dict[str, list[str]]:
    sop = extract_section(markdown, "审查执行说明书（3+1）")
    locator = extract_child_section(sop, "一、定位词体系")
    groups: dict[str, list[str]] = {}
    current_group = ""
    for line in locator.splitlines():
        heading = re.match(r"^####\s+(.+?)\s*$", line)
        if heading:
            current_group = heading.group(1).strip()
            groups.setdefault(current_group, [])
            continue
        item = re.match(r"^-\s+(.+?)\s*$", line)
        if item and current_group:
            word = item.group(1).strip().rstrip("。；;")
            if word:
                groups.setdefault(current_group, []).append(word)
    return {key: value for key, value in groups.items() if value}


def source_lines(text: str) -> list[str]:
    lines = text.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def extract_text_from_docx(path: Path) -> tuple[str, str]:
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout, "textutil"
    raise RuntimeError(f"无法提取 docx 文本：{path.name}")


def extract_text_from_doc(path: Path) -> tuple[str, str]:
    antiword = subprocess.run(["antiword", str(path)], capture_output=True, text=True, check=False)
    if antiword.returncode == 0 and antiword.stdout.strip():
        return antiword.stdout, "antiword"
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout, "textutil"
    raise RuntimeError(f"无法提取 doc 文本：{path.name}")


def load_review_file(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return read_text(path), "plain-text"
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".doc":
        return extract_text_from_doc(path)
    raise RuntimeError(f"暂不支持的待审文件类型：{path.suffix}")


def line_has_any(line: str, words: list[str]) -> list[str]:
    return [word for word in words if word and word in line]


def collect_candidate_windows(
    review_text: str,
    word_groups: dict[str, list[str]],
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

    object_words = word_groups.get("显性关键词", []) + word_groups.get("同义近义词", [])
    limit_words = word_groups.get("限制动作词", [])
    consequence_words = word_groups.get("后果词", [])
    exclusion_words = word_groups.get("排除词", [])

    scored: list[tuple[int, int, int, dict[str, list[str]]]] = []
    for idx, line in enumerate(raw_lines):
        hits = {group: line_has_any(line, words) for group, words in word_groups.items()}
        total_hits = sum(len(words) for words in hits.values())
        if total_hits == 0:
            continue
        stats["raw_hit_count"] += 1

        has_object = bool(line_has_any(line, object_words))
        has_limit = bool(line_has_any(line, limit_words))
        has_consequence = bool(line_has_any(line, consequence_words))
        has_exclusion = bool(line_has_any(line, exclusion_words))

        score = total_hits
        if has_object and has_consequence:
            score += 8
        if has_object and has_limit and has_consequence:
            score += 16
        if has_object and has_limit:
            score += 4
        if has_object and has_exclusion:
            score += 6
        if not has_object and total_hits:
            score -= 2
        if score < min_candidate_score:
            continue

        stats["filtered_hit_count"] += 1
        start = max(0, idx - context_before)
        end = min(len(raw_lines), idx + context_after + 1)
        scored.append((score, start, end, hits))

    if not scored:
        stats["skip_reason"] = "未命中 3+1 定位词或仅命中弱词"
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
        chunks.append(f"[候选窗口 {idx}] score={score}; " + "；".join(hit_parts) + "\n" + "\n".join(chunk_lines))

    excerpt = "\n\n".join(chunks)
    if len(excerpt) > max_excerpt_chars:
        excerpt = excerpt[:max_excerpt_chars] + "\n\n[候选窗口已按 max-review-excerpt-chars 截断]"
    return excerpt, len(merged), stats


def resolve_llm_config(args: argparse.Namespace) -> None:
    args.base_url = args.base_url or os.environ.get(ENV_BASE_URL) or os.environ.get("CHECKPOINT_LLM_BASE_URL")
    args.model = args.model or os.environ.get(ENV_MODEL) or os.environ.get("CHECKPOINT_LLM_MODEL")
    args.api_key = args.api_key or os.environ.get(ENV_API_KEY) or os.environ.get("CHECKPOINT_LLM_API_KEY")
    missing = []
    if not args.base_url:
        missing.append(ENV_BASE_URL)
    if not args.model:
        missing.append(ENV_MODEL)
    if not args.api_key:
        missing.append(ENV_API_KEY)
    if missing:
        raise RuntimeError("缺少模型连接配置，请通过环境变量或命令行参数提供：" + "、".join(missing))


def build_messages(sop_id: str, title: str, sop_text: str, review_name: str, review_excerpt: str) -> list[dict[str, str]]:
    system = (
        "/no_think\n"
        "你是政府采购招标文件合规审查小模型。"
        "你只能根据给定的 3+1 审查执行说明书和待审文件候选窗口审查。"
        "必须按 3+1 顺序执行：定位词体系、组合触发规则、审查推理规则、质量控制与验证规则。"
        "不要输出思考过程，不要输出解释性前言，输出必须是 JSON。"
    )
    user = textwrap.dedent(
        f"""
        审查说明书：{sop_id} {title}
        待审文件：{Path(review_name).name}

        执行要求：
        1. 只能根据下方 3+1 审查执行说明书审查。
        2. 必须逐条判断候选证据属于强触发、中触发、弱触发或不触发。
        3. 最终结论只能是：命中 / 待人工复核 / 不命中。
        4. 证据摘录必须来自待审文件候选窗口，不得改写原文。
        5. 必须检查排除词、不触发规则和常见误判。
        6. 如果证据不足，输出待人工复核，不能强行命中。
        7. 输出严格合法 JSON，不要使用 markdown。

        输出 JSON 结构：
        {{
          "sop_id": "{sop_id}",
          "sop_title": "{title}",
          "verdict": "命中|待人工复核|不命中",
          "summary": "一句话总结审查结论",
          "execution_trace": {{
            "word_location": "定位词体系执行情况",
            "trigger_classification": "强/中/弱/不触发判断情况",
            "reasoning": "命中/复核/不命中推理情况",
            "quality_control": "证据、排除条件、常见误判检查情况"
          }},
          "candidates": [
            {{
              "line_anchor": "行号范围",
              "excerpt": "原文证据摘录",
              "trigger_level": "强触发|中触发|弱触发|不触发",
              "candidate_verdict": "命中|待人工复核|不命中",
              "reason": "判断理由",
              "exclusion_checked": "已检查的排除条件"
            }}
          ]
        }}

        【3+1 审查执行说明书】
        {sop_text}

        【待审文件候选窗口】
        {review_excerpt}
        """
    ).strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_model(args: argparse.Namespace, messages: list[dict[str, str]]) -> dict[str, Any]:
    url = args.base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": args.model,
        "messages": messages,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
        "enable_thinking": False,
    }
    command = [
        "curl",
        "-sS",
        "--max-time",
        str(args.timeout),
        "-H",
        "Content-Type: application/json",
        "-H",
        f"Authorization: Bearer {args.api_key}",
        "--data",
        json.dumps(payload, ensure_ascii=False),
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.strip()}")
    response = json.loads(result.stdout)
    content = response["choices"][0]["message"]["content"]
    if content is None:
        raise RuntimeError("模型返回 content 为空")
    return json.loads(content)


def normalize_result(result: dict[str, Any], sop_id: str, title: str) -> dict[str, Any]:
    result.setdefault("sop_id", sop_id)
    result.setdefault("sop_title", title)
    if result.get("verdict") not in {"命中", "待人工复核", "不命中"}:
        result["verdict"] = "待人工复核"
    if not isinstance(result.get("candidates"), list):
        result["candidates"] = []
    if not isinstance(result.get("execution_trace"), dict):
        result["execution_trace"] = {}
    return result


def markdown_report(report: dict[str, Any]) -> str:
    result = report["model_result"]
    lines = [
        f"# {report['sop_id']} {report['sop_title']} 3+1验证报告",
        "",
        "## 运行信息",
        f"- 开始时间：{report['started_at']}",
        f"- 结束时间：{report['ended_at']}",
        f"- 模型：{report['model']}",
        f"- 审查说明书：{report['sop_path']}",
        f"- 待审文件：{Path(report['review_file']).name}",
        f"- 文本抽取方式：{report['text_extractor']}",
        "",
        "## 结论",
        f"- 结果：{result.get('verdict', '')}",
        f"- 摘要：{result.get('summary', '')}",
        "",
        "## 3+1执行过程",
    ]
    trace = result.get("execution_trace", {})
    lines.extend(
        [
            f"- 定位词体系：{trace.get('word_location', '')}",
            f"- 组合触发规则：{trace.get('trigger_classification', '')}",
            f"- 审查推理规则：{trace.get('reasoning', '')}",
            f"- 质量控制与验证规则：{trace.get('quality_control', '')}",
            "",
            "## 候选证据",
        ]
    )
    candidates = result.get("candidates", [])
    if not candidates:
        lines.append("- 未召回候选证据。")
    for idx, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"### 候选 {idx}",
                f"- 行号：{candidate.get('line_anchor', '')}",
                f"- 触发层级：{candidate.get('trigger_level', '')}",
                f"- 候选结论：{candidate.get('candidate_verdict', '')}",
                f"- 理由：{candidate.get('reason', '')}",
                f"- 排除检查：{candidate.get('exclusion_checked', '')}",
                "",
                "证据摘录：",
                "",
                "```text",
                str(candidate.get("excerpt", "")).strip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def run_one(args: argparse.Namespace, sop_path: Path, review_path: Path, output_dir: Path) -> dict[str, Any]:
    started_at = now_text()
    sop_markdown = read_text(sop_path)
    sop_id = extract_id(sop_markdown)
    title = extract_title(sop_markdown)
    append_text(output_dir / "batch.log", f"\n=== {sop_id} start {started_at} ===\n")
    append_text(output_dir / "batch.log", f"checkpoint_title={title}\n")
    review_text, extractor = load_review_file(review_path)
    word_groups = parse_word_groups(sop_markdown)
    review_excerpt, window_count, recall_stats = collect_candidate_windows(
        review_text,
        word_groups,
        args.context_before,
        args.context_after,
        args.max_windows,
        args.max_line_chars,
        args.max_review_excerpt_chars,
        args.min_candidate_score,
    )
    if not review_excerpt:
        review_excerpt = f"[未召回候选窗口] {recall_stats.get('skip_reason', '')}"
    sop_text = compact_sop_text(sop_markdown, args.max_sop_chars)
    messages = build_messages(sop_id, title, sop_text, str(review_path), review_excerpt)

    sop_dir = output_dir / slugify_filename(f"{sop_id}-{title}")
    write_text(sop_dir / "prompt.md", messages[1]["content"])
    model_result = normalize_result(call_model(args, messages), sop_id, title)
    ended_at = now_text()
    report: dict[str, Any] = {
        "sop_id": sop_id,
        "sop_title": title,
        "sop_path": relative_path(sop_path),
        "review_file": str(review_path),
        "started_at": started_at,
        "ended_at": ended_at,
        "model": args.model,
        "text_extractor": extractor,
        "candidate_window_count": window_count,
        "recall_stats": recall_stats,
        "model_result": model_result,
    }
    report_file = sop_dir / f"{slugify_filename(sop_id + '-' + title)}.md"
    write_text(report_file, markdown_report(report))
    write_text(sop_dir / "summary.md", "\n".join([
        f"# {sop_id} 验证摘要",
        "",
        f"- 结果：{model_result.get('verdict', '')}",
        f"- 摘要：{model_result.get('summary', '')}",
        f"- 报告：[[{report_file.name}]]",
        "",
    ]))
    report["report_file"] = relative_path(report_file)
    append_text(output_dir / "batch.log", f"=== {sop_id} end status=0 {ended_at} verdict={model_result.get('verdict', '')} ===\n")
    return report


def collect_sop_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    if args.sop:
        paths.append(args.sop)
    if args.sop_glob:
        paths.extend(Path(item) for item in glob.glob(args.sop_glob))
    unique = sorted({path.resolve() for path in paths})
    if not unique:
        raise RuntimeError("请提供 --sop 或 --sop-glob")
    return [Path(path) for path in unique]


def risk_level_for(verdict: str) -> str:
    if verdict == "命中":
        return "高"
    if verdict == "待人工复核":
        return "待人工复核"
    return "不命中"


def issue_type(title: str, summary: str) -> str:
    text = f"{title} {summary}"
    labels = []
    for keyword, label in [
        ("评分", "评分项"),
        ("资格", "资格条件"),
        ("证明", "证明材料"),
        ("证书", "证书材料"),
        ("检测", "检测报告"),
        ("样品", "样品要求"),
        ("验收", "验收履约"),
        ("合同", "合同条款"),
        ("公告", "采购程序"),
        ("中小企业", "政府采购政策"),
        ("进口", "政府采购政策"),
        ("专利", "专利或专有技术"),
        ("软件著作权", "专利或专有技术"),
        ("地域", "差别歧视"),
        ("本地", "差别歧视"),
    ]:
        if keyword in text and label not in labels:
            labels.append(label)
    return ", ".join(labels) if labels else "合规风险"


def normalize_excerpt(excerpt: str) -> str:
    text = re.sub(r"\s+", " ", str(excerpt)).strip()
    text = re.sub(r"[，。；;：:\s]+", "", text)
    return text[:260]


def collect_business_issues(reports: list[dict[str, Any]], target_verdict: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for report in reports:
        result = report["model_result"]
        verdict = str(result.get("verdict", ""))
        if verdict != target_verdict:
            continue
        candidates = result.get("candidates", []) or []
        selected = [
            candidate for candidate in candidates
            if str(candidate.get("candidate_verdict", verdict)) in {target_verdict, "命中", "待人工复核"}
        ]
        if not selected:
            selected = [{"line_anchor": "", "excerpt": "", "reason": str(result.get("summary", ""))}]
        for candidate in selected:
            line_anchor = str(candidate.get("line_anchor", "")).strip()
            excerpt = str(candidate.get("excerpt", "")).strip()
            summary = str(result.get("summary", "")).strip()
            if target_verdict == "待人工复核":
                issue_key = f"pending::{report['sop_id']}::{summary}"
            elif not excerpt:
                issue_key = f"no-excerpt::{report['sop_id']}::{summary}"
            else:
                issue_key = f"excerpt::{normalize_excerpt(excerpt)}"
            issue = grouped.setdefault(
                issue_key,
                {
                    "line_anchors": [],
                    "excerpts": [],
                    "verdict": target_verdict,
                    "summaries": [],
                    "checkpoints": [],
                    "checkpoint_ids": set(),
                    "types": [],
                },
            )
            if line_anchor and line_anchor not in issue["line_anchors"]:
                issue["line_anchors"].append(line_anchor)
            if excerpt and excerpt not in issue["excerpts"]:
                issue["excerpts"].append(excerpt)
            reason = str(candidate.get("reason", "")).strip() or summary
            if summary and summary not in issue["summaries"]:
                issue["summaries"].append(summary)
            if report["sop_id"] not in issue["checkpoint_ids"]:
                item = {
                    "sop_id": report["sop_id"],
                    "title": report["sop_title"],
                    "verdict": verdict,
                    "summary": summary,
                    "reason": reason,
                }
                issue["checkpoints"].append(item)
                issue["checkpoint_ids"].add(report["sop_id"])
            label = issue_type(report["sop_title"], summary)
            if label not in issue["types"]:
                issue["types"].append(label)
    issues = list(grouped.values())
    for issue in issues:
        issue.pop("checkpoint_ids", None)
    return sorted(
        issues,
        key=lambda item: (
            not item["line_anchors"],
            item["line_anchors"][0] if item["line_anchors"] else "",
            -len(item["checkpoints"]),
        ),
    )


def write_business_report(output_dir: Path, reports: list[dict[str, Any]], args: argparse.Namespace, run_started_at: str, run_ended_at: str) -> None:
    hits = collect_business_issues(reports, "命中")
    pending = collect_business_issues(reports, "待人工复核")
    review_name = Path(args.review_file).name
    title = f"{review_name} 业务审查报告"
    lines = [
        "---",
        f'title: "{safe_frontmatter_value(title)}"',
        "page_type: business-audit-report",
        f"run_dir: {relative_path(output_dir)}",
        f"generated_at: {run_ended_at}",
        "---",
        "",
        f"# {title}",
        "",
        "## 一、审查结论摘要",
        "",
        "本报告由 AI 审查生成，用于辅助识别政府采购文件中的合规风险。报告结论不替代采购人、采购代理机构、评审专家、法务人员或监管部门的人工判断。",
        "",
        "- 审查方式：AI 自动审查",
        f"- 审查模型：{args.model}",
        f"- 待审文件：{review_name}",
        f"- 开始时间：{run_started_at}",
        f"- 结束时间：{run_ended_at}",
        f"- 检查点数量：{len(reports)}",
        f"- 形成业务风险问题：{len(hits)} 个",
        f"- 待人工复核事项：{len(pending)} 个",
        "",
        "",
        "## 二、问题明细",
        "",
    ]
    if not hits:
        lines.append("本轮未形成可直接列示的业务风险问题。")
        lines.append("")
    for index, issue in enumerate(hits, start=1):
        names = "、".join(item["title"] for item in issue["checkpoints"][:2])
        suffix = "等关联风险" if len(issue["checkpoints"]) > 1 else ""
        lines.extend(render_business_issue(index, issue, f"问题 {index}：{names}{suffix}"))

    lines.extend(["", "## 三、待人工复核事项", ""])
    if not pending:
        lines.append("本轮未形成待人工复核事项。")
        lines.append("")
    for index, issue in enumerate(pending, start=1):
        names = "、".join(item["title"] for item in issue["checkpoints"][:2])
        suffix = "等关联风险" if len(issue["checkpoints"]) > 1 else ""
        lines.extend(render_business_issue(index, issue, f"复核事项 {index}：{names}{suffix}", pending=True))

    lines.extend([
        "",
        "## 四、审查范围与依据",
        "",
        "- 本报告依据本库 `wiki/review-sops/items/` 中的 3+1 审查执行说明书生成。",
        "- 本报告按同一证据摘录聚合多个检查点，便于业务人员从原文问题出发查看关联风险。",
        "- `命中` 表示小模型按照 SOP 找到明确风险线索；`待人工复核` 表示证据、上下文或法规适用仍需人工确认。",
        "",
        "## 五、AI审查特别提醒说明",
        "",
        "本报告为 AI 自动审查结果，可能存在文本抽取遗漏、上下文理解偏差、法规适用口径差异或模型误判。业务使用前，应由具备政府采购实务经验的人员结合完整采购文件、公告、合同、项目背景和现行法规进行复核确认。",
        "",
    ])
    write_text(output_dir / "业务审查报告.md", "\n".join(lines))


def render_business_issue(index: int, issue: dict[str, Any], heading: str, pending: bool = False) -> list[str]:
    verdict = "待人工复核" if pending else "命中"
    line_anchors = issue.get("line_anchors", [])
    excerpts = issue.get("excerpts", [])
    excerpt = excerpts[0] if excerpts else "本项未返回明确原文摘录，请查看对应 SOP 报告。"
    lines = [
        f"### {heading}",
        "",
        f"- 风险等级：{risk_level_for(verdict)}",
        f"- 问题类型：{', '.join(issue['types']) if issue['types'] else '合规风险'}",
        f"- 证据位置：{'、'.join(line_anchors) if line_anchors else '未明确'}",
        f"- 当前状态：{verdict}",
        "",
        "#### 原文摘录",
        "",
        "```text",
        excerpt,
        "```",
        "",
    ]
    if len(excerpts) > 1:
        lines.extend([
            "#### 同类证据摘录",
            "",
        ])
        for extra_index, extra_excerpt in enumerate(excerpts[1:], start=2):
            lines.extend([
                f"摘录 {extra_index}：",
                "",
                "```text",
                extra_excerpt,
                "```",
                "",
            ])
    lines.extend([
        "#### 触发检查点",
        "",
        "| 检查点 | 结论 | 说明 |",
        "|---|---|---|",
    ])
    for item in issue["checkpoints"]:
        summary = str(item.get("summary") or item.get("reason") or "").replace("\n", " ")
        lines.append(f"| {item['sop_id']} {item['title']} | {item['verdict']} | {summary} |")
    risk_text = "；".join(issue["summaries"]) or "需结合采购文件完整上下文、项目实际需求和适用法规进行确认。"
    lines.extend([
        "",
        "#### 风险说明" if not pending else "#### 需人工确认事项",
        "",
        risk_text,
        "",
    ])
    return lines


def write_batch_summary(output_dir: Path, reports: list[dict[str, Any]]) -> None:
    rows = ["sop_id\tverdict\tsummary\treport_file"]
    for report in reports:
        result = report["model_result"]
        rows.append(
            "\t".join([
                report["sop_id"],
                str(result.get("verdict", "")),
                str(result.get("summary", "")).replace("\t", " "),
                report.get("report_file", ""),
            ])
        )
    write_text(output_dir / "results.tsv", "\n".join(rows) + "\n")
    lines = ["# 3+1 批量验证报告", ""]
    for report in reports:
        result = report["model_result"]
        lines.append(f"- `{report['sop_id']}`：{result.get('verdict', '')}。{result.get('summary', '')}")
    write_text(output_dir / "审查报告.md", "\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证 3+1 审查执行说明书。")
    parser.add_argument("--sop", type=Path, help="单个 3+1 审查执行说明书")
    parser.add_argument("--sop-glob", help="批量验证 glob，例如 'wiki/review-sops/items/*.md'")
    parser.add_argument("--review-file", type=Path, required=True, help="待审文件，支持 md/txt/doc/docx")
    parser.add_argument("--output-dir", type=Path, help="输出目录，默认 validation/review-sop-runs/review-sop-...")
    parser.add_argument("--base-url", help=f"OpenAI 兼容接口 base_url；也可用 {ENV_BASE_URL}")
    parser.add_argument("--api-key", help=f"OpenAI 兼容接口密钥；也可用 {ENV_API_KEY}")
    parser.add_argument("--model", help=f"模型名称；也可用 {ENV_MODEL}")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--context-before", type=int, default=8)
    parser.add_argument("--context-after", type=int, default=10)
    parser.add_argument("--max-windows", type=int, default=10)
    parser.add_argument("--max-line-chars", type=int, default=700)
    parser.add_argument("--max-review-excerpt-chars", type=int, default=26000)
    parser.add_argument("--max-sop-chars", type=int, default=18000)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--min-candidate-score", type=int, default=DEFAULT_MIN_CANDIDATE_SCORE)
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    resolve_llm_config(args)
    sop_paths = collect_sop_paths(args)
    output_dir = args.output_dir or (DEFAULT_OUTPUT_ROOT / f"review-sop-{time.strftime('%Y%m%d-%H%M%S')}")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_started_at = now_text()
    write_text(output_dir / "batch.log", "\n".join([
        f"batch_dir={relative_path(output_dir)}",
        f"review_file={relative_path(args.review_file)}",
        f"checkpoint_count={len(sop_paths)}",
        "mode=review-sop-3plus1",
        f"jobs={args.jobs}",
        f"max_tokens={args.max_tokens}",
        f"started_at={run_started_at}",
        "",
    ]))

    reports: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
        future_map = {
            executor.submit(run_one, args, sop_path, args.review_file, output_dir): sop_path
            for sop_path in sop_paths
        }
        for future in concurrent.futures.as_completed(future_map):
            sop_path = future_map[future]
            try:
                report = future.result()
                reports.append(report)
                print(f"ok {now_text()} sop={report['sop_id']} verdict={report['model_result'].get('verdict')} output={report.get('report_file')}", flush=True)
            except Exception as exc:
                print(f"error {now_text()} sop={relative_path(sop_path)} {exc}", flush=True)
                raise
    reports.sort(key=lambda item: item["sop_id"])
    write_batch_summary(output_dir, reports)
    run_ended_at = now_text()
    write_business_report(output_dir, reports, args, run_started_at, run_ended_at)
    append_text(output_dir / "batch.log", f"\ncompleted_at={run_ended_at}\ncompleted_count={len(reports)}\n")
    print(f"done output={relative_path(output_dir)} count={len(reports)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
