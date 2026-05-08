"""V2 gold change ledger utilities.

This module belongs to the quality evaluation layer. It records and optionally
applies gold-answer calibration decisions. It must not be imported by the daily
business review runtime.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from shared.utils import now_text, relative_path, write_text


CHANGE_TYPES = {
    "atomic-split",
    "add-gold",
    "ignore-new",
    "downgrade-gold",
    "reject-output",
}


@dataclass(frozen=True)
class GoldChange:
    change_type: str
    line: int
    checkpoint: str
    reason: str
    new_checkpoint: str = ""
    risk_text: str = ""
    violation_reason: str = ""
    risk_tip: str = ""
    suggestion: str = ""
    case_no: int | None = None
    sample_name: str = ""
    reviewer: str = "Codex"
    created_at: str = ""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def gold_rows(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("检查结果") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("cannot find 检查结果 list in gold json")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("gold 检查结果 must contain only object rows")
    return rows


def row_line(row: dict[str, Any]) -> int | None:
    value = row.get("行号") or row.get("line") or row.get("line_no")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def split_names(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").replace("，", ",").split(",") if item.strip()]


def join_names(names: list[str]) -> str:
    return ", ".join(dict.fromkeys(item for item in names if item))


def matching_rows(rows: list[dict[str, Any]], line: int, checkpoint: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        if row_line(row) != line:
            continue
        names = split_names(str(row.get("审查点名称") or ""))
        if checkpoint in names or str(row.get("审查点名称") or "") == checkpoint:
            matches.append(row)
    return matches


def ensure_metadata(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("gold metadata requires object-style gold json")
    meta = payload.get("V2元数据")
    if not isinstance(meta, dict):
        meta = {}
        payload["V2元数据"] = meta
    return meta


def append_metadata_note(payload: Any, change: GoldChange) -> None:
    meta = ensure_metadata(payload)
    note = (
        f"{change.created_at}：{change.reviewer} {change.change_type} "
        f"line{change.line} {change.checkpoint}"
    )
    if change.new_checkpoint:
        note += f" -> {change.new_checkpoint}"
    note += f"；{change.reason}"
    previous = str(meta.get("最近校准") or "").strip()
    meta["最近校准"] = f"{previous} {note}".strip() if previous else note
    changes = meta.get("结构化变更记录")
    if not isinstance(changes, list):
        changes = []
        meta["结构化变更记录"] = changes
    changes.append(asdict(change))


def apply_add_gold(rows: list[dict[str, Any]], change: GoldChange) -> None:
    if not change.risk_text:
        raise ValueError("add-gold requires --risk-text")
    if matching_rows(rows, change.line, change.new_checkpoint or change.checkpoint):
        return
    rows.append(
        {
            "行号": change.line,
            "风险原文": change.risk_text,
            "审查点名称": change.new_checkpoint or change.checkpoint,
            "违规原因": change.violation_reason or change.reason,
            "风险提示": change.risk_tip or "Codex 裁判确认属于 151 NBD 覆盖范围内的真实风险，纳入 V2 评测。",
            "修改建议": change.suggestion or "按对应 NBD SOP 核查并修改采购文件表述。",
        }
    )


def apply_ignore_new(rows: list[dict[str, Any]], change: GoldChange) -> None:
    targets = matching_rows(rows, change.line, change.checkpoint)
    if not targets:
        raise ValueError(f"cannot find gold row for line={change.line}, checkpoint={change.checkpoint}")
    for row in targets:
        names = split_names(str(row.get("审查点名称") or ""))
        if change.checkpoint in names:
            names = [f"{name}（新增）" if name == change.checkpoint else name for name in names]
            row["审查点名称"] = join_names(names)
        else:
            row["审查点名称"] = f"{row.get('审查点名称')}（新增）"


def apply_downgrade_gold(rows: list[dict[str, Any]], change: GoldChange) -> None:
    targets = matching_rows(rows, change.line, change.checkpoint)
    if not targets:
        raise ValueError(f"cannot find gold row for line={change.line}, checkpoint={change.checkpoint}")
    for row in targets:
        names = [name for name in split_names(str(row.get("审查点名称") or "")) if name != change.checkpoint]
        if change.new_checkpoint and change.new_checkpoint not in names:
            names.append(change.new_checkpoint)
        if not names:
            raise ValueError("downgrade would remove all checkpoint names")
        row["审查点名称"] = join_names(names)
        if change.reason:
            row["风险提示"] = f"{row.get('风险提示') or ''} 本条已裁判降级：{change.reason}".strip()


def apply_atomic_split(rows: list[dict[str, Any]], change: GoldChange) -> None:
    targets = matching_rows(rows, change.line, change.checkpoint)
    if not targets:
        raise ValueError(f"cannot find gold row for line={change.line}, checkpoint={change.checkpoint}")
    if not change.new_checkpoint:
        raise ValueError("atomic-split requires --new-checkpoint")
    for row in targets:
        names = split_names(str(row.get("审查点名称") or ""))
        if change.new_checkpoint not in names:
            names.append(change.new_checkpoint)
        row["审查点名称"] = join_names(names)


def apply_gold_change(gold_json: Path, change: GoldChange, apply: bool = False) -> dict[str, Any]:
    payload = load_json(gold_json)
    rows = gold_rows(payload)
    if apply:
        if change.change_type == "add-gold":
            apply_add_gold(rows, change)
        elif change.change_type == "ignore-new":
            apply_ignore_new(rows, change)
        elif change.change_type == "downgrade-gold":
            apply_downgrade_gold(rows, change)
        elif change.change_type == "atomic-split":
            apply_atomic_split(rows, change)
        elif change.change_type == "reject-output":
            pass
        else:
            raise ValueError(f"unknown change type: {change.change_type}")
        append_metadata_note(payload, change)
        write_json(gold_json, payload)
    return asdict(change)


def append_ledger(ledger_path: Path, gold_json: Path, change: GoldChange, applied: bool) -> Path:
    existing: dict[str, Any] = {}
    if ledger_path.exists():
        existing = load_json(ledger_path)
        if not isinstance(existing, dict):
            existing = {}
    changes = existing.get("changes")
    if not isinstance(changes, list):
        changes = []
    changes.append({**asdict(change), "gold_json": str(gold_json), "applied": applied})
    payload = {
        "schema_version": "nbd-v2-gold-change-ledger/v1",
        "updated_at": now_text(),
        "gold_json": str(gold_json),
        "changes": changes,
    }
    write_json(ledger_path, payload)
    write_text(ledger_path.with_suffix(".md"), render_ledger_markdown(payload))
    return ledger_path


def render_ledger_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# V2 金标变更账本",
        "",
        f"- 更新时间：{payload.get('updated_at', '')}",
        f"- 标准答案：`{payload.get('gold_json', '')}`",
        "",
        "| 时间 | 类型 | 行号 | 原审查点 | 调整后审查点 | 是否应用 | 理由 |",
        "|---|---|---:|---|---|---|---|",
    ]
    for item in payload.get("changes") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("created_at") or ""),
                    str(item.get("change_type") or ""),
                    str(item.get("line") or ""),
                    str(item.get("checkpoint") or ""),
                    str(item.get("new_checkpoint") or ""),
                    "是" if item.get("applied") else "否",
                    str(item.get("reason") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="记录或应用 V2 金标变更")
    parser.add_argument("--gold-json", required=True, type=Path)
    parser.add_argument("--ledger", type=Path, help="默认写入 gold json 同目录同名 .gold-ledger.json")
    parser.add_argument("--change-type", required=True, choices=sorted(CHANGE_TYPES))
    parser.add_argument("--line", required=True, type=int)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--new-checkpoint", default="")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--risk-text", default="")
    parser.add_argument("--violation-reason", default="")
    parser.add_argument("--risk-tip", default="")
    parser.add_argument("--suggestion", default="")
    parser.add_argument("--case-no", type=int)
    parser.add_argument("--sample-name", default="")
    parser.add_argument("--reviewer", default="Codex")
    parser.add_argument("--apply", action=argparse.BooleanOptionalAction, default=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
