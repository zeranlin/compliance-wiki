#!/usr/bin/env python3
"""比较 current plain-text parser 与 experimental blocks parser 对 checkpoint CLI 的影响。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def safe_mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def run_current(vcc, review_file: Path, checkpoint_file: Path) -> dict:
    t0 = time.perf_counter()
    review_text, method = vcc.load_review_file(review_file)
    checkpoint_md = checkpoint_file.read_text(encoding="utf-8")
    keywords = vcc.parse_keyword_groups(checkpoint_md)
    cp_id = vcc.extract_checkpoint_id(checkpoint_md)
    cp_title = vcc.extract_title(checkpoint_md)
    compact = vcc.compact_checkpoint_text(checkpoint_md, 18000)
    excerpt, window_count, stats = vcc.collect_candidate_windows(
        review_text=review_text,
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
    messages = vcc.build_messages(cp_id, cp_title, compact, review_file.name, excerpt)
    return {
        "parser": "current",
        "method": method,
        "checkpoint_id": cp_id,
        "checkpoint_title": cp_title,
        "window_count": window_count,
        "raw_hit_count": stats["raw_hit_count"],
        "filtered_hit_count": stats["filtered_hit_count"],
        "selected_scores": stats["selected_scores"],
        "excerpt_chars": len(excerpt),
        "prompt_chars": len(messages[1]["content"]),
        "elapsed_seconds": time.perf_counter() - t0,
        "excerpt": excerpt,
        "messages": messages,
    }


def run_experimental(vcc, experimental, review_file: Path, checkpoint_file: Path) -> dict:
    t0 = time.perf_counter()
    blocks, lines, _ = experimental.extract_docx_blocks(review_file)
    review_text = "\n".join(line.text for line in lines)
    checkpoint_md = checkpoint_file.read_text(encoding="utf-8")
    keywords = vcc.parse_keyword_groups(checkpoint_md)
    cp_id = vcc.extract_checkpoint_id(checkpoint_md)
    cp_title = vcc.extract_title(checkpoint_md)
    compact = vcc.compact_checkpoint_text(checkpoint_md, 18000)
    excerpt, window_count, stats = vcc.collect_candidate_windows(
        review_text=review_text,
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
    messages = vcc.build_messages(cp_id, cp_title, compact, review_file.name, excerpt)
    return {
        "parser": "experimental",
        "block_count": len(blocks),
        "line_count": len(lines),
        "checkpoint_id": cp_id,
        "checkpoint_title": cp_title,
        "window_count": window_count,
        "raw_hit_count": stats["raw_hit_count"],
        "filtered_hit_count": stats["filtered_hit_count"],
        "selected_scores": stats["selected_scores"],
        "excerpt_chars": len(excerpt),
        "prompt_chars": len(messages[1]["content"]),
        "elapsed_seconds": time.perf_counter() - t0,
        "excerpt": excerpt,
        "messages": messages,
    }


def llm_verdict(vcc, base_url: str, api_key: str, model: str, messages: list[dict], timeout: int = 180) -> dict:
    raw = vcc.post_openai_compatible(
        base_url=base_url,
        api_key=api_key,
        model=model,
        messages=messages,
        temperature=0.0,
        timeout_seconds=timeout,
        max_tokens=vcc.DEFAULT_MAX_TOKENS,
    )
    parsed = vcc.parse_model_json(raw)
    normalized = vcc.normalize_result(
        parsed,
        checkpoint_id=parsed.get("checkpoint_id", ""),
        checkpoint_title=parsed.get("checkpoint_title", ""),
    )
    return {
        "verdict": normalized.get("verdict"),
        "summary": normalized.get("summary", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B 比较 checkpoint parser 前置层")
    parser.add_argument("--review-file", type=Path, required=True)
    parser.add_argument("--checkpoint-glob", default="wiki/checkpoints/*.md")
    parser.add_argument("--limit", type=int, default=0, help="只比较前 N 个 checkpoint，0 表示全量")
    parser.add_argument("--llm-sample", type=int, default=0, help="挑差异最大的前 N 个 checkpoint 做 LLM 结果漂移对比")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    root = Path.cwd()
    vcc = load_module(root / "scripts" / "validate_checkpoint_cli.py", "vcc")
    experimental = load_module(root / "scripts" / "experimental_review_blocks_cli.py", "experimental_blocks")

    checkpoint_files = sorted(root.glob(args.checkpoint_glob))
    if args.limit > 0:
        checkpoint_files = checkpoint_files[: args.limit]

    rows: list[dict] = []
    current_times: list[float] = []
    experimental_times: list[float] = []
    current_prompt_chars: list[int] = []
    experimental_prompt_chars: list[int] = []

    for checkpoint_file in checkpoint_files:
        current = run_current(vcc, args.review_file, checkpoint_file)
        experimental_result = run_experimental(vcc, experimental, args.review_file, checkpoint_file)
        row = {
            "checkpoint_file": str(checkpoint_file),
            "checkpoint_id": current["checkpoint_id"],
            "checkpoint_title": current["checkpoint_title"],
            "current": {k: v for k, v in current.items() if k not in {"excerpt", "messages"}},
            "experimental": {k: v for k, v in experimental_result.items() if k not in {"excerpt", "messages"}},
            "delta": {
                "window_count": experimental_result["window_count"] - current["window_count"],
                "excerpt_chars": experimental_result["excerpt_chars"] - current["excerpt_chars"],
                "prompt_chars": experimental_result["prompt_chars"] - current["prompt_chars"],
                "elapsed_seconds": experimental_result["elapsed_seconds"] - current["elapsed_seconds"],
            },
            "abs_prompt_delta": abs(experimental_result["prompt_chars"] - current["prompt_chars"]),
            "current_messages": current["messages"],
            "experimental_messages": experimental_result["messages"],
        }
        rows.append(row)
        current_times.append(current["elapsed_seconds"])
        experimental_times.append(experimental_result["elapsed_seconds"])
        current_prompt_chars.append(current["prompt_chars"])
        experimental_prompt_chars.append(experimental_result["prompt_chars"])

    rows.sort(key=lambda item: item["abs_prompt_delta"], reverse=True)

    summary = {
        "checkpoint_count": len(rows),
        "current_avg_elapsed_seconds": safe_mean(current_times),
        "experimental_avg_elapsed_seconds": safe_mean(experimental_times),
        "current_avg_prompt_chars": safe_mean(current_prompt_chars),
        "experimental_avg_prompt_chars": safe_mean(experimental_prompt_chars),
        "avg_prompt_delta": safe_mean(experimental_prompt_chars) - safe_mean(current_prompt_chars),
        "avg_elapsed_delta": safe_mean(experimental_times) - safe_mean(current_times),
        "top_prompt_deltas": [
            {
                "checkpoint_id": row["checkpoint_id"],
                "checkpoint_title": row["checkpoint_title"],
                "prompt_delta": row["delta"]["prompt_chars"],
                "window_delta": row["delta"]["window_count"],
            }
            for row in rows[:10]
        ],
    }

    llm_compare = []
    if args.llm_sample > 0:
        base_url = vcc.os.environ.get(vcc.ENV_BASE_URL)
        api_key = vcc.os.environ.get(vcc.ENV_API_KEY)
        model = vcc.os.environ.get(vcc.ENV_MODEL)
        if base_url and api_key and model:
            for row in rows[: args.llm_sample]:
                current_verdict = llm_verdict(vcc, base_url, api_key, model, row["current_messages"])
                experimental_verdict = llm_verdict(vcc, base_url, api_key, model, row["experimental_messages"])
                llm_compare.append(
                    {
                        "checkpoint_id": row["checkpoint_id"],
                        "checkpoint_title": row["checkpoint_title"],
                        "current": current_verdict,
                        "experimental": experimental_verdict,
                    }
                )
        else:
            llm_compare.append({"error": "缺少本地模型环境变量，未执行 llm_sample 对比"})

    output = {
        "review_file": str(args.review_file),
        "summary": summary,
        "llm_compare": llm_compare,
        "rows": [
            {
                k: v
                for k, v in row.items()
                if k not in {"current_messages", "experimental_messages"}
            }
            for row in rows
        ],
    }

    if args.output_json:
        args.output_json.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(args.output_json))
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
