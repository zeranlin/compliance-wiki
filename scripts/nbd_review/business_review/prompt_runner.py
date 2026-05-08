"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from shared.schemas import CandidateWindow, NBDItem
from business_review.document_compiler import fact_summary_markdown
from business_review.recall_runner import load_candidate_set_payload
from shared.utils import read_text, run_path, write_text

def candidate_count(windows: list[CandidateWindow]) -> int:
    return len(windows)


def decision_protocol_markdown() -> str:
    return "\n".join(
        [
            "必须按以下顺序审查，不能跳步：",
            "1. 逐个读取 primary 候选窗口，记录正式证据、行号、条款类型和候选结论。",
            "2. 对每个候选窗口判断：是否出现 NBD SOP 所描述的审查对象、限制行为、证明材料要求、评分/资格/履约后果。",
            "3. 再判断排除条件：候选是否只是目录、模板、格式、通用示例；是否存在同一 NBD 的反向正式条款；是否缺少 NBD SOP 要求的关键事实。",
            "4. NBD SOP 中的具体命中条件、排除条件例外、不得适用某排除理由等专门规则，优先于通用排除判断。",
            "5. 若至少一个 primary 候选满足命中条件，且排除条件未触发，应输出命中。",
            "6. 若所有候选均为模板、格式、目录、通用条款，且 NBD SOP 并不审查这类文本本身，或正式证据与 NBD SOP 不对应，应输出不命中或待人工复核。",
            "7. 最终 verdict 必须由候选窗口逐项结论汇总得出，不能先给结论再找理由。",
        ]
    )


def review_boundary_markdown() -> str:
    return "\n".join(
        [
            "待人工复核只能用于以下情形：",
            "- primary 候选中有疑似风险，但缺少 NBD SOP 明确要求的关键事实，无法判断适用边界。",
            "- 同一 NBD 的 primary 候选之间存在正式条款冲突，且候选窗口无法消除冲突。",
            "- 数值、金额、比例、权重或期限需要计算，但表格结构或计算口径不清。",
            "- 候选原文语义不完整、被截断，或只能看到支撑上下文，无法确认正式效力。",
            "",
            "不得因为措辞谨慎、模型不确定、或需要人工再次确认就默认输出待人工复核。",
            "如果 primary 候选已经直接呈现 NBD SOP 禁止或要求审查的风险形态，且无排除条件，应输出命中。",
        ]
    )


def hard_decision_markdown() -> str:
    return "\n".join(
        [
            "明确风险判定原则：",
            "- 当 NBD 标题、SOP 或命中条件使用“不得、禁止、不得要求、不得限定、需、应当、必须”等明确义务词时，候选窗口出现对应被禁止或被要求的事实，原则上不得降为待人工复核。",
            "- 当候选窗口同时包含审查对象和限制行为，并且位于 primary 正式章节时，应优先按命中条件判断；只有排除条件成立时才转为不命中或待人工复核。",
            "- 当候选窗口为评分因素、资格条件、采购需求、履约要求、合同付款、证明材料要求等正式条款，且出现 NBD SOP 对应风险事实，应把该窗口作为主证据。",
            "- 当 NBD 标题或 SOP 要求提供证书、报告、证明材料、认证文件等，候选窗口只要求承诺、保证、声明、符合要求，而没有设置对应证明材料的提交要求时，应按“证明材料要求缺失或被承诺替代”判断；除非 NBD SOP 明确允许承诺替代，不应仅因此降为待人工复核。",
            "- 当候选窗口自身使用“若涉及、如涉及、属于、列明、应当”等条件性配置语言，且 NBD 审查目标是该配置是否完整、是否要求提交对应证明材料时，应审查该条件性配置本身是否合规；不得仅因未先确认项目品目一定触发条件就降为待人工复核。",
            "- 当 NBD 审查目标本身是证明材料、承诺函、声明函或格式条款是否合规时，不得因为候选位于承诺函、声明函或响应格式中就自动排除；必须先判断该格式条款是否承载了正式响应义务。",
            "- 当 NBD 审查目标是评分项与需求是否对应、证书是否合理、证明材料是否被承诺替代、服务期限/付款期限/退还方式是否明确时，若 primary 候选已经呈现评分后果或响应义务，而候选窗口及支持上下文未显示对应依据，应按 NBD SOP 的缺失型命中条件判断，不得只说“需人工核对全文”。",
            "- 当候选窗口只是合同模板、投标格式、承诺函空白项、目录或政策引用，不得作为命中主证据。",
            "- NBD SOP 的排除条件、反证条件和“不应输出多条”的候选合并要求优先于上述硬命中原则；一旦候选触发排除条件，或 SOP 要求同一事项只保留代表性候选，不得为了凑齐命中数量继续输出。",
            "- 如果候选同时包含可疑词和明确排除词，应先按 NBD SOP 判断该候选的主审查对象；主审查对象落入排除条件时，该候选不能作为命中 candidate。",
        ]
    )


def atomic_candidate_protocol_markdown() -> str:
    return "\n".join(
        [
            "原子化候选输出协议：",
            "- candidate 是行号级证据单元，不是 NBD 汇总结论。一个 candidate 只能承载一个可独立复核的风险事实。",
            "- 同一候选窗口包含多个可独立复核的审查对象时，必须逐行或逐对象拆分判断。",
            "- 候选窗口的 table_scoring 若列出多个 line_anchor，说明窗口内存在多个独立表格行；正向输出必须优先使用 table_scoring 中的最小行号，而不是直接沿用候选窗口的大范围 line_anchor。",
            "- 当候选窗口 line_anchor 覆盖多行，但 table_scoring 显示每一行都有独立 label、权重或评分准则时，每个满足 NBD SOP 的表格行都应单独输出 candidate。",
            "- 多个风险事实分别满足同一 NBD 命中条件或待复核条件时，应输出多条 candidates；不要把多个行号合并为一条摘要候选。",
            "- line_anchor 应尽量使用该风险事实所在的最小行号或最小连续行号；只有原文确实跨行不可分割时，才使用窗口范围。",
            "- excerpt 只摘录该原子风险事实的关键原文，不要把整段评分表、整组证书或多个条款塞进一个 excerpt。",
            "- 若同一行内列出多个可独立判断的证书、认证、机构、参数或证明材料，并且分别触发同一 NBD，应在同一 line_anchor 下输出多条 candidates。",
            "- 正向候选输出应先覆盖不同证据类型、不同条款位置和不同风险对象，再考虑同类风险内的强弱排序；不得把名额全部用于同一类重复证据。",
            "- primary 候选窗口已经按召回分值、正式性和完整度排序。若排名靠前的 primary 候选满足 NBD 命中条件且未触发排除条件，应优先输出；不得无理由跳过前排候选而输出后排同类候选。",
            "- 当 NBD SOP 使用“代表行、最早、第一条、统领性评分行、具体明细代表行、只输出 1-2 条”等候选选择要求时，必须按 SOP 的选择顺序执行：先从 rank 最小且满足命中条件的 primary 候选中选择；只有前排候选触发排除条件、属于同一风险对象重复项或证据明显弱于后排不同风险对象时，才可跳过。",
            "- 对“代表性候选”不能自由挑选后文同类行替代前文合格候选。若跳过 rank 更靠前或行号更小的同类 primary 候选，summary 或 execution_trace 必须说明跳过原因；不能说明原因时，应输出前排候选。",
            "- 当正向事实超过 8 条时，先按候选窗口 rank 从前到后筛选；只有前排候选属于模板、重复同一风险对象、触发排除条件或证据弱于后排不同风险对象时，才可跳过，并应在 summary 中说明已按代表性选择。",
            "- 如果已有多个正向候选属于同一风险形态、同一设备或相邻重复条款，而其他 primary 候选也满足命中条件，应保留代表性候选，把剩余名额用于其他行号或其他风险形态。",
            "- 对配置缺失、占位符、空白项、引用其他章节但未给出实质内容的风险，应优先输出最能证明缺失或占位的候选行。",
            "- 最多输出 8 条正向 candidates；若正向事实超过 8 条，优先输出证据最强、分值/资格后果最明确、行号最清楚的候选，并在 summary 中说明还有同类风险。",
            "- 不命中候选不需要原子化展开，只保留最关键的 1-3 个排除理由即可。",
        ]
    )


def flatten_focus_terms(hit_words: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    if not isinstance(hit_words, dict):
        return terms
    for values in hit_words.values():
        if isinstance(values, list):
            for value in values:
                term = str(value or "").strip()
                if term and len(term) <= 24 and not any(mark in term for mark in ["{", "}", "(", ")", "|", "\\"]):
                    terms.append(term)
    return sorted(set(terms), key=len, reverse=True)


def focused_compact_window_text(value: str, max_chars: int, focus_terms: list[str]) -> str:
    matches: list[tuple[int, int]] = []
    for term in focus_terms:
        pos = value.find(term)
        if pos >= 0:
            matches.append((pos, len(term)))
    if not matches:
        return value[:max_chars].rstrip() + "\n[候选窗口原文已压缩]"

    budget = max(120, max_chars)
    snippets: list[tuple[int, str]] = []
    used: list[tuple[int, int]] = []
    per_snippet = max(90, budget // min(4, len(matches)))
    selected_positions: list[int] = []
    for pos, _ in sorted(matches, key=lambda item: (-item[1], item[0])):
        if all(abs(pos - selected) > per_snippet // 2 for selected in selected_positions):
            selected_positions.append(pos)
        if len(selected_positions) >= 4:
            break
    for pos in selected_positions:
        start = max(0, pos - per_snippet // 3)
        end = min(len(value), start + per_snippet)
        start = max(0, end - per_snippet)
        if any(not (end <= old_start or start >= old_end) for old_start, old_end in used):
            continue
        used.append((start, end))
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(value) else ""
        snippets.append((start, prefix + value[start:end].strip() + suffix))
        if sum(len(s) for _, s in snippets) >= budget:
            break
    compacted = "\n[命中词附近片段]\n".join(snippet for _, snippet in sorted(snippets))
    if len(compacted) > max_chars:
        compacted = compacted[:max_chars].rstrip()
    return compacted + "\n[候选窗口原文已按命中词附近压缩]"


def render_focus_snippets(text: str, focus_terms: list[str], max_chars: int = 900) -> str:
    value = str(text or "")
    if not value or not focus_terms:
        return "[]"
    snippet_text = focused_compact_window_text(value, max_chars, focus_terms)
    snippets = [part.strip() for part in snippet_text.split("\n[命中词附近片段]\n") if part.strip()]
    cleaned = [
        part.replace("[候选窗口原文已按命中词附近压缩]", "").strip()
        for part in snippets
        if part and not part.startswith("[候选窗口原文")
    ]
    return json.dumps(cleaned[:4], ensure_ascii=False)


def compact_window_text(text: str, max_chars: int, focus_terms: list[str] | None = None) -> str:
    value = str(text or "")
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    focus_terms = focus_terms or []
    if max_chars < 300:
        if focus_terms:
            return focused_compact_window_text(value, max_chars, focus_terms)
        return value[:max_chars].rstrip() + "\n[候选窗口原文已压缩]"
    if focus_terms and not any(term in value[:max_chars] for term in focus_terms):
        return focused_compact_window_text(value, max_chars, focus_terms)
    head_len = int(max_chars * 0.65)
    tail_len = max_chars - head_len
    return value[:head_len].rstrip() + "\n[候选窗口原文中部已压缩]\n" + value[-tail_len:].lstrip()


def window_text_limit(max_prompt_chars: int, window_count: int) -> int:
    if window_count <= 0:
        return 0
    window_budget = max(3200, int(max_prompt_chars * 0.34))
    metadata_reserve = window_count * 460
    text_budget = max(0, window_budget - metadata_reserve)
    if text_budget <= 0:
        return 240
    return max(240, min(1200, text_budget // window_count))


def render_windows(windows: list[CandidateWindow], max_text_chars: int = 0) -> str:
    if not windows:
        return "无有效候选窗口。"
    chunks: list[str] = []
    for window in windows:
        source = window.source or {}
        text = compact_window_text(window.text, max_text_chars, flatten_focus_terms(window.hit_words))
        table_scoring = compact_table_scoring((window.source or {}).get("table_scoring") or [])
        completeness_missing = [key for key, value in window.completeness.items() if not value]
        focus_terms = flatten_focus_terms(window.hit_words)
        chunks.append(
            "\n".join(
                [
                    f"[候选窗口 {window.window_id}]",
                    "meta: "
                    + json.dumps(
                        {
                            "candidate_id": window.window_id,
                            "line_anchor": window.line_anchor,
                            "window_type": window.window_type,
                            "section_role": window.section_role,
                            "rank": source.get("selection_rank", ""),
                            "score": window.score,
                            "quality": window.recall_quality,
                            "missing": completeness_missing,
                        },
                        ensure_ascii=False,
                    ),
                    "section_path: " + (" > ".join(window.section_path) if window.section_path else ""),
                    "recall_reason: " + "；".join(window.recall_reason[:4]),
                    "table_scoring: " + json.dumps(table_scoring, ensure_ascii=False),
                    "focus_snippets: " + render_focus_snippets(window.text, focus_terms),
                    "原文：",
                    text,
                ]
            )
        )
    return "\n\n".join(chunks)


def compact_table_scoring(table_scoring: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for item in table_scoring[:6]:
        if not isinstance(item, dict):
            continue
        analysis = item.get("row_scoring_analysis") or {}
        if not isinstance(analysis, dict):
            analysis = {}
        anomaly = analysis.get("anomaly") if isinstance(analysis.get("anomaly"), dict) else {}
        compacted.append(
            {
                "line_anchor": item.get("line_anchor"),
                "row_number": item.get("row_number"),
                "label": analysis.get("label"),
                "declared_weight": (analysis.get("declared_weight") or {}).get("raw") if isinstance(analysis.get("declared_weight"), dict) else None,
                "max_internal_score": analysis.get("max_internal_score"),
                "anomaly_type": anomaly.get("type") if isinstance(anomaly, dict) else None,
                "structure_warnings": item.get("structure_warnings") or [],
            }
        )
    if len(table_scoring) > len(compacted):
        compacted.append({"omitted_table_scoring_count": len(table_scoring) - len(compacted)})
    return compacted


def numeric_review_instruction(item: NBDItem) -> str:
    text = f"{item.nbd_id} {item.title} {item.compact_text[:3000]}"
    if not any(word in text for word in ["权重", "总和", "分值", "比例", "金额", "期限", "数量", "超过", "不得低于", "不得超过"]):
        return ""
    return (
        "本 NBD 涉及数值、权重、金额、比例、期限或数量判断。"
        "必须在 execution_trace.hit_conditions.summary 或 result_branch.reason 中写出计算过程：抽取项、算式、计算结果、阈值或标准值。"
        "如果候选窗口表格层级不清、表头/权重列/评分项列缺失、或无法确认哪些数字应参与求和，不得只凭单个数字输出命中；应输出待人工复核并说明“表格层级不清/计算口径不确定”。"
        "评分表中常见“权重列为总评折算分值、行内按百分制或子项最高分评分”的结构；若 NBD SOP 的排除条件说明已有每项分值、最高得分或折算口径，不得仅用权重列数值与行内最高分不同判定命中。"
    )


def build_messages(
    item: NBDItem,
    review_name: str,
    facts: dict[str, Any],
    windows: list[CandidateWindow],
    max_prompt_chars: int,
) -> list[dict[str, str]]:
    rendered_windows = render_windows(windows, window_text_limit(max_prompt_chars, len(windows)))
    system = (
        "/no_think\n"
        "你是政府采购文件 NBD 小模型审查员。"
        "你只能根据 NBD 可执行 SOP 和候选窗口判断风险。"
        "业务判断、命中条件、排除条件必须来自 NBD 可执行 SOP，不得根据本模板自行新增规则。"
        "轻事实摘要只能用于排除明显不适用，不能单独构成命中证据。"
        "不得把目录、通用条款、合同模板、投标文件格式直接当作正式风险证据；但若 NBD SOP 明确审查模板残留、空白项、合同条款、格式条款或承诺格式本身，则应按该 NBD SOP 判断。"
        "同一 NBD 出现多个 primary 候选窗口且内容存在允许/禁止、需要/不需要、已设置/未设置等冲突时，必须逐一比对后再给结论，并在 execution_trace.context_reading.summary 中说明冲突窗口。"
        "候选窗口的 completeness 若存在 no 项，应先判断 NBD SOP 的审查目标。"
        "如果 NBD SOP 本身审查的是缺失、未设置、未明确、未提供、未对应、承诺替代证明材料等风险，completeness 的 no 项可能正是命中证据，不得因此自动降为待人工复核。"
        "如果 NBD SOP 需要完整事实才能判断比例、金额、品目、例外或合法必要性，且缺失要素不是风险本身，才应输出待人工复核。"
        "候选窗口 source.table_scoring 或轻事实摘要中出现 structure_warnings 时，必须把它当作计算口径不确定信号处理。"
        "如果排除条件已触发，或你的摘要/理由说明已经明确写出“已明确、已满足、已载明、不构成风险、符合要求、不属于风险”，verdict 必须为不命中，不能输出命中。"
        "如果候选窗口只有模板、格式、目录、通用条款等 support 证据，不能输出命中；证据不足时输出待人工复核或不命中。"
        "如果 primary 候选窗口已经直接满足 NBD SOP 的命中条件，且没有排除条件，不得输出待人工复核。"
        "candidate_count 必须等于实际候选窗口数量。"
        "candidates 只列需要进入审查结果的候选，不要列对比用的不命中候选。"
        "candidates 必须逐项列出所有判定为命中或待人工复核的原子候选，最多 8 项；每个候选必须引用候选窗口中的 candidate_id 和 line_anchor。"
        "不得把理由中已经判定为不命中、不得命中、触发排除、不构成本 NBD 风险、不进入 candidates 的候选继续写成 candidate_verdict=命中。"
        "如果 candidate.reason 或 execution_trace 已说明某候选不满足 SOP、仅为排除示例、仅为对比用候选，必须从 candidates 中删除；最终不命中时才可保留少量不命中候选说明排除理由。"
        "输出 JSON 前必须自检：每一条 candidate_verdict=命中的候选，其 reason 必须正向说明已满足 NBD SOP 命中条件，且 exclusion_triggered 必须为 false。"
        "candidate_verdict=命中的 reason 必须是确定性结论，不能只写“可能、需确认、需要核实、通常、一般、疑似、倾向、风险较低”等推测性依据；如果只能推测，应改为待人工复核或不命中。"
        "若 reason 同时包含正向命中语义和反向排除语义，以反向排除语义为准，不得输出为命中 candidate。"
        "如果 verdict 为命中，candidates 中至少必须有 1 项 candidate_verdict 为命中，且该项必须来自候选窗口原文。"
        "如果 verdict 为待人工复核，candidates 中至少必须有 1 项 candidate_verdict 为待人工复核，且该项必须来自候选窗口原文。"
        "如果最终不命中，只列最关键的 1-3 个不命中候选及理由。"
        "每个 candidate.excerpt 不超过 120 个汉字，candidate.reason 不超过 80 个汉字；长原文只摘录最关键证据。"
        "不得只在 summary 中概括风险而省略 candidates；没有 candidate_id 和 line_anchor 的命中不能作为有效审查结果。"
        "最终 verdict 必须与 execution_trace.result_branch.branch、候选 candidate_verdict、summary 的正反语义一致。"
        "输出必须是严格 JSON。"
        "JSON 字符串内不要使用未转义的英文双引号；需要举例时改用中文引号、括号或直接省略引号，确保整段内容可被 json.loads 解析。"
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
  "candidate_count": {candidate_count(windows)},
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
      "candidate_id": "候选窗口ID，例如 W01",
      "line_anchor": "行号范围",
      "excerpt": "原文证据摘录，不超过120个汉字",
      "clause_type": "资格条件|评分因素|采购需求|证明材料|履约要求|合同条款|公告信息|模板残留|其他",
      "window_type": "primary|support",
      "evidence_strength": "强|中|弱",
      "hit_condition_met": true,
      "exclusion_triggered": false,
      "candidate_verdict": "命中|待人工复核|不命中",
      "reason": "不超过80个汉字"
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

【判定顺序】
{decision_protocol_markdown()}

【待人工复核边界】
{review_boundary_markdown()}

【明确风险判定原则】
{hard_decision_markdown()}

【原子化候选输出协议】
{atomic_candidate_protocol_markdown()}

【候选窗口】
{rendered_windows}
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
    payload = load_candidate_set_payload(output_dir, item)
    windows = [CandidateWindow(**window) for window in payload.get("windows", [])]
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
