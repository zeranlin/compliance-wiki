#!/usr/bin/env python3
"""NBD 日常审查 CLI。

第一版保持极简：入口参数在本文件，核心流程在 engine.py。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engine import (
    run_build_prompt_stage,
    run_compile_document,
    run_compile_nbd,
    run_lint_runtime,
    run_model_stage,
    run_preflight,
    run_recall_stage,
    run_report_stage,
    run_review,
)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--review-file", type=Path, required=True, help="待审查文件")
    parser.add_argument("--nbd", action="append", default=[], help="单个 NBD 文件路径或 NBD id，可重复")
    parser.add_argument("--nbd-glob", default="wiki/bd-review-points/items/NBD*.md", help="NBD 文件 glob")
    parser.add_argument("--theme", type=Path, help="NBD 主题页，读取 frontmatter nbd_ids")
    parser.add_argument("--output-dir", type=Path, help="输出目录")
    parser.add_argument("--max-primary-windows", type=int, default=5)
    parser.add_argument("--max-support-windows", type=int, default=3)
    parser.add_argument("--max-window-chars", type=int, default=5000)
    parser.add_argument("--max-prompt-chars", type=int, default=16000)


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


def add_recall_args(parser: argparse.ArgumentParser) -> None:
    add_stage_output_arg(parser)
    parser.add_argument("--nbd", action="append", default=[], help="只处理指定 NBD id，可重复")
    parser.add_argument("--max-primary-windows", type=int, default=5)
    parser.add_argument("--max-support-windows", type=int, default=3)
    parser.add_argument("--max-window-chars", type=int, default=5000)


def add_prompt_args(parser: argparse.ArgumentParser) -> None:
    add_stage_output_arg(parser)
    parser.add_argument("--nbd", action="append", default=[], help="只处理指定 NBD id，可重复")
    parser.add_argument("--max-prompt-chars", type=int, default=16000)


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
    parser = argparse.ArgumentParser(description="NBD 日常审查 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight", help="只做候选窗口召回，不调用模型")
    add_common_args(preflight)
    preflight.set_defaults(func=run_preflight)

    lint_runtime = sub.add_parser("lint-runtime", help="检查运行时代码是否混入 NBD 专属业务硬编码")
    lint_runtime.add_argument("--path", type=Path, help="默认检查 scripts/nbd_review")
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

    run = sub.add_parser("run", help="召回候选窗口并调用小模型执行 NBD")
    add_common_args(run)
    run.add_argument("--base-url", help="OpenAI 兼容接口 base_url")
    run.add_argument("--api-key", help="OpenAI 兼容接口密钥")
    run.add_argument("--model", help="模型名称")
    run.add_argument("--jobs", type=int, default=8)
    run.add_argument("--timeout", type=int, default=1800)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens", type=int, default=6144)
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
