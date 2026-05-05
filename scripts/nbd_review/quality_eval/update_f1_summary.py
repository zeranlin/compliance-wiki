#!/usr/bin/env python3
"""Update a markdown F1 summary table from a completed NBD run."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SUMMARY_COLUMNS = 15
CASE_TABLE_START = "| 案例 | 文件 | 运行状态 | V1 标准答案数 |"
OVERALL_TABLE_START = "| 口径 | 标准答案数 | 工程输出数 | 匹配成功数 |"


@dataclass(frozen=True)
class F1Metrics:
    gold_total: int
    pred_total: int
    match_total: int
    recall: float
    precision: float
    f1: float


@dataclass(frozen=True)
class CaseMetrics:
    v1: F1Metrics
    v2: F1Metrics


def load_metrics(path: Path) -> F1Metrics:
    data = json.loads(path.read_text(encoding="utf-8"))
    return F1Metrics(
        gold_total=int(data["gold_total"]),
        pred_total=int(data["pred_total"]),
        match_total=int(data["match_total"]),
        recall=float(data["recall"]),
        precision=float(data["precision"]),
        f1=float(data["f1"]),
    )


def load_case_metrics(run_dir: Path) -> CaseMetrics:
    return CaseMetrics(
        v1=load_metrics(run_dir / "evaluation-v1" / "metrics.json"),
        v2=load_metrics(run_dir / "evaluation-v2" / "metrics.json"),
    )


def split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown_row(cells: Iterable[object]) -> str:
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


def format_float(value: float) -> str:
    return f"{value:.4f}"


def format_metric_cells(metrics: F1Metrics) -> list[str]:
    return [
        str(metrics.gold_total),
        str(metrics.pred_total),
        str(metrics.match_total),
        format_float(metrics.recall),
        format_float(metrics.precision),
        format_float(metrics.f1),
    ]


def compute_total(rows: list[list[str]], offset: int) -> F1Metrics:
    gold_total = sum(int(row[offset]) for row in rows)
    pred_total = sum(int(row[offset + 1]) for row in rows)
    match_total = sum(int(row[offset + 2]) for row in rows)
    recall = match_total / gold_total if gold_total else 0.0
    precision = match_total / pred_total if pred_total else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    return F1Metrics(gold_total, pred_total, match_total, recall, precision, f1)


def find_case_rows(lines: list[str]) -> tuple[int, int]:
    header_index = next((idx for idx, line in enumerate(lines) if line.startswith(CASE_TABLE_START)), -1)
    if header_index < 0:
        raise ValueError("cannot find case metrics table")
    start = header_index + 2
    end = start
    while end < len(lines) and re.match(r"^\|\s*\d+\s*\|", lines[end]):
        end += 1
    return start, end


def replace_case_row(
    lines: list[str],
    case_no: int,
    metrics: CaseMetrics,
    status: str | None,
    file_label: str | None,
) -> None:
    start, end = find_case_rows(lines)
    target_prefix = re.compile(rf"^\|\s*{case_no}\s*\|")
    for index in range(start, end):
        if not target_prefix.match(lines[index]):
            continue
        cells = split_markdown_row(lines[index])
        if len(cells) != SUMMARY_COLUMNS:
            raise ValueError(f"case row has {len(cells)} columns, expected {SUMMARY_COLUMNS}: {lines[index]}")
        if file_label:
            cells[1] = file_label
        if status:
            cells[2] = status
        cells[3:9] = format_metric_cells(metrics.v1)
        cells[9:15] = format_metric_cells(metrics.v2)
        lines[index] = render_markdown_row(cells)
        return
    raise ValueError(f"cannot find case row: {case_no}")


def parse_case_metric_rows(lines: list[str]) -> list[list[str]]:
    start, end = find_case_rows(lines)
    rows = [split_markdown_row(line) for line in lines[start:end]]
    for row in rows:
        if len(row) != SUMMARY_COLUMNS:
            raise ValueError(f"case row has {len(row)} columns, expected {SUMMARY_COLUMNS}: {row}")
    return rows


def replace_overall_table(lines: list[str], v1: F1Metrics, v2: F1Metrics) -> None:
    header_index = next((idx for idx, line in enumerate(lines) if line.startswith(OVERALL_TABLE_START)), -1)
    if header_index < 0:
        raise ValueError("cannot find overall metrics table")
    lines[header_index + 2] = render_markdown_row(["V1", *format_metric_cells(v1)])
    lines[header_index + 3] = render_markdown_row(["V2", *format_metric_cells(v2)])


def replace_formula_block(lines: list[str], v1: F1Metrics, v2: F1Metrics) -> None:
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "计算公式："), -1)
    if start < 0:
        raise ValueError("cannot find formula block")
    end = start + 1
    while end < len(lines) and not lines[end].startswith("## 3."):
        end += 1
    block = [
        "计算公式：",
        f"- V1 召回率 = 匹配成功数 / 标准答案数 = {v1.match_total} / {v1.gold_total} = {format_float(v1.recall)}。",
        f"- V1 精确率 = 匹配成功数 / 工程输出数 = {v1.match_total} / {v1.pred_total} = {format_float(v1.precision)}。",
        f"- V1 F1 = 2 * 召回率 * 精确率 / (召回率 + 精确率) = {format_float(v1.f1)}。",
        f"- V2 召回率 = 匹配成功数 / 标准答案数 = {v2.match_total} / {v2.gold_total} = {format_float(v2.recall)}。",
        f"- V2 精确率 = 匹配成功数 / 工程输出数 = {v2.match_total} / {v2.pred_total} = {format_float(v2.precision)}。",
        f"- V2 F1 = 2 * 召回率 * 精确率 / (召回率 + 精确率) = {format_float(v2.f1)}。",
        "",
    ]
    lines[start:end] = block


def update_summary(
    summary_path: Path,
    case_no: int,
    run_dir: Path,
    status: str | None = None,
    file_label: str | None = None,
) -> tuple[F1Metrics, F1Metrics]:
    text = summary_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    replace_case_row(lines, case_no, load_case_metrics(run_dir), status, file_label)
    rows = parse_case_metric_rows(lines)
    v1_total = compute_total(rows, 3)
    v2_total = compute_total(rows, 9)
    replace_overall_table(lines, v1_total, v2_total)
    replace_formula_block(lines, v1_total, v2_total)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return v1_total, v2_total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将单个 NBD run 的 F1-V1/F1-V2 指标回写到汇总报告")
    parser.add_argument("--summary-md", required=True, type=Path, help="汇总报告 markdown")
    parser.add_argument("--case-no", required=True, type=int, help="案例编号")
    parser.add_argument("--run-dir", required=True, type=Path, help="已完成评测的 NBD run 目录")
    parser.add_argument("--status", help="可选：覆盖运行状态列，例如：专项完成")
    parser.add_argument("--file-label", help="可选：覆盖文件列")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    v1_total, v2_total = update_summary(
        summary_path=args.summary_md.resolve(),
        case_no=args.case_no,
        run_dir=args.run_dir.resolve(),
        status=args.status,
        file_label=args.file_label,
    )
    print(f"updated={args.summary_md.resolve()}")
    print(f"V1: 标准答案数={v1_total.gold_total} 工程输出数={v1_total.pred_total} 匹配成功数={v1_total.match_total} 召回率={v1_total.recall:.4f} 精确率={v1_total.precision:.4f} F1值={v1_total.f1:.4f}")
    print(f"V2: 标准答案数={v2_total.gold_total} 工程输出数={v2_total.pred_total} 匹配成功数={v2_total.match_total} 召回率={v2_total.recall:.4f} 精确率={v2_total.precision:.4f} F1值={v2_total.f1:.4f}")


if __name__ == "__main__":
    main()
