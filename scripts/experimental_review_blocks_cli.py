#!/usr/bin/env python3
"""临时实验：把 review docx 组织成 lines + blocks，并与当前 plain-text 解析对比。"""

from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from docx import Document
from docx.document import Document as _Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass
class ReviewLine:
    line_no: int
    text: str
    block_id: str


@dataclass
class ReviewBlock:
    block_id: str
    block_type: str
    order_index: int
    text: str
    line_start: int
    line_end: int


def iter_block_items(parent: _Document) -> Iterable[Paragraph | Table]:
    parent_elm = parent.element.body
    for child in parent_elm.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def normalize_text(text: str) -> str:
    return (
        text.replace("\r", "")
        .replace("\x0b", "\n")
        .replace("\x0c", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
    )


def paragraph_to_text(p: Paragraph) -> str:
    return normalize_text(p.text).strip()


def table_to_text(t: Table) -> str:
    lines: list[str] = []
    for row in t.rows:
        cells = [normalize_text(cell.text).strip() for cell in row.cells]
        if any(cells):
            lines.append("\t".join(cells))
    return "\n".join(lines).strip()


def extract_docx_blocks(path: Path) -> tuple[list[ReviewBlock], list[ReviewLine], str]:
    doc = Document(str(path))
    blocks: list[ReviewBlock] = []
    lines: list[ReviewLine] = []
    line_no = 1
    order_index = 1

    for item in iter_block_items(doc):
        if isinstance(item, Paragraph):
            text = paragraph_to_text(item)
            block_type = "paragraph"
        else:
            text = table_to_text(item)
            block_type = "table"

        if not text:
            continue

        block_id = f"b{order_index:04d}"
        block_lines = text.split("\n")
        start = line_no
        for block_line in block_lines:
            lines.append(ReviewLine(line_no=line_no, text=block_line, block_id=block_id))
            line_no += 1
        end = line_no - 1
        blocks.append(
            ReviewBlock(
                block_id=block_id,
                block_type=block_type,
                order_index=order_index,
                text=text,
                line_start=start,
                line_end=end,
            )
        )
        order_index += 1

    review_text = "\n\n".join(block.text for block in blocks)
    return blocks, lines, review_text


def load_current_parser_module(root: Path):
    script = root / "scripts" / "validate_checkpoint_cli.py"
    spec = importlib.util.spec_from_file_location("validate_checkpoint_cli", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_summary(blocks: list[ReviewBlock], lines: list[ReviewLine], text: str) -> dict:
    table_blocks = [b for b in blocks if b.block_type == "table"]
    paragraph_blocks = [b for b in blocks if b.block_type == "paragraph"]
    return {
        "block_count": len(blocks),
        "paragraph_block_count": len(paragraph_blocks),
        "table_block_count": len(table_blocks),
        "line_count": len(lines),
        "char_count": len(text),
        "first_blocks": [asdict(b) for b in blocks[:6]],
        "sample_table_blocks": [asdict(b) for b in table_blocks[:4]],
    }


def compare_candidates(
    root: Path,
    review_file: Path,
    checkpoint_file: Path,
    experimental_lines: list[ReviewLine],
) -> dict:
    mod = load_current_parser_module(root)
    checkpoint_md = checkpoint_file.read_text(encoding="utf-8")
    keywords = mod.parse_keyword_groups(checkpoint_md)
    cp_id = mod.extract_checkpoint_id(checkpoint_md)
    cp_title = mod.extract_title(checkpoint_md)

    current_text, _ = mod.load_review_file(review_file)
    current_excerpt, current_count, current_stats = mod.collect_candidate_windows(
        review_text=current_text,
        keyword_groups=keywords,
        checkpoint_id=cp_id,
        checkpoint_title=cp_title,
        context_before=5,
        context_after=10,
        max_windows=12,
        max_line_chars=900,
        max_excerpt_chars=12000,
        min_candidate_score=3,
    )

    experimental_text = "\n".join(line.text for line in experimental_lines)
    experimental_excerpt, experimental_count, experimental_stats = mod.collect_candidate_windows(
        review_text=experimental_text,
        keyword_groups=keywords,
        checkpoint_id=cp_id,
        checkpoint_title=cp_title,
        context_before=5,
        context_after=10,
        max_windows=12,
        max_line_chars=900,
        max_excerpt_chars=12000,
        min_candidate_score=3,
    )

    return {
        "checkpoint_id": cp_id,
        "checkpoint_title": cp_title,
        "current": {
            "window_count": current_count,
            "raw_hit_count": current_stats["raw_hit_count"],
            "filtered_hit_count": current_stats["filtered_hit_count"],
            "selected_scores": current_stats["selected_scores"],
            "excerpt_chars": len(current_excerpt),
            "excerpt_head": current_excerpt.splitlines()[:24],
        },
        "experimental": {
            "window_count": experimental_count,
            "raw_hit_count": experimental_stats["raw_hit_count"],
            "filtered_hit_count": experimental_stats["filtered_hit_count"],
            "selected_scores": experimental_stats["selected_scores"],
            "excerpt_chars": len(experimental_excerpt),
            "excerpt_head": experimental_excerpt.splitlines()[:24],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="临时比较 plain-text 解析 vs blocks+lines 解析")
    parser.add_argument("--review-file", type=Path, required=True)
    parser.add_argument("--checkpoint-file", type=Path, help="可选，对某个 checkpoint 做候选窗口对比")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    root = Path.cwd()
    mod = load_current_parser_module(root)

    current_text, current_method = mod.load_review_file(args.review_file)
    current_lines = mod.source_lines(current_text)
    experimental_blocks, experimental_lines, experimental_text = extract_docx_blocks(args.review_file)

    result = {
        "review_file": str(args.review_file),
        "current": {
            "method": current_method,
            "line_count": len(current_lines),
            "char_count": len(current_text),
            "head_lines": current_lines[:20],
            "sample_lines_around_0757": current_lines[749:765],
        },
        "experimental": build_summary(experimental_blocks, experimental_lines, experimental_text),
    }

    if args.checkpoint_file:
        result["candidate_compare"] = compare_candidates(
            root=root,
            review_file=args.review_file,
            checkpoint_file=args.checkpoint_file,
            experimental_lines=experimental_lines,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("CURRENT")
        print(json.dumps(result["current"], ensure_ascii=False, indent=2))
        print("EXPERIMENTAL")
        print(json.dumps(result["experimental"], ensure_ascii=False, indent=2))
        if "candidate_compare" in result:
            print("CANDIDATE_COMPARE")
            print(json.dumps(result["candidate_compare"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
