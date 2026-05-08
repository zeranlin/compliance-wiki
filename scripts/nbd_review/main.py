#!/usr/bin/env python3
"""NBD CLI entrypoint.

Commands are grouped into three layers:

- business review: daily document review with NBD and a small model.
- quality evaluation: V1/V2 metrics, exported findings, and summaries.
- governance: diagnostics, F1 regression analysis, and runtime hygiene checks.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from business_review.pipeline import (
    run_build_prompt_stage,
    run_compile_document,
    run_compile_nbd,
    run_model_stage,
    run_preflight,
    run_recall_stage,
    run_report_stage,
    run_review,
)
from governance.lint_runtime import run_lint_runtime


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-file", type=Path, required=True, help="待审查文件")
    parser.add_argument("--nbd", action="append", default=[], help="单个 NBD 文件路径或 NBD id，可重复")
    parser.add_argument("--nbd-glob", default="wiki/bd-review-points/items/NBD*.md", help="NBD 文件 glob")
    parser.add_argument("--theme", type=Path, help="NBD 主题页，读取 frontmatter nbd_ids")
    parser.add_argument("--output-dir", type=Path, help="输出目录")
    parser.add_argument("--max-primary-windows", type=int, default=5)
    parser.add_argument("--max-support-windows", type=int, default=3)
    parser.add_argument("--max-window-chars", type=int, default=5000)
    parser.add_argument("--max-prompt-chars", type=int, default=32000)


def add_document_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-file", type=Path, required=True, help="待审查文件")
    parser.add_argument("--output-dir", type=Path, help="输出目录")


def add_nbd_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--nbd", action="append", default=[], help="单个 NBD 文件路径或 NBD id，可重复")
    parser.add_argument("--nbd-glob", default="wiki/bd-review-points/items/NBD*.md", help="NBD 文件 glob")
    parser.add_argument("--theme", type=Path, help="NBD 主题页，读取 frontmatter nbd_ids")
    parser.add_argument("--output-dir", type=Path, help="输出目录")


def add_stage_output_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-dir", type=Path, required=True, help="已有运行目录")


def run_export_gold_like(args: argparse.Namespace) -> int:
    from quality_eval.export_gold_like import build_gold_like, write_json

    run_dir = args.output_dir.resolve()
    output = args.output or (run_dir / "evaluation" / "工程审查结果_按标准答案格式.json")
    data = build_gold_like(run_dir, include_no_line=args.include_no_line)
    write_json(output.resolve(), data)
    print(output.resolve())
    print(f"exported={len(data['检查结果'])}")
    return 0


def run_compare_f1_runs(args: argparse.Namespace) -> int:
    from governance.compare_f1_runs import compare_runs, format_float, render_markdown
    from shared.utils import write_text

    output_dir = args.output_dir or (args.new_run / "evaluation-comparison")
    report = compare_runs(args.old_run.resolve(), args.new_run.resolve(), set(args.nbd or []))
    write_text(output_dir / "f1-regression-analysis.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(output_dir / "F1下降自动归因报告.md", render_markdown(report))
    print(output_dir / "F1下降自动归因报告.md")
    print(f"f1_dropped={report['f1_dropped']}")
    print(f"old_f1={format_float(report['old_total']['f1'])} new_f1={format_float(report['new_total']['f1'])} delta={report['delta']['f1']:+.4f}")
    return 1 if report["f1_dropped"] else 0


def run_update_f1_summary(args: argparse.Namespace) -> int:
    from quality_eval.update_f1_summary import update_summary

    v1_total, v2_total = update_summary(
        summary_path=args.summary_md.resolve(),
        case_no=args.case_no,
        run_dir=args.run_dir.resolve(),
        status=args.status,
        file_label=args.file_label,
    )
    print(args.summary_md.resolve())
    print(f"V1: 标准答案数={v1_total.gold_total} 工程输出数={v1_total.pred_total} 匹配成功数={v1_total.match_total} 召回率={v1_total.recall:.4f} 精确率={v1_total.precision:.4f} F1值={v1_total.f1:.4f}")
    print(f"V2: 标准答案数={v2_total.gold_total} 工程输出数={v2_total.pred_total} 匹配成功数={v2_total.match_total} 召回率={v2_total.recall:.4f} 精确率={v2_total.precision:.4f} F1值={v2_total.f1:.4f}")
    return 0


def run_diagnose_f1(args: argparse.Namespace) -> int:
    from governance.diagnose_f1 import run_diagnosis

    run_diagnosis(args)
    return 0


def run_index_runs(args: argparse.Namespace) -> int:
    from governance.run_index import write_run_index
    from shared.utils import relative_path

    json_path, md_path = write_run_index(args.base_dir.resolve(), args.output_dir.resolve())
    print(relative_path(md_path))
    print(relative_path(json_path))
    return 0


def run_evaluate_f1(args: argparse.Namespace) -> int:
    from quality_eval.evaluate_f1 import (
        POSITIVE_VERDICTS,
        compute_metrics,
        load_gold_with_ignored,
        load_predictions,
        match_items,
        write_report,
    )

    gold_path = args.gold_json.resolve()
    run_dir = args.run_dir.resolve()
    output_dir = (args.output_dir or (run_dir / "evaluation")).resolve()
    gold_items, ignored_gold_items = load_gold_with_ignored(gold_path)
    pred_items, no_line_predictions = load_predictions(run_dir, POSITIVE_VERDICTS)
    matches = match_items(gold_items, pred_items, args.line_match)
    write_report(output_dir, gold_path, run_dir, gold_items, pred_items, no_line_predictions, matches, args.line_match, ignored_gold_items)
    pred_total = len(pred_items) + len(no_line_predictions)
    metrics = compute_metrics(len(gold_items), pred_total, len(matches))
    print(f"gold_total={len(gold_items)}")
    print(f"ignored_gold_total={len(ignored_gold_items)}")
    print(f"pred_total={pred_total}")
    print(f"match_total={len(matches)}")
    print(f"recall={metrics['recall']:.4f}")
    print(f"precision={metrics['precision']:.4f}")
    print(f"f1={metrics['f1']:.4f}")
    print(output_dir)
    return 0


def run_mark_run_role(args: argparse.Namespace) -> int:
    from quality_eval.run_roles import split_csv, write_run_role

    payload = write_run_role(
        run_dir=args.run_dir.resolve(),
        role=args.role,
        case_no=args.case_no,
        sample_name=args.sample_name,
        item_category=args.item_category,
        base_run=args.base_run.resolve() if args.base_run else None,
        targeted_runs=[path.resolve() for path in args.targeted_run],
        related_nbds=split_csv(args.nbd),
        notes=args.notes,
    )
    print(args.run_dir.resolve() / "run-role.json")
    print(f"role={payload['role']}")
    return 0


def run_build_hybrid(args: argparse.Namespace) -> int:
    from quality_eval.hybrid_builder import build_hybrid_run
    from quality_eval.run_roles import split_csv
    from shared.utils import relative_path

    payload = build_hybrid_run(
        base_run=args.base_run.resolve(),
        targeted_runs=[path.resolve() for path in args.targeted_run],
        output_dir=args.output_dir.resolve(),
        selected_nbds=set(split_csv(args.nbd)),
        case_no=args.case_no,
        sample_name=args.sample_name,
        item_category=args.item_category,
        notes=args.notes,
    )
    print(relative_path(args.output_dir.resolve()))
    print(f"targeted_runs={len(payload['targeted_runs'])}")
    return 0


def run_create_ledger(args: argparse.Namespace) -> int:
    from governance.ledger import write_ledger
    from shared.utils import relative_path

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


def run_record_gold_change(args: argparse.Namespace) -> int:
    from quality_eval.gold_changes import GoldChange, append_ledger, apply_gold_change
    from shared.utils import now_text, relative_path

    gold_json = args.gold_json.resolve()
    ledger = args.ledger.resolve() if args.ledger else gold_json.with_suffix(".gold-ledger.json")
    change = GoldChange(
        change_type=args.change_type,
        line=args.line,
        checkpoint=args.checkpoint,
        new_checkpoint=args.new_checkpoint,
        reason=args.reason,
        risk_text=args.risk_text,
        violation_reason=args.violation_reason,
        risk_tip=args.risk_tip,
        suggestion=args.suggestion,
        case_no=args.case_no,
        sample_name=args.sample_name,
        reviewer=args.reviewer,
        created_at=now_text(),
    )
    apply_gold_change(gold_json, change, apply=args.apply)
    append_ledger(ledger, gold_json, change, applied=args.apply)
    print(relative_path(ledger))
    print(relative_path(ledger.with_suffix(".md")))
    print(f"applied={args.apply}")
    return 0


def run_case_quality_command(args: argparse.Namespace) -> int:
    from quality_eval.case_quality import run_case_quality
    from shared.utils import relative_path

    payload = run_case_quality(args)
    primary_dir = next(
        (
            payload.get(key)
            for key in ("evaluation_v4_dir", "evaluation_v3_dir", "evaluation_v2_dir", "evaluation_v1_dir")
            if payload.get(key)
        ),
        "",
    )
    if primary_dir:
        print(relative_path(Path(primary_dir)))
    for key in ("v1", "v2", "v3", "v4"):
        metrics = payload.get(key)
        if isinstance(metrics, dict):
            print(f"{key.upper()}_F1={metrics['f1']:.4f}")
    return 0


def add_recall_args(parser: argparse.ArgumentParser) -> None:
    add_stage_output_arg(parser)
    parser.add_argument("--nbd", action="append", default=[], help="只处理指定 NBD id，可重复")
    parser.add_argument("--max-primary-windows", type=int, default=5)
    parser.add_argument("--max-support-windows", type=int, default=3)
    parser.add_argument("--max-window-chars", type=int, default=5000)


def add_prompt_args(parser: argparse.ArgumentParser) -> None:
    add_stage_output_arg(parser)
    parser.add_argument("--nbd", action="append", default=[], help="只处理指定 NBD id，可重复")
    parser.add_argument("--max-prompt-chars", type=int, default=32000)


def add_model_args(parser: argparse.ArgumentParser) -> None:
    add_prompt_args(parser)
    parser.add_argument("--base-url", help="OpenAI 兼容接口 base_url")
    parser.add_argument("--api-key", help="OpenAI 兼容接口密钥")
    parser.add_argument("--model", help="模型名称")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=6144)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reuse-raw-response", action=argparse.BooleanOptionalAction, default=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NBD 三层质量工程 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="只做候选窗口召回，不调用模型")
    add_common_args(preflight)
    preflight.set_defaults(func=run_preflight)

    lint_runtime = sub.add_parser("lint-runtime", help="检查运行时代码是否混入 NBD 专属业务硬编码")
    lint_runtime.add_argument("--path", type=Path, help="默认检查 scripts/nbd_review/business_review")
    lint_runtime.set_defaults(func=run_lint_runtime)

    compile_document = sub.add_parser("compile-document", help="编译待审文件为 Document IR")
    add_document_args(compile_document)
    compile_document.set_defaults(func=run_compile_document)

    compile_nbd = sub.add_parser("compile-nbd", help="编译 NBD markdown 为 NBD IR")
    add_nbd_args(compile_nbd)
    compile_nbd.set_defaults(func=run_compile_nbd)

    recall = sub.add_parser("recall", help="基于 Document IR 和 NBD IR 生成候选窗口")
    add_recall_args(recall)
    recall.set_defaults(func=run_recall_stage)

    build_prompt = sub.add_parser("build-prompt", help="基于 NBD IR 和候选窗口生成小模型 prompt")
    add_prompt_args(build_prompt)
    build_prompt.set_defaults(func=run_build_prompt_stage)

    run_model = sub.add_parser("run-model", help="调用小模型执行已生成的 prompt")
    add_model_args(run_model)
    run_model.set_defaults(func=run_model_stage)

    report = sub.add_parser("report", help="基于模型结果生成召回矩阵和业务报告")
    add_stage_output_arg(report)
    report.set_defaults(func=run_report_stage)

    export_gold_like = sub.add_parser("export-gold-like", help="导出接近标准答案格式的工程命中结果 JSON")
    add_stage_output_arg(export_gold_like)
    export_gold_like.add_argument("--output", type=Path, help="输出 JSON 路径")
    export_gold_like.add_argument("--include-no-line", action=argparse.BooleanOptionalAction, default=True)
    export_gold_like.set_defaults(func=run_export_gold_like)

    evaluate_f1 = sub.add_parser("evaluate-f1", help="质量评测层：计算指定金标相对 NBD run 的召回率、精确率和 F1")
    evaluate_f1.add_argument("--gold-json", required=True, type=Path, help="标准答案 JSON")
    evaluate_f1.add_argument("--run-dir", required=True, type=Path, help="NBD CLI 输出目录")
    evaluate_f1.add_argument("--output-dir", type=Path, help="评测结果输出目录")
    evaluate_f1.add_argument("--line-match", choices=["range", "exact"], default="range", help="预测为范围行号时的匹配方式")
    evaluate_f1.set_defaults(func=run_evaluate_f1)

    mark_role = sub.add_parser("mark-run-role", help="质量评测层：标记 run 的 baseline/targeted/final 角色")
    mark_role.add_argument("--run-dir", required=True, type=Path)
    mark_role.add_argument("--role", required=True, choices=["baseline", "targeted", "final-full", "final-hybrid"])
    mark_role.add_argument("--case-no", type=int)
    mark_role.add_argument("--sample-name", default="")
    mark_role.add_argument("--item-category", default="")
    mark_role.add_argument("--base-run", type=Path)
    mark_role.add_argument("--targeted-run", action="append", default=[], type=Path)
    mark_role.add_argument("--nbd", action="append", default=[], help="相关 NBD，可重复；也可逗号分隔")
    mark_role.add_argument("--notes", default="")
    mark_role.set_defaults(func=run_mark_run_role)

    build_hybrid = sub.add_parser("build-hybrid", help="质量评测层：由 full run 和 targeted run 构造 final-hybrid 评测口径")
    build_hybrid.add_argument("--base-run", required=True, type=Path)
    build_hybrid.add_argument("--targeted-run", required=True, action="append", type=Path)
    build_hybrid.add_argument("--output-dir", required=True, type=Path)
    build_hybrid.add_argument("--nbd", action="append", default=[], help="只合并指定 NBD，可重复；也可逗号分隔")
    build_hybrid.add_argument("--case-no", type=int)
    build_hybrid.add_argument("--sample-name", default="")
    build_hybrid.add_argument("--item-category", default="")
    build_hybrid.add_argument("--notes", default="")
    build_hybrid.set_defaults(func=run_build_hybrid)

    compare_f1 = sub.add_parser("compare-f1-runs", help="对比两个已评测 run，F1 下降时自动输出归因报告")
    compare_f1.add_argument("--old-run", type=Path, required=True)
    compare_f1.add_argument("--new-run", type=Path, required=True)
    compare_f1.add_argument("--nbd", action="append", default=[], help="只分析指定 NBD，可重复")
    compare_f1.add_argument("--output-dir", type=Path, help="默认写入 new-run/evaluation-comparison")
    compare_f1.set_defaults(func=run_compare_f1_runs)

    diagnose_f1 = sub.add_parser("diagnose-f1", help="建设治理层：诊断 F1 漏报卡在 Document IR、候选窗口、prompt 还是模型判定")
    diagnose_f1.add_argument("--gold-json", required=True, type=Path)
    diagnose_f1.add_argument("--run-dir", required=True, type=Path)
    diagnose_f1.add_argument("--metrics-json", type=Path, help="默认读取 run-dir/evaluation/metrics.json")
    diagnose_f1.add_argument("--output-dir", type=Path, help="默认写入 run-dir/evaluation")
    diagnose_f1.set_defaults(func=run_diagnose_f1)

    create_ledger = sub.add_parser("create-ledger", help="建设治理层：生成单案例专项提升账本模板")
    create_ledger.add_argument("--output", required=True, type=Path)
    create_ledger.add_argument("--case-no", type=int)
    create_ledger.add_argument("--sample-name", default="")
    create_ledger.add_argument("--item-category", default="")
    create_ledger.add_argument("--baseline-run", type=Path)
    create_ledger.add_argument("--target-f1", type=float, default=0.9)
    create_ledger.set_defaults(func=run_create_ledger)

    record_gold_change = sub.add_parser("record-gold-change", help="质量评测层：记录或应用 V2 金标变更")
    record_gold_change.add_argument("--gold-json", required=True, type=Path)
    record_gold_change.add_argument("--ledger", type=Path, help="默认写入 gold json 同目录同名 .gold-ledger.json")
    record_gold_change.add_argument("--change-type", required=True, choices=["add-gold", "atomic-split", "downgrade-gold", "ignore-new", "reject-output"])
    record_gold_change.add_argument("--line", required=True, type=int)
    record_gold_change.add_argument("--checkpoint", required=True)
    record_gold_change.add_argument("--new-checkpoint", default="")
    record_gold_change.add_argument("--reason", required=True)
    record_gold_change.add_argument("--risk-text", default="")
    record_gold_change.add_argument("--violation-reason", default="")
    record_gold_change.add_argument("--risk-tip", default="")
    record_gold_change.add_argument("--suggestion", default="")
    record_gold_change.add_argument("--case-no", type=int)
    record_gold_change.add_argument("--sample-name", default="")
    record_gold_change.add_argument("--reviewer", default="Codex")
    record_gold_change.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    record_gold_change.set_defaults(func=run_record_gold_change)

    index_runs = sub.add_parser("index-runs", help="建设治理层：生成 validation/nbd-runs 运行产物索引")
    index_runs.add_argument("--base-dir", type=Path, default=Path("validation/nbd-runs"))
    index_runs.add_argument("--output-dir", type=Path, default=Path("validation/nbd-runs/governance"))
    index_runs.set_defaults(func=run_index_runs)

    update_summary = sub.add_parser("update-f1-summary", help="将单个 run 的 F1-V1/F1-V2 指标回写到汇总报告")
    update_summary.add_argument("--summary-md", type=Path, required=True, help="汇总报告 markdown")
    update_summary.add_argument("--case-no", type=int, required=True, help="案例编号")
    update_summary.add_argument("--run-dir", type=Path, required=True, help="已完成评测的 NBD run 目录")
    update_summary.add_argument("--status", help="可选：覆盖运行状态列")
    update_summary.add_argument("--file-label", help="可选：覆盖文件列")
    update_summary.set_defaults(func=run_update_f1_summary)

    case_quality = sub.add_parser("case-quality", help="质量评测层：执行单案例 V1/V2/V3/V4 评测、健康检查、总表回写流水线")
    case_quality.add_argument("--run-dir", required=True, type=Path)
    case_quality.add_argument("--gold-v1", required=True, type=Path)
    case_quality.add_argument("--gold-v2", required=True, type=Path)
    case_quality.add_argument("--gold-v3", type=Path, help="可选：V3 金标 JSON")
    case_quality.add_argument("--gold-v4", type=Path, help="可选：V4 金标 JSON")
    case_quality.add_argument("--case-no", type=int)
    case_quality.add_argument("--sample-name", default="")
    case_quality.add_argument("--item-category", default="")
    case_quality.add_argument("--summary-md", type=Path)
    case_quality.add_argument("--status", help="回写汇总报告的状态；默认按 target-f1 自动判断")
    case_quality.add_argument("--file-label", help="回写汇总报告的文件列")
    case_quality.add_argument("--target-f1", type=float, default=0.9)
    case_quality.add_argument("--line-match", choices=["range", "exact"], default="range")
    case_quality.add_argument("--role", choices=["baseline", "targeted", "final-full", "final-hybrid"], default="final-full")
    case_quality.add_argument("--notes", default="")
    case_quality.add_argument("--gold-like-output", type=Path)
    case_quality.add_argument("--output-json", type=Path)
    case_quality.add_argument("--output-md", type=Path)
    case_quality.add_argument("--include-no-line", action=argparse.BooleanOptionalAction, default=True)
    case_quality.set_defaults(func=run_case_quality_command)

    run = sub.add_parser("run", help="召回候选窗口并调用小模型执行 NBD")
    add_common_args(run)
    run.add_argument("--base-url", help="OpenAI 兼容接口 base_url")
    run.add_argument("--api-key", help="OpenAI 兼容接口密钥")
    run.add_argument("--model", help="模型名称")
    run.add_argument("--jobs", type=int, default=8)
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens", type=int, default=6144)
    run.add_argument("--artifact-mode", choices=["compact", "full"], default="compact", help="运行产物保留模式；compact 清理可重新生成的 prompt 和 NBD IR")
    run.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--reuse-raw-response", action=argparse.BooleanOptionalAction, default=True)
    run.set_defaults(func=run_review)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
