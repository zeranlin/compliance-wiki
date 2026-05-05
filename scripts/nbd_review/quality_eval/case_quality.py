"""Single-case quality evaluation pipeline.

The command orchestrates quality-layer steps for an existing business run. It
does not call the model and does not change business review results.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quality_eval.evaluate_f1 import (
    POSITIVE_VERDICTS,
    compute_metrics,
    load_gold_with_ignored,
    load_predictions,
    match_items,
    write_report,
)
from quality_eval.export_gold_like import build_gold_like, write_json
from quality_eval.run_roles import write_run_role
from quality_eval.update_f1_summary import update_summary
from shared.utils import now_text, relative_path, write_text


def load_metrics(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(gold_json: Path, run_dir: Path, output_dir: Path, line_match: str) -> dict[str, Any]:
    gold_items, ignored_gold_items = load_gold_with_ignored(gold_json)
    pred_items, no_line_predictions = load_predictions(run_dir, POSITIVE_VERDICTS)
    matches = match_items(gold_items, pred_items, line_match)
    write_report(
        output_dir,
        gold_json,
        run_dir,
        gold_items,
        pred_items,
        no_line_predictions,
        matches,
        line_match,
        ignored_gold_items,
    )
    return {
        "gold_total": len(gold_items),
        "ignored_gold_total": len(ignored_gold_items),
        "pred_total": len(pred_items) + len(no_line_predictions),
        "match_total": len(matches),
        **compute_metrics(len(gold_items), len(pred_items) + len(no_line_predictions), len(matches)),
        "false_negative_total": len(gold_items) - len(matches),
        "false_positive_total": len(pred_items) + len(no_line_predictions) - len(matches),
    }


def render_summary(payload: dict[str, Any]) -> str:
    v1 = payload.get("v1") or {}
    v2 = payload.get("v2") or {}
    lines = [
        "# 单案例质量评测流水线报告",
        "",
        f"- 生成时间：{payload.get('created_at', '')}",
        f"- 品目：{payload.get('item_category', '')}",
        f"- 案例编号：{payload.get('case_no', '')}",
        f"- 样本名称：{payload.get('sample_name', '')}",
        f"- run：`{payload.get('run_dir', '')}`",
        f"- 目标 F1-V2：{float(payload.get('target_f1') or 0):.4f}",
        "",
        "## 指标",
        "",
        "| 口径 | 标准答案数 | 忽略新增数 | 工程输出数 | 匹配成功数 | 召回率 | 精确率 | F1 值 | 漏报数 | 误报数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, metrics in (("V1", v1), ("V2", v2)):
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    str(metrics.get("gold_total", "")),
                    str(metrics.get("ignored_gold_total", "")),
                    str(metrics.get("pred_total", "")),
                    str(metrics.get("match_total", "")),
                    f"{float(metrics.get('recall') or 0):.4f}",
                    f"{float(metrics.get('precision') or 0):.4f}",
                    f"{float(metrics.get('f1') or 0):.4f}",
                    str(metrics.get("false_negative_total", "")),
                    str(metrics.get("false_positive_total", "")),
                ]
            )
            + " |"
        )
    status = "达标" if float(v2.get("f1") or 0) >= float(payload.get("target_f1") or 0) else "未达标"
    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"- F1-V2 状态：{status}。",
            f"- 工程标准答案格式 JSON：`{payload.get('gold_like_json', '')}`",
            f"- V1 评测目录：`{payload.get('evaluation_v1_dir', '')}`",
            f"- V2 评测目录：`{payload.get('evaluation_v2_dir', '')}`",
        ]
    )
    if payload.get("summary_md"):
        lines.append(f"- 已回写汇总报告：`{payload.get('summary_md')}`")
    return "\n".join(lines) + "\n"


def run_case_quality(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        raise FileNotFoundError(run_dir)
    evaluation_dir = run_dir / "evaluation"
    gold_like_path = args.gold_like_output.resolve() if args.gold_like_output else evaluation_dir / "工程审查结果_按标准答案格式.json"
    data = build_gold_like(run_dir, include_no_line=args.include_no_line)
    write_json(gold_like_path, data)

    v1_dir = run_dir / "evaluation-v1"
    v2_dir = run_dir / "evaluation-v2"
    v1_metrics = evaluate(args.gold_v1.resolve(), run_dir, v1_dir, args.line_match)
    v2_metrics = evaluate(args.gold_v2.resolve(), run_dir, v2_dir, args.line_match)

    if args.case_no or args.sample_name or args.item_category:
        write_run_role(
            run_dir=run_dir,
            role=args.role,
            case_no=args.case_no,
            sample_name=args.sample_name,
            item_category=args.item_category,
            notes=args.notes,
        )

    totals = None
    if args.summary_md:
        status = args.status
        if not status:
            status = "专项完成" if v2_metrics["f1"] >= args.target_f1 else "专项进行中"
        totals = update_summary(
            summary_path=args.summary_md.resolve(),
            case_no=args.case_no,
            run_dir=run_dir,
            status=status,
            file_label=args.file_label,
        )

    payload = {
        "schema_version": "nbd-case-quality/v1",
        "created_at": now_text(),
        "case_no": args.case_no,
        "sample_name": args.sample_name,
        "item_category": args.item_category,
        "run_dir": str(run_dir),
        "target_f1": args.target_f1,
        "gold_v1": str(args.gold_v1.resolve()),
        "gold_v2": str(args.gold_v2.resolve()),
        "gold_like_json": str(gold_like_path),
        "evaluation_v1_dir": str(v1_dir),
        "evaluation_v2_dir": str(v2_dir),
        "summary_md": str(args.summary_md.resolve()) if args.summary_md else "",
        "role": args.role,
        "notes": args.notes,
        "v1": v1_metrics,
        "v2": v2_metrics,
    }
    if totals:
        v1_total, v2_total = totals
        payload["summary_totals"] = {
            "v1": v1_total.__dict__,
            "v2": v2_total.__dict__,
        }
    output_json = args.output_json.resolve() if args.output_json else run_dir / "case-quality.json"
    output_md = args.output_md.resolve() if args.output_md else run_dir / "case-quality.md"
    write_text(output_json, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text(output_md, render_summary(payload))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="执行单案例质量评测流水线")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--gold-v1", required=True, type=Path)
    parser.add_argument("--gold-v2", required=True, type=Path)
    parser.add_argument("--case-no", type=int)
    parser.add_argument("--sample-name", default="")
    parser.add_argument("--item-category", default="")
    parser.add_argument("--summary-md", type=Path)
    parser.add_argument("--status", help="回写汇总报告的状态；默认按 target-f1 自动判断")
    parser.add_argument("--file-label", help="回写汇总报告的文件列")
    parser.add_argument("--target-f1", type=float, default=0.9)
    parser.add_argument("--line-match", choices=["range", "exact"], default="range")
    parser.add_argument("--role", choices=["baseline", "targeted", "final-full", "final-hybrid"], default="final-full")
    parser.add_argument("--notes", default="")
    parser.add_argument("--gold-like-output", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--include-no-line", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def main() -> int:
    payload = run_case_quality(parse_args())
    print(relative_path(Path(payload["evaluation_v2_dir"])))
    print(f"V1_F1={payload['v1']['f1']:.4f}")
    print(f"V2_F1={payload['v2']['f1']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
