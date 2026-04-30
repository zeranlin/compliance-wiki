"""Render NBD runtime artifacts and business-readable reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from postprocessor import (
    best_group_evidence,
    business_family_label,
    clean_inline,
    first_text,
    group_business_rows,
    has_blocking_quality_flag,
    issue_status,
    issue_title,
    issue_types,
    model_quality_flags,
    risk_level,
    row_quality_flags,
)
from recall_runner import write_recall_matrix
from utils import now_text, read_text, relative_path, write_text


def write_report_artifacts(output_dir: Path, results: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if results is None:
        results = [json.loads(read_text(path)) for path in sorted((output_dir / "items").glob("*/result.json"))]
    for row in results:
        flags = model_quality_flags(row)
        row["quality_flags"] = flags
        if isinstance(row.get("model_result"), dict):
            row["model_result"]["quality_flags"] = flags
    results.sort(key=lambda row: str(row.get("nbd", {}).get("id", "")))
    write_text(output_dir / "nbd-results.json", json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    recall_rows = [
        {
            "nbd_id": row.get("nbd", {}).get("id"),
            "title": row.get("nbd", {}).get("title"),
            "candidate_file": row.get("candidate_file", ""),
            "candidate_count": row.get("candidate_window_count", 0),
            "recall_stats": row.get("recall_stats", {}),
            "windows": row.get("windows", []),
        }
        for row in results
    ]
    write_recall_matrix(output_dir, recall_rows)
    write_business_report(output_dir, results)
    return results


def _markdown_cell(text: Any, limit: int = 180) -> str:
    return clean_inline(text, limit).replace("|", "\\|")


def _report_review_file(results: list[dict[str, Any]]) -> str:
    for row in results:
        review_file = row.get("review_file")
        if review_file:
            return Path(str(review_file)).name
    return "待审文件"


def _report_started_at(results: list[dict[str, Any]]) -> str:
    values = [str(row.get("started_at", "")) for row in results if row.get("started_at")]
    return min(values) if values else ""


def _report_ended_at(results: list[dict[str, Any]]) -> str:
    values = [str(row.get("ended_at", "")) for row in results if row.get("ended_at")]
    return max(values) if values else ""


def _report_model(results: list[dict[str, Any]]) -> str:
    return first_text([str(row.get("model", "")) for row in results])


def _run_nbd_count(output_dir: Path, results: list[dict[str, Any]]) -> int:
    run_file = output_dir / "run.json"
    if run_file.exists():
        try:
            payload = json.loads(read_text(run_file))
            value = int(payload.get("nbd_count") or 0)
            if value > 0:
                return value
        except Exception:
            pass
    return len(results)


def _verdict_count(results: list[dict[str, Any]], verdict: str) -> int:
    return sum(1 for row in results if row.get("model_result", {}).get("verdict") == verdict)


def _quality_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in results if row_quality_flags(row)]


def _quality_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in results:
        for flag in row_quality_flags(row):
            code = str(flag.get("code") or "unknown")
            counts[code] = counts.get(code, 0) + 1
    return counts


def _render_checkpoint_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = ["| NBD | 结论 | 说明 |", "|---|---|---|"]
    for row in rows:
        meta = row.get("nbd", {}) or {}
        result = row.get("model_result", {}) or {}
        lines.append(
            "| "
            + _markdown_cell(f"{meta.get('id', '')} {meta.get('title', '')}", 90)
            + " | "
            + _markdown_cell(result.get("verdict", ""), 20)
            + " | "
            + _markdown_cell(result.get("summary", ""), 260)
            + " |"
        )
    return lines


def _render_issue(idx: int, group: dict[str, Any], heading: str) -> list[str]:
    rows = group["rows"]
    evidence = best_group_evidence(rows)
    family_label = business_family_label(rows[0], evidence) if rows else "其他"
    status = issue_status(rows)
    title = issue_title(rows, group["family"])
    summaries = [clean_inline(row.get("model_result", {}).get("summary"), 220) for row in rows]
    suggestions = [clean_inline(row.get("model_result", {}).get("revision_suggestion"), 220) for row in rows]
    risk_tips = [clean_inline(row.get("model_result", {}).get("risk_tip"), 220) for row in rows]
    risk_text = "；".join(list(dict.fromkeys([value for value in summaries + risk_tips if value]))[:4])
    suggestion_text = "；".join(list(dict.fromkeys([value for value in suggestions if value]))[:3])
    lines = [
        "",
        f"### {heading} {idx}：{title}",
        "",
        f"- 风险等级：{risk_level(rows)}",
        f"- 问题类型：{issue_types(rows, evidence)}",
        f"- 问题族：{family_label}",
        f"- 证据位置：{evidence.get('line_anchor') or '待人工确认'}",
        f"- 当前状态：{status}",
        "",
        "#### 原文摘录",
        "",
        "```text",
        evidence.get("excerpt") or "未取得可展示原文摘录，需查看候选窗口或原始文件确认。",
        "```",
        "",
        "#### 触发 NBD",
        "",
        *_render_checkpoint_table(rows),
        "",
        "#### 风险说明",
        "",
        risk_text or "需结合采购文件完整上下文、项目实际需求和适用法规进行人工确认。",
    ]
    if suggestion_text:
        lines.extend(["", "#### 修改建议", "", suggestion_text])
    if status == "待人工复核":
        lines.extend(["", "#### 需人工确认事项", "", "- 需结合采购文件完整上下文、项目实际需求、适用法规和正式附件进行人工确认。"])
    return lines


def _render_quality_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["", "本次未发现需要单列复核的模型输出质量异常。"]
    lines = [
        "",
        "| NBD | 模型结论 | 质量标记 | 说明 |",
        "|---|---|---|---|",
    ]
    for row in rows:
        meta = row.get("nbd", {}) or {}
        result = row.get("model_result", {}) or {}
        flags = row_quality_flags(row)
        lines.append(
            "| "
            + _markdown_cell(f"{meta.get('id', '')} {meta.get('title', '')}", 100)
            + " | "
            + _markdown_cell(result.get("verdict", ""), 20)
            + " | "
            + _markdown_cell("、".join(str(flag.get("code") or "") for flag in flags), 80)
            + " | "
            + _markdown_cell("；".join(str(flag.get("message") or "") for flag in flags), 260)
            + " |"
        )
    return lines


def _family_counts(groups: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for group in groups:
        rows = group.get("rows") or []
        evidence = best_group_evidence(rows)
        label = business_family_label(rows[0], evidence) if rows else "其他"
        counts[label] = counts.get(label, 0) + 1
    return counts


def _render_family_counts(groups: list[dict[str, Any]]) -> list[str]:
    counts = _family_counts(groups)
    labels = ["资格条件", "评分规则", "样品检测", "技术参数", "商务合同", "政府采购政策", "其他"]
    return [f"- {label}：{counts.get(label, 0)}" for label in labels if counts.get(label, 0)]


def write_business_report(output_dir: Path, results: list[dict[str, Any]]) -> None:
    # Postprocessor guard: this stage only groups and renders normalized model results.
    # It must not create new hit verdicts or override model_result.verdict.
    hits = [row for row in results if row.get("model_result", {}).get("verdict") == "命中"]
    reviews = [row for row in results if row.get("model_result", {}).get("verdict") == "待人工复核"]
    nbd_total = _run_nbd_count(output_dir, results)
    model_total = len(results)
    failure_total = max(0, nbd_total - model_total)
    miss_total = _verdict_count(results, "不命中")
    hit_total = _verdict_count(results, "命中")
    review_total = _verdict_count(results, "待人工复核")
    quality_rows = _quality_rows(results)
    quality_counts = _quality_counts(results)
    business_rows = [row for row in hits + reviews if not has_blocking_quality_flag(row)]
    actionable_groups = group_business_rows(business_rows)
    issue_groups = [group for group in actionable_groups if issue_status(group["rows"]) == "命中"]
    review_groups = [group for group in actionable_groups if issue_status(group["rows"]) == "待人工复核"]
    review_file = _report_review_file(results)
    generated_at = now_text()
    title = f"{review_file} 业务审查报告"
    lines = [
        "---",
        f"title: {title}",
        "page_type: business-audit-report",
        f"run_dir: {relative_path(output_dir)}",
        f"generated_at: {generated_at}",
        "---",
        "",
        f"# {title}",
        "",
        "## 一、审查结论摘要",
        "",
        "本报告由 AI 审查生成，用于辅助识别政府采购文件中的合规风险。报告结论不替代采购人、采购代理机构、评审专家、法务审核方或监管部门的人工判断。",
        "",
        "- 审查方式：NBD SOP 自动审查",
        f"- 审查模型：{_report_model(results)}",
        f"- 待审文件：{review_file}",
        f"- 开始时间：{_report_started_at(results)}",
        f"- 结束时间：{_report_ended_at(results)}",
        f"- NBD 总数：{nbd_total}",
        f"- 模型结果：{model_total}",
        f"- 失败数：{failure_total}",
        "",
        "### 结果统计",
        "",
        f"- 不命中：{miss_total}",
        f"- 命中：{hit_total}",
        f"- 待人工复核：{review_total}",
        "",
        "### 模型输出质量",
        "",
        f"- 需单列复核的模型输出：{len(quality_rows)}",
        f"- 自相矛盾命中：{quality_counts.get('verdict_contradiction', 0)}",
        f"- 模板/support 单证据命中：{quality_counts.get('template_only_hit', 0)}",
        f"- 缺少 primary 证据命中：{quality_counts.get('primary_window_missing', 0)}",
        f"- 缺少计算过程命中：{quality_counts.get('missing_calculation', 0)}",
        f"- 重复引用同一证据：{quality_counts.get('duplicate_same_evidence', 0)}",
        f"- 评分表结构不确定：{quality_counts.get('scoring_table_structure_uncertain', 0)}",
        "",
        "### 业务聚合",
        "",
        f"- 形成业务风险问题：{len(issue_groups)} 个",
        f"- 待人工复核事项：{len(review_groups)} 个",
        "",
        "### 问题族统计",
        "",
        *_render_family_counts(issue_groups + review_groups),
        "",
        "",
        "## 二、问题明细",
    ]
    if issue_groups:
        for idx, group in enumerate(issue_groups, start=1):
            lines.extend(_render_issue(idx, group, "问题"))
    else:
        lines.extend(["", "本次未形成明确业务风险问题。"])
    lines.extend(["", "", "## 三、待人工复核事项"])
    if review_groups:
        for idx, group in enumerate(review_groups, start=1):
            lines.extend(_render_issue(idx, group, "复核事项"))
    else:
        lines.extend(["", "本次无待人工复核事项。"])
    lines.extend(["", "", "## 四、模型输出质量复核"])
    lines.extend(_render_quality_table(quality_rows))
    lines.extend(
        [
            "",
            "",
            "## 五、AI审查特别提醒说明",
            "",
            "- 本报告只展示模型基于候选窗口识别出的疑似风险，不替代完整人工审查。",
            "- 对“待人工复核”事项，应回到采购文件原文、附件、公告和合同条款核对后再作正式结论。",
            "- 若同一段原文触发多个 NBD，本报告会合并展示为同一业务问题，便于定位修改位置。",
            "- 对正式对外结论，应结合项目品目、采购方式、预算金额、地域口径和最新监管要求进行确认。",
        ]
    )
    content = "\n".join(lines) + "\n"
    write_text(output_dir / "业务审查报告.md", content)
    write_text(output_dir / "business-report.md", content)
