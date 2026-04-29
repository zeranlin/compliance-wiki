#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION_LIST = ROOT / "wiki/bd-review-points/audits/NBD建设清单.md"
OUTPUT = ROOT / "wiki/bd-review-points/audits/NBD全量分型计划.md"

MAINTAINED_REFERENCES = {
    "明确禁止型": "NBD01-001 / NBD01-003",
    "评分因素型": "NBD02-001 / NBD02-007",
    "关联比较型": "NBD02-015",
    "合理性判断型": "NBD03-001",
    "配置缺失型": "NBD04-001",
    "政策判断型": "NBD05-003",
    "数值比例型": "NBD06-003",
    "履约配置型": "NBD06-006",
    "品目专项型": "NBD07-002 / NBD07-021",
}

TYPE_BATCH = {
    "明确禁止型": "第一批",
    "评分因素型": "第一批",
    "数值比例型": "第一批",
    "履约配置型": "第一批",
    "配置缺失型": "第二批",
    "政策判断型": "第二批",
    "关联比较型": "第三批",
    "合理性判断型": "第三批",
    "品目专项型": "第三批",
}

TYPE_CONTEXT = {
    "明确禁止型": "资格/准入章节；必要时读取格式区排除噪声",
    "评分因素型": "评分表；必要时读取证明材料和资格条件",
    "关联比较型": "评分表 + 采购需求/商务要求/技术要求",
    "合理性判断型": "资格/评分/证明材料 + 采购需求/品目事实",
    "配置缺失型": "正式公告/配置章节 + 全文确认",
    "政策判断型": "预算/品目/采购包 + 政策设置章节",
    "数值比例型": "金额条款 + 预算/最高限价/合同金额",
    "履约配置型": "合同/履约/分包/联合体章节",
    "品目专项型": "项目名称/清单/技术参数 + 专项资质/证书要求",
}


def parse_construction_rows() -> list[dict[str, str]]:
    text = CONSTRUCTION_LIST.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    in_table = False
    headers = [
        "nbd_id",
        "excel_row",
        "source_no",
        "domain",
        "item_scope",
        "risk_level",
        "finding_type",
        "standard_scope",
        "law_status",
        "is_sample",
        "title",
        "rule_summary",
    ]
    for line in text.splitlines():
        if line.startswith("| NBD ID | Excel行"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < len(headers):
            continue
        rows.append(dict(zip(headers, parts[: len(headers)])))
    return rows


def has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def classify(row: dict[str, str]) -> tuple[str, str, str]:
    nbd_id = row["nbd_id"]
    domain = row["domain"]
    item_scope = row["item_scope"]
    title = row["title"]
    rule = row["rule_summary"]
    text = f"{title} {rule}"

    if row["is_sample"] == "是":
        sample_map = {
            "NBD01-001": ("明确禁止型", "高", "首批 maintained 标杆"),
            "NBD01-003": ("明确禁止型", "高", "首批 maintained 标杆"),
            "NBD02-001": ("评分因素型", "高", "首批 maintained 标杆"),
            "NBD02-007": ("评分因素型", "高", "首批 maintained 标杆"),
            "NBD02-015": ("关联比较型", "高", "首批 maintained 标杆"),
            "NBD03-001": ("合理性判断型", "高", "首批 maintained 标杆"),
            "NBD04-001": ("配置缺失型", "高", "首批 maintained 标杆"),
            "NBD05-003": ("政策判断型", "高", "首批 maintained 标杆"),
            "NBD06-003": ("数值比例型", "高", "首批 maintained 标杆"),
            "NBD06-006": ("履约配置型", "高", "首批 maintained 标杆"),
            "NBD07-002": ("品目专项型", "高", "首批 maintained 标杆"),
            "NBD07-021": ("品目专项型", "高", "首批 maintained 标杆"),
        }
        if nbd_id in sample_map:
            return sample_map[nbd_id]

    if has_any(text, ["特定金额的业绩", "特定金额业绩"]):
        if domain.startswith("NBD02"):
            return ("评分因素型", "高", "金额业绩限制作为评分因素，核心仍是评分后果")
        return ("明确禁止型", "高", "金额业绩限制作为资格或准入条件")

    if has_any(text, ["联合体企业合同金额比例", "分包的具体内容、金额", "分包的具体内容", "允许采用分包"]):
        return ("履约配置型", "高", "联合体或分包履约边界配置")

    if has_any(text, ["必须设定服务地点", "需明确投标人资质证明", "明确最高限价", "必须设定采购项目预算金额", "须设定明确的投标报价要求", "需说明投标文件编制要求", "须按规定设置实质性条款", "内容一致性校验", "疑似错别字检查", "文件乱码检测"]):
        return ("配置缺失型", "中", "文件内容、格式或必备配置完整性问题")

    if has_any(text, ["含有GB", "国家强制性标准", "★号"]):
        return ("配置缺失型", "中", "强制性标准标识配置问题")

    if has_any(text, ["履约保证金退还方式", "履约验收方案"]):
        return ("履约配置型", "高", "合同履约配置完整性问题")

    if has_any(text, ["合法保证金形式"]):
        return ("明确禁止型", "中", "保证金形式限制，不是金额比例计算")

    if has_any(text, ["合同履行期限", "质保期", "10个工作日"]):
        return ("数值比例型", "高", "需要抽取期限并与规则上限比较")

    if domain.startswith("NBD07") or item_scope not in {"", "通用"}:
        if has_any(text, ["比例", "经费", "金额"]) and has_any(text, ["不得超过", "按政策", "比例"]):
            return ("数值比例型", "中", "品目专项中含比例计算，生成时应同时参考品目专项型")
        if has_any(text, ["评审项", "评分", "与需求对应", "是否完整", "冲突"]):
            return ("关联比较型", "中", "品目专项中的评分/需求对照问题")
        if has_any(text, ["合理设置", "相符", "资质要求", "证书作为资格条件"]):
            return ("合理性判断型", "中", "品目专项中的资质合理性问题")
        return ("品目专项型", "高", "按品目事实先行识别")

    if domain.startswith("NBD05"):
        return ("政策判断型", "高", "政府采购政策类")

    if has_any(text, ["未在采购需求", "采购需求的关联度", "与采购需求", "需求对应", "技术参数", "冲突", "是否完整"]):
        return ("关联比较型", "中", "需要比较评分/要求与采购需求")

    if has_any(text, ["合理性", "合理设置", "认证范围", "关联度", "不相符", "证书设置", "资质要求"]):
        return ("合理性判断型", "中", "需要判断要求与采购标的的必要关联")

    if has_any(text, ["保证金", "支付", "比例", "金额", "预算金额", "价格扣除", "400万", "200万"]):
        if domain.startswith("NBD06") or has_any(text, ["不得超过", "超出", "比例", "金额", "预算"]):
            return ("数值比例型", "高", "需要抽取金额/比例/期限")

    if has_any(text, ["分包", "联合体企业合同金额", "合同金额比例", "履约", "合同"]):
        return ("履约配置型", "高", "履约或合同配置类")

    if has_any(text, ["需载明", "载明", "需设定", "需补充", "未明确", "详细说明", "正确设置采购方式", "核心产品"]):
        return ("配置缺失型", "中", "正式章节配置缺失或信息不完整")

    if domain.startswith("NBD02") or has_any(text, ["评审", "评分", "得分", "加分", "作为评审因素", "评分项"]):
        return ("评分因素型", "高", "评审规则类")

    if domain.startswith("NBD01") or has_any(text, ["资格条件", "合格供应商", "不得限定", "不得将", "不得要求", "不得设置"]):
        return ("明确禁止型", "高", "资格或准入限制类")

    if domain.startswith("NBD04"):
        return ("配置缺失型", "中", "内容规范配置类")

    if domain.startswith("NBD03"):
        return ("合理性判断型", "中", "需求合理性类")

    return ("合理性判断型", "低", "规则无法稳定初分，需人工复核")


def priority(row: dict[str, str], nbd_type: str, confidence: str) -> str:
    if row["is_sample"] == "是":
        return "标杆已完成"
    if confidence == "低":
        return "暂缓"
    if TYPE_BATCH[nbd_type] == "第一批":
        return "优先生成"
    if TYPE_BATCH[nbd_type] == "第二批":
        return "第二批生成"
    return "后置生成"


def escape_cell(value: str) -> str:
    return value.replace("\n", " / ").replace("|", "／").strip()


def main() -> None:
    rows = parse_construction_rows()
    enriched = []
    for row in rows:
        nbd_type, confidence, note = classify(row)
        row = dict(row)
        row["nbd_type"] = nbd_type
        row["confidence"] = confidence
        row["batch"] = TYPE_BATCH[nbd_type]
        row["priority"] = priority(row, nbd_type, confidence)
        row["support_context"] = TYPE_CONTEXT[nbd_type]
        row["reference"] = MAINTAINED_REFERENCES[nbd_type]
        row["note"] = note
        enriched.append(row)

    by_type = Counter(row["nbd_type"] for row in enriched)
    by_batch = Counter(row["batch"] for row in enriched)
    by_priority = Counter(row["priority"] for row in enriched)
    by_conf = Counter(row["confidence"] for row in enriched)

    lines: list[str] = []
    lines.extend(
        [
            "---",
            "id: nbd-full-typing-plan",
            "title: NBD 全量分型计划",
            "page_type: nbd-typing-plan",
            "status: draft",
            "last_reviewed: 2026-04-28",
            "---",
            "",
            "上级导航：[[../index|新版 BD 审查点明细库]]",
            "",
            "# NBD 全量分型计划",
            "",
            "## 1. 定位",
            "本计划用于把 `通用（深圳）` 来源的 153 个 NBD 执行单元映射到已验证的 NBD 类型标杆，作为后续全量生成、分批验证和升级 maintained 的生产排程。",
            "",
            "本计划是初分型计划，不是最终业务结论。置信度为 `中` 或 `低` 的条目，在生成前应人工复核类型和支持上下文。",
            "",
            "## 2. 分型依据",
            "- 来源清单：[[NBD建设清单|NBD 建设清单]]",
            "- 类型模板：[[../NBD类型标杆手册|NBD 类型标杆手册]]",
            "- 生成原则：先归类，再生成；先 fixture，再验收；先小批量调通，再扩展全量。",
            "",
            "## 3. 汇总",
            "### 3.1 按类型",
            "| 类型 | 数量 | maintained 参照 |",
            "|---|---:|---|",
        ]
    )
    for nbd_type, count in sorted(by_type.items()):
        lines.append(f"| {nbd_type} | {count} | {MAINTAINED_REFERENCES[nbd_type]} |")

    lines.extend(["", "### 3.2 按批次", "| 批次 | 数量 |", "|---|---:|"])
    for batch in ["第一批", "第二批", "第三批"]:
        lines.append(f"| {batch} | {by_batch[batch]} |")

    lines.extend(["", "### 3.3 按优先级", "| 优先级 | 数量 |", "|---|---:|"])
    for key in ["标杆已完成", "优先生成", "第二批生成", "后置生成", "暂缓"]:
        if by_priority[key]:
            lines.append(f"| {key} | {by_priority[key]} |")

    lines.extend(["", "### 3.4 按分型置信度", "| 置信度 | 数量 |", "|---|---:|"])
    for key in ["高", "中", "低"]:
        lines.append(f"| {key} | {by_conf[key]} |")

    first_batch = [row for row in enriched if row["priority"] == "优先生成"]
    pilot_quota = {
        "明确禁止型": 8,
        "评分因素型": 8,
        "数值比例型": 5,
        "履约配置型": 3,
    }
    pilot_batch = []
    used_ids = set()
    for nbd_type, quota in pilot_quota.items():
        picked = [
            row
            for row in first_batch
            if row["nbd_type"] == nbd_type and row["confidence"] == "高" and row["nbd_id"] not in used_ids
        ][:quota]
        pilot_batch.extend(picked)
        used_ids.update(row["nbd_id"] for row in picked)
    lines.extend(
        [
            "",
            "## 4. 第一批建议",
            "第一批建议优先生成判断链较短、标杆稳定的类型：明确禁止型、评分因素型、数值比例型、履约配置型。",
            "",
            f"- 第一批可生成数量：{len(first_batch)}",
            f"- 先导批建议数量：{len(pilot_batch)}",
            "- 生成后先做召回预检，再每类抽样 smoke。",
            "- 如果第一批中出现大量中置信度条目，应先拆出待复核组，不进入批量页面生成。",
            "",
            "### 4.1 先导批",
            "先导批用于验证 Excel 驱动生成脚本和类型模板，不追求覆盖全部第一批。建议先生成下列条目，确认页面质量、召回窗口和小模型输出稳定后，再扩展到完整第一批。",
            "",
            "| NBD ID | 类型 | 审查点 | maintained 参照 |",
            "|---|---|---|---|",
        ]
    )
    for row in pilot_batch:
        lines.append(
            "| {nbd_id} | {nbd_type} | {title} | {reference} |".format(
                **{k: escape_cell(v) for k, v in row.items()}
            )
        )

    lines.extend(
        [
            "",
            "### 4.2 完整第一批",
            "| NBD ID | 类型 | 置信度 | 审查点 | maintained 参照 |",
            "|---|---|---|---|---|",
        ]
    )
    for row in first_batch:
        lines.append(
            "| {nbd_id} | {nbd_type} | {confidence} | {title} | {reference} |".format(
                **{k: escape_cell(v) for k, v in row.items()}
            )
        )

    lines.extend(
        [
            "",
            "## 5. 全量分型明细",
            "| NBD ID | Excel行 | 问题域 | 品目 | 风险等级 | 类型 | 批次 | 优先级 | 置信度 | 支持上下文 | maintained 参照 | 审查点 | 备注 |",
            "|---|---:|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for row in enriched:
        safe = {k: escape_cell(v) for k, v in row.items()}
        lines.append(
            "| {nbd_id} | {excel_row} | {domain} | {item_scope} | {risk_level} | {nbd_type} | {batch} | {priority} | {confidence} | {support_context} | {reference} | {title} | {note} |".format(
                **safe
            )
        )

    lines.extend(
        [
            "",
            "## 6. 生成前检查",
            "- `高` 置信度条目可以进入对应批次生成。",
            "- `中` 置信度条目生成前应检查是否跨类型，必要时拆成主类型和辅助上下文。",
            "- `低` 置信度条目暂缓生成，先补业务定义或法规依据。",
            "- 任何条目生成后都不得直接升级 maintained，必须先经过召回预检和小模型 smoke。",
            "",
            "## 7. 下一步",
            "建议先基于本计划新建 Excel 驱动的 NBD 生成脚本，且默认不覆盖 12 个 maintained 标杆。第一批生成范围控制在 `优先生成` 条目内，生成状态使用 `draft` 或 `testing`。",
        ]
    )

    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} rows={len(enriched)}")
    print("types", dict(sorted(by_type.items())))
    print("priorities", dict(sorted(by_priority.items())))


if __name__ == "__main__":
    main()
