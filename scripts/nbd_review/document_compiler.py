"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from schemas import DOCUMENT_IR_SCHEMA, DocumentBlock, STRUCTURE_PATTERNS
from utils import compact, looks_like_heading, normalize_key, read_text, run_path, vcc, write_text

def _number_value(text: str) -> float | None:
    value = str(text or "").strip()
    if not value:
        return None
    cvalue = compact(value)
    if len(cvalue) > 16 or "\n" in value:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(?:\s*%|\s*分)?\s*", value)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _looks_like_weight_header(value: str) -> bool:
    cvalue = compact(value)
    return any(word in cvalue for word in ["权重", "分值", "分数", "满分"])


def table_ir_from_rows(rows: list[list[str]]) -> dict[str, Any]:
    """Build generic table structure for Document IR without applying NBD rules."""
    if not rows:
        return {}
    max_cols = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (max_cols - len(row)) for row in rows]
    header = normalized_rows[0] if normalized_rows else []
    header_key = compact(" ".join(header))
    weight_columns = [idx for idx, cell in enumerate(header) if _looks_like_weight_header(cell)]
    if not weight_columns:
        weight_columns = [
            idx
            for idx in range(max_cols)
            if sum(1 for row in normalized_rows[1:] if idx < len(row) and _number_value(row[idx]) is not None) >= 2
            and any(word in header_key for word in ["评分", "评审", "权重", "分值"])
        ]
    item_columns = [
        idx
        for idx, cell in enumerate(header)
        if any(word in compact(cell) for word in ["评分项", "评审因素", "内容", "名称", "序号"])
    ]
    scoring_rows: list[dict[str, Any]] = []
    for offset, row in enumerate(normalized_rows[1:], start=2):
        weight_values = [
            {"column_index": idx, "header": header[idx] if idx < len(header) else "", "value": _number_value(row[idx]), "raw": row[idx]}
            for idx in weight_columns
            if idx < len(row) and _number_value(row[idx]) is not None
        ]
        if not weight_values and not any(word in compact(" ".join(row)) for word in ["得分", "不得分", "评分", "权重"]):
            continue
        label_parts = [row[idx] for idx in item_columns if idx < len(row) and row[idx]]
        scoring_rows.append(
            {
                "row_number": offset,
                "label": " / ".join(label_parts) if label_parts else next((cell for cell in row if cell), ""),
                "weight_values": weight_values,
                "cells": row,
            }
        )
    top_weights = [
        value["value"]
        for row in scoring_rows
        for value in row.get("weight_values", [])
        if isinstance(value.get("value"), (int, float))
    ]
    return {
        "rows": normalized_rows,
        "header": header,
        "row_count": len(normalized_rows),
        "column_count": max_cols,
        "weight_columns": weight_columns,
        "item_columns": item_columns,
        "scoring": {
            "is_scoring_like": bool(scoring_rows) and any(word in header_key + compact("\n".join("\t".join(row) for row in normalized_rows[:3])) for word in ["评分", "评审", "权重", "分值"]),
            "rows": scoring_rows[:80],
            "weight_sum": round(sum(top_weights), 4) if top_weights else None,
            "weight_count": len(top_weights),
            "structure_warnings": table_structure_warnings(normalized_rows, header, weight_columns, scoring_rows),
        },
    }


def table_structure_warnings(
    rows: list[list[str]],
    header: list[str],
    weight_columns: list[int],
    scoring_rows: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if scoring_rows and not header:
        warnings.append("missing_header")
    if scoring_rows and not weight_columns:
        warnings.append("missing_weight_column")
    if scoring_rows and len(weight_columns) > 1:
        warnings.append("multiple_weight_columns")
    if scoring_rows and any(len(set(row)) < len([cell for cell in row if cell]) for row in rows[:5]):
        warnings.append("possible_merged_or_repeated_cells")
    if scoring_rows and any(not row.get("label") for row in scoring_rows):
        warnings.append("missing_scoring_item_label")
    return warnings

def extract_docx_blocks(path: Path) -> tuple[list[DocumentBlock], dict[str, Any], str]:
    try:
        import docx  # type: ignore
        from docx.document import Document as _Document  # type: ignore
        from docx.oxml.table import CT_Tbl  # type: ignore
        from docx.oxml.text.paragraph import CT_P  # type: ignore
        from docx.table import Table  # type: ignore
        from docx.text.paragraph import Paragraph  # type: ignore
    except ImportError as exc:
        raise RuntimeError(f"无法结构化提取 {path.name}，python-docx 不可用") from exc

    def iter_block_items(parent: _Document):
        for child in parent.element.body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    def table_rows(table: Any) -> list[list[str]]:
        rows: list[list[str]] = []
        for row in table.rows:
            cells = [vcc.normalize_extracted_text(str(cell.text or "")).strip() for cell in row.cells]
            if any(cells):
                rows.append(cells)
        return rows

    def table_to_text(rows: list[list[str]]) -> str:
        return "\n".join("\t".join(row) for row in rows).strip()

    document = docx.Document(str(path))
    blocks: list[DocumentBlock] = []
    line_no = 1
    block_index = 1
    stats = {"paragraph_blocks": 0, "table_blocks": 0, "block_count": 0, "line_count": 0}
    for item in iter_block_items(document):
        if item.__class__.__name__ == "Paragraph":
            text = vcc.normalize_extracted_text(str(item.text or "")).strip()
            block_type = "paragraph"
            if text:
                stats["paragraph_blocks"] += 1
        else:
            rows = table_rows(item)
            text = table_to_text(rows)
            block_type = "table"
            if text:
                stats["table_blocks"] += 1
        if not text:
            continue
        lines = text.split("\n")
        start = line_no
        line_no += len(lines)
        blocks.append(
            DocumentBlock(
                block_id=f"b{block_index:04d}",
                block_type=block_type,
                order_index=block_index,
                line_start=start,
                line_end=line_no - 1,
                text=text,
                lines=lines,
                table=table_ir_from_rows(rows) if block_type == "table" else {},
            )
        )
        block_index += 1
    stats["block_count"] = len(blocks)
    stats["line_count"] = line_no - 1
    return blocks, stats, "python-docx-blocks"


def load_document_blocks(path: Path) -> tuple[list[DocumentBlock], dict[str, Any], str]:
    if path.suffix.lower() == ".docx":
        blocks, stats, extractor = extract_docx_blocks(path)
        try:
            plain_text, plain_extractor = vcc.extract_text_from_docx(path)
        except Exception:
            plain_text = ""
            plain_extractor = ""
        if plain_text:
            structured_keys = {normalize_key(block.text) for block in blocks if normalize_key(block.text)}
            fallback_blocks: list[DocumentBlock] = []
            for idx, line in enumerate(vcc.source_lines(plain_text), start=1):
                text = line.strip()
                if not text:
                    continue
                key = normalize_key(text)
                if key and key in structured_keys:
                    continue
                fallback_blocks.append(
                    DocumentBlock(
                        block_id=f"p{idx:04d}",
                        block_type="plain_fallback",
                        order_index=10_000 + idx,
                        line_start=idx,
                        line_end=idx,
                        text=text,
                        lines=[text],
                    )
                )
            assign_section_roles(fallback_blocks)
            blocks.extend(fallback_blocks)
            stats["plain_fallback_blocks"] = len(fallback_blocks)
            extractor = f"{extractor}+{plain_extractor}-fallback" if plain_extractor else extractor
    else:
        text, extractor = vcc.load_review_file(path)
        lines = vcc.source_lines(text)
        blocks = [
            DocumentBlock(
                block_id=f"b{idx:04d}",
                block_type="paragraph",
                order_index=idx,
                line_start=idx,
                line_end=idx,
                text=line,
                lines=[line],
            )
            for idx, line in enumerate(lines, start=1)
            if line.strip()
        ]
        stats = {"paragraph_blocks": len(blocks), "table_blocks": 0, "block_count": len(blocks), "line_count": len(lines)}
    assign_section_roles(blocks)
    return blocks, stats, extractor


def infer_section_role(text: str, current_role: str) -> tuple[str, float, list[str]]:
    ctext = compact(text)
    if (
        current_role in {"qualification", "qualification_primary", "announcement"}
        and re.search(r"(供应商|投标人).{0,12}(须|必须|应|需|不低于|不得|不予|无效|不通过)", ctext)
        and not re.search(r"得\d*(?:\.\d+)?分|不得分|评分|评审|加分|扣分", ctext)
    ):
        return "qualification_primary", 0.72, ["命中供应商/投标人正式约束句式"]
    best_role = current_role or "unknown"
    best_conf = 0.2 if current_role and current_role != "unknown" else 0.0
    reasons: list[str] = [f"继承上级角色：{current_role}"] if best_conf else []

    for role, title_words, table_words in STRUCTURE_PATTERNS:
        title_hits = [word for word in title_words if word and word in ctext]
        table_hits = [word for word in table_words if word and word in ctext]
        if not title_hits and not table_hits:
            continue
        conf = 0.45 + 0.12 * min(len(title_hits), 3) + 0.10 * min(len(table_hits), 3)
        if role == "scoring" and re.search(r"得\d+(?:\.\d+)?分|不得分|权重", ctext):
            conf += 0.15
            table_hits.append("得分/权重结构")
        if role == "scoring_primary" and re.search(r"得\d+(?:\.\d+)?分|不得分|权重", ctext):
            conf += 0.15
            table_hits.append("得分/权重结构")
        if role == "qualification_primary" and re.search(r"投标无效|资格审查不通过|响应无效|不具备投标资格|不予通过", ctext):
            conf += 0.12
            table_hits.append("资格/响应后果")
        if role == "catalog" and len(text) > 120:
            conf -= 0.25
        if conf > best_conf:
            best_role = role
            best_conf = min(conf, 0.95)
            reasons = []
            if title_hits:
                reasons.append("命中标题/结构词：" + "、".join(title_hits))
            if table_hits:
                reasons.append("命中表格/结构特征：" + "、".join(table_hits))
    return best_role or "unknown", round(best_conf, 2), reasons


def assign_section_roles(blocks: list[DocumentBlock]) -> None:
    section_path: list[str] = []
    current_role = "unknown"
    for block in blocks:
        first_line = block.lines[0].strip() if block.lines else block.text.strip()
        role, conf, reasons = infer_section_role(block.text, current_role)
        if looks_like_heading(first_line):
            section_path = section_path[:2]
            section_path.append(first_line)
            heading_role, heading_conf, heading_reasons = infer_section_role(first_line, current_role)
            if heading_conf >= conf:
                role, conf, reasons = heading_role, heading_conf, heading_reasons
            if role != "unknown" and conf >= 0.45:
                current_role = role
        block.section_path = list(section_path)
        block.section_role = role
        block.section_role_confidence = conf
        block.section_role_reason = reasons


def document_ir_from_blocks(review_file: Path, blocks: list[DocumentBlock], stats: dict[str, Any], extractor: str, facts: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": DOCUMENT_IR_SCHEMA,
        "source_file": str(review_file),
        "extractor": extractor,
        "stats": stats,
        "facts": facts,
        "blocks": [asdict(block) for block in blocks],
    }



def load_document_ir(output_dir: Path) -> tuple[Path, list[DocumentBlock], dict[str, Any], dict[str, Any], str]:
    path = output_dir / "document-ir.json"
    if not path.exists():
        raise RuntimeError(f"缺少 Document IR：{run_path(output_dir, path)}")
    payload = json.loads(read_text(path))
    if payload.get("schema_version") != DOCUMENT_IR_SCHEMA:
        raise RuntimeError(f"Document IR schema 不匹配：{payload.get('schema_version')}")
    blocks = [DocumentBlock(**block) for block in payload.get("blocks", [])]
    source_file = Path(str(payload.get("source_file") or ""))
    stats = payload.get("stats") or {}
    facts = payload.get("facts") or {}
    extractor = str(payload.get("extractor") or "")
    return source_file, blocks, stats, facts, extractor



def write_document_artifacts(output_dir: Path, review_file: Path) -> tuple[list[DocumentBlock], dict[str, Any], dict[str, Any], str]:
    blocks, stats, extractor = load_document_blocks(review_file)
    facts = fact_summary_from_blocks(blocks)
    write_text(output_dir / "document-ir.json", json.dumps(document_ir_from_blocks(review_file, blocks, stats, extractor, facts), ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "facts.json", json.dumps(facts, ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "facts.md", fact_summary_markdown(facts) + "\n")
    return blocks, stats, facts, extractor


def fact_summary_from_blocks(blocks: list[DocumentBlock]) -> dict[str, Any]:
    lines = [line for block in blocks for line in block.lines]
    text_lines = "\n".join(lines)
    def first(patterns: list[str]) -> str:
        for line in lines:
            c = compact(line)
            for pattern in patterns:
                m = re.search(pattern, c)
                if m:
                    return m.group(1) if m.groups() else line.strip()
        return ""
    weights: dict[str, float] = {}
    for line in lines:
        c = compact(line)
        if "技术部分" in c:
            nums = re.findall(r"\d+(?:\.\d+)?", c)
            if nums:
                weights.setdefault("技术", float(nums[-1]))
        if "商务部分" in c:
            nums = re.findall(r"\d+(?:\.\d+)?", c)
            if nums:
                weights.setdefault("商务", float(nums[-1]))
        if "诚信情况" in c:
            nums = re.findall(r"\d+(?:\.\d+)?", c)
            if nums:
                weights.setdefault("诚信", float(nums[-1]))
        if re.search(r"价格.*\d+$", c):
            nums = re.findall(r"\d+(?:\.\d+)?", c)
            if nums:
                weights.setdefault("价格", float(nums[-1]))
    scoring_tables: list[dict[str, Any]] = []
    for block in blocks:
        table = block.table or {}
        scoring = table.get("scoring") or {}
        if not scoring.get("is_scoring_like"):
            continue
        scoring_tables.append(
            {
                "block_id": block.block_id,
                "line_anchor": f"{block.line_start:04d}-{block.line_end:04d}",
                "section_role": block.section_role,
                "weight_sum": scoring.get("weight_sum"),
                "weight_count": scoring.get("weight_count"),
                "structure_warnings": scoring.get("structure_warnings") or [],
                "rows": [
                    {
                        "row_number": row.get("row_number"),
                        "label": row.get("label"),
                        "weight_values": row.get("weight_values"),
                    }
                    for row in (scoring.get("rows") or [])[:20]
                ],
            }
        )
    return {
        "project_type": first([r"项目类型[:：]?(服务类|货物类|工程类)"]) or ("服务类" if "服务类" in text_lines else ""),
        "procurement_method": first([r"采购方式[:：]?([^，。；;\t ]+)"]),
        "evaluation_method": first([r"评标方法[:：]?([^，。；;\t ]+)"]),
        "joint_bid": "不接受" if "不接受联合体投标" in text_lines else ("接受" if re.search(r"本项目接受联合体投标", text_lines) else ""),
        "import_product": "不接受" if "不接受投标人选用进口产品" in text_lines or "不接受进口产品" in text_lines else "",
        "industry": first([r"项目，属于([^，。；;]+行业)", r"项目.*属于([^，。；;]+行业)"]),
        "bid_bond": "不收取" if "本项目不收取投标保证金" in text_lines else "",
        "scoring_weights": {"weights": weights, "total": sum(weights.values())},
        "scoring_tables": scoring_tables[:12],
    }


def fact_summary_markdown(facts: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## 轻事实摘要",
            "",
            "以下事实只作背景和低级误报防护，不得单独构成命中证据。",
            "",
            f"- 项目类型：{facts.get('project_type') or '未抽取'}",
            f"- 采购方式：{facts.get('procurement_method') or '未抽取'}",
            f"- 评标方法：{facts.get('evaluation_method') or '未抽取'}",
            f"- 是否接受联合体：{facts.get('joint_bid') or '未抽取'}",
            f"- 是否接受进口产品：{facts.get('import_product') or '未抽取'}",
            f"- 标的所属行业：{facts.get('industry') or '未抽取'}",
            f"- 投标保证金：{facts.get('bid_bond') or '未抽取'}",
            f"- 评分权重：{json.dumps(facts.get('scoring_weights', {}), ensure_ascii=False)}",
            f"- 评分表结构摘要：{json.dumps(facts.get('scoring_tables', []), ensure_ascii=False)[:4000]}",
        ]
    )
