"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from shared.schemas import MODEL_REVIEW_RESULT_SCHEMA, CandidateWindow, DocumentBlock, NBDItem
from business_review.postprocessor import (
    dedupe_model_candidates,
    model_quality_flags,
    prune_output_constraint_violations,
    prune_self_rejected_positive_candidates,
    repair_verdict_candidate_consistency,
)
from business_review.prompt_runner import build_messages, prompt_stats, read_prompt_messages, write_prompt_files
from business_review.recall_runner import build_candidate_windows, candidate_set_payload, load_candidate_set_payload
from business_review.nbd_compiler import parse_output_constraints
from shared.utils import now_text, read_text, relative_path, run_path, vcc, write_text

def artifact_refs(output_dir: Path, item: NBDItem) -> dict[str, str]:
    return {
        "document_ir": run_path(output_dir, output_dir / "document-ir.json"),
        "nbd_ir": run_path(output_dir, output_dir / "nbd-ir" / f"{item.nbd_id}.json"),
        "candidate_file": run_path(output_dir, output_dir / "candidates" / f"{item.nbd_id}.json"),
        "prompt_file": run_path(output_dir, output_dir / "prompts" / f"{item.nbd_id}.md"),
        "raw_response_file": run_path(output_dir, output_dir / "raw-responses" / f"{item.nbd_id}.json"),
    }


def resolve_run_ref(output_dir: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else output_dir / path


def result_has_current_artifacts(output_dir: Path, report: dict[str, Any], item: NBDItem) -> bool:
    refs = artifact_refs(output_dir, item)
    for key, expected in refs.items():
        if report.get(key) != expected:
            return False
        if not resolve_run_ref(output_dir, expected).exists():
            return False
    return True


def normalize_nbd_result(result: dict[str, Any], item: NBDItem) -> dict[str, Any]:
    result.setdefault("schema_version", MODEL_REVIEW_RESULT_SCHEMA)
    result.setdefault("nbd_id", item.nbd_id)
    result.setdefault("nbd_title", item.title)
    if result.get("verdict") not in {"命中", "待人工复核", "不命中"}:
        result["verdict"] = "待人工复核"
    if not isinstance(result.get("candidates"), list):
        result["candidates"] = []
    result["candidate_count"] = len(result["candidates"])
    result.setdefault("risk_tip", "")
    result.setdefault("revision_suggestion", "")
    if not isinstance(result.get("legal_basis"), list):
        result["legal_basis"] = []
    return result


def output_constraints_for(item: NBDItem) -> dict[str, Any]:
    if isinstance(item.meta.get("_output_constraints"), dict):
        return dict(item.meta.get("_output_constraints") or {})
    return parse_output_constraints(item.markdown)


def write_model_result_artifact(
    output_dir: Path,
    review_file: Path,
    facts: dict[str, Any],
    item: NBDItem,
    args: Any,
) -> dict[str, Any]:
    item_dir = output_dir / "items" / item.nbd_id
    result_file = item_dir / "result.json"
    if args.resume and result_file.exists():
        existing_report = json.loads(read_text(result_file))
        if result_has_current_artifacts(output_dir, existing_report, item):
            return existing_report
    candidate_payload = load_candidate_set_payload(output_dir, item)
    windows = [CandidateWindow(**window) for window in candidate_payload.get("windows", [])]
    recall_stats = candidate_payload.get("recall_stats") or {}
    refs = artifact_refs(output_dir, item)
    messages = read_prompt_messages(output_dir, item)
    raw_response_file = output_dir / "raw-responses" / f"{item.nbd_id}.json"
    started_at = now_text()
    response = call_model(args, messages, raw_response_file)
    model_result = normalize_nbd_result(vcc.parse_model_json(response), item)
    ended_at = now_text()
    report = {
        "started_at": started_at,
        "ended_at": ended_at,
        "model": args.model or os.environ.get(vcc.ENV_MODEL) or "",
        "nbd": {"id": item.nbd_id, "title": item.title, **item.meta},
        "nbd_path": relative_path(item.path),
        "review_file": relative_path(review_file),
        **refs,
        "candidate_window_count": len(windows),
        "recall_stats": recall_stats,
        "windows": [asdict(window) for window in windows],
        "output_constraints": output_constraints_for(item),
        "model_result": model_result,
    }
    prune_self_rejected_positive_candidates(report)
    prune_output_constraint_violations(report)
    repair_verdict_candidate_consistency(report)
    dedupe_model_candidates(report)
    flags = model_quality_flags(report)
    report["quality_flags"] = flags
    model_result["quality_flags"] = flags
    write_text(result_file, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(item_dir / "summary.md", f"# {item.nbd_id} {item.title} 摘要\n\n- 结果：{model_result.get('verdict')}\n- 摘要：{model_result.get('summary')}\n- 召回质量：{recall_stats.get('recall_quality')}\n")
    return report


def call_model(args: Any, messages: list[dict[str, str]], raw_response_file: Path) -> dict[str, Any]:
    if args.reuse_raw_response and raw_response_file.exists():
        return json.loads(read_text(raw_response_file))
    base_url = args.base_url or os.environ.get(vcc.ENV_BASE_URL)
    api_key = args.api_key or os.environ.get(vcc.ENV_API_KEY)
    model = args.model or os.environ.get(vcc.ENV_MODEL)
    if not base_url or not api_key or not model:
        raise RuntimeError("缺少模型配置：--base-url/--api-key/--model 或环境变量")
    response = vcc.post_openai_compatible(base_url, api_key, model, messages, args.temperature, args.timeout, args.max_tokens)
    if _chat_content_is_empty(response):
        response = post_responses_stream_compatible(base_url, api_key, model, messages, args.timeout)
    write_text(raw_response_file, json.dumps(response, ensure_ascii=False, indent=2) + "\n")
    return response


def _chat_content_is_empty(response: dict[str, Any]) -> bool:
    try:
        return response["choices"][0]["message"].get("content") is None
    except Exception:
        return False


def _responses_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3]
    return value + "/responses"


def _split_instructions_and_input(messages: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
    instructions = "\n\n".join(str(message.get("content") or "") for message in messages if message.get("role") == "system")
    input_messages = [
        {"role": str(message.get("role") or "user"), "content": str(message.get("content") or "")}
        for message in messages
        if message.get("role") != "system"
    ]
    return instructions or "/no_think\n只输出严格 JSON。", input_messages


def _parse_responses_sse(text: str) -> str:
    chunks: list[str] = []
    done_text = ""
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload_text = line[6:].strip()
        if payload_text == "[DONE]":
            continue
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue
        event_type = payload.get("type")
        if event_type == "response.output_text.delta":
            chunks.append(str(payload.get("delta") or ""))
        elif event_type == "response.output_text.done":
            done_text = str(payload.get("text") or "")
    return done_text or "".join(chunks)


def post_responses_stream_compatible(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout_seconds: int,
) -> dict[str, Any]:
    instructions, input_messages = _split_instructions_and_input(messages)
    payload = {
        "model": model,
        "instructions": instructions,
        "input": input_messages,
        "store": False,
        "stream": True,
    }
    request = urllib.request.Request(
        _responses_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            stream_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Responses API failed: HTTP {exc.code} {detail[:1000]}") from exc
    content = _parse_responses_sse(stream_text)
    if not content.strip():
        raise RuntimeError("Responses API 未返回 output_text")
    return {
        "object": "chat.completion",
        "model": model,
        "adapter": "responses-stream",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
    }


def run_one_item(args: Any, review_file: Path, output_dir: Path, blocks: list[DocumentBlock], facts: dict[str, Any], item: NBDItem) -> dict[str, Any]:
    result_file = output_dir / "items" / item.nbd_id / "result.json"
    if args.resume and result_file.exists():
        existing_report = json.loads(read_text(result_file))
        if result_has_current_artifacts(output_dir, existing_report, item):
            return existing_report
    windows, recall_stats = build_candidate_windows(
        blocks,
        item,
        max_primary=args.max_primary_windows,
        max_support=args.max_support_windows,
        max_window_chars=args.max_window_chars,
    )
    refs = artifact_refs(output_dir, item)
    candidate_file = output_dir / "candidates" / f"{item.nbd_id}.json"
    candidate_payload = candidate_set_payload(item, windows, recall_stats)
    write_text(candidate_file, json.dumps(candidate_payload, ensure_ascii=False, indent=2) + "\n")
    messages = build_messages(item, review_file.name, facts, windows, args.max_prompt_chars)
    write_prompt_files(output_dir, item, messages, prompt_stats(item, messages, args.max_prompt_chars))
    raw_response_file = output_dir / "raw-responses" / f"{item.nbd_id}.json"
    started_at = now_text()
    response = call_model(args, messages, raw_response_file)
    model_result = normalize_nbd_result(vcc.parse_model_json(response), item)
    ended_at = now_text()
    item_dir = output_dir / "items" / item.nbd_id
    report = {
        "started_at": started_at,
        "ended_at": ended_at,
        "model": args.model or os.environ.get(vcc.ENV_MODEL) or "",
        "nbd": {"id": item.nbd_id, "title": item.title, **item.meta},
        "nbd_path": relative_path(item.path),
        "review_file": relative_path(review_file),
        **refs,
        "candidate_window_count": len(windows),
        "recall_stats": recall_stats,
        "windows": [asdict(window) for window in windows],
        "output_constraints": output_constraints_for(item),
        "model_result": model_result,
    }
    prune_self_rejected_positive_candidates(report)
    prune_output_constraint_violations(report)
    repair_verdict_candidate_consistency(report)
    dedupe_model_candidates(report)
    flags = model_quality_flags(report)
    report["quality_flags"] = flags
    model_result["quality_flags"] = flags
    write_text(result_file, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_text(item_dir / "summary.md", f"# {item.nbd_id} {item.title} 摘要\n\n- 结果：{model_result.get('verdict')}\n- 摘要：{model_result.get('summary')}\n- 召回质量：{recall_stats.get('recall_quality')}\n")
    return report
