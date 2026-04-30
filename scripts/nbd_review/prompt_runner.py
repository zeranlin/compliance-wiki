"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas import CandidateWindow, NBDItem
from document_compiler import fact_summary_markdown
from recall_runner import load_candidate_set
from utils import read_text, run_path, write_text

def render_windows(windows: list[CandidateWindow]) -> str:
    if not windows:
        return "无有效候选窗口。"
    chunks: list[str] = []
    for window in windows:
        completeness_lines = [f"- {key}: {'yes' if value else 'no'}" for key, value in window.completeness.items()]
        chunks.append(
            "\n".join(
                [
                    f"[候选窗口 {window.window_id}]",
                    f"window_type: {window.window_type}",
                    f"section_role: {window.section_role}",
                    f"section_role_confidence: {window.section_role_confidence}",
                    "section_path: " + (" > ".join(window.section_path) if window.section_path else ""),
                    f"line_anchor: {window.line_anchor}",
                    f"score: {window.score}",
                    "recall_reason: " + "；".join(window.recall_reason),
                    f"recall_quality: {window.recall_quality}",
                    "table_scoring: " + json.dumps((window.source or {}).get("table_scoring") or [], ensure_ascii=False),
                    "completeness:",
                    *completeness_lines,
                    "",
                    "原文：",
                    window.text,
                ]
            )
        )
    return "\n\n".join(chunks)


def numeric_review_instruction(item: NBDItem) -> str:
    text = f"{item.nbd_id} {item.title} {item.compact_text[:3000]}"
    if not any(word in text for word in ["权重", "总和", "分值", "比例", "金额", "期限", "数量", "超过", "不得低于", "不得超过"]):
        return ""
    return (
        "本 NBD 涉及数值、权重、金额、比例、期限或数量判断。"
        "必须在 execution_trace.hit_conditions.summary 或 result_branch.reason 中写出计算过程：抽取项、算式、计算结果、阈值或标准值。"
        "如果候选窗口表格层级不清、表头/权重列/评分项列缺失、或无法确认哪些数字应参与求和，不得只凭单个数字输出命中；应输出待人工复核并说明“表格层级不清/计算口径不确定”。"
    )


def build_messages(item: NBDItem, review_name: str, facts: dict[str, Any], windows: list[CandidateWindow], max_prompt_chars: int) -> list[dict[str, str]]:
    system = (
        "/no_think\n"
        "你是政府采购文件 NBD 小模型审查员。"
        "你只能根据 NBD 可执行 SOP 和候选窗口判断风险。"
        "业务判断、命中条件、排除条件必须来自 NBD 可执行 SOP，不得根据本模板自行新增规则。"
        "轻事实摘要只能用于排除明显不适用，不能单独构成命中证据。"
        "不得把目录、通用条款、合同模板、投标文件格式直接当作正式风险证据。"
        "同一 NBD 出现多个 primary 候选窗口且内容存在允许/禁止、需要/不需要、已设置/未设置等冲突时，必须逐一比对后再给结论，并在 execution_trace.context_reading.summary 中说明冲突窗口。"
        "候选窗口的 completeness 若存在 no 项，不能直接输出确定命中；应说明缺失要素，必要时输出待人工复核。"
        "候选窗口 source.table_scoring 或轻事实摘要中出现 structure_warnings 时，必须把它当作计算口径不确定信号处理。"
        "如果排除条件已触发，或你的摘要/理由说明已经明确写出“已明确、已满足、已载明、不构成风险、符合要求、不属于风险”，verdict 必须为不命中，不能输出命中。"
        "如果候选窗口只有模板、格式、目录、通用条款等 support 证据，不能输出命中；证据不足时输出待人工复核或不命中。"
        "最终 verdict 必须与 execution_trace.result_branch.branch、候选 candidate_verdict、summary 的正反语义一致。"
        "输出必须是严格 JSON。"
    )
    user = f"""
目标 NBD：{item.nbd_id} {item.title}
待审文件：{review_name}

输出 JSON 结构：
{{
  "nbd_id": "{item.nbd_id}",
  "nbd_title": "{item.title}",
  "verdict": "命中|待人工复核|不命中",
  "summary": "一句话总结审查结论",
  "candidate_count": 0,
  "execution_trace": {{
    "candidate_recall": {{"status": "已执行", "summary": "..."}},
    "context_reading": {{"status": "已执行", "summary": "..."}},
    "clause_classification": {{"status": "已执行", "summary": "...", "clause_types": []}},
    "hit_conditions": {{"status": "已执行", "A": false, "B": false, "C": false, "summary": "..."}},
    "exclusion_checks": {{"status": "已执行", "triggered": [], "not_triggered": []}},
    "result_branch": {{"status": "已执行", "branch": "命中|待人工复核|不命中", "reason": "..."}}
  }},
  "candidates": [
    {{
      "line_anchor": "行号范围",
      "excerpt": "原文证据摘录",
      "clause_type": "资格条件|评分因素|采购需求|证明材料|履约要求|合同条款|公告信息|模板残留|其他",
      "candidate_verdict": "命中|待人工复核|不命中",
      "reason": "..."
    }}
  ],
  "risk_tip": "",
  "revision_suggestion": "",
  "legal_basis": []
}}

【NBD 可执行 SOP】
{item.compact_text}

【轻事实摘要】
{fact_summary_markdown(facts)}

【数值/表格审查补充要求】
{numeric_review_instruction(item) or "本 NBD 未识别为数值计算型；仍需按 NBD SOP 判断。"}

【候选窗口】
{render_windows(windows)}
""".strip()
    if len(user) > max_prompt_chars:
        user = user[:max_prompt_chars] + "\n[Prompt 已按 max_prompt_chars 截断]"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def prompt_stats(item: NBDItem, messages: list[dict[str, str]], max_prompt_chars: int | None = None) -> dict[str, Any]:
    system_chars = sum(len(message.get("content") or "") for message in messages if message.get("role") == "system")
    user_chars = sum(len(message.get("content") or "") for message in messages if message.get("role") == "user")
    total_chars = sum(len(message.get("content") or "") for message in messages)
    truncated = any("[Prompt 已按 max_prompt_chars 截断]" in str(message.get("content") or "") for message in messages)
    return {
        "nbd_id": item.nbd_id,
        "nbd_title": item.title,
        "prompt_source": "prompt-ir",
        "system_chars": system_chars,
        "user_chars": user_chars,
        "total_chars": total_chars,
        "nbd_sop_chars": len(item.compact_text or ""),
        "max_prompt_chars": max_prompt_chars,
        "truncated": truncated,
    }


def write_prompt_files(output_dir: Path, item: NBDItem, messages: list[dict[str, str]], stats: dict[str, Any]) -> None:
    prompt_file = output_dir / "prompts" / f"{item.nbd_id}.md"
    messages_file = output_dir / "prompts" / f"{item.nbd_id}.json"
    write_text(prompt_file, messages[1]["content"] + "\n")
    write_text(messages_file, json.dumps({"messages": messages, "prompt_stats": stats}, ensure_ascii=False, indent=2) + "\n")


def write_prompt_artifact(output_dir: Path, review_name: str, facts: dict[str, Any], item: NBDItem, args: Any) -> list[dict[str, str]]:
    windows, _ = load_candidate_set(output_dir, item)
    messages = build_messages(item, review_name, facts, windows, args.max_prompt_chars)
    stats = prompt_stats(item, messages, args.max_prompt_chars)
    write_prompt_files(output_dir, item, messages, stats)
    return messages


def write_prompt_artifacts(output_dir: Path, review_name: str, facts: dict[str, Any], items: list[NBDItem], args: Any) -> None:
    stats_records: list[dict[str, Any]] = []
    for item in items:
        messages = write_prompt_artifact(output_dir, review_name, facts, item, args)
        stats_records.append(prompt_stats(item, messages, args.max_prompt_chars))
    if stats_records:
        write_text(output_dir / "prompts" / "prompt-stats.json", json.dumps(prompt_stats_summary(stats_records), ensure_ascii=False, indent=2) + "\n")


def prompt_stats_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    totals = sorted(int(record.get("total_chars") or 0) for record in records)
    system_lengths = sorted(int(record.get("system_chars") or 0) for record in records)
    user_lengths = sorted(int(record.get("user_chars") or 0) for record in records)
    sop_lengths = sorted(int(record.get("nbd_sop_chars") or 0) for record in records)
    return {
        "schema_version": "prompt-stats/v1",
        "prompt_count": len(records),
        "total_chars": _length_summary(totals),
        "system_chars": _length_summary(system_lengths),
        "user_chars": _length_summary(user_lengths),
        "nbd_sop_chars": _length_summary(sop_lengths),
        "truncated_count": sum(1 for record in records if record.get("truncated")),
        "records": records,
    }


def _length_summary(values: list[int]) -> dict[str, Any]:
    if not values:
        return {"min": 0, "avg": 0, "median": 0, "p90": 0, "max": 0}
    return {
        "min": values[0],
        "avg": round(sum(values) / len(values), 1),
        "median": values[len(values) // 2],
        "p90": values[min(len(values) - 1, int(len(values) * 0.9))],
        "max": values[-1],
    }


def read_prompt_messages(output_dir: Path, item: NBDItem) -> list[dict[str, str]]:
    messages_file = output_dir / "prompts" / f"{item.nbd_id}.json"
    if not messages_file.exists():
        raise RuntimeError(f"缺少 Prompt 消息文件：{run_path(output_dir, messages_file)}，请先执行 build-prompt")
    payload = json.loads(read_text(messages_file))
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise RuntimeError(f"Prompt 消息文件格式错误：{run_path(output_dir, messages_file)}")
    return messages
