#!/usr/bin/env python3
"""用 OpenAI 兼容接口验证: 1 个风险点 SOP + 1 份待审核文件 + 1 次小模型执行。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path.cwd()
DEFAULT_VALIDATION_ROOT = WORKSPACE_ROOT / "validation" / "cli-runs"
DEFAULT_PARALLELISM = max(1, min(4, os.cpu_count() or 1))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


def load_review_file_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return read_text(path), "plain-text"
    if suffix == ".docx":
        return extract_text_from_docx(path)
    if suffix == ".doc":
        return extract_text_from_doc(path)
    raise RuntimeError(f"暂不支持的待审核文件类型：{path.suffix}")


def extract_heading_section(markdown: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)"
    )
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def extract_title(markdown: str) -> str:
    frontmatter = re.match(r"(?ms)^---\n(.*?)\n---", markdown)
    if frontmatter:
        title_match = re.search(r"^title:\s*(.+)$", frontmatter.group(1), re.M)
        if title_match:
            return title_match.group(1).strip()
    title_line = re.search(r"^#\s+(.+)$", markdown, re.M)
    return title_line.group(1).strip() if title_line else "unknown-finding"


def parse_sop_keywords(sop_text: str) -> dict[str, list[str]]:
    keys = ["表头词", "对象词", "对象词补充", "限制词", "后果词"]
    result: dict[str, list[str]] = {key: [] for key in keys}
    for key in keys:
        match = re.search(rf"(?m)^-\s*{re.escape(key)}：\s*(.+)$", sop_text)
        if not match:
            continue
        parts = []
        for item in re.split(r"[、，,]", match.group(1)):
            cleaned = item.strip().rstrip("。；;：:")
            if cleaned:
                parts.append(cleaned)
        result[key] = parts
    return result


def numbered_text_lines(text: str) -> list[str]:
    return text.splitlines()


def normalize_line_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def locate_excerpt_line_range(review_text: str, excerpt: str) -> str | None:
    lines = numbered_text_lines(review_text)
    excerpt_lines = [normalize_line_for_match(line) for line in excerpt.splitlines() if normalize_line_for_match(line)]
    if not excerpt_lines:
        return None

    normalized_lines = [normalize_line_for_match(line) for line in lines]
    first_line = excerpt_lines[0]
    best_start: int | None = None
    best_score = -1

    for idx, line in enumerate(normalized_lines):
        if not line:
            continue
        if first_line == line:
            score = 4
        elif first_line in line or line in first_line:
            score = 2
        else:
            continue

        for offset, excerpt_line in enumerate(excerpt_lines[1:], start=1):
            probe = idx + offset
            if probe >= len(normalized_lines):
                break
            target = normalized_lines[probe]
            if excerpt_line == target or excerpt_line in target or target in excerpt_line:
                score += 1

        if score > best_score:
            best_score = score
            best_start = idx

    if best_start is None:
        return None

    end = min(len(lines), best_start + max(1, len(excerpt_lines)))
    start_line = best_start + 1
    end_line = end
    if start_line == end_line:
        return f"行号 {start_line:04d}"
    return f"行号 {start_line:04d}-{end_line:04d}"


def match_keywords(line: str, keyword_groups: dict[str, list[str]]) -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {group: set() for group in keyword_groups}
    for group, words in keyword_groups.items():
        for word in words:
            if word and word in line:
                hits[group].add(word)
    return hits


def collect_candidate_windows(
    text: str,
    keyword_groups: dict[str, list[str]],
    context_before: int,
    context_after: int,
    max_windows: int,
) -> tuple[str, int]:
    lines = numbered_text_lines(text)
    windows: list[tuple[int, int, dict[str, set[str]], int, int]] = []
    for idx, line in enumerate(lines):
        hits = match_keywords(line, keyword_groups)
        total_hits = sum(len(words) for words in hits.values())
        category_hits = sum(1 for words in hits.values() if words)
        if total_hits == 0:
            continue
        start = max(0, idx - context_before)
        end = min(len(lines), idx + context_after + 1)
        windows.append((start, end, hits, category_hits, total_hits))

    if not windows:
        return "\n".join(lines[: min(len(lines), 200)]), 0

    windows.sort(key=lambda item: (item[3], item[4], -(item[0])), reverse=True)
    windows = windows[:max_windows]

    merged: list[tuple[int, int, dict[str, set[str]], int, int]] = []
    for start, end, hits, category_hits, total_hits in windows:
        if not merged or start > merged[-1][1]:
            merged.append((start, end, {k: set(v) for k, v in hits.items()}, category_hits, total_hits))
            continue
        prev_start, prev_end, prev_hits, prev_category_hits, prev_total_hits = merged[-1]
        merged_hits = {group: set(prev_hits[group]) | set(hits[group]) for group in keyword_groups}
        merged[-1] = (
            prev_start,
            max(prev_end, end),
            merged_hits,
            max(prev_category_hits, category_hits),
            max(prev_total_hits, total_hits),
        )

    chunks: list[str] = []
    for idx, (start, end, hits, category_hits, total_hits) in enumerate(merged, start=1):
        chunk = "\n".join(lines[start:end])
        hit_parts = []
        for group, words in hits.items():
            if words:
                hit_parts.append(f"{group}=" + "、".join(sorted(words)))
        hit_text = "；".join(hit_parts)
        chunks.append(
            f"[候选窗口 {idx}] 命中组数：{category_hits}；命中词数：{total_hits}；{hit_text}\n{chunk}"
        )
    return "\n\n".join(chunks), len(merged)


def trim_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def load_finding_payload(path: Path) -> dict[str, Any]:
    finding_text = read_text(path)
    sop_text = extract_heading_section(finding_text, "审查逻辑")
    if not sop_text:
        raise RuntimeError(f"{path.name} 未找到 `## 审查逻辑` 段落")
    return {
        "path": path,
        "text": finding_text,
        "title": extract_title(finding_text),
        "sop_text": sop_text,
    }


def build_messages(
    finding_title: str,
    sop_text: str,
    review_excerpt: str,
    review_file_name: str,
) -> list[dict[str, str]]:
    system = (
        "你是政府采购招标文件合规审查小模型。"
        "你只能根据给定的 finding 审查逻辑 SOP 和待审核文件原文节选执行盲测。"
        "你不能发明未出现在原文中的证据，也不能只因关键词命中就直接下结论。"
        "输出必须是 JSON。"
    )
    user = textwrap.dedent(
        f"""
        目标风险点：{finding_title}

        任务要求：
        1. 只能根据下方 SOP 进行审查。
        2. 先给出 SOP 3 召回到的候选条款。
        3. 再对每个候选条款执行 SOP 4、SOP 5、SOP 6、SOP 7。
        4. 最终结论只能是：命中 / 不命中 / 待复核。
        5. 如果证据不足，必须输出待复核，不能强行命中。

        输出 JSON 结构：
        {{
          "finding_title": "...",
          "verdict": "命中|不命中|待复核",
          "summary": "...",
          "sop_execution": {{
            "sop3_recall": {{
              "status": "已执行",
              "summary": "...",
              "candidate_count": 0
            }},
            "sop4_clause_classification": {{
              "status": "已执行",
              "summary": "...",
              "clause_types": ["评分项|资格条件|符合性审查|证明材料|履约要求|验收要求|模板残留|其他"]
            }},
            "sop5_hit_checks": {{
              "status": "已执行",
              "summary": "...",
              "passed_checks": ["..."],
              "failed_checks": ["..."]
            }},
            "sop6_exclusion_checks": {{
              "status": "已执行",
              "summary": "...",
              "triggered_exclusions": ["..."],
              "not_triggered_exclusions": ["..."]
            }},
            "sop7_boundary_reference": {{
              "status": "已执行",
              "summary": "...",
              "references": ["正例 1|反例 2"]
            }}
          }},
          "candidates": [
            {{
              "line_anchor": "...",
              "excerpt": "...",
              "matched_keywords": ["..."],
              "clause_type": "评分项|资格条件|符合性审查|证明材料|履约要求|验收要求|模板残留|其他",
              "sop5_checks": [
                {{"check": "...", "result": true, "reason": "..."}}
              ],
              "sop6_checks": [
                {{"check": "...", "result": false, "reason": "..."}}
              ],
              "boundary_reference": "使用了哪个正例或反例解释边界"
            }}
          ]
        }}

        【审查逻辑 SOP】
        {sop_text}

        【待审核文件】
        {review_file_name}

        【待审核文件候选窗口】
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
) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
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
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"接口未返回合法 JSON：{result.stdout[:1000]}") from exc


def parse_model_json(raw_response: dict) -> dict:
    try:
        content = raw_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected model response: {raw_response}") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model did not return valid JSON: {content}") from exc


def normalize_model_result(model_result: dict[str, Any]) -> dict[str, Any]:
    candidates = model_result.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
        model_result["candidates"] = candidates

    sop_execution = model_result.get("sop_execution")
    if not isinstance(sop_execution, dict):
        sop_execution = {}

    clause_types: list[str] = []
    passed_checks: list[str] = []
    failed_checks: list[str] = []
    triggered_exclusions: list[str] = []
    not_triggered_exclusions: list[str] = []
    references: list[str] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        clause_type = candidate.get("clause_type")
        if isinstance(clause_type, str) and clause_type and clause_type not in clause_types:
            clause_types.append(clause_type)

        for item in candidate.get("sop5_checks", []) if isinstance(candidate.get("sop5_checks"), list) else []:
            if not isinstance(item, dict):
                continue
            check = item.get("check")
            result = item.get("result")
            if isinstance(check, str):
                if result is True and check not in passed_checks:
                    passed_checks.append(check)
                if result is False and check not in failed_checks:
                    failed_checks.append(check)

        for item in candidate.get("sop6_checks", []) if isinstance(candidate.get("sop6_checks"), list) else []:
            if not isinstance(item, dict):
                continue
            check = item.get("check")
            result = item.get("result")
            if isinstance(check, str):
                if result is True and check not in triggered_exclusions:
                    triggered_exclusions.append(check)
                if result is False and check not in not_triggered_exclusions:
                    not_triggered_exclusions.append(check)

        boundary_reference = candidate.get("boundary_reference")
        if isinstance(boundary_reference, str) and boundary_reference and boundary_reference not in references:
            references.append(boundary_reference)

    def ensure_step(
        key: str,
        *,
        summary: str,
        extra: dict[str, Any],
    ) -> None:
        current = sop_execution.get(key)
        if not isinstance(current, dict):
            current = {}
        current.setdefault("status", "已执行")
        current.setdefault("summary", summary)
        for extra_key, extra_value in extra.items():
            current.setdefault(extra_key, extra_value)
        sop_execution[key] = current

    ensure_step(
        "sop3_recall",
        summary=f"共召回 {len(candidates)} 个候选条款。",
        extra={"candidate_count": len(candidates)},
    )
    ensure_step(
        "sop4_clause_classification",
        summary="已对候选条款完成条款类型识别。",
        extra={"clause_types": clause_types},
    )
    ensure_step(
        "sop5_hit_checks",
        summary="已按命中条件逐项核验。",
        extra={"passed_checks": passed_checks, "failed_checks": failed_checks},
    )
    ensure_step(
        "sop6_exclusion_checks",
        summary="已按排除条件逐项核验。",
        extra={
            "triggered_exclusions": triggered_exclusions,
            "not_triggered_exclusions": not_triggered_exclusions,
        },
    )
    ensure_step(
        "sop7_boundary_reference",
        summary="已结合正例/反例边界进行归纳。",
        extra={"references": references},
    )
    model_result["sop_execution"] = sop_execution
    return model_result


def enrich_model_result_with_evidence_position(model_result: dict[str, Any], review_text: str) -> dict[str, Any]:
    candidates = model_result.get("candidates")
    if not isinstance(candidates, list):
        return model_result
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        excerpt = str(candidate.get("excerpt", "")).strip()
        if not excerpt:
            continue
        line_range = locate_excerpt_line_range(review_text, excerpt)
        if line_range:
            candidate["evidence_line_range"] = line_range
    return model_result


def expected_from_full_risk_scan(full_risk_scan_text: str, finding_title: str) -> str:
    if finding_title in full_risk_scan_text:
        return "命中"
    return "未知"


def compare_result(predicted: str, expected: str) -> dict[str, str | bool]:
    if expected == "未知":
        return {"expected": expected, "matched": False, "note": "full-risk-scan 未直接包含该 finding 标题，需人工对账"}
    return {
        "expected": expected,
        "matched": predicted == expected,
        "note": "predicted 与 full-risk-scan 标题映射一致" if predicted == expected else "predicted 与 full-risk-scan 标题映射不一致，需人工复核",
    }


def report_json_block(report: dict[str, Any]) -> str:
    return (
        "<!-- REPORT_JSON_START\n"
        + json.dumps(report, ensure_ascii=False, indent=2)
        + "\nREPORT_JSON_END -->\n"
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def slugify_filename(name: str) -> str:
    sanitized = re.sub(r'[\\\\/:*?"<>|]+', "-", name).strip()
    return sanitized or "unknown"


def to_relative_path(path_value: str | Path | None) -> str | None:
    if path_value is None:
        return None
    path = Path(path_value)
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


def sanitize_stem(name: str) -> str:
    text = re.sub(r"\.[A-Za-z0-9]+$", "", name).strip()
    return slugify_filename(text)


def default_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def default_batch_output_dir(review_path: Path) -> Path:
    return DEFAULT_VALIDATION_ROOT / f"batch-{sanitize_stem(review_path.stem)}-{default_run_id()}"


def validate_output_dir_policy(output_dir: Path) -> None:
    forbidden = WORKSPACE_ROOT / "wiki" / "audits"
    if under_path(output_dir, forbidden):
        raise RuntimeError(
            "CLI 验证输出目录不得位于 `wiki/audits/`；请改用 `validation/` 等与 `wiki/` 并列的目录。"
        )


def parse_report_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except Exception:
            return None
    match = re.search(r"<!-- REPORT_JSON_START\s*(\{.*?\})\s*REPORT_JSON_END -->", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def read_report_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return parse_report_from_text(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_evidence_from_report_path(report_path: str | Path | None) -> list[dict[str, str]]:
    if report_path is None:
        return []
    path = Path(report_path)
    report = read_report_file(path)
    if not isinstance(report, dict):
        return []
    model_result = report.get("model_result", {})
    candidates = model_result.get("candidates", [])
    evidences: list[dict[str, str]] = []
    if not isinstance(candidates, list):
        return evidences
    for candidate in candidates[:3]:
        if not isinstance(candidate, dict):
            continue
        line_anchor = str(candidate.get("evidence_line_range") or candidate.get("line_anchor", "")).strip()
        excerpt = str(candidate.get("excerpt", "")).strip()
        if not line_anchor and not excerpt:
            continue
        evidences.append(
            {
                "line_anchor": line_anchor,
                "excerpt": excerpt,
            }
        )
    return evidences


def risk_level_from_verdict(verdict: str) -> str:
    if verdict == "命中":
        return "高风险"
    if verdict == "待复核":
        return "待人工复核"
    if verdict == "不命中":
        return "本轮未命中"
    return "未知"


def markdown_link(label: str, target: str | Path | None, current_dir: Path) -> str:
    if not target:
        return label
    path = Path(str(target))
    rel = os.path.relpath(path, current_dir)
    return f"[{label}]({rel})"


def render_report_markdown(
    report: dict[str, Any],
    *,
    current_path: Path,
    summary_path: Path | None = None,
    summary_md_path: Path | None = None,
    full_report_path: Path | None = None,
    previous_path: Path | None = None,
    next_path: Path | None = None,
    run_id: str | None = None,
) -> str:
    current_dir = current_path.parent
    model_result = report.get("model_result", {}) if isinstance(report.get("model_result"), dict) else {}
    candidates = model_result.get("candidates", []) if isinstance(model_result.get("candidates"), list) else []
    sop_execution = model_result.get("sop_execution", {}) if isinstance(model_result.get("sop_execution"), dict) else {}
    comparison = report.get("comparison", {}) if isinstance(report.get("comparison"), dict) else {}
    verdict = str(model_result.get("verdict", "未知"))
    title = str(report.get("finding_title", "未知风险点"))

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 导航")
    nav_parts = []
    if summary_md_path:
        nav_parts.append(markdown_link("批量索引", summary_md_path, current_dir))
    if summary_path:
        nav_parts.append(markdown_link("汇总JSON", summary_path, current_dir))
    if full_report_path:
        nav_parts.append(markdown_link("文件级结论", full_report_path, current_dir))
    if previous_path:
        nav_parts.append(markdown_link("上一个", previous_path, current_dir))
    if next_path:
        nav_parts.append(markdown_link("下一个", next_path, current_dir))
    lines.append("- " + " | ".join(nav_parts) if nav_parts else "- 无")
    lines.append("")
    lines.append("## 基本信息")
    if run_id:
        lines.append(f"- run_id: {run_id}")
    lines.append(f"- finding_title: {title}")
    lines.append(f"- verdict: {verdict}")
    lines.append(f"- review_file: {report.get('review_file')}")
    lines.append(f"- finding_file: {report.get('finding')}")
    lines.append(f"- model: {report.get('model')}")
    timing = report.get("timing", {}) if isinstance(report.get("timing"), dict) else {}
    if timing:
        lines.append(f"- started_at: {timing.get('started_at')}")
        lines.append(f"- finished_at: {timing.get('finished_at')}")
        lines.append(f"- duration_seconds: {timing.get('duration_seconds')}")
    lines.append("")
    lines.append("## 审查结论")
    lines.append(f"- 结论：{verdict}")
    lines.append(f"- 结论摘要：{model_result.get('summary', '')}")
    if comparison:
        lines.append(f"- 对账期望：{comparison.get('expected')}")
        lines.append(f"- 对账结果：{'一致' if comparison.get('matched') else '需复核'}")
        lines.append(f"- 对账说明：{comparison.get('note')}")
    lines.append("")
    lines.append("## SOP 执行")
    for step_key in [
        "sop3_recall",
        "sop4_clause_classification",
        "sop5_hit_checks",
        "sop6_exclusion_checks",
        "sop7_boundary_reference",
    ]:
        step = sop_execution.get(step_key, {})
        if not isinstance(step, dict):
            continue
        lines.append(f"### {step_key}")
        lines.append(f"- 状态：{step.get('status', '')}")
        lines.append(f"- 摘要：{step.get('summary', '')}")
        extra_lines: list[str] = []
        for key in [
            "candidate_count",
            "clause_types",
            "passed_checks",
            "failed_checks",
            "triggered_exclusions",
            "not_triggered_exclusions",
            "references",
        ]:
            value = step.get(key)
            if isinstance(value, list) and value:
                extra_lines.append(f"- {key}: " + "；".join(str(x) for x in value))
            elif value not in (None, "", []):
                extra_lines.append(f"- {key}: {value}")
        lines.extend(extra_lines)
        lines.append("")
    lines.append("## 候选条款")
    if not candidates:
        lines.append("- 本轮未召回候选条款。")
        lines.append("")
    else:
        for idx, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                continue
            lines.append(f"### 候选 {idx}")
            lines.append(f"- 条款类型：{candidate.get('clause_type', '')}")
            lines.append(f"- 证据位置：{candidate.get('evidence_line_range') or candidate.get('line_anchor', '')}")
            matched_keywords = candidate.get("matched_keywords")
            if isinstance(matched_keywords, list) and matched_keywords:
                lines.append("- 命中关键词：" + "、".join(str(x) for x in matched_keywords))
            lines.append(f"- 边界参照：{candidate.get('boundary_reference', '')}")
            lines.append("- 证据摘录：")
            lines.append("")
            lines.append("```text")
            lines.append(str(candidate.get("excerpt", "")).strip())
            lines.append("```")
            sop5_checks = candidate.get("sop5_checks")
            if isinstance(sop5_checks, list) and sop5_checks:
                lines.append("- SOP5核查：")
                for item in sop5_checks:
                    if isinstance(item, dict):
                        lines.append(f"  - {item.get('check', '')} => {item.get('result')}；{item.get('reason', '')}")
            sop6_checks = candidate.get("sop6_checks")
            if isinstance(sop6_checks, list) and sop6_checks:
                lines.append("- SOP6排除：")
                for item in sop6_checks:
                    if isinstance(item, dict):
                        lines.append(f"  - {item.get('check', '')} => {item.get('result')}；{item.get('reason', '')}")
            lines.append("")
    lines.append(report_json_block(report))
    return "\n".join(lines).rstrip() + "\n"


def render_full_risk_scan_style_markdown(summary: dict[str, Any]) -> str:
    review_file = Path(str(summary["review_file"]))
    title = review_file.stem
    output_dir = Path(str(summary.get("output_dir", ".")))
    conclusion = summary.get("review_conclusion", {})
    hits = conclusion.get("命中", [])
    pending = conclusion.get("待复核", [])
    not_hit = conclusion.get("不命中", [])
    unknown = conclusion.get("未知", [])
    error_count = int(summary.get("error_count", 0))

    lines: list[str] = []
    lines.append(f"# {title} 全风险点扫描")
    lines.append("")
    lines.append(f"- source_file: {to_relative_path(review_file)}")
    lines.append(f"- scan_date: {time.strftime('%Y-%m-%d')}")
    lines.append("- scan_method: findings-SOP 批量审查 + 小模型执行验证 + 文件级结论归纳")
    lines.append(f"- review_status: {'reviewed' if error_count == 0 else 'needs-review'}")
    if isinstance(summary.get("timing"), dict):
        lines.append(f"- run_started_at: {summary['timing'].get('started_at')}")
        lines.append(f"- run_finished_at: {summary['timing'].get('finished_at')}")
    lines.append("")
    lines.append("## 审查结论")
    lines.append(f"- 本次基于 `wiki/findings/` 全量风险点对待审文件进行逐项审查，共检查 {summary.get('total_findings', 0)} 个标准风险点。")
    lines.append(f"- 当前明确命中 {len(hits)} 项，待复核 {len(pending)} 项，不命中 {len(not_hit)} 项，另有 {error_count} 项执行失败需补跑。")
    if hits:
        hit_titles = "、".join(item.get("finding_title", "") for item in hits)
        lines.append(f"- 当前已识别的主要风险集中在：{hit_titles}。")
    if pending:
        pending_titles = "、".join(item.get("finding_title", "") for item in pending)
        lines.append(f"- 仍需结合完整正文或补充证据进一步复核的事项包括：{pending_titles}。")
    if error_count:
        lines.append("- 由于存在执行失败项，本结论属于可用审查稿，但仍建议对失败风险点补跑后再作为最终全量结论使用。")
    lines.append("")
    lines.append("## 风险点")

    risk_items = hits + pending
    if risk_items:
        for idx, item in enumerate(risk_items, start=1):
            verdict = str(item.get("verdict", ""))
            lines.append(f"### {idx}. {item.get('finding_title', '')}")
            lines.append(f"- 结论层级：{risk_level_from_verdict(verdict)}")
            lines.append(f"- 风险分析：{item.get('summary', '')}")
            timing = item.get("timing")
            if isinstance(timing, dict):
                lines.append(f"- SOP开始时间：{timing.get('started_at')}")
                lines.append(f"- SOP结束时间：{timing.get('finished_at')}")
            evidences = item.get("evidences", [])
            if evidences:
                lines.append("- 证据位置：")
                for evidence in evidences:
                    lines.append(f"  - {evidence.get('line_anchor', '未提取位置')}")
                lines.append("- 证据摘录：")
                for evidence in evidences:
                    lines.append(f"  - {evidence.get('excerpt', '')}")
            lines.append(f"- 审查结果：{verdict}")
            output = item.get("output")
            if output:
                lines.append(f"- 结果文件：{markdown_link(str(item.get('finding_title', '结果文件')), output_dir / Path(str(output)).name, output_dir)}")
            lines.append("")
    else:
        lines.append("- 本轮未识别出明确命中的标准风险点。")
        lines.append("")

    lines.append("## 未单列为风险的事项")
    if not_hit:
        for item in not_hit:
            lines.append(f"- {item.get('finding_title', '')}：{item.get('summary', '')}")
    else:
        lines.append("- 本轮无“不命中”事项。")
    if unknown:
        for item in unknown:
            lines.append(f"- {item.get('finding_title', '')}：结果未知，建议人工复核。")
    if error_count:
        lines.append("")
        lines.append("## 需补跑事项")
        for item in summary.get("results", []):
            if item.get("status") == "error":
                lines.append(f"- {item.get('finding_title', '')}：{item.get('error', '')}")

    return "\n".join(lines).rstrip() + "\n"


def render_summary_markdown(summary: dict[str, Any], output_dir: Path) -> str:
    review_file = Path(str(summary.get("review_file", "")))
    lines: list[str] = []
    lines.append(f"# {review_file.stem} 验证结果索引")
    lines.append("")
    lines.append("## 文件")
    if summary.get("run_id"):
        lines.append(f"- run_id: {summary.get('run_id')}")
    lines.append(f"- review_file: {summary.get('review_file')}")
    lines.append(f"- findings_dir: {summary.get('findings_dir')}")
    lines.append(f"- output_dir: {summary.get('output_dir')}")
    lines.append(f"- model: {summary.get('model')}")
    timing = summary.get("timing", {}) if isinstance(summary.get("timing"), dict) else {}
    if timing:
        lines.append(f"- started_at: {timing.get('started_at')}")
        lines.append(f"- finished_at: {timing.get('finished_at')}")
    lines.append("")
    lines.append("## 总览")
    lines.append(f"- total_findings: {summary.get('total_findings')}")
    lines.append(f"- completed: {summary.get('completed')}")
    lines.append(f"- error_count: {summary.get('error_count')}")
    verdict_counts = summary.get("verdict_counts", {})
    if isinstance(verdict_counts, dict):
        for key, value in verdict_counts.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## 结果目录")
    lines.append(f"- {markdown_link('文件级结论', output_dir / 'full-risk-scan-style.md', output_dir)}")
    lines.append(f"- {markdown_link('汇总JSON', output_dir / 'summary.json', output_dir)}")
    lines.append(f"- {markdown_link('运行进度', output_dir / 'progress.json', output_dir)}")
    lines.append("")
    lines.append("## 风险点结果")
    for item in sorted(summary.get("results", []), key=lambda x: int(x.get("index", 0)) if isinstance(x, dict) else 0):
        if not isinstance(item, dict):
            continue
        label = f"{item.get('index')}. {item.get('finding_title', '')}"
        output = item.get("output")
        if output:
            label = markdown_link(label, output_dir / Path(str(output)).name, output_dir)
        status_text = item.get("status", "")
        verdict_text = item.get("verdict", "")
        summary_text = item.get("summary", "") or item.get("error", "")
        lines.append(f"- {label} | status={status_text} | verdict={verdict_text} | {summary_text}")
    return "\n".join(lines).rstrip() + "\n"


def dump_report(report: dict[str, Any], output_path: Path | None) -> None:
    if output_path and output_path.suffix.lower() == ".md":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(render_report_markdown(report, current_path=output_path), encoding="utf-8")
        print(output_path.read_text(encoding="utf-8"))
        return
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)


def validate_single_finding(
    *,
    finding_path: Path,
    finding_title: str | None,
    sop_text: str | None,
    review_path: Path,
    full_risk_scan_path: Path | None,
    full_risk_scan_text: str | None,
    review_text: str | None,
    review_file_extract_method: str | None,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    timeout_seconds: int,
    context_before: int,
    context_after: int,
    max_windows: int,
    max_excerpt_chars: int,
) -> dict[str, Any]:
    finding_started_at = now_text()
    finding_started_ts = time.time()
    local_finding_title = finding_title
    local_sop_text = sop_text
    if local_finding_title is None or local_sop_text is None:
        payload = load_finding_payload(finding_path)
        local_finding_title = str(payload["title"])
        local_sop_text = str(payload["sop_text"])

    preprocess_started_ts = time.time()
    keyword_groups = parse_sop_keywords(local_sop_text)
    if review_text is None or review_file_extract_method is None:
        review_text, review_file_extract_method = load_review_file_text(review_path)
    excerpt, candidate_window_count = collect_candidate_windows(
        text=review_text,
        keyword_groups=keyword_groups,
        context_before=context_before,
        context_after=context_after,
        max_windows=max_windows,
    )
    excerpt = trim_chars(excerpt, max_excerpt_chars)
    preprocess_seconds = round(time.time() - preprocess_started_ts, 3)

    messages = build_messages(
        finding_title=local_finding_title,
        sop_text=local_sop_text,
        review_excerpt=excerpt,
        review_file_name=review_path.name,
    )
    api_started_ts = time.time()
    raw_response = post_openai_compatible(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )
    api_seconds = round(time.time() - api_started_ts, 3)
    model_result = parse_model_json(raw_response)
    model_result = normalize_model_result(model_result)
    model_result = enrich_model_result_with_evidence_position(model_result, review_text)

    report: dict[str, Any] = {
        "finding": to_relative_path(finding_path),
        "finding_title": local_finding_title,
        "review_file": to_relative_path(review_path),
        "review_file_extract_method": review_file_extract_method,
        "full_risk_scan": to_relative_path(full_risk_scan_path) if full_risk_scan_path else None,
        "model": model,
        "base_url": base_url,
        "keyword_groups": keyword_groups,
        "candidate_window_count": candidate_window_count,
        "excerpt_preview_chars": len(excerpt),
        "model_result": model_result,
        "timing": {
            "started_at": finding_started_at,
            "finished_at": now_text(),
            "duration_seconds": round(time.time() - finding_started_ts, 3),
            "preprocess_seconds": preprocess_seconds,
            "api_seconds": api_seconds,
        },
    }

    if full_risk_scan_path:
        scan_text = full_risk_scan_text if full_risk_scan_text is not None else read_text(full_risk_scan_path)
        expected = expected_from_full_risk_scan(scan_text, local_finding_title)
        predicted = model_result.get("verdict", "未知")
        report["comparison"] = compare_result(str(predicted), expected)

    return report


def arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按 finding 的审查逻辑 SOP 对待审核文件执行小模型验证")
    parser.add_argument("--finding", help="单个 finding markdown 文件")
    parser.add_argument("--findings-dir", help="finding 目录；会遍历目录下全部 .md 文件执行全量审查")
    parser.add_argument("--review-file", help="待审核文件，支持 doc/docx/md/txt；优先直接传原始待审核文件")
    parser.add_argument("--numbered-text", help="兼容旧参数，等同于 --review-file")
    parser.add_argument("--full-risk-scan", help="可选，对账用 full-risk-scan 文件；不属于最小验证输入")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", ""), help="OpenAI 兼容接口地址，例如 http://host:port/v1")
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""), help="接口密钥，建议通过环境变量传入")
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", ""), help="模型名")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--context-before", type=int, default=5)
    parser.add_argument("--context-after", type=int, default=6)
    parser.add_argument("--max-windows", type=int, default=5)
    parser.add_argument("--max-excerpt-chars", type=int, default=8000)
    parser.add_argument("--parallelism", type=int, default=DEFAULT_PARALLELISM, help="全量目录模式下的并发数，默认按机器自动设置，建议 2-4")
    parser.add_argument("--resume", action="store_true", help="全量目录模式下跳过已存在结果文件的 finding")
    parser.add_argument("--output", help="可选，单项输出文件；传 .md 时输出 Markdown，传 .json 时输出 JSON")
    parser.add_argument("--output-dir", help="全量目录模式下的输出目录；每个 finding 生成 1 个 Markdown，并输出 summary/progress/full-risk-scan-style 文件")
    return parser


def main() -> int:
    args = arg_parser().parse_args()
    if not args.base_url or not args.api_key or not args.model:
        print("缺少 --base-url / --api-key / --model，或对应环境变量未设置。", file=sys.stderr)
        return 2

    if bool(args.finding) == bool(args.findings_dir):
        print("`--finding` 与 `--findings-dir` 必须二选一。", file=sys.stderr)
        return 2

    review_file_arg = args.review_file or args.numbered_text
    if not review_file_arg:
        print("缺少 --review-file；旧参数 --numbered-text 也可兼容使用。", file=sys.stderr)
        return 2

    review_path = Path(review_file_arg)
    full_risk_scan_path = Path(args.full_risk_scan) if args.full_risk_scan else None
    common_kwargs = {
        "review_path": review_path,
        "full_risk_scan_path": full_risk_scan_path,
        "full_risk_scan_text": None,
        "review_text": None,
        "review_file_extract_method": None,
        "base_url": args.base_url,
        "api_key": args.api_key,
        "model": args.model,
        "temperature": args.temperature,
        "timeout_seconds": args.timeout_seconds,
        "context_before": args.context_before,
        "context_after": args.context_after,
        "max_windows": args.max_windows,
        "max_excerpt_chars": args.max_excerpt_chars,
    }

    if args.finding:
        if args.output:
            try:
                validate_output_dir_policy(Path(args.output))
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        finding_payload = load_finding_payload(Path(args.finding))
        if full_risk_scan_path:
            common_kwargs["full_risk_scan_text"] = read_text(full_risk_scan_path)
        report = validate_single_finding(
            finding_path=Path(args.finding),
            finding_title=str(finding_payload["title"]),
            sop_text=str(finding_payload["sop_text"]),
            **common_kwargs,
        )
        dump_report(report, Path(args.output) if args.output else None)
        return 0

    findings_dir = Path(args.findings_dir)
    if not findings_dir.is_dir():
        print(f"`--findings-dir` 不是目录：{findings_dir}", file=sys.stderr)
        return 2
    if args.output:
        print("使用 `--findings-dir` 时不应再传 `--output`；请改用 `--output-dir`。", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir) if args.output_dir else default_batch_output_dir(review_path)
    try:
        validate_output_dir_policy(output_dir)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.parallelism < 1:
        print("`--parallelism` 不能小于 1。", file=sys.stderr)
        return 2
    finding_paths = sorted(findings_dir.glob("*.md"))
    if not finding_paths:
        print(f"`--findings-dir` 下没有找到 .md 文件：{findings_dir}", file=sys.stderr)
        return 2

    review_text, review_file_extract_method = load_review_file_text(review_path)
    common_kwargs["review_text"] = review_text
    common_kwargs["review_file_extract_method"] = review_file_extract_method
    if full_risk_scan_path:
        common_kwargs["full_risk_scan_text"] = read_text(full_risk_scan_path)

    finding_catalog = [load_finding_payload(path) for path in finding_paths]

    summary: dict[str, Any] = {
        "run_id": sanitize_stem(output_dir.name),
        "review_file": to_relative_path(review_path),
        "review_file_extract_method": review_file_extract_method,
        "findings_dir": to_relative_path(findings_dir),
        "output_dir": to_relative_path(output_dir),
        "model": args.model,
        "base_url": args.base_url,
        "total_findings": len(finding_paths),
        "completed": 0,
        "parallelism": args.parallelism,
        "resume": args.resume,
        "results": [],
        "timing": {
            "started_at": now_text(),
        },
    }
    progress_path = output_dir / "progress.json"
    summary_path = output_dir / "summary.json"
    summary_md_path = output_dir / "summary.md"
    full_report_path = output_dir / "full-risk-scan-style.md"
    tasks: list[dict[str, Any]] = []
    for index, payload in enumerate(finding_catalog, start=1):
        finding_path = Path(payload["path"])
        finding_title = str(payload["title"])
        output_path = output_dir / f"{slugify_filename(finding_title)}.md"
        item: dict[str, Any] = {
            "finding": to_relative_path(finding_path),
            "finding_title": finding_title,
            "sop_text": payload["sop_text"],
            "output": to_relative_path(output_path),
            "index": index,
            "total": len(finding_paths),
        }
        if args.resume and output_path.exists():
            try:
                existing = read_report_file(output_path)
                if not isinstance(existing, dict):
                    raise RuntimeError("结果文件不是可解析的报告格式")
                if isinstance(existing, dict):
                    if "finding" in existing:
                        existing["finding"] = to_relative_path(existing.get("finding"))
                    if "review_file" in existing:
                        existing["review_file"] = to_relative_path(existing.get("review_file"))
                    if "full_risk_scan" in existing:
                        existing["full_risk_scan"] = to_relative_path(existing.get("full_risk_scan"))
                    existing.setdefault(
                        "timing",
                        {
                            "started_at": None,
                            "finished_at": None,
                            "duration_seconds": None,
                        },
                    )
                item["status"] = "skipped"
                item["verdict"] = existing.get("model_result", {}).get("verdict", "未知")
                item["summary"] = existing.get("model_result", {}).get("summary", "")
                item["timing"] = existing.get("timing")
                summary["completed"] += 1
            except Exception as exc:
                item["status"] = "error"
                item["error"] = f"读取已存在结果失败：{exc}"
            summary["results"].append(item)
            print(json.dumps({"status": "skip", **item}, ensure_ascii=False), flush=True)
            continue
        tasks.append(item)

    total_pending = len(tasks)
    started = 0
    finished = summary["completed"]

    def update_progress(current_finding: str | None, last_finished: str | None, last_status: str | None) -> None:
        write_json(
            progress_path,
            {
                "status": "running" if finished < len(finding_paths) else "finished",
                "started": started,
                "completed": finished,
                "total": len(finding_paths),
                "pending": max(len(finding_paths) - finished, 0),
                "current_finding": current_finding,
                "last_finished": last_finished,
                "last_status": last_status,
                "updated_at": now_text(),
                "run_started_at": summary["timing"]["started_at"],
            },
        )

    def run_task(task: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        task["sop_started_at"] = now_text()
        report = validate_single_finding(
            finding_path=Path(task["finding"]),
            finding_title=str(task["finding_title"]),
            sop_text=str(task["sop_text"]),
            **common_kwargs,
        )
        return task, report, None

    update_progress(None, None, None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallelism) as executor:
        future_map: dict[concurrent.futures.Future[tuple[dict[str, Any], dict[str, Any] | None, str | None]], dict[str, Any]] = {}
        for task in tasks:
            started += 1
            print(
                json.dumps(
                    {
                        "status": "start",
                        "index": task["index"],
                        "total": task["total"],
                        "started": started,
                        "pending_tasks": total_pending,
                        "finding_title": task["finding_title"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            future = executor.submit(run_task, task)
            future_map[future] = task
            update_progress(task["finding_title"], None, None)

        for future in concurrent.futures.as_completed(future_map):
            task = future_map[future]
            item = dict(task)
            try:
                _, report, error = future.result()
                if error:
                    raise RuntimeError(error)
                item["status"] = "ok"
                item["verdict"] = report.get("model_result", {}).get("verdict", "未知") if report else "未知"
                item["summary"] = report.get("model_result", {}).get("summary", "") if report else ""
                item["timing"] = report.get("timing") if report else None
                finished += 1
                summary["completed"] += 1
                current_path = output_dir / Path(str(item["output"])).name
                previous_path = None
                next_path = None
                current_index = int(item.get("index", 0))
                if current_index > 1:
                    previous_title = str(finding_catalog[current_index - 2]["title"])
                    previous_path = output_dir / f"{slugify_filename(previous_title)}.md"
                if current_index < len(finding_paths):
                    next_title = str(finding_catalog[current_index]["title"])
                    next_path = output_dir / f"{slugify_filename(next_title)}.md"
                current_path.write_text(
                    render_report_markdown(
                        report,
                        current_path=current_path,
                        summary_path=summary_path,
                        summary_md_path=summary_md_path,
                        full_report_path=full_report_path,
                        previous_path=previous_path,
                        next_path=next_path,
                        run_id=sanitize_stem(review_path.stem),
                    ),
                    encoding="utf-8",
                )
            except Exception as exc:
                item["status"] = "error"
                item["error"] = str(exc)
                item["timing"] = {
                    "started_at": item.get("sop_started_at"),
                    "finished_at": now_text(),
                    "duration_seconds": None,
                }
                finished += 1
            summary["results"].append(item)
            update_progress(None, item["finding_title"], item["status"])
            print(json.dumps(item, ensure_ascii=False), flush=True)

    verdict_counts: dict[str, int] = {}
    error_count = 0
    verdict_buckets: dict[str, list[dict[str, Any]]] = {
        "命中": [],
        "不命中": [],
        "待复核": [],
        "未知": [],
    }
    for item in summary["results"]:
        if item["status"] == "error":
            error_count += 1
            continue
        if item["status"] not in {"ok", "skipped"}:
            continue
        verdict = str(item.get("verdict", "未知"))
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        verdict_buckets.setdefault(verdict, []).append(
            {
                "finding_title": item.get("finding_title"),
                "verdict": verdict,
                "summary": item.get("summary", ""),
                "output": item.get("output"),
                "timing": item.get("timing"),
                "evidences": extract_evidence_from_report_path(output_dir / Path(str(item.get("output"))).name),
            }
        )
    summary["verdict_counts"] = verdict_counts
    summary["error_count"] = error_count
    summary["review_conclusion"] = {
        "命中": verdict_buckets.get("命中", []),
        "不命中": verdict_buckets.get("不命中", []),
        "待复核": verdict_buckets.get("待复核", []),
        "未知": verdict_buckets.get("未知", []),
    }
    summary["timing"]["finished_at"] = now_text()
    conclusion_md = render_full_risk_scan_style_markdown(summary)
    summary["full_risk_scan_style_report"] = {
        "format": "markdown",
        "path": to_relative_path(full_report_path),
    }

    write_json(summary_path, summary)
    summary_md_path.write_text(render_summary_markdown(summary, output_dir), encoding="utf-8")
    full_report_path.write_text(conclusion_md, encoding="utf-8")
    write_json(
        progress_path,
        {
            "status": "finished",
            "current_index": len(finding_paths),
            "total": len(finding_paths),
            "current_finding": None,
            "completed": summary["completed"],
            "error_count": error_count,
            "updated_at": now_text(),
            "run_started_at": summary["timing"]["started_at"],
            "run_finished_at": summary["timing"]["finished_at"],
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
