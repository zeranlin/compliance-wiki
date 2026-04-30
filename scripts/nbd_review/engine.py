#!/usr/bin/env python3
"""Compatibility facade for the NBD daily review CLI.

The implementation is split across compiler, recall, prompt, model, and reporting modules.
This file intentionally remains thin so runtime orchestration does not grow into a second rule base.
"""

from __future__ import annotations

from pipeline import (
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

__all__ = [
    "run_build_prompt_stage",
    "run_compile_document",
    "run_compile_nbd",
    "run_lint_runtime",
    "run_model_stage",
    "run_preflight",
    "run_recall_stage",
    "run_report_stage",
    "run_review",
]
