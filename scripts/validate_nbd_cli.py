#!/usr/bin/env python3
"""验证 NBD 审查点的小模型可执行性。

本脚本是新版 NBD 的专用 CLI：
- preflight：只做候选召回预检，不调用模型。
- run：调用 OpenAI 兼容小模型，对单份待审文件批量执行 NBD。

底层复用 validate_checkpoint_cli.py 的文档抽取、结构化召回和接口调用能力，
但 prompt、输出结构和汇总报告使用 NBD 语义。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import re
import textwrap
import time
from pathlib import Path
from typing import Any

import validate_checkpoint_cli as vcc


WORKSPACE_ROOT = Path.cwd()
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "validation" / "nbd-runs"
DEFAULT_PREFLIGHT_ROOT = WORKSPACE_ROOT / "validation" / "nbd-preflight"
DEFAULT_JOBS = 8
DEFAULT_MAX_TOKENS = 6144
DEFAULT_SUPPORT_CONTEXT_CHARS = 5000


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


def parse_frontmatter(markdown: str) -> dict[str, Any]:
    return vcc.parse_frontmatter(markdown)


def nbd_id(markdown: str) -> str:
    value = parse_frontmatter(markdown).get("id")
    return str(value).strip() if value else vcc.extract_checkpoint_id(markdown)


def nbd_title(markdown: str) -> str:
    return vcc.extract_title(markdown)


def nbd_meta(markdown: str) -> dict[str, Any]:
    meta = parse_frontmatter(markdown)
    return {
        "id": str(meta.get("id") or nbd_id(markdown)),
        "title": str(meta.get("title") or nbd_title(markdown)),
        "risk_level": str(meta.get("risk_level") or ""),
        "finding_type": str(meta.get("finding_type") or ""),
        "standard_scope": str(meta.get("standard_scope") or ""),
        "item_scope": str(meta.get("item_scope") or ""),
        "source_material": str(meta.get("source_material") or ""),
        "source_row": str(meta.get("source_row") or ""),
        "status": str(meta.get("status") or ""),
    }


def compact_nbd_text(markdown: str, max_chars: int) -> str:
    return vcc.compact_checkpoint_text(markdown, max_chars)


def source_lines(text: str) -> list[str]:
    return vcc.source_lines(text)


def nbd_support_profiles(meta: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """按 NBD 类型补充全局上下文，避免小模型只看局部关键词窗口。"""
    nbd_id_value = str(meta.get("id") or "")
    title = str(meta.get("title") or "")
    profiles: list[tuple[str, list[str]]] = []

    if nbd_id_value.startswith("NBD04") or "联合体" in title:
        profiles.append(("联合体公告上下文", ["联合体", "接受联合体", "不接受联合体", "允许联合体", "不允许联合体"]))

    if nbd_id_value == "NBD06-001" or "联合体企业合同金额比例" in title:
        profiles.extend(
            [
                ("联合体接受状态上下文", ["接受联合体", "不接受联合体", "允许联合体", "联合体投标", "联合体响应"]),
                ("联合体金额比例上下文", ["合同金额", "合同份额", "承担金额", "承担比例", "成员单位", "牵头单位"]),
            ]
        )

    if nbd_id_value == "NBD06-007" or "收到发票后10个工作日" in title:
        profiles.extend(
            [
                ("付款期限上下文", ["收到发票", "10个工作日", "十个工作日", "付款", "支付", "资金支付", "付款期限"]),
                ("付款条款上下文", ["付款方式", "付款进度", "合同价款支付", "发票", "验收合格"]),
            ]
        )

    if nbd_id_value == "NBD06-010" or "履约验收方案" in title:
        profiles.extend(
            [
                ("履约验收方案上下文", ["履约验收方案", "验收方案", "验收标准", "验收程序", "验收方式", "验收时间", "验收主体"]),
                ("合同验收上下文", ["验收合格", "组织验收", "最终验收", "交付验收", "采购人验收"]),
            ]
        )

    if nbd_id_value.startswith("NBD05") or "中小企业" in title:
        profiles.extend(
            [
                ("项目预算上下文", ["预算金额", "采购预算", "项目预算", "最高限价", "控制价"]),
                ("中小企业政策上下文", ["中小企业", "专门面向", "预留份额", "价格扣除", "小微企业"]),
            ]
        )

    if nbd_id_value == "NBD02-015" or "售后" in title:
        profiles.extend(
            [
                ("售后评分上下文", ["售后服务", "售后服务方案", "服务承诺", "质保", "保修"]),
                ("采购需求上下文", ["采购需求", "技术要求", "服务要求", "商务要求", "需求清单"]),
            ]
        )

    if nbd_id_value.startswith("NBD03") or "证书" in title:
        profiles.extend(
            [
                ("证书评分上下文", ["证书", "认证", "资质", "资格证", "职业资格"]),
                ("采购需求上下文", ["采购需求", "技术要求", "服务要求", "商务要求", "需求清单"]),
            ]
        )

    if nbd_id_value == "NBD06-006" or "分包" in title:
        profiles.extend(
            [
                ("分包上下文", ["分包", "分包意向", "非主体", "非关键性", "分包金额", "分包比例"]),
                ("中小企业政策上下文", ["中小企业", "专门面向", "预留份额", "价格扣除", "小微企业"]),
            ]
        )

    if nbd_id_value == "NBD07-021" or "医疗" in title or "射线" in title:
        profiles.extend(
            [
                ("医疗设备上下文", ["医疗器械", "医疗设备", "注册证", "备案凭证", "辐射安全许可证", "射线"]),
                ("货物清单上下文", ["货物清单", "设备清单", "采购清单", "技术参数", "配置清单"]),
            ]
        )

    # 去重，保留顺序。
    seen: set[str] = set()
    result: list[tuple[str, list[str]]] = []
    for name, words in profiles:
        key = name + "\0" + "\0".join(words)
        if key not in seen:
            result.append((name, words))
            seen.add(key)
    return result


def collect_keyword_context(
    lines: list[str],
    title: str,
    keywords: list[str],
    *,
    context_before: int = 3,
    context_after: int = 8,
    max_windows: int = 3,
    max_line_chars: int = 900,
) -> str:
    ranges: list[tuple[int, int]] = []
    for idx, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line)
        if any(word and word in compact for word in keywords):
            ranges.append((max(0, idx - context_before), min(len(lines), idx + context_after + 1)))

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        if not merged or start > merged[-1][1] + 2:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    chunks: list[str] = []
    for window_no, (start, end) in enumerate(merged[:max_windows], start=1):
        chunk_lines = []
        for line_no in range(start + 1, end + 1):
            line = lines[line_no - 1]
            if len(line) > max_line_chars:
                line = line[:max_line_chars] + "……[本行已截断]"
            chunk_lines.append(f"{line_no:04d}: {line}")
        chunks.append(f"[{title} {window_no}]\n" + "\n".join(chunk_lines))
    return "\n\n".join(chunks)


def collect_nbd_support_context(
    meta: dict[str, Any],
    review_text: str,
    max_chars: int,
) -> tuple[str, dict[str, Any]]:
    if max_chars <= 0:
        return "", {"enabled": False, "profiles": []}
    lines = source_lines(review_text)
    profile_outputs: list[str] = []
    profile_stats: list[dict[str, Any]] = []
    for profile_name, keywords in nbd_support_profiles(meta):
        text = collect_keyword_context(lines, profile_name, keywords)
        if not text:
            profile_stats.append({"profile": profile_name, "keywords": keywords, "matched": False})
            continue
        profile_outputs.append(text)
        profile_stats.append({"profile": profile_name, "keywords": keywords, "matched": True})

    if not profile_outputs:
        return "", {"enabled": True, "profiles": profile_stats, "chars": 0}

    text = (
        "[NBD支持上下文]\n"
        "以下内容不是独立风险证据，只用于补足预算、公告、采购需求、品目属性、货物清单等全局信息；"
        "最终命中仍必须回到 NBD 命中条件和正式约束条款。\n\n"
        + "\n\n".join(profile_outputs)
    )
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[NBD支持上下文已截断]"
    return text, {"enabled": True, "profiles": profile_stats, "chars": len(text)}


def build_nbd_messages(
    meta: dict[str, Any],
    nbd_text: str,
    review_name: str,
    review_excerpt: str,
) -> list[dict[str, str]]:
    system = (
        "/no_think\n"
        "你是政府采购文件合规审查小模型。"
        "你只能根据给定的 NBD 标准检查点说明书和待审文件候选窗口进行审查。"
        "NBD 是标准 BD 检查点说明书，不是普通知识页。"
        "你必须按 NBD 的定位与召回剖面、候选召回规则、上下文读取规则、命中条件、排除条件和判断结果分流执行。"
        "你不能发明未出现在候选窗口中的证据，不能只因关键词命中就输出命中。"
        "不要输出思考过程，不要输出解释性前言，输出必须是严格 JSON。"
    )
    user = textwrap.dedent(
        f"""
        目标 NBD：{meta['id']} {meta['title']}
        风险等级：{meta.get('risk_level', '')}
        输出性质：{meta.get('finding_type', '')}
        适用边界：{meta.get('standard_scope', '')}
        待审文件：{review_name}

        执行要求：
        1. 只能根据下方 NBD 标准检查点说明书和候选窗口审查。
        2. 必须先列出候选条款，再逐条核对基础命中条件、命中条件和排除条件。
        3. 最终结论只能是：命中 / 待人工复核 / 不命中。
        4. 如果候选窗口不足以支撑结论，必须输出待人工复核或不命中，不能强行命中。
        5. 证据摘录必须来自待审文件候选窗口，不得改写原文。
        6. 若 NBD 风险等级为“提醒”，仍按命中/待人工复核/不命中输出，但 result_type 应体现“提醒”或“配置缺失”等性质。
        7. 若候选位于合同模板、投标文件格式、声明函/承诺函格式、示范文本或目录中，且 NBD 排除条件已明确覆盖，应输出不命中；只有无法判断其是否为正式约束条款时，才输出待人工复核。
        8. 输出必须是严格合法 JSON：字符串内部禁止未转义英文双引号，不要输出制表符、异常空白或超长空白。

        输出 JSON 结构：
        {{
          "nbd_id": "{meta['id']}",
          "nbd_title": "{meta['title']}",
          "risk_level": "{meta.get('risk_level', '')}",
          "result_type": "风险|提醒|配置缺失|口径错误|编制建议|其他",
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
              "line_anchor": "行号范围，例如 0123-0128",
              "excerpt": "原文证据摘录",
              "clause_type": "资格条件|评分因素|采购需求|证明材料|履约要求|合同条款|公告信息|模板残留|其他",
              "basic_hit_conditions": {{"A": false, "B": false, "C": false}},
              "triggered_exclusions": [],
              "candidate_verdict": "命中|待人工复核|不命中",
              "reason": "..."
            }}
          ],
          "risk_tip": "可直接展示的风险提示；不适用则为空字符串",
          "revision_suggestion": "可直接展示的修改建议；不适用则为空字符串",
          "legal_basis": ["依据名称或条款；无法确认则为空数组"]
        }}

        【NBD 标准检查点说明书】
        {nbd_text}

        【待审文件候选窗口与支持上下文】
        {review_excerpt}
        """
    ).strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def normalize_nbd_result(result: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    result.setdefault("nbd_id", meta["id"])
    result.setdefault("nbd_title", meta["title"])
    result.setdefault("risk_level", meta.get("risk_level", ""))
    result.setdefault("result_type", meta.get("finding_type", "") or "其他")
    if result.get("verdict") not in {"命中", "待人工复核", "不命中"}:
        result["verdict"] = "待人工复核"
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        result["candidates"] = []
    result["candidate_count"] = len(result["candidates"])
    trace = result.get("execution_trace")
    if not isinstance(trace, dict):
        trace = {}
    for key in [
        "candidate_recall",
        "context_reading",
        "clause_classification",
        "hit_conditions",
        "exclusion_checks",
        "result_branch",
    ]:
        step = trace.get(key)
        if not isinstance(step, dict):
            step = {}
        step.setdefault("status", "已执行")
        step.setdefault("summary", "")
        trace[key] = step
    result["execution_trace"] = trace
    result.setdefault("risk_tip", "")
    result.setdefault("revision_suggestion", "")
    if not isinstance(result.get("legal_basis"), list):
        result["legal_basis"] = []
    return result


def expand_glob(pattern: str) -> list[Path]:
    paths = sorted(Path(p) for p in glob.glob(pattern))
    return [p.resolve() for p in paths if p.is_file()]


def expand_review_files(args: argparse.Namespace) -> list[Path]:
    files: list[Path] = []
    if getattr(args, "review_file", None):
        files.append(args.review_file.resolve())
    if getattr(args, "review_glob", None):
        files.extend(expand_glob(args.review_glob))
    # de-duplicate while preserving order
    seen: set[str] = set()
    result: list[Path] = []
    for path in files:
        key = str(path)
        if key not in seen:
            result.append(path)
            seen.add(key)
    return result


def expand_nbd_files(args: argparse.Namespace) -> list[Path]:
    files: list[Path] = []
    if getattr(args, "nbd", None):
        files.append(args.nbd.resolve())
    if getattr(args, "nbd_glob", None):
        files.extend(expand_glob(args.nbd_glob))
    seen: set[str] = set()
    result: list[Path] = []
    for path in files:
        key = str(path)
        if key not in seen:
            result.append(path)
            seen.add(key)
    return result


def validate_output_dir(path: Path) -> None:
    vcc.validate_output_dir(path)


def recall_for_nbd(
    nbd_path: Path,
    review_variants: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    markdown = read_text(nbd_path)
    meta = nbd_meta(markdown)
    keywords = vcc.parse_keyword_groups(markdown)
    recall = vcc.choose_review_recall(
        review_variants,
        keywords,
        meta["id"],
        meta["title"],
        args,
    )
    support_text, support_stats = collect_nbd_support_context(
        meta,
        str(recall.get("review_text") or ""),
        int(getattr(args, "support_context_chars", DEFAULT_SUPPORT_CONTEXT_CHARS)),
    )
    if support_text:
        excerpt = str(recall.get("review_excerpt") or "")
        if excerpt:
            excerpt = excerpt + "\n\n" + support_text
        else:
            excerpt = support_text
        max_chars = int(args.max_review_excerpt_chars)
        if len(excerpt) > max_chars:
            excerpt = excerpt[:max_chars] + "\n\n[候选窗口与支持上下文已按 max-review-excerpt-chars 截断]"
        recall["review_excerpt"] = excerpt
    recall["nbd_support_context_stats"] = support_stats
    return meta, recall, markdown


def run_preflight(args: argparse.Namespace) -> int:
    nbd_files = expand_nbd_files(args)
    review_files = expand_review_files(args)
    if not nbd_files:
        raise SystemExit("preflight 必须提供 --nbd 或 --nbd-glob。")
    if not review_files:
        raise SystemExit("preflight 必须提供 --review-file 或 --review-glob。")

    output_dir = (args.output_dir or DEFAULT_PREFLIGHT_ROOT / f"nbd-preflight-{run_id()}").resolve()
    validate_output_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    variants_cache: dict[str, dict[str, Any]] = {}
    for review_file in review_files:
        print(f"load review {review_file.name}", flush=True)
        variants_cache[str(review_file)] = vcc.load_review_file_variants(review_file)

    for nbd_path in nbd_files:
        for review_file in review_files:
            try:
                meta, recall, _ = recall_for_nbd(nbd_path, variants_cache[str(review_file)], args)
                stats = recall.get("recall_stats", {})
                excerpt = str(recall.get("review_excerpt", ""))
                rows.append(
                    {
                        "nbd_id": meta["id"],
                        "nbd_title": meta["title"],
                        "risk_level": meta.get("risk_level", ""),
                        "finding_type": meta.get("finding_type", ""),
                        "nbd_file": relative_path(nbd_path),
                        "review_file": str(review_file),
                        "review_name": review_file.name,
                        "channel": recall.get("channel", ""),
                        "fallback_used": bool(recall.get("fallback_used", False)),
                        "window_count": int(recall.get("window_count", 0)),
                        "excerpt_chars": len(excerpt),
                        "raw_hit_count": stats.get("raw_hit_count", 0),
                        "filtered_hit_count": stats.get("filtered_hit_count", 0),
                        "max_score": stats.get("max_score", 0),
                        "selected_scores": stats.get("selected_scores", []),
                        "selected_block_ids": stats.get("selected_block_ids", []),
                        "skip_reason": stats.get("skip_reason", ""),
                        "support_context_stats": recall.get("nbd_support_context_stats", {}),
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "nbd_file": relative_path(nbd_path),
                        "review_file": str(review_file),
                        "review_name": review_file.name,
                        "error": str(exc),
                    }
                )

    output = {
        "created_at": now_text(),
        "nbd_count": len(nbd_files),
        "review_file_count": len(review_files),
        "rows": rows,
    }
    write_text(output_dir / "recall_matrix.json", json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "recall_matrix.md", preflight_markdown(output))
    print(relative_path(output_dir / "recall_matrix.md"))
    return 0


def preflight_markdown(data: dict[str, Any]) -> str:
    rows = data["rows"]
    by_nbd: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_nbd.setdefault(row.get("nbd_id") or row.get("nbd_file", ""), []).append(row)

    lines = [
        "---",
        "id: nbd-preflight-output",
        "title: NBD 召回预检",
        "page_type: nbd-validation-output",
        "status: draft",
        f"last_reviewed: {time.strftime('%Y-%m-%d')}",
        "---",
        "",
        "# NBD 召回预检",
        "",
        f"- 生成时间：{data['created_at']}",
        f"- NBD 数量：{data['nbd_count']}",
        f"- 样本文档数量：{data['review_file_count']}",
        f"- 组合数：{len(rows)}",
        "- 说明：本次只做候选召回预检，不调用小模型。",
        "",
        "## 按 NBD 汇总",
        "| NBD | 标题 | 有候选文档数 | 组合数 | 平均候选数 | 最大候选数 | 备注 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for nbd, items in sorted(by_nbd.items()):
        valid = [r for r in items if not r.get("error")]
        ok = [r for r in valid if int(r.get("window_count") or 0) > 0]
        avg = sum(int(r.get("window_count") or 0) for r in valid) / len(valid) if valid else 0
        mx = max([int(r.get("window_count") or 0) for r in valid] or [0])
        note = "需补关键词" if not ok else ("候选偏多，需查误报" if avg >= 6 else "")
        title = items[0].get("nbd_title", "")
        lines.append(f"| {nbd} | {title} | {len(ok)} | {len(items)} | {avg:.1f} | {mx} | {note} |")

    lines += [
        "",
        "## 明细矩阵",
        "| NBD | 样本文档 | 通道 | 候选数 | raw hits | filtered hits | max score | selected blocks | skip/error |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        if row.get("error"):
            lines.append(
                f"| {row.get('nbd_id', row.get('nbd_file', ''))} | {row['review_name']} | - | 0 | 0 | 0 | 0 | - | {row['error']} |"
            )
            continue
        blocks = "、".join(str(x) for x in row.get("selected_block_ids") or [])
        lines.append(
            f"| {row['nbd_id']} | {row['review_name']} | {row.get('channel', '')} | "
            f"{row.get('window_count', 0)} | {row.get('raw_hit_count', 0)} | "
            f"{row.get('filtered_hit_count', 0)} | {row.get('max_score', 0)} | "
            f"{blocks} | {row.get('skip_reason', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_single_nbd(
    args: argparse.Namespace,
    nbd_path: Path,
    review_file: Path,
    review_variants: dict[str, Any],
    output_dir: Path,
) -> int:
    markdown = read_text(nbd_path)
    meta = nbd_meta(markdown)
    compact_text = compact_nbd_text(markdown, args.max_nbd_chars)
    started_at = now_text()
    print(f"start {started_at} nbd={meta['id']} file={review_file.name}", flush=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        _, recall, _ = recall_for_nbd(nbd_path, review_variants, args)
        review_excerpt = str(recall["review_excerpt"])
        window_count = int(recall["window_count"])
        recall_stats = dict(recall["recall_stats"])
        recall_channel = str(recall.get("channel", "plain"))
        fallback_used = bool(recall.get("fallback_used", False))
        recall_fallback_reason = str(recall.get("recall_fallback_reason", ""))
        extractor = str(recall.get("extractor", ""))

        prompt_file = output_dir / "prompt.md"
        write_text(
            prompt_file,
            "# NBD Prompt Preview\n\n"
            + f"- nbd: {meta['id']} {meta['title']}\n"
            + f"- risk_level: {meta.get('risk_level', '')}\n"
            + f"- finding_type: {meta.get('finding_type', '')}\n"
            + f"- review_file: {relative_path(review_file)}\n"
            + f"- recall_channel: {recall_channel}\n"
            + f"- fallback_used: {fallback_used}\n"
            + f"- candidate_windows: {window_count}\n\n"
            + f"- nbd_chars: {len(compact_text)}\n"
            + f"- review_excerpt_chars: {len(review_excerpt)}\n\n"
            + f"- recall_stats: {json.dumps(recall_stats, ensure_ascii=False)}\n\n"
            + f"- nbd_support_context_stats: {json.dumps(recall.get('nbd_support_context_stats', {}), ensure_ascii=False)}\n\n"
            + (
                f"- recall_fallback_reason: {recall_fallback_reason}\n\n"
                if recall_fallback_reason
                else ""
            )
            + "## NBD 标准检查点说明书\n\n"
            + compact_text
            + "\n\n## 候选窗口\n\n"
            + (review_excerpt or "无有效候选窗口。")
            + "\n",
        )

        messages = build_nbd_messages(meta, compact_text, review_file.name, review_excerpt or "无有效候选窗口。")
        raw_response_file = output_dir / "raw-response.json"
        if args.reuse_raw_response and raw_response_file.exists():
            response = json.loads(read_text(raw_response_file))
            model_name = str(response.get("model") or args.model or os.environ.get(vcc.ENV_MODEL) or "raw-response")
            print(f"reuse raw-response {relative_path(raw_response_file)}", flush=True)
        else:
            vcc.resolve_llm_config(args)
            response = vcc.post_openai_compatible(
                args.base_url,
                args.api_key,
                args.model,
                messages,
                args.temperature,
                args.timeout,
                args.max_tokens,
            )
            model_name = str(args.model)
            write_text(raw_response_file, json.dumps(response, ensure_ascii=False, indent=2) + "\n")

        model_result = normalize_nbd_result(vcc.parse_model_json(response), meta)
        ended_at = now_text()
        report = {
            "started_at": started_at,
            "ended_at": ended_at,
            "model": model_name,
            "nbd": meta,
            "nbd_path": relative_path(nbd_path),
            "review_file": relative_path(review_file),
            "text_extractor": extractor,
            "recall_channel": recall_channel,
            "fallback_used": fallback_used,
            "recall_fallback_reason": recall_fallback_reason,
            "candidate_window_count": window_count,
            "recall_stats": recall_stats,
            "nbd_support_context_stats": recall.get("nbd_support_context_stats", {}),
            "recall_config": recall.get("recall_config", {}),
            "structured_stats": recall.get("structured_stats", {}),
            "prompt_file": relative_path(prompt_file),
            "raw_response_file": relative_path(raw_response_file),
            "model_result": model_result,
        }
        report_file = output_dir / f"{meta['id']}-{slugify_filename(meta['title'])}.md"
        report["report_file"] = relative_path(report_file)
        write_text(report_file, nbd_report_markdown(report))
        write_text(output_dir / "summary.md", nbd_summary_markdown(report))
        write_text(output_dir / "result.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"ok {ended_at} verdict={model_result.get('verdict')} output={relative_path(report_file)}", flush=True)
        return 0
    except Exception as exc:
        ended_at = now_text()
        error_report = {
            "started_at": started_at,
            "ended_at": ended_at,
            "nbd": meta,
            "nbd_path": relative_path(nbd_path),
            "review_file": relative_path(review_file),
            "error": str(exc),
        }
        write_text(output_dir / "error.json", json.dumps(error_report, ensure_ascii=False, indent=2) + "\n")
        print(f"error {ended_at} nbd={meta['id']} error={exc}", flush=True)
        return 1


def nbd_report_markdown(report: dict[str, Any]) -> str:
    meta = report["nbd"]
    result = report["model_result"]
    candidates = result.get("candidates", [])
    lines = [
        f"# {meta['id']} {meta['title']} NBD 验证报告",
        "",
        "## 元信息",
        f"- 模型：{report['model']}",
        f"- 待审文件：{Path(report['review_file']).name}",
        f"- NBD 文件：{report['nbd_path']}",
        f"- 风险等级：{meta.get('risk_level', '')}",
        f"- 输出性质：{meta.get('finding_type', '')}",
        f"- 适用边界：{meta.get('standard_scope', '')}",
        f"- 召回通道：{report.get('recall_channel', '')}",
        f"- 候选窗口数：{report.get('candidate_window_count', 0)}",
        f"- 召回统计：`{json.dumps(report.get('recall_stats', {}), ensure_ascii=False)}`",
        "",
        "## 结论",
        f"- 结果：{result.get('verdict', '待人工复核')}",
        f"- 结果类型：{result.get('result_type', '')}",
        f"- 摘要：{result.get('summary', '')}",
        f"- 风险提示：{result.get('risk_tip', '')}",
        f"- 修改建议：{result.get('revision_suggestion', '')}",
        "",
        "## 候选条款",
    ]
    if not candidates:
        lines.append("- 无。")
    for idx, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"### 候选 {idx}",
                f"- 行号：{candidate.get('line_anchor', '')}",
                f"- 类型：{candidate.get('clause_type', '')}",
                f"- 结论：{candidate.get('candidate_verdict', '')}",
                f"- 理由：{candidate.get('reason', '')}",
                "",
                "```text",
                str(candidate.get("excerpt", "")),
                "```",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def nbd_summary_markdown(report: dict[str, Any]) -> str:
    meta = report["nbd"]
    result = report["model_result"]
    return "\n".join(
        [
            f"# {meta['id']} {meta['title']} 摘要",
            "",
            f"- 待审文件：{Path(report['review_file']).name}",
            f"- 结果：{result.get('verdict', '待人工复核')}",
            f"- 结果类型：{result.get('result_type', '')}",
            f"- 摘要：{result.get('summary', '')}",
            f"- 召回通道：{report.get('recall_channel', '')}",
            f"- 候选窗口数：{report.get('candidate_window_count', 0)}",
            f"- 报告：[[{Path(report['report_file']).name}]]",
            "",
        ]
    )


def write_run_index(batch_dir: Path) -> tuple[Path, Path]:
    results = sorted(batch_dir.glob("*/result.json"))
    rows = [json.loads(read_text(path)) for path in results]
    data_file = batch_dir / "nbd-results.json"
    write_text(data_file, json.dumps(rows, ensure_ascii=False, indent=2) + "\n")

    lines = [
        "# NBD 批量验证汇总",
        "",
        f"- 批次目录：`{relative_path(batch_dir)}`",
        f"- 结果数量：{len(rows)}",
        "",
        "| NBD | 标题 | 结果 | 类型 | 候选数 | 摘要 |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        meta = row["nbd"]
        result = row["model_result"]
        lines.append(
            f"| {meta['id']} | {meta['title']} | {result.get('verdict', '')} | "
            f"{result.get('result_type', '')} | {row.get('candidate_window_count', 0)} | "
            f"{str(result.get('summary', '')).replace('|', '/')} |"
        )
    report_file = batch_dir / "nbd-batch-report.md"
    write_text(report_file, "\n".join(lines) + "\n")
    return report_file, data_file


def run_model_validation(args: argparse.Namespace) -> int:
    nbd_files = expand_nbd_files(args)
    if not nbd_files:
        raise SystemExit("run 必须提供 --nbd 或 --nbd-glob。")
    if not args.review_file:
        raise SystemExit("run 必须提供 --review-file。")
    review_file = args.review_file.resolve()
    batch_dir = (args.output_dir or DEFAULT_OUTPUT_ROOT / f"nbd-run-{run_id()}").resolve()
    validate_output_dir(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)

    review_variants = vcc.load_review_file_variants(review_file)
    jobs = max(1, int(args.jobs or 1))
    failures = 0

    def run_one(nbd_path: Path) -> int:
        markdown = read_text(nbd_path)
        meta = nbd_meta(markdown)
        out = batch_dir / meta["id"]
        if args.resume and (out / "result.json").exists():
            print(f"skip existing {meta['id']}", flush=True)
            return 0
        return run_single_nbd(args, nbd_path, review_file, review_variants, out)

    if jobs == 1:
        for nbd_path in nbd_files:
            failures += 1 if run_one(nbd_path) else 0
    else:
        print(f"nbd run parallel jobs={jobs}", flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(run_one, path): path for path in nbd_files}
            for future in concurrent.futures.as_completed(future_map):
                try:
                    status = future.result()
                except Exception as exc:
                    print(f"error {future_map[future]} {exc}", flush=True)
                    status = 1
                if status != 0:
                    failures += 1

    if failures != len(nbd_files):
        report_file, data_file = write_run_index(batch_dir)
        print(f"nbd report ok output={relative_path(report_file)} data={relative_path(data_file)}", flush=True)
    print(f"nbd run done output={relative_path(batch_dir)} failures={failures}", flush=True)
    return 1 if failures else 0


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--nbd", type=Path, help="单个 NBD md 文件路径")
    parser.add_argument("--nbd-glob", help="NBD 文件 glob，例如 'wiki/bd-review-points/items/NBD*.md'")
    parser.add_argument("--context-before", type=int, default=5)
    parser.add_argument("--context-after", type=int, default=10)
    parser.add_argument("--max-windows", type=int, default=12)
    parser.add_argument("--max-line-chars", type=int, default=900)
    parser.add_argument("--max-review-excerpt-chars", type=int, default=12000)
    parser.add_argument("--min-candidate-score", type=int, default=vcc.DEFAULT_MIN_CANDIDATE_SCORE)
    parser.add_argument("--support-context-chars", type=int, default=DEFAULT_SUPPORT_CONTEXT_CHARS)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NBD 小模型验证 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="只做候选召回预检，不调用模型")
    add_common_args(preflight)
    preflight.add_argument("--review-file", type=Path)
    preflight.add_argument("--review-glob")
    preflight.add_argument("--output-dir", type=Path)
    preflight.set_defaults(func=run_preflight)

    run = sub.add_parser("run", help="调用小模型执行 NBD")
    add_common_args(run)
    run.add_argument("--review-file", type=Path, required=True)
    run.add_argument("--output-dir", type=Path)
    run.add_argument("--base-url", help=f"OpenAI 兼容接口 base_url；也可用环境变量 {vcc.ENV_BASE_URL}")
    run.add_argument("--api-key", help=f"OpenAI 兼容接口密钥；也可用环境变量 {vcc.ENV_API_KEY}")
    run.add_argument("--model", help=f"模型名称；也可用环境变量 {vcc.ENV_MODEL}")
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    run.add_argument("--max-nbd-chars", type=int, default=18000)
    run.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    run.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--reuse-raw-response", action=argparse.BooleanOptionalAction, default=True)
    run.set_defaults(func=run_model_validation)
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
