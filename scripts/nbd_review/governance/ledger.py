"""Governance ledger templates for single-case NBD tuning."""

from __future__ import annotations

import argparse
from pathlib import Path

from shared.utils import relative_path, write_text


def render_ledger(
    case_no: int | None,
    sample_name: str,
    item_category: str,
    baseline_run: Path | None,
    target_f1: float,
) -> str:
    case_text = str(case_no) if case_no is not None else ""
    baseline = str(baseline_run) if baseline_run else ""
    return "\n".join(
        [
            f"# {item_category}{'案例' + case_text if case_text else ''} NBD 专项提升账本",
            "",
            "## 1. 样本信息",
            "",
            f"- 品目：{item_category}",
            f"- 案例编号：{case_text}",
            f"- 样本名称：{sample_name}",
            f"- baseline run：`{baseline}`",
            f"- V2-F1 目标：{target_f1:.4f}",
            "",
            "## 2. P 阶段记录",
            "",
            "| 阶段 | 目标问题 | 涉及 NBD | run | V1 F1 | V2 F1 | 净收益结论 | 是否合并 | 下一步 |",
            "|---|---|---|---|---:|---:|---|---|---|",
            "| P0 baseline | 建立全量基线 | 151 全量 |  |  |  |  |  |  |",
            "",
            "## 3. 漏报归因",
            "",
            "| 类型 | 数量 | 代表 NBD | 代表行号 | 处理方向 |",
            "|---|---:|---|---|---|",
            "",
            "## 4. 误报归因",
            "",
            "| 类型 | 数量 | 代表 NBD | 代表行号 | 处理方向 |",
            "|---|---:|---|---|---|",
            "",
            "## 5. V2 裁判校准",
            "",
            "| 行号 | 审查点 | 裁判结论 | 是否进入 V2 | 理由 |",
            "|---|---|---|---|---|",
            "",
            "## 6. 合并决策",
            "",
            "| targeted run | 涉及 NBD | 匹配变化 | 精确率变化 | 是否进入 final-hybrid | 理由 |",
            "|---|---|---:|---:|---|---|",
            "",
            "## 7. 最终结论",
            "",
            "- final run：",
            "- V1 指标：",
            "- V2 指标：",
            "- 是否回写总表：",
            "- 未处理问题：",
            "",
        ]
    )


def write_ledger(
    output: Path,
    case_no: int | None = None,
    sample_name: str = "",
    item_category: str = "",
    baseline_run: Path | None = None,
    target_f1: float = 0.9,
) -> Path:
    write_text(output, render_ledger(case_no, sample_name, item_category, baseline_run, target_f1))
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成单案例 NBD 专项提升账本模板")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-no", type=int)
    parser.add_argument("--sample-name", default="")
    parser.add_argument("--item-category", default="")
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--target-f1", type=float, default=0.9)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = write_ledger(
        output=args.output.resolve(),
        case_no=args.case_no,
        sample_name=args.sample_name,
        item_category=args.item_category,
        baseline_run=args.baseline_run.resolve() if args.baseline_run else None,
        target_f1=args.target_f1,
    )
    print(relative_path(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
