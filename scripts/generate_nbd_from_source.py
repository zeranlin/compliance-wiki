#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import openpyxl


ROOT = Path(__file__).resolve().parents[1]
SOURCE_XLSX = ROOT / "casesrc/01-合规性审查需求分析（新版架构）.xlsx"
PLAN = ROOT / "wiki/bd-review-points/audits/NBD全量分型计划.md"
ITEMS_DIR = ROOT / "wiki/bd-review-points/items"
REPORT_DIR = ROOT / "wiki/bd-review-points/audits"

MAINTAINED_IDS = {
    "NBD01-001",
    "NBD01-003",
    "NBD02-001",
    "NBD02-007",
    "NBD02-015",
    "NBD03-001",
    "NBD04-001",
    "NBD05-003",
    "NBD06-003",
    "NBD06-006",
    "NBD07-002",
    "NBD07-021",
}

TESTING_IDS = {
    "NBD01-002",
    "NBD01-004",
    "NBD01-023",
    "NBD01-032",
    "NBD02-002",
    "NBD02-003",
    "NBD02-014",
    "NBD02-027",
    "NBD02-028",
    "NBD02-029",
    "NBD02-030",
    "NBD02-039",
    "NBD02-042",
    "NBD06-018",
    "NBD06-019",
    "NBD01-008",
    "NBD01-017",
    "NBD01-021",
    "NBD01-022",
    "NBD01-025",
    "NBD01-028",
    "NBD01-029",
    "NBD02-013",
    "NBD02-016",
    "NBD03-003",
    "NBD03-004",
    "NBD03-005",
    "NBD04-003",
    "NBD06-009",
    "NBD07-003",
    "NBD07-004",
    "NBD07-008",
    "NBD07-009",
    "NBD07-010",
    "NBD07-011",
    "NBD07-012",
    "NBD07-013",
    "NBD07-014",
    "NBD07-015",
    "NBD07-016",
    "NBD07-017",
    "NBD07-018",
    "NBD07-019",
    "NBD07-020",
    "NBD07-022",
    "NBD07-023",
    "NBD07-024",
    "NBD01-037",
    "NBD01-038",
    "NBD07-025",
    "NBD07-026",
    "NBD07-027",
    "NBD07-028",
    "NBD03-006",
    "NBD07-029",
    "NBD07-030",
    "NBD05-006",
    "NBD02-043",
    "NBD07-032",
    "NBD07-033",
    "NBD02-044",
    "NBD07-034",
    "NBD07-035",
    "NBD05-007",
    "NBD06-004",
    "NBD06-001",
    "NBD06-007",
    "NBD06-010",
}

PROMOTED_MAINTAINED_IDS = {
    "NBD01-002",
    "NBD01-004",
    "NBD01-005",
    "NBD01-006",
    "NBD01-007",
    "NBD01-009",
    "NBD01-010",
    "NBD01-011",
    "NBD01-012",
    "NBD01-013",
    "NBD01-014",
    "NBD01-015",
    "NBD01-016",
    "NBD01-019",
    "NBD01-020",
    "NBD01-024",
    "NBD01-026",
    "NBD01-030",
    "NBD01-035",
    "NBD01-036",
    "NBD02-002",
    "NBD02-003",
    "NBD02-004",
    "NBD02-005",
    "NBD02-006",
    "NBD02-008",
    "NBD02-009",
    "NBD02-010",
    "NBD02-011",
    "NBD02-012",
    "NBD02-017",
    "NBD02-018",
    "NBD02-019",
    "NBD02-020",
    "NBD02-021",
    "NBD02-022",
    "NBD02-023",
    "NBD02-024",
    "NBD02-025",
    "NBD02-026",
    "NBD02-031",
    "NBD02-034",
    "NBD02-035",
    "NBD02-036",
    "NBD02-037",
    "NBD02-038",
    "NBD02-040",
    "NBD02-041",
    "NBD05-001",
    "NBD05-002",
    "NBD05-004",
    "NBD05-005",
    "NBD06-011",
    "NBD06-012",
    "NBD06-013",
    "NBD06-015",
    "NBD06-016",
    "NBD06-017",
    "NBD07-031",
    "NBD01-018",
    "NBD01-027",
    "NBD01-031",
    "NBD01-033",
    "NBD01-034",
    "NBD02-032",
    "NBD02-033",
    "NBD03-002",
    "NBD03-004",
    "NBD04-002",
    "NBD04-004",
    "NBD07-001",
    "NBD07-003",
    "NBD07-005",
    "NBD07-006",
    "NBD07-007",
    "NBD01-037",
    "NBD01-038",
    "NBD02-043",
    "NBD07-008",
    "NBD07-009",
    "NBD07-010",
    "NBD07-011",
    "NBD07-012",
    "NBD07-013",
    "NBD07-014",
    "NBD07-015",
    "NBD07-016",
    "NBD07-017",
    "NBD07-019",
    "NBD07-020",
    "NBD07-022",
    "NBD07-023",
    "NBD07-024",
    "NBD07-026",
    "NBD07-030",
    "NBD07-033",
    "NBD06-001",
    "NBD06-002",
    "NBD06-004",
    "NBD06-005",
    "NBD06-007",
    "NBD06-008",
    "NBD06-010",
    "NBD06-014",
    "NBD01-008",
    "NBD01-017",
    "NBD01-021",
    "NBD01-022",
    "NBD01-023",
    "NBD01-025",
    "NBD01-028",
    "NBD01-029",
    "NBD01-032",
    "NBD02-013",
    "NBD02-014",
    "NBD02-016",
    "NBD02-027",
    "NBD02-028",
    "NBD02-029",
    "NBD02-030",
    "NBD02-039",
    "NBD02-042",
    "NBD02-044",
    "NBD03-003",
    "NBD03-005",
    "NBD03-006",
    "NBD04-003",
    "NBD05-006",
    "NBD05-007",
    "NBD06-009",
    "NBD06-018",
    "NBD06-019",
    "NBD07-004",
    "NBD07-018",
    "NBD07-025",
    "NBD07-027",
    "NBD07-028",
    "NBD07-029",
    "NBD07-032",
    "NBD07-034",
    "NBD07-035",
}

TYPE_PROFILES = {
    "明确禁止型": {
        "priority": "资格条件、资格审查表、公告资格要求、供应商须知、正式准入条款",
        "roles": ["申请人的资格要求", "投标人资格要求", "供应商资格", "资格性审查", "资格审查表", "特定资格要求", "准入要求", "合格供应商条件"],
        "actions": ["须", "必须", "应", "要求", "设置", "限定", "指定", "采用", "提供", "仅限", "不得", "不接受", "不予受理", "不具备", "作为资格", "资格条件"],
        "effects": ["投标资格", "资格审查", "合格供应商", "投标无效", "响应无效", "不予通过", "不得参与"],
        "support": ["资格条件", "资格审查表", "公告资格要求", "投标文件格式", "采购需求"],
        "downrank": ["项目所在地", "服务地点", "履约地点", "合同地址", "投标文件格式", "声明函", "承诺函", "目录"],
        "high": ["资格角色 + 审查对象 + 限制行为", "资格审查表 + 审查对象 + 投标资格后果"],
        "mid": ["审查对象 + 行为词", "资格角色 + 审查对象"],
        "low": ["仅出现在格式表单或声明函中", "仅为项目背景、地址或履约地点说明"],
        "special": [
            "必须确认候选条款是否位于资格条件、资格审查表、公告资格要求等正式准入位置。",
            "只有审查对象与投标资格、资格审查、响应有效性或准入后果绑定时，才可命中。",
            "仅为信息填报、格式模板、项目背景、履约地点或采购人地址时，不命中。",
            "若条款可能具有法律法规或项目特殊必要性，但候选窗口无法确认，应输出待人工复核。",
        ],
    },
    "评分因素型": {
        "priority": "评分标准、评审因素、商务评分、技术评分、综合评分表、证明材料列",
        "roles": ["评分标准", "评审因素", "商务评分", "技术评分", "综合评分表", "评分细则", "评标办法", "证明材料"],
        "actions": ["提供", "具有", "满足", "每提供", "每满足", "得分", "不得分", "加分", "评分", "作为评审因素", "去掉", "剔除", "计算", "要求", "不得要求", "选用", "不得选用", "限制"],
        "effects": ["得分", "不得分", "加分", "评分", "满分", "分值", "商务分", "技术分"],
        "support": ["评分表表头", "评分项名称", "证明材料列", "资格条件", "采购需求", "项目属性"],
        "downrank": ["项目名称", "合同地址", "用户地址", "履约地点", "投标文件格式", "目录", "承诺函"],
        "high": ["评分角色 + 审查对象 + 得分结构", "评分项名称 + 审查对象 + 分值后果"],
        "mid": ["审查对象 + 得分/加分", "评分角色 + 审查对象"],
        "low": ["仅出现在证明材料格式中", "仅为项目名称、地址或背景说明"],
        "special": [
            "必须确认候选条款是否位于评分表或具有明确分值后果。",
            "评分项、分值、证明材料列和备注列应合并读取，不得只读单个关键词。",
            "仅在采购需求、合同地址、项目名称或格式模板中出现审查对象时，不命中。",
            "若评分对象与采购需求的关联性不明，应输出待人工复核。",
        ],
    },
    "数值比例型": {
        "priority": "供应商须知前附表、保证金条款、预算金额、最高限价、合同金额、期限条款",
        "roles": ["供应商须知前附表", "投标人须知", "保证金要求", "项目基本情况", "预算金额", "最高限价", "合同条款", "付款方式"],
        "actions": ["收取", "缴纳", "提交", "不得超过", "不低于", "不少于", "低于", "超过", "设置为", "金额为", "比例为", "期限为", "退还", "支付"],
        "effects": ["投标无效", "响应无效", "不予受理", "保证金金额", "预算金额", "最高限价", "合同金额", "期限"],
        "support": ["预算金额", "最高限价", "采购预算", "合同金额", "采购包金额", "是否收取", "期限"],
        "downrank": ["格式", "目录", "示范文本", "不收取", "无需缴纳", "非本项保证金"],
        "high": ["数值对象 + 金额/比例/期限模式 + 支持上下文", "正式条款 + 数值上限/下限 + 后果"],
        "mid": ["对象词 + 金额模式", "对象词 + 比例或期限"],
        "low": ["仅为退还流程说明", "仅为格式模板或政策引用"],
        "special": [
            "必须先识别数值对象的类型，避免把不同保证金、金额或期限混为一类。",
            "抽取金额、比例或期限后，必须再抽取对应基数或上限规则。",
            "无法确认基数、采购包或对象类型时，输出待人工复核。",
            "明确不收取或无需缴纳且未产生违规数值后果时，不命中。",
        ],
    },
    "履约配置型": {
        "priority": "合同条款、履约要求、分包条款、联合体条款、验收方案、保证金退还条款",
        "roles": ["合同条款", "履约要求", "分包", "联合体", "验收方案", "付款方式", "履约保证金", "供应商须知"],
        "actions": ["允许", "可以", "应明确", "须明确", "约定", "退还", "验收", "履行", "承担", "分包"],
        "effects": ["合同履行", "履约验收", "合同金额", "比例", "具体内容", "责任划分", "退还方式"],
        "support": ["合同条款", "采购需求", "分包内容", "金额比例", "联合体协议", "验收标准"],
        "downrank": ["禁止转包", "违法分包", "通用合同模板", "法律责任", "格式附件"],
        "high": ["履约角色 + 配置对象 + 必填内容缺失", "允许分包/联合体 + 内容/金额/比例不明确"],
        "mid": ["履约对象 + 应明确", "合同条款 + 配置对象"],
        "low": ["仅通用模板或法律责任表述", "仅禁止转包或违法分包"],
        "special": [
            "必须区分禁止性条款和允许后需要明确配置的条款。",
            "若采购文件允许某种履约安排，应检查内容、金额、比例、期限、责任或退还方式是否明确。",
            "仅出现通用合同模板、法律责任或格式附件时，不得直接命中。",
            "配置部分明确但关键要素缺失时，优先输出待人工复核。",
        ],
    },
    "政策判断型": {
        "priority": "采购政策、项目基本情况、预算金额、采购品目、是否接受进口产品、中小企业政策章节",
        "roles": ["采购政策", "落实政府采购政策", "中小企业", "进口产品", "采购品目", "预算金额", "项目基本情况"],
        "actions": ["专门面向", "价格扣除", "接受", "不接受", "要求提供", "必须提供", "不得要求", "证明文件", "声明函", "授权", "符合"],
        "effects": ["政策适用", "资格审查", "价格扣除", "投标无效", "响应无效", "证明材料"],
        "support": ["预算金额", "采购品目", "采购包", "是否专门面向中小企业", "是否接受进口产品", "政策设置章节"],
        "downrank": ["格式模板", "声明函样式", "政策引用", "目录", "合同条款"],
        "high": ["政策角色 + 项目事实 + 政策设置后果", "采购品目/预算 + 政策要求 + 证明材料"],
        "mid": ["政策对象 + 行为词", "项目事实 + 政策对象"],
        "low": ["仅为声明函格式", "仅为政策法规引用或目录"],
        "special": [
            "必须先确认采购品目、预算金额、采购包属性或是否接受进口产品等项目事实。",
            "政策设置与项目事实不一致时，才可命中。",
            "仅在格式模板、声明函样式或政策引用中出现关键词时，不命中。",
            "项目事实缺失或政策适用条件不完整时，输出待人工复核。",
        ],
    },
    "配置缺失型": {
        "priority": "招标公告、项目基本情况、采购需求、供应商须知前附表、核心产品和联合体等正式配置章节",
        "roles": ["招标公告", "项目基本情况", "采购需求", "供应商须知前附表", "核心产品", "联合体", "采购包"],
        "actions": ["载明", "明确", "列明", "注明", "设置", "未载明", "未明确", "未列明", "引用", "标注", "缺少", "出现", "提交", "编制", "要求"],
        "effects": ["公告信息", "采购文件完整性", "投标响应", "资格审查", "评审依据"],
        "support": ["正式公告段落", "项目基本情况", "采购需求清单", "采购包信息", "全文缺失确认"],
        "downrank": ["目录", "格式模板", "合同通用条款", "声明函", "示例文本"],
        "high": ["正式配置章节 + 必填配置对象缺失", "公告/前附表 + 配置对象未明确"],
        "mid": ["配置对象 + 未明确", "正式章节 + 配置对象"],
        "low": ["仅在目录或格式模板出现", "仅为通用示例或政策引用"],
        "special": [
            "配置缺失型必须优先定位正式公告或正式配置章节。",
            "判断缺失时，应结合支持上下文进行全文确认，不能只凭单个关键词窗口。",
            "配置在其他正式章节已明确且可回证时，不命中。",
            "无法确认正式章节完整性时，输出待人工复核。",
        ],
    },
    "合理性判断型": {
        "priority": "资格条件、评分标准、采购需求、证明材料、证书/资质/认证要求及品目事实",
        "roles": ["资格条件", "评分标准", "采购需求", "证明材料", "资质", "资格", "认证", "证书"],
        "actions": ["要求", "提供", "具有", "取得", "作为条件", "作为评审因素", "加分", "得分"],
        "effects": ["资格审查", "评分", "加分", "投标无效", "响应无效", "履约能力"],
        "support": ["采购需求", "品目事实", "证书性质", "法定强制要求", "评分分值", "证明材料"],
        "downrank": ["格式模板", "合同附件", "声明函", "政策引用", "目录"],
        "high": ["证书/资质对象 + 资格或评分后果 + 品目事实", "要求对象 + 法定强制性缺失 + 审查后果"],
        "mid": ["证书/资质对象 + 行为词", "采购需求 + 证明材料"],
        "low": ["仅为格式模板", "仅为合同履约后提交材料"],
        "special": [
            "必须判断要求与采购标的、履约能力和法定强制要求之间是否存在必要关联。",
            "不得把所有证书、认证或资质要求直接判为违规。",
            "采购需求、品目事实或证书性质不足时，输出待人工复核。",
            "仅作为投标文件格式或中标后办理事项且不影响资格/评分时，不命中。",
        ],
    },
    "关联比较型": {
        "priority": "评分标准、采购需求、技术要求、服务要求、证明材料、用户需求书",
        "roles": ["评分标准", "评审因素", "采购需求", "技术要求", "服务要求", "用户需求书", "证明材料"],
        "actions": ["作为评审因素", "得分", "加分", "要求", "提供", "体现", "满足", "对应", "关联"],
        "effects": ["评分", "加分", "响应", "履约能力", "需求匹配", "证明材料"],
        "support": ["采购需求", "评分项", "分值", "证明材料", "技术参数", "服务内容"],
        "downrank": ["目录", "格式模板", "声明函", "合同通用条款", "政策引用"],
        "high": ["评分项 + 采购需求对应对象 + 分值后果", "评分对象 + 需求缺失或不一致"],
        "mid": ["评分对象 + 采购需求", "证明材料 + 分值"],
        "low": ["仅为格式模板或声明函", "仅为合同履约后材料"],
        "special": [
            "必须同时读取评分设置和采购需求，判断两者是否存在对应关系。",
            "评分内容在采购需求中没有体现、明显新增或细化为额外负担时，才可命中。",
            "采购需求已明确同类要求且评分只是客观响应评价时，不命中。",
            "评分项、需求内容或证明材料任一侧缺失时，输出待人工复核。",
        ],
    },
    "品目专项型": {
        "priority": "采购需求、货物清单、技术参数、品目属性、专项资质、检测报告、行业许可章节",
        "roles": ["采购需求", "货物清单", "技术参数", "检测报告", "专项资质", "行业许可", "医疗器械", "设备清单"],
        "actions": ["要求", "提供", "具备", "出具", "检测", "许可", "备案", "认证", "满足"],
        "effects": ["资格审查", "评分", "实质性响应", "投标无效", "履约要求", "合规风险"],
        "support": ["品目事实", "技术参数", "货物清单", "法定许可", "主管部门要求", "检测机构要求"],
        "downrank": ["通用格式", "合同模板", "售后服务", "包装运输", "目录"],
        "high": ["品目事实 + 专项要求 + 审查后果", "专项资质/检测对象 + 限制行为 + 法定依据缺失"],
        "mid": ["专项对象 + 行为词", "品目事实 + 证明材料"],
        "low": ["仅为通用履约或售后材料", "仅在模板或附件中出现"],
        "special": [
            "必须先确认采购标的或品目事实，再判断专项资质、检测报告或行业许可要求。",
            "国家行政机关另有强制规定时，不得直接命中，应输出待人工复核或不命中。",
            "普通第三方检测、通用质量证明和特定机构限定必须区分。",
            "品目事实不足或专项法规不清时，输出待人工复核。",
        ],
    },
}


@dataclass
class PlanRow:
    nbd_id: str
    excel_row: int
    domain: str
    item_scope: str
    risk_level: str
    nbd_type: str
    batch: str
    priority: str
    confidence: str
    support_context: str
    reference: str
    title: str
    note: str


@dataclass
class SourceRow:
    source_no: str
    title: str
    item_scope: str
    risk_level: str
    rule: str
    advice: str
    laws: list[str]
    articles: list[str]
    law_texts: list[str]
    cases: str
    excel_row: int


def split_md_row(line: str) -> list[str]:
    return [p.strip() for p in line.strip().strip("|").split("|")]


def parse_plan(section: str) -> list[PlanRow]:
    text = PLAN.read_text(encoding="utf-8")
    rows: list[PlanRow] = []
    in_table = False
    headers: list[str] = []
    for line in text.splitlines():
        if section == "pilot":
            if line.startswith("### 4.1 先导批"):
                in_table = True
            elif in_table and line.startswith("### 4.2"):
                break
            if not in_table or not line.startswith("|") or line.startswith("|---"):
                continue
            parts = split_md_row(line)
            if parts and parts[0] == "NBD ID":
                headers = parts
                continue
            if len(parts) == 4 and parts[0].startswith("NBD"):
                full = find_full_plan_row(parts[0])
                if full:
                    rows.append(full)
        elif section == "first":
            if line.startswith("## 5. 全量分型明细"):
                in_table = True
            if not in_table or not line.startswith("|") or line.startswith("|---"):
                continue
            parts = split_md_row(line)
            if parts and parts[0] == "NBD ID":
                headers = parts
                continue
            if len(parts) >= 13 and parts[7] == "优先生成":
                rows.append(parts_to_plan_row(parts))
    return rows


def find_full_plan_row(nbd_id: str) -> PlanRow | None:
    text = PLAN.read_text(encoding="utf-8")
    in_table = False
    for line in text.splitlines():
        if line.startswith("## 5. 全量分型明细"):
            in_table = True
            continue
        if not in_table or not line.startswith("|") or line.startswith("|---"):
            continue
        parts = split_md_row(line)
        if parts and parts[0] == "NBD ID":
            continue
        if len(parts) >= 13 and parts[0] == nbd_id:
            return parts_to_plan_row(parts)
    return None


def parts_to_plan_row(parts: list[str]) -> PlanRow:
    return PlanRow(
        nbd_id=parts[0],
        excel_row=int(parts[1]) if parts[1].isdigit() else 0,
        domain=parts[2],
        item_scope=parts[3],
        risk_level=parts[4],
        nbd_type=parts[5],
        batch=parts[6],
        priority=parts[7],
        confidence=parts[8],
        support_context=parts[9],
        reference=parts[10],
        title=parts[11],
        note=parts[12],
    )


def load_source_rows() -> dict[int, SourceRow]:
    wb = openpyxl.load_workbook(SOURCE_XLSX, data_only=True)
    ws = wb["通用（深圳）"]
    out: dict[int, SourceRow] = {}
    current: SourceRow | None = None

    for idx, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        source_no = clean(row[0])
        item_scope = clean(row[1])
        risk_level = clean(row[2])
        title = clean(row[3])
        rule = clean(row[4])
        advice = clean(row[5])
        law = clean(row[6])
        article = clean(row[8])
        law_text = clean(row[9])
        case = clean(row[10])

        if title:
            current = SourceRow(
                source_no=source_no,
                title=title,
                item_scope=item_scope,
                risk_level=risk_level,
                rule=rule,
                advice=advice,
                laws=[],
                articles=[],
                law_texts=[],
                cases=case,
                excel_row=idx,
            )
            out[idx] = current
        if current and law:
            current.laws.append(law)
        if current and article:
            current.articles.append(article)
        if current and law_text:
            current.law_texts.append(law_text)

    return out


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def yaml_escape(value: str) -> str:
    return value.replace("\n", " ").replace(":", "：")


def filename_for(row: PlanRow) -> str:
    safe_title = row.title.replace("/", "-").replace("\\", "-").strip()
    return f"{row.nbd_id} {safe_title}.md"


def extract_terms(title: str, rule: str, nbd_type: str) -> list[str]:
    text = f"{title} {rule}"
    candidates = []
    keywords = [
        "所有制", "组织形式", "注册资本", "资产总额", "营业收入", "从业人员", "利润", "纳税额",
        "股权结构", "成立年限", "经营年限", "资质证照", "人员证书", "行政区域", "业绩",
        "金额", "行业", "奖项", "荣誉", "联合体", "保证金", "履约保证金", "质量保证金",
        "质保期", "售后", "评分", "价格分", "综合评分法", "低价优先法", "合同金额比例",
        "履约验收方案", "付款方式", "赠品", "回扣", "评定分离", "最高限价", "最低限价",
        "预算金额", "实质性条款", "现场踏勘", "分包", "证书", "职称", "学历",
        "学位", "PMP", "电子证照", "纸质证照", "核心产品", "进口产品", "厂家授权",
        "生产厂家授权", "中小企业声明函", "价格扣除", "区间值", "权重总和",
        "合同履行期限", "履行期限", "服务期限", "经费比例", "项目经费", "样品",
    ]
    for kw in keywords:
        if kw in text:
            candidates.append(kw)

    if "组织形式" in text:
        candidates.extend(["组织形式", "法人", "非法人组织", "分支机构", "独立法人", "自然人"])
    if "组织形" in text:
        candidates.extend(["组织形式", "法人", "非法人组织", "分支机构", "独立法人", "自然人", "公司", "事业单位"])
    if "所有制" in text:
        candidates.extend(["所有制", "所有制形式", "企业性质", "供应商性质", "国有企业", "民营企业", "事业单位", "外资企业"])
    if "股权结构" in text or "成立年限" in text or "经营年限" in text:
        candidates.extend(["股权结构", "成立年限", "经营年限", "控股", "外资", "成立时间", "经营时间", "连续经营", "持续经营", "经营稳定性", "经营情况"])
    if "资质证照" in text or "人员证书" in text or "证书" in text:
        candidates.extend(["资质证照", "认证证书", "资质证书", "人员证书", "项目负责人证书", "许可证", "证书", "认证"])
    if "行政区域的业绩" in text or "行政区划的奖项" in text:
        candidates.extend(["行政区域", "行政区划", "广东省", "深圳市", "本市", "本区", "业绩", "奖项", "荣誉"])
    if "特定行业的业绩" in text or "特定行业的奖项" in text:
        candidates.extend(["行业", "特定行业", "行业协会", "物业", "医院", "学校", "业绩", "奖项", "荣誉"])
    if "经营网点" in text:
        candidates.extend(["经营网点", "服务网点", "本地网点", "固定经营场所", "营业网点", "分支机构"])
    if "商标" in text or "品牌" in text or "供应商" in text:
        candidates.extend(["商标", "品牌", "型号", "供应商名称", "指定品牌", "参考品牌", "原厂授权", "A牌", "图片", "实物图片"])
    if "主观性" in text or "品牌要求" in text:
        candidates.extend(["知名", "一线", "权威", "优质", "参考品牌", "主流品牌", "国际品牌"])
    if "评定分离" in text:
        candidates.extend(["评定分离", "候选中标供应商", "候选供应商", "推荐", "定标方式", "自定法", "抽签定标", "定标"])
    if "最高限价" in text or "采购预算" in text:
        candidates.extend(["最高限价", "采购预算", "预算金额", "限价金额"])
    if "最低限价" in text:
        candidates.extend(["最低限价", "最低报价", "报价下限", "低于最低限价", "成本警戒线"])
    if "原件" in text:
        candidates.extend(["原件", "原件备查", "证照原件", "证明材料原件", "资格证明原件"])
    if "法定代表人" in text and "到场" in text:
        candidates.extend(["法定代表人", "法人代表", "必须到场", "身份核验", "现场参加", "开标现场"])
    if "敏感风险词" in text:
        candidates.extend(["唯一", "指定", "必须使用", "不得偏离", "原厂", "原厂服务", "独家", "排他"])
    if "中国质量认证监督管理中心" in text:
        candidates.extend(["中国质量认证监督管理中心", "质量认证监督管理中心", "认证情况"])
    if "职称证书" in text:
        candidates.extend(["职称证书", "职称", "人社部门", "人力资源社会保障部门", "颁发机构", "备案"])
    if "国家级证书" in text or "400万" in text:
        candidates.extend(["国家级", "省级及以上", "荣誉证书", "奖项", "400万", "预算金额", "评分"])
    if "注册地或所在地" in text:
        candidates.extend(["注册地", "所在地", "本地", "本市", "本区", "服务机构", "得分"])
    if "资产所有权" in text:
        candidates.extend(["自有", "租赁", "资产所有权", "自有设备", "租赁设备", "得分"])
    if "无明确认定标准" in text:
        candidates.extend(["优", "良", "中", "差", "横向比较", "酌情", "综合评价", "分档", "认定标准"])
    if "最高价和最低价" in text:
        candidates.extend(["去掉最高", "去掉最低", "去掉一个最高", "去掉一个最低", "最高报价", "最低报价", "评标基准价", "价格分"])
    if "低价优先法" in text:
        candidates.extend(["低价优先法", "评标基准价", "平均价", "基准价", "价格分计算"])
    if "价格分值" in text or "价格分分值" in text:
        candidates.extend(["价格分", "价格权重", "价格部分", "30%", "10%", "60%", "综合评分法", "竞争性磋商"])
    if "评定分离" in text and "重大项目" in text:
        candidates.extend(["评定分离", "重大项目", "特定品目", "评标办法", "中标候选人", "定标"])
    if "电子证照" in text or "纸质证照" in text:
        candidates.extend(["电子证照", "纸质证照", "纸质复印件", "证照原件", "在线核验", "共享范围"])
    if "权重总和" in text:
        candidates.extend(["权重总和", "总分", "100%", "技术分", "商务分", "价格分", "评标信息"])
    if "评分细项分值" in text:
        candidates.extend(["评分细项", "细项分值", "满分", "分档", "超过满分", "评分子项"])
    if "区间值" in text:
        candidates.extend(["区间值", "3至5分", "3-5分", "分值区间", "评分区间", "分档"])
    if "合同履行期限" in text or "履行期限" in text:
        candidates.extend(["合同履行期限", "履行期限", "服务期限", "合同期限", "24个月", "36个月", "48个月"])
    if "合法保证金形式" in text:
        candidates.extend(["保证金形式", "银行转账", "支票", "汇票", "本票", "保函", "合法形式"])
    if "现场踏勘" in text:
        candidates.extend(["现场踏勘", "踏勘确认函", "资格审查", "必须参加", "自愿踏勘", "不影响投标"])
    if "项目验收方案" in text:
        candidates.extend(["项目验收方案", "验收方案", "验收流程", "验收人员", "验收计划", "评分"])
    if "付款方式" in text and "评审因素" in text:
        candidates.extend(["付款方式", "付款节点", "延后付款", "评分", "得分", "合同条款"])
    if "自主知识产权" in text or "自有专利" in text:
        candidates.extend(["自主知识产权", "自有专利", "专利证书", "知识产权证书", "加分"])
    if "学历" in text:
        candidates.extend(["学历", "本科", "全日制", "非全日制", "国家承认", "学习方式"])
    if "学位" in text:
        candidates.extend(["学位", "硕士", "博士", "岗位职责", "采购需求", "加分"])
    if "PMP" in text or "项目经理证书" in text:
        candidates.extend(["PMP", "项目经理证书", "项目管理证书", "项目经理", "加分"])
    if "认证机构" in text:
        candidates.extend(["认证机构", "指定认证机构", "颁发机构", "证书", "不得分"])
    if "样品" in text:
        candidates.extend(["样品", "样品制作", "制作标准", "规格", "封样", "评审要求"])
    if "实质性条款" in text or "星号条款" in text:
        candidates.extend(["实质性条款", "星号条款", "★", "▲", "负偏离", "响应性审查", "符合性审查", "不满足作无效投标", "技术要求偏离表"])
    if "实质性条款" in text:
        candidates.extend(["实质性条款", "星号条款", "响应性审查", "重复计分", "评分"])
    if "量化打分" in text or "量化" in text:
        candidates.extend(["量化打分", "量化标准", "优得", "良得", "一般得", "评分分档", "客观指标", "评审标准"])
    if "项目经费比例" in text or "经费比例" in text:
        candidates.extend(["项目经费", "经费比例", "政策要求", "比例", "30%", "10%"])
    if "进口产品" in text:
        candidates.extend(["进口产品", "接受进口产品", "不接受进口产品", "厂家授权", "生产厂家授权", "授权证明"])
    if "CNAS" in text:
        candidates.extend(["CNAS", "CNAS标识", "CNAS资质", "检测报告", "检测机构", "CMA", "国际互认", "非进口项目", "不接受进口产品"])
    if "国际标准" in text or "ISO" in text or "ASTM" in text or "BIFMA" in text:
        candidates.extend(["国际标准", "ISO", "ASTM", "BIFMA", "BS", "检测标准", "标准代号", "非进口项目", "不接受进口产品", "国内同等标准"])
    if "检测报告数量" in text or "超过五份" in text or "5份" in text:
        candidates.extend(["检测报告", "检测报告数量", "报告数量", "检测报告份数", "五份", "5份", "6份", "六份", "提供检测报告", "出具检测报告"])
    if "会计师事务所" in text or "律师事务所" in text or "执业年限" in text:
        candidates.extend(["会计师事务所", "律师事务所", "事务所", "执业年限", "成立年限", "成立时间", "经营年限", "评审因素", "评分", "得分", "项目负责人"])
    if "价格扣除" in text:
        candidates.extend(["价格扣除", "专门面向中小企业", "小微企业", "中小企业", "采购包"])
    if "中小企业声明函" in text:
        candidates.extend(["中小企业声明函", "中小企业证明", "主管部门证明", "身份证明", "证明材料"])
    if "付款方式" in text and ("载明" in text or "必须" in text):
        candidates.extend(["付款方式", "付款节点", "支付方式", "支付条件", "合同价款", "载明"])
    if "最高限价" in text or "采购预算" in text or "预算金额" in text:
        candidates.extend(["预算金额", "采购预算", "最高限价", "报价上限", "采购包预算", "项目预算", "控制价", "限价", "超过预算"])
    if "采购方式" in text:
        candidates.extend(["采购方式", "公开招标", "竞争性谈判", "竞争性磋商", "询价", "单一来源", "采购限额", "预算金额"])
    if "评定分离" in text:
        candidates.extend(["评定分离", "重大项目", "特定品目", "定标", "评标办法", "中标候选人", "候选供应商"])
    if "国务院已明令取消" in text or "非强制" in text or "资质、资格、认证" in text:
        candidates.extend(["国务院已明令取消", "已取消", "非强制", "国家行政机关非强制", "资质", "资格", "认证", "资格条件", "评分", "得分"])
    if "准入类" in text or "行政许可类" in text or "职业证书" in text:
        candidates.extend(["准入类", "行政许可", "职业资格证书", "执业资格", "上岗证", "资格职业证书", "评分项", "得分"])
    if "电子证照" in text or "纸质证照" in text:
        candidates.extend(["电子证照", "纸质证照", "纸质复印件", "原件备查", "在线核验", "共享范围", "证照材料"])
    if "权重总和" in text or "100%" in text:
        candidates.extend(["权重总和", "100%", "总分", "技术分", "商务分", "价格分", "评分表", "评标信息"])
    if "评分细项分值" in text or "细项分值" in text:
        candidates.extend(["评分细项", "细项分值", "满分", "分档", "评分子项", "超过满分", "评分表"])
    if "敏感风险词" in text:
        candidates.extend(["唯一", "指定", "原厂", "独家", "排他", "必须使用", "不得偏离", "特定品牌", "专利"])
    if "内容一致性" in text:
        candidates.extend(["内容一致性", "不一致", "前后不一致", "金额不一致", "名称不一致", "条款冲突"])
    if "GB" in text or "强制性标准" in text:
        candidates.extend(["GB", "GB/T", "国家强制性标准", "强制性标准", "★号", "星号", "技术参数"])
    if "服务地点" in text:
        candidates.extend(["服务地点", "履约地点", "项目地点", "实施地点", "交付地点", "服务范围"])
    if "交货时间" in text:
        candidates.extend(["交货时间", "交货期", "供货期", "交付时间", "到货时间", "合同签订后", "收到采购人通知", "完成供货"])
    if "交货地点" in text:
        candidates.extend(["交货地点", "交付地点", "到货地点", "送货地点", "安装地点", "采购人指定地点", "项目现场"])
    if "服务期限" in text:
        candidates.extend(["服务期限", "服务期", "项目服务期", "合同期限", "履行期限", "服务时间", "一年", "12个月", "36个月"])
    if "投标文件编制要求" in text:
        candidates.extend(["投标文件编制要求", "投标文件组成", "编制要求", "投标文件格式", "签署盖章", "响应文件"])
    if "投标报价要求" in text:
        candidates.extend(["投标报价要求", "报价要求", "报价方式", "投标报价", "总价", "分项报价"])
    if "资质证明及资料提交形式" in text:
        candidates.extend(["资质证明", "资料提交形式", "证明材料", "扫描件", "复印件", "电子件", "原件"])
    if "投标有效期" in text:
        candidates.extend(["投标有效期", "有效期", "投标截止", "开标之日", "90日", "不少于"])
    if "所属行业" in text:
        candidates.extend(["所属行业", "采购标的所属行业", "中小企业划型", "行业", "采购品目", "标的名称", "行业类别", "工业", "软件和信息技术服务业", "租赁和商务服务业"])
    if "CMA" in text:
        candidates.extend(["CMA", "CMA标识", "CMA资质", "资质认定标志", "检测报告", "检验报告", "检测机构", "检测范围", "资质范围", "负偏离"])
    if "检验检测报告" in text or "必要且合理的时间" in text:
        candidates.extend(["检验检测报告", "检测报告", "报告出具时间", "检测时间", "投标截止前", "公告发布后", "必要且合理时间", "样品检测", "检测周期"])
    if "技术参数区间" in text or "参数区间" in text:
        candidates.extend(["技术参数", "参数区间", "区间说明", "范围值", "不低于", "不高于", "5-20", "负偏离", "响应数值", "范围涵盖"])
    if "物业管理服务范围" in text or "物业服务" in text:
        candidates.extend(["物业管理", "物业服务", "服务范围", "建筑面积", "建筑物范围", "设备清单", "服务内容", "人员配置", "岗位配置", "服务标准"])
    if "燃气具" in text:
        candidates.extend(["燃气具", "燃气器具", "燃气燃烧器具", "安装维修", "维修资质", "燃气具安装维修资质", "燃气燃烧器具安装维修", "资质证书"])
    if "技术评审项" in text or "技术要求偏离表" in text:
        candidates.extend(["技术评审项", "技术评分", "技术要求表", "技术参数表", "服务要求表", "技术要求偏离表", "技术偏离表", "评审项", "评分标准", "需求部分"])
    if "节能产品" in text or "环保产品" in text:
        candidates.extend(["节能产品", "环保产品", "节能证书", "环保产品认证证书", "中国节能产品认证证书", "强制节能", "品目清单", "评分项"])
    if "本国产品声明函" in text:
        candidates.extend(["本国产品声明函", "进口产品", "不接受进口", "接受进口", "货物清单", "声明函", "国产"])
    if "高空服务" in text or "高处作业" in text:
        candidates.extend(["高空服务", "高处作业", "特种作业操作证", "登高", "外墙", "高空维修", "作业类别"])
    if "强制节能产品" in text:
        candidates.extend(["强制节能产品", "中国节能产品认证证书", "节能产品认证证书", "品目清单", "空调", "显示器", "打印机"])
    if "货物参数" in text or "标准与要求" in text:
        candidates.extend(["货物参数", "技术参数", "国家标准", "行业标准", "执行标准", "参数要求", "检测标准", "技术要求"])
    if "商用密码" in text:
        candidates.extend(["商用密码", "密码应用", "密评", "商用密码产品", "密码模块", "安全性", "证书", "资格条件"])
    if "数据库" in text:
        candidates.extend(["数据库", "分布式数据库", "集中式数据库", "数据库产品", "数据库政府采购需求标准", "财库"])
    if "商务评审项" in text:
        candidates.extend(["商务评审项", "商务评分", "商务要求", "商务条款", "商务偏离表", "评审项", "评分标准"])
    if "人员评审项" in text:
        candidates.extend(["人员评审项", "人员评分", "岗位要求", "人员配置", "项目负责人", "团队人员", "评分标准"])
    if "错别字" in text:
        candidates.extend(["错别字", "笔误", "文字错误", "名称错误", "金额错误", "前后不一致"])
    if "乱码" in text:
        candidates.extend(["乱码", "异常字符", "无法识别", "字符错误", "□□", "���"])
    if "收到发票" in text or "资金支付" in text:
        candidates.extend(["收到发票", "发票", "10个工作日", "资金支付", "支付"])
    if "履约验收方案" in text:
        candidates.extend(["履约验收方案", "履约验收", "验收方案", "验收标准"])
    if "履约保证金" in text:
        candidates.extend(["履约保证金", "合同金额", "退还方式", "退还时间", "退还条件"])
    if "质量保证金" in text:
        candidates.extend(["质量保证金", "工程项目", "货物项目", "服务项目"])
    if "其他保证金" in text or "不合理的保证金" in text:
        candidates.extend(["保证金", "诚信保证金", "安全保证金", "农民工工资保证金", "维修保证金", "培训保证金", "担保函", "担保", "责任保险", "保险"])
    if "质保期" in text:
        candidates.extend(["质保期", "免费质保", "免费质保期", "保修期", "质量保证期", "不少于", "24个月", "三年", "36个月", "整机", "服务期", "厂家标准"])
    if "注册地" in text or "所在地" in text:
        candidates.extend(["注册地", "所在地", "本地", "本市", "服务机构", "服务点", "本地服务", "服务响应点"])
    if "联合体" in text and "合同金额比例" in text:
        candidates.extend(["联合体", "合同金额比例", "成员单位", "承担金额", "承担比例"])
    if "特定金额的业绩" in text or "限定金额的业绩" in text:
        candidates.extend(["业绩", "合同金额业绩", "单项合同金额", "项目金额", "万元以上业绩", "大型项目", "项目规模", "合同规模", "大额业绩"])

    title_clean = title
    for prefix in ["不得将", "不得以", "不得要求", "不得设置", "不得限定", "不得收取", "不得用", "不得"]:
        title_clean = title_clean.replace(prefix, "")
    for suffix in ["作为评审因素", "作为资格条件", "设置为评审因素", "设置为资格条件", "方面设置为评审因素"]:
        title_clean = title_clean.replace(suffix, "")
    title_parts = re.split(r"[，、；;（）() /]+", title_clean)
    candidates.extend([p for p in title_parts if 2 <= len(p) <= 16 and not p.endswith("的")])

    priority_terms: list[str] = []
    if "高空服务" in text or "高处作业" in text:
        priority_terms.extend(["高空服务", "高处作业", "特种作业操作证", "登高", "外墙", "高空维修", "作业类别"])
    if "货物参数" in text or "标准与要求" in text:
        priority_terms.extend(["货物参数", "技术参数", "国家标准", "行业标准", "执行标准", "参数要求", "检测标准", "技术要求"])
    if "数据库" in text:
        priority_terms.extend(["数据库", "分布式数据库", "集中式数据库", "数据库产品", "数据库政府采购需求标准"])
    if priority_terms:
        candidates = priority_terms + candidates

    seen = set()
    result = []
    for term in candidates:
        term = term.strip(" ：:，。；;、")
        if not term or term in seen:
            continue
        if term in {"不得", "设置", "作为", "要求", "需", "须", "合理", "正确", "存在风险", "并进行提示"}:
            continue
        if any(stop in term for stop in ["若相关条款", "此类表述", "则存在", "进行提示", "采购文件中", "供应商具有"]):
            continue
        if len(term) > 14:
            continue
        seen.add(term)
        result.append(term)
        if len(result) >= 16:
            break
    if "履约保证金" in result:
        result = [term for term in result if term not in {"保证金", "金额"}]
    if "质量保证金" in result:
        result = [term for term in result if term not in {"保证金", "金额"}]
    if "特定金额的业绩" in text or "限定金额的业绩" in text:
        result = [term for term in result if term != "金额"]
    if "联合体" in text and "合同金额比例" in text:
        result = [term for term in result if term != "金额"]
    return result or [title]


def split_advice(advice: str) -> tuple[str, str]:
    risk_tip = advice
    suggestion = "按审查规则删除、补充或调整相关条款，使其与采购需求、法规依据和公平竞争要求一致。"
    if "风险提示：" in advice:
        risk_tip = advice.split("风险提示：", 1)[1]
    if "修改建议：" in risk_tip:
        risk_tip, suggestion = risk_tip.split("修改建议：", 1)
    elif "修改建议：" in advice:
        suggestion = advice.split("修改建议：", 1)[1]
    return risk_tip.strip() or "采购文件相关条款可能存在合规风险。", suggestion.strip()


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def render_page(plan: PlanRow, source: SourceRow) -> str:
    profile = TYPE_PROFILES[plan.nbd_type]
    terms = extract_terms(plan.title, source.rule, plan.nbd_type)
    risk_tip, suggestion = split_advice(source.advice)
    laws = "；".join(dict.fromkeys(source.laws)) or "待法规桥接清洗"
    examples = source.cases or "待补充真实样例或 fixture。"
    standard_scope = infer_standard_scope(source, plan)
    finding_type = "风险" if source.risk_level in {"高", "中", "低"} else "提醒"
    if plan.nbd_id in PROMOTED_MAINTAINED_IDS:
        status = "maintained"
        version = "v1-maintained"
    elif plan.nbd_id in TESTING_IDS:
        status = "testing"
        version = "v1-testing"
    else:
        status = "draft"
        version = "v1-generated-pilot"

    pattern_terms = build_patterns(terms, plan.nbd_type)
    hit_conditions = build_hit_conditions(plan, source, terms)
    exclude_conditions = build_exclude_conditions(plan.nbd_type, plan, source)

    return f"""---
id: {plan.nbd_id}
title: {yaml_escape(plan.title)}
page_type: nbd-review-point
status: {status}
source_material: 通用（深圳）
source_row: {plan.excel_row}
item_scope: {source.item_scope or plan.item_scope}
risk_level: {source.risk_level or plan.risk_level}
finding_type: {finding_type}
standard_scope: {standard_scope}
source_region: 深圳
applicable_regions:
  - 全国
version: {version}
last_reviewed: 2026-04-28
---

上级导航：[[../index|新版 BD 审查点明细库]]

# {plan.nbd_id} {plan.title}

## 审查目标
{source.rule or f"审查采购文件是否存在“{plan.title}”相关风险。"}

## 适用范围
- 品目：{source.item_scope or plan.item_scope or "通用"}
- NBD 类型：{plan.nbd_type}
- 优先章节：{profile["priority"]}
- 风险等级：{source.risk_level or plan.risk_level or "未标注"}
- 输出性质：{finding_type}
- 适用地区初判：{standard_scope}

## 定位与召回剖面
### 章节角色词
{bullets(profile["roles"])}

### 对象词簇
{bullets(terms)}

### 行为词簇
{bullets(profile["actions"])}

### 后果词簇
{bullets(profile["effects"])}

### 数值/模式规则
{bullets(pattern_terms)}

### 支持上下文词
{bullets(profile["support"])}

### 降权/排除词
{bullets(profile["downrank"])}

### 高价值组合
{bullets(profile["high"])}

### 中价值组合
{bullets(profile["mid"])}

### 低价值组合
{bullets(profile["low"])}

## 候选召回规则
- 优先召回“高价值组合”命中的正式约束条款。
- “中价值组合”用于补充候选或形成支持上下文，不应直接等同于风险命中。
- “低价值组合”默认降权，不应挤占主候选窗口；仅在缺少高价值候选时作为辅助上下文。
- 候选位于投标文件格式、目录、附件、声明函、承诺函、合同通用条款或示范文本时，必须降级为待人工复核或不命中。
- 对需要项目事实的判断，应同时召回支持上下文；支持上下文只补足事实，不单独构成命中证据。

## 上下文读取规则
- 读取候选条款所在完整块。
- 若候选位于表格，必须读取表头、评分项名称、分值列、证明材料列和备注列。
- 若候选涉及资格、评分、合同、预算或政策后果，读取前后相邻块确认其正式效力。
- 若候选涉及预算、品目、采购需求、货物清单或政策设置，必须读取支持上下文。
- 若正式章节缺失或候选来源无法确认，输出待人工复核，不得强行命中。

## 专项判断方法
{bullets(profile["special"])}

## 基础命中条件
- A：候选条款位于本 NBD 适用章节或正式约束文本。
- B：候选条款涉及本 NBD 的审查对象。
- C：候选条款可能影响资格、评分、响应、合同、政策适用或文件完整性。
- D：未命中排除条件，且支持上下文不足以证明其合法必要。

## 命中条件
同时满足以下条件时，输出命中：
{bullets(hit_conditions)}

## 排除条件
命中以下任一情况时，原则上不命中；证据不足时输出待人工复核：
{bullets(exclude_conditions)}

## 判断结果分流
### 命中
- 满足基础命中条件和命中条件。
- 证据来自正式约束条款。
- 风险提示和修改建议可以直接输出。

### 待人工复核
- 候选相关，但正式章节、项目事实、法规边界或支持上下文不足。
- 需要人工确认采购品目、预算金额、需求内容、货物清单、证书关联度或地方口径。

### 不命中
- 未召回相关高价值候选。
- 候选属于排除条件。
- 支持上下文证明项目已作合规设置。

## 风险提示
{risk_tip}

## 修改建议
{suggestion}

## 审查依据
{laws}

## 示例
{examples}

## 反例
待通过 fixture 或真实样本补充。

## 边界例
候选条款与审查对象相关，但缺少正式章节、项目事实、支持上下文或法规例外判断时，应输出待人工复核。

## 易误报场景
- 关键词只出现在目录、附件、投标文件格式或通用模板中。
- 候选文本只是政策引用、背景说明或信息填报项。
- 候选缺少资格、评分、响应、合同、政策适用或文件完整性后果。
- 支持上下文不足时，小模型把不确定情况强行判为命中。

## 地区适用说明
- 当前适用边界初判：{standard_scope}。
- 深圳材料是孵化来源，不代表本 NBD 仅适用于深圳。
- 后续应通过法规桥接进一步清洗为 national、regional 或 mixed。

## 调试备注
- {version}：由 `scripts/generate_nbd_from_source.py` 根据 [[../audits/NBD全量分型计划|NBD 全量分型计划]] 生成。
- maintained 参照：{plan.reference}。
- 分型置信度：{plan.confidence}。
- 分型备注：{plan.note}。
- 当前状态为 `{status}`。

## 小模型可执行性自检
- 只读“定位与召回剖面”能否召回候选条款：待预检。
- 高价值组合是否能召回关键证据：待预检。
- 低价值组合和降权词是否能控制噪声：待验证。
- 支持上下文是否足够支撑判断：待验证。
- 命中、待复核、不命中分流是否稳定：待 smoke。
"""


def infer_standard_scope(source: SourceRow, plan: PlanRow) -> str:
    law_text = " ".join(source.laws + source.law_texts + [source.rule])
    if "深圳" in law_text:
        return "regional"
    if "地方" in law_text and "国家" in law_text:
        return "mixed"
    return "national"


def build_patterns(terms: list[str], nbd_type: str) -> list[str]:
    main = terms[:4]
    patterns: list[str] = []
    if nbd_type == "数值比例型":
        patterns.extend(
            [
                r"\d+(\.\d+)?\s*(元|万元|%)",
                r"\d+\s*(日|天|个月|工作日)",
                r"(预算金额|最高限价|合同金额).*\d+(\.\d+)?\s*(元|万元)",
                r"(不得超过|不高于|低于|以内).*\d+(\.\d+)?\s*%",
            ]
        )
    elif nbd_type == "评分因素型":
        patterns.extend([f"{re.escape(term)}.*(得\\d+(\\.\\d+)?分|不得分|加\\d+(\\.\\d+)?分)" for term in main])
        patterns.append(r"(得|加)\d+(\.\d+)?分")
    elif nbd_type == "明确禁止型":
        patterns.extend([f"(须|必须|仅限|不得|不接受).*{re.escape(term)}" for term in main])
        patterns.append(r"(投标无效|响应无效|资格不通过|不具备投标资格)")
    elif nbd_type == "履约配置型":
        patterns.extend([f"{re.escape(term)}.*(内容|金额|比例|期限|责任|退还|验收)" for term in main])
        patterns.append(r"(未明确|未约定|应明确|须明确)")
    else:
        patterns.extend([f"{re.escape(term)}.*(资格|评分|合同|需求|无效|不通过)" for term in main])
    return patterns[:6]


def build_hit_conditions(plan: PlanRow, source: SourceRow, terms: list[str]) -> list[str]:
    obj = "、".join(terms[:4])
    text = f"{plan.title} {source.rule}"
    if plan.nbd_id == "NBD01-012":
        return [
            "正式资格、准入或资格审查条款要求供应商获得特定行政区域、行政区划或地方级别的奖项、荣誉、称号。",
            "未取得该地方奖项或荣誉会导致资格审查不通过、响应无效或不得参与。",
            "候选不是证书颁发机构地址、企业注册地址或证明材料来源地说明。",
        ]
    if plan.nbd_id == "NBD01-013":
        return [
            "正式资格、准入或资格审查条款要求供应商获得特定行业协会、特定行业领域、特定行业称号或行业荣誉。",
            "未取得该行业奖项或荣誉会导致资格审查不通过、响应无效或不得参与。",
            "支持上下文不能证明该奖项是依法必须或与准入资格直接相关。",
        ]
    if plan.nbd_id == "NBD01-014":
        return [
            "正式资格、准入或资格审查条款要求供应商在特定地区已有经营网点、服务网点、营业网点或固定经营场所。",
            "未满足网点条件会导致资格审查不通过、响应无效或不得参与。",
            "候选不是中标后服务响应安排、履约服务点承诺或售后服务方案评分。",
        ]
    if plan.nbd_id == "NBD01-015":
        return [
            "采购需求、技术参数、资格条件或评分条款指定明确商标、品牌、型号、供应商名称、产品实物图片或内部结构图。",
            "该指定会实质指向特定供应商、特定产品或排除可替代产品。",
            "候选不是依法允许的兼容性说明，也未使用“或相当于”等开放表述消除限定效果。",
        ]
    if plan.nbd_id == "NBD01-016":
        return [
            "采购需求、技术参数或品牌要求中使用知名、一线、权威、优质、参考品牌、主流品牌等主观描述。",
            "该描述用于定义产品、品牌、服务或供应商要求，缺少可量化、可检验标准。",
            "候选不是投标人自愿介绍、市场调研背景或非约束性说明。",
        ]
    if plan.nbd_id == "NBD01-019":
        return [
            "项目明确采用评定分离。",
            "候选中标供应商、候选供应商或入围候选数量不是 3 家，或未明确为 3 家。",
            "该数量设置来自评标/定标正式规则，而不是示例或模板说明。",
        ]
    if plan.nbd_id == "NBD01-020":
        return [
            "项目明确采用评定分离。",
            "定标方式未采用自定法，或采用抽签、票决、集体议事等非自定法表述。",
            "该定标方式来自正式评标/定标规则。",
        ]
    if plan.nbd_id == "NBD01-023":
        return [
            "采购文件同时载明采购预算金额和最高限价金额。",
            "能够抽取并比较二者数值，且最高限价金额大于采购预算金额。",
            "候选金额属于同一采购项目或同一采购包，不是不同包组或不同币种金额混读。",
        ]
    if plan.nbd_id == "NBD01-024":
        return [
            "采购文件正式设置最低限价、报价下限、低于某金额无效或不得低于某价格。",
            "该最低价要求影响报价有效性、投标资格或评审结果。",
            "候选不是最高限价、预算金额、成本警戒提醒或异常低价说明。",
        ]
    if plan.nbd_id == "NBD01-026":
        return [
            "采购文件要求供应商提交资质证明、证照、证件或相关证明材料原件，或写明原件备查/现场核验原件。",
            "该要求作为投标文件提交、资格审查、开标或评审要求。",
            "候选不是电子证照核验、成交后合同签订核验或投诉处理阶段补充核验。",
        ]
    if plan.nbd_id == "NBD01-030":
        return [
            "开标、投标、签到或现场环节要求投标人的法定代表人、法人代表必须到场。",
            "不到场会导致投标无效、拒收投标文件、不得参与开标或类似后果。",
            "候选不是授权代表可到场、线上开标身份验证或可选择出席的说明。",
        ]
    if plan.nbd_id == "NBD01-032":
        return [
            "正式约束条款中出现唯一、指定、必须使用、独家、排他、原厂等敏感风险词。",
            "该词语可能导致供应商、产品、品牌、服务方式或履约主体被不合理限定。",
            "候选不是法律条文引用、投标文件真实性承诺、投诉责任说明或无实质限制的普通表述。",
        ]
    if plan.nbd_id == "NBD01-035":
        return [
            "采购文件要求或评分中出现中国质量认证监督管理中心出具、认证或颁发的证书。",
            "该证书作为资格条件、评分因素、证明材料或履约要求。",
            "候选不是风险提示、负面清单或明确禁止该机构证书的说明。",
        ]
    if plan.nbd_id == "NBD01-036":
        return [
            "资格、评分或人员要求中设置职称证书。",
            "条款限定职称证书必须由人社部门、人力资源社会保障部门或某具体机构颁发，且未包含“或经人社部门备案的颁证机构”等开放表述。",
            "该限定影响资格审查、评分得分或响应有效性。",
        ]
    if plan.nbd_id == "NBD02-006":
        return [
            "项目采购金额、预算金额或最高限价小于 400 万元。",
            "评分标准中要求国家级、省级及以上奖项、荣誉或证书作为得分条件。",
            "该荣誉证书与得分、加分、不得分、分值档位或评分权重绑定。",
        ]
    if plan.nbd_id == "NBD02-012":
        return [
            "评分标准、商务评分或技术评分中将供应商注册地、所在地、本地机构或本地服务网点作为得分条件。",
            "该地域因素与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是项目履约地点、响应时间承诺或中标后设点安排。",
        ]
    if plan.nbd_id == "NBD02-014":
        return [
            "评分标准中设置可能隐含企业组织形式、规模、经营年限限制的资质证照、认证证书或荣誉证书。",
            "该证书与得分、加分、不得分、分值档位或评分权重绑定。",
            "支持上下文不能证明该证书与采购需求核心履约能力直接相关且公平可取得。",
        ]
    if plan.nbd_id == "NBD02-017":
        return [
            "评分标准中评价供应商设备、场地、车辆、设施或资产的所有权性质。",
            "自有与租赁、购买与租用等不同资产取得方式被设置不同分值或得分门槛。",
            "候选不是要求供应商具备使用权、调配能力或履约保障能力的中性表述。",
        ]
    if plan.nbd_id == "NBD02-018":
        return [
            "评分标准设置优/良/中/差、横向比较、综合评价、酌情打分等分档或主观评分。",
            "各档分值缺少明确、可核验、可量化的认定标准。",
            "该分档会影响得分、加分、不得分或分值权重。",
        ]
    if plan.nbd_id == "NBD02-019":
        return [
            "采购文件采用综合评分法、公开招标、邀请招标或竞争性磋商等价格分评审规则。",
            "价格分计算或评标基准价规则中明确去掉最高报价、最低报价或同时去掉最高价和最低价。",
            "该规则用于计算价格分或评标基准价，而不是异常低价审查说明。",
        ]
    if plan.nbd_id == "NBD02-020":
        return [
            "项目采用综合评分法。",
            "价格分计算方式不是低价优先法，或采用平均价、基准价、区间价、接近基准价得高分等方式。",
            "该价格分规则适用于正式评审，不是示例或已被正确低价优先法替代的旧文本。",
        ]
    if plan.nbd_id == "NBD02-021":
        return [
            "项目为货物采购并采用综合评分法。",
            "价格分、价格权重或报价得分占总分值比例低于 30%。",
            "能够识别总分值和价格分值属于同一评分体系。",
        ]
    if plan.nbd_id == "NBD02-022":
        return [
            "项目为服务采购且非政务信息系统采购项目，并采用综合评分法。",
            "价格分、价格权重或报价得分占总分值比例低于 10%。",
            "能够识别总分值和价格分值属于同一评分体系。",
        ]
    if plan.nbd_id == "NBD02-023":
        return [
            "项目采购方式为竞争性磋商，且项目为货物类项目。",
            "价格分、价格权重或报价得分占总分值比例低于 30% 或高于 60%。",
            "能够识别总分值和价格分值属于同一评分体系。",
        ]
    if plan.nbd_id == "NBD01-005":
        return [
            "正式资格、准入或资格审查条款将股权结构、控股类型、成立年限、经营年限或成立日期设为门槛。",
            "不满足该企业背景指标会导致资格审查不通过、响应无效、不得参与或类似准入后果。",
            "该要求不是企业基本信息填报、营业执照成立日期展示或普通主体资格证明。",
        ]
    if plan.nbd_id in {"NBD01-006", "NBD01-007"}:
        return [
            "正式资格、准入或资格审查条款要求供应商或人员持有与采购需求必要性不清、且可能隐含企业规模、组织形式、经营年限限制的证书。",
            "该证书要求作为准入条件、资格审查项或响应有效性条件，而不是评分加分项。",
            "支持上下文不能证明该证书是履行项目依法必须具备的行政许可、强制认证或岗位资格。",
        ]
    if plan.nbd_id == "NBD01-009":
        return [
            "正式资格、准入或资格审查条款要求供应商具备特定行政区域内的业绩。",
            "行政区域要求与业绩资格门槛、资格审查通过或响应有效性绑定。",
            "候选不是项目履约地点、服务地点、采购人所在地或合同履行区域说明。",
        ]
    if plan.nbd_id == "NBD01-010":
        return [
            "正式资格、准入或资格审查条款要求供应商具备达到特定合同金额、项目金额、累计金额或预算规模的业绩。",
            "金额门槛与资格审查通过、响应有效性或不得参与绑定。",
            "候选不是本项目预算、最高限价、报价或合同价款说明。",
        ]
    if plan.nbd_id == "NBD01-011":
        return [
            "正式资格、准入或资格审查条款要求供应商具备特定行业、特定领域、特定部门、特定采购人类型或特定使用场景业绩。",
            "该行业或领域限定与资格审查通过、响应有效性或不得参与绑定。",
            "候选不是单纯要求同类项目、类似项目或与采购需求相关的普通履约经验；若只写同类/类似且行业边界不清，应输出待人工复核。",
        ]
    if plan.nbd_id == "NBD02-004":
        return [
            "评分标准、商务评分或技术评分中将特定行政区域、行政区划或地方级别的奖项、荣誉、称号作为得分条件。",
            "该地方奖项或荣誉与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是证书颁发机构地址、项目所在地、企业注册地址或证明材料来源地说明。",
        ]
    if plan.nbd_id == "NBD02-005":
        return [
            "评分标准、商务评分或技术评分中将特定行业协会、特定行业领域、特定行业称号或行业荣誉作为得分条件。",
            "该行业奖项或荣誉与得分、加分、不得分、分值档位或评分权重绑定。",
            "支持上下文不能证明该奖项是采购需求客观必要且可由多元主体公平取得的评价材料。",
        ]
    if plan.nbd_id == "NBD02-008":
        return [
            "评分标准、商务评分或技术评分中将股权结构、控股类型、成立年限、经营年限或成立日期作为得分条件。",
            "该企业背景指标与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是企业基本信息填报、营业执照成立日期展示或证明材料格式说明。",
        ]
    if plan.nbd_id == "NBD02-009":
        return [
            "评分标准、商务评分或技术评分中将供应商所有制形式、组织形式、注册地、所在地或本地机构设置作为得分条件。",
            "该身份、组织或地域因素与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是项目履约地点、服务响应安排、企业地址填报或投标文件格式说明。",
        ]
    if plan.nbd_id == "NBD02-010":
        return [
            "评分标准、商务评分或技术评分中将国有企业、民营企业、事业单位、外资企业等所有制形式作为得分条件。",
            "所有制形式与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是企业性质信息填报、政策统计或供应商基本情况表。",
        ]
    if plan.nbd_id == "NBD02-011":
        return [
            "评分标准、商务评分或技术评分中将法人、独立法人、公司、分支机构、事业单位等组织形式作为得分条件。",
            "组织形式与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是法定供应商定义、主体资格证明、授权签署或投标文件格式说明。",
        ]
    if plan.nbd_id == "NBD06-002":
        return [
            "正式供应商须知、合同条款或商务条款要求供应商缴纳投标保证金、履约保证金、质量保证金以外的其他保证金。",
            "该保证金具有收取金额、比例、缴纳时间、扣罚或不缴纳后果。",
            "候选不是保函形式说明、保险、担保服务选择、诚信承诺或法定三类保证金的别称。",
        ]
    if plan.nbd_id == "NBD06-005":
        return [
            "采购文件要求收取质量保证金。",
            "项目为货物或服务项目，或虽为工程项目但质量保证金比例超过合同金额 5%。",
            "该要求来自正式合同、商务条款、供应商须知或付款/结算安排，而不是单纯质量保证承诺。",
        ]
    if plan.nbd_id == "NBD06-008":
        return [
            "货物类项目正式采购需求、商务条款或合同条款约定质保期、免费质保期、保修期或质量保证期。",
            "能够抽取质保期限，且期限超过 24 个月。",
            "候选不是设备设计寿命、耗材有效期、服务期、维保响应期或供应商自愿承诺评分项。",
        ]
    if plan.nbd_id == "NBD06-014":
        return [
            "采购文件正式要求收取履约保证金。",
            "全文或相关合同/商务条款未明确履约保证金退还条件、退还时间、退还程序或退还方式。",
            "缺失会导致供应商无法判断履约保证金何时、如何或在何种条件下返还。",
        ]
    if plan.nbd_id == "NBD01-002":
        return [
            "正式资格、准入或资格审查条款限定供应商必须为法人、独立法人、企业法人、公司、事业单位、分支机构或其他特定组织形式。",
            "该组织形式要求会影响供应商参与资格、资格审查结论、响应有效性或投标无效后果。",
            "支持上下文不能证明该组织形式限制具有明确法律法规依据或项目不可替代必要性。",
        ]
    if plan.nbd_id == "NBD01-004":
        return [
            "正式资格、准入或资格审查条款将注册资本、资产总额、营业收入、从业人员、利润、纳税额等规模或财务指标设为门槛。",
            "不满足该规模或财务指标会导致资格审查不通过、响应无效、不得参与或类似准入后果。",
            "该要求不是中小企业声明、财务状况报告、纳税证明、社保缴纳等法定资格证明材料的普通提交要求。",
        ]
    if plan.nbd_id == "NBD02-002":
        return [
            "评分标准、商务评分或技术评分中将特定行业、特定领域、特定部门、特定采购人类型或特定使用场景的业绩作为得分条件。",
            "该行业或领域限定与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是单纯要求同类项目、类似项目或与采购需求相关的普通履约经验；若只写同类/类似且行业边界不清，应输出待人工复核。",
        ]
    if plan.nbd_id == "NBD02-003":
        return [
            "评分标准、商务评分或技术评分中将业绩合同金额、项目金额、单项金额、累计金额或预算规模作为得分条件。",
            "该金额门槛与得分、加分、不得分、分值档位或评分权重绑定。",
            "候选不是单纯按业绩数量、份数、合同个数或履约评价计分；仅数量计分且无金额门槛时不命中。",
        ]
    if plan.nbd_id == "NBD06-001":
        return [
            "正式公告、供应商须知前附表或联合体条款明确接受或允许联合体投标。",
            "采购文件未明确联合体各成员承担的合同金额、合同份额或比例。",
            "该缺失会影响联合体成员履约责任、合同金额分配或中小企业政策执行判断。",
        ]
    if "收到发票" in text or "资金支付" in text:
        return [
            "正式付款条款未明确采购人在收到发票后 10 个工作日内完成资金支付。",
            "或正式付款条款明确的支付期限超过 10 个工作日。",
            "该期限不是单纯合同模板示例，而是本项目专用条款、商务要求或付款方式中的正式约定。",
        ]
    if plan.nbd_id == "NBD06-010":
        return [
            "采购文件未设置履约验收方案，或仅笼统写明验收合格、按合同验收。",
            "正式条款缺少验收主体、验收标准、验收程序、验收时间、验收方式或验收责任中的关键要素。",
            "该缺失会影响供应商理解交付、验收和付款条件。",
        ]
    if "履约保证金" in text and "比例" in text:
        return [
            "采购文件要求收取履约保证金。",
            "能够抽取履约保证金比例或金额，并能识别合同金额或项目是否专门面向中小企业。",
            "履约保证金超过合同金额 10%，或专门面向中小企业采购项目超过合同金额 5%。",
        ]
    if "质量保证金" in text and "比例" in text:
        return [
            "采购文件要求收取质量保证金。",
            "项目不属于依法可设置质量保证金的工程项目，或质量保证金比例超过规则允许范围。",
            "该要求来自正式合同、商务或供应商须知条款。",
        ]
    if plan.nbd_type == "明确禁止型":
        return [
            f"正式资格、准入或资格审查条款中出现与“{obj}”相关的限制性要求。",
            "该要求会影响供应商参与资格、资格审查或响应有效性。",
            "支持上下文不能证明该限制具有法律法规依据或项目不可替代必要性。",
        ]
    if plan.nbd_type == "评分因素型":
        return [
            f"评分标准或评审因素中出现与“{obj}”相关的评价对象。",
            "该评价对象与得分、加分、不得分或分值权重绑定。",
            "该评分设置不属于对采购需求中明确必要内容的客观响应评价。",
        ]
    if plan.nbd_type == "数值比例型":
        return [
            f"正式条款中出现与“{obj}”相关的金额、比例或期限要求。",
            "能够抽取相应数值和判断基数、上限或期限规则。",
            "计算或比对后超过规则允许范围，或缺少必要配置导致供应商无法判断。",
        ]
    if plan.nbd_type == "履约配置型":
        return [
            f"采购文件允许或要求与“{obj}”相关的履约安排。",
            "文件未明确具体内容、金额、比例、期限、责任或退还方式等关键要素。",
            "该缺失可能影响供应商理解履约边界或合同责任。",
        ]
    return [
        f"正式条款中出现与“{obj}”相关的审查对象。",
        "该条款产生资格、评分、合同、政策适用或文件完整性后果。",
        "未命中排除条件，且支持上下文不能证明其合规。",
    ]


def build_exclude_conditions(nbd_type: str, plan: PlanRow | None = None, source: SourceRow | None = None) -> list[str]:
    common = [
        "相关词仅出现在目录、附件、投标文件格式、声明函或承诺函中。",
        "候选条款只是项目背景、地址、政策引用或信息填报要求，未产生实质后果。",
    ]
    text = ""
    if plan:
        text += plan.title
    if source:
        text += " " + source.rule
    if "收到发票" in text or "资金支付" in text:
        return common + [
            "正式付款条款已明确采购人在收到发票后 10 个工作日内完成资金支付。",
            "候选仅为发票、付款材料或流程描述，未约定支付期限。",
        ]
    if plan and plan.nbd_id == "NBD01-005":
        return common + [
            "股权结构、成立日期、经营年限仅出现在供应商基本情况表、营业执照信息或信息填报项中。",
            "条款只是要求依法成立、有效存续或具有独立承担民事责任能力，未设置具体年限、日期或股权门槛。",
            "相关要求位于评分标准而非资格条件时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id in {"NBD01-012", "NBD01-013"}:
        return common + [
            "奖项或荣誉仅作为评分因素，不影响资格审查或准入。",
            "奖项词仅出现在供应商基本情况、证明材料示例、项目背景或投标文件格式中。",
            "条款未限定特定行政区划、特定行业协会或特定行业称号。",
        ]
    if plan and plan.nbd_id == "NBD01-014":
        return common + [
            "条款仅要求中标后设置服务网点、服务响应点或履约服务团队。",
            "经营网点要求位于评分标准或售后服务方案中，不作为资格审查门槛。",
            "网点表述仅为采购人地址、服务地点或项目履约地点。",
        ]
    if plan and plan.nbd_id in {"NBD01-015", "NBD01-016"}:
        return common + [
            "品牌、型号或图片仅为兼容性说明、现有设备接口说明或非约束性参考，且允许同等或相当产品。",
            "主观性词语仅出现在投标人承诺、市场背景、非评分非资格的说明文字中。",
            "条款已转化为明确、可量化、可检验的技术参数。",
        ]
    if plan and plan.nbd_id in {"NBD01-019", "NBD01-020"}:
        return common + [
            "项目未采用评定分离。",
            "候选供应商数量明确为 3 家，或定标方式明确为自定法。",
            "候选只出现在政策引用、流程介绍或非本项目模板中。",
        ]
    if plan and plan.nbd_id == "NBD01-023":
        return common + [
            "最高限价小于或等于采购预算。",
            "只出现预算金额或最高限价其中一个，无法比较时输出待人工复核。",
            "金额属于不同采购包、不同币种或不同口径，无法确认同一基数时输出待人工复核。",
        ]
    if plan and plan.nbd_id == "NBD01-024":
        return common + [
            "条款仅设置最高限价、预算金额、成本警戒线或异常低价说明。",
            "低于成本报价需说明或可能被评审，不等同于最低限价。",
        ]
    if plan and plan.nbd_id == "NBD01-026":
        return common + [
            "条款仅要求提供复印件、扫描件、电子证照或承诺函。",
            "原件核验发生在中标后、合同签订前、投诉处理或监管核查阶段，未作为投标文件提交要求。",
        ]
    if plan and plan.nbd_id == "NBD01-030":
        return common + [
            "允许法定代表人或授权代表任选其一到场。",
            "仅为线上开标身份验证、授权委托要求或可自愿参加开标说明。",
        ]
    if plan and plan.nbd_id == "NBD01-032":
        return common + [
            "敏感词仅出现在法律法规引用、投标真实性承诺、处罚条款或投诉处理说明中。",
            "该词语没有限定品牌、供应商、产品、技术路线或履约主体。",
        ]
    if plan and plan.nbd_id == "NBD01-035":
        return common + [
            "条款明确禁止或排除中国质量认证监督管理中心相关证书。",
            "该机构名称仅出现在风险提示、案例说明或审查意见中。",
        ]
    if plan and plan.nbd_id == "NBD01-036":
        return common + [
            "职称要求未限定颁发机构。",
            "表述为人社部门或经人社部门备案的颁证机构，属于开放表述。",
            "证书要求仅为投标文件格式或人员信息填报，未影响资格或评分。",
        ]
    if plan and plan.nbd_id == "NBD02-006":
        return common + [
            "项目金额达到或超过 400 万元。",
            "奖项、荣誉或证书不是国家级、省级及以上，或未绑定评分分值。",
            "项目金额、采购包或评分对象无法确认时输出待人工复核。",
        ]
    if plan and plan.nbd_id in {"NBD02-012", "NBD02-014", "NBD02-017", "NBD02-018", "NBD02-019", "NBD02-020", "NBD02-021", "NBD02-022", "NBD02-023"}:
        return common + [
            "候选不位于评分标准，且不存在得分、加分、不得分或分值后果。",
            "候选仅为项目背景、采购需求、投标文件格式、政策引用或证明材料示例。",
            "项目属性、采购方式、金额基数或评分对象无法确认时输出待人工复核。",
        ]
    if plan and plan.nbd_id in {"NBD01-006", "NBD01-007"}:
        return common + [
            "证书属于项目依法必须的行政许可、强制认证、特种作业资格、医疗器械许可、食品经营许可等明确法定资质。",
            "证书仅作为评分项、人员能力加分项、投标文件格式或承诺函附件，不影响资格审查。",
            "证书要求与采购需求核心履约能力直接相关，且未隐含企业规模、组织形式或经营年限限制。",
        ]
    if plan and plan.nbd_id == "NBD01-009":
        return common + [
            "行政区域词仅为项目所在地、服务地点、履约地点、采购人地址或案例发生地。",
            "条款只要求同类或类似业绩，未限定特定行政区域。",
            "相关要求位于评分标准而非资格条件时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD01-010":
        return common + [
            "金额仅为本项目预算金额、最高限价、报价、合同价款或付款安排，未作为历史业绩资格门槛。",
            "条款只要求业绩数量或合同证明，未设置金额门槛。",
            "相关要求位于评分标准而非资格条件时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD01-011":
        return common + [
            "条款仅要求同类项目、类似项目或与采购内容相关经验，未限定特定行业、部门、采购人类型或使用场景。",
            "行业词仅为本项目名称、采购需求、履约背景或证明材料示例。",
            "相关要求位于评分标准而非资格条件时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD02-004":
        return common + [
            "行政区划词仅为颁证机构地址、项目所在地、企业注册地址或证明材料来源地，未作为评分对象。",
            "评分项仅要求合法有效奖项、荣誉或认证，未限定特定行政区划。",
            "相关要求位于资格条件而非评分标准时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD02-005":
        return common + [
            "奖项或荣誉未限定特定行业协会、特定行业领域或特定行业称号。",
            "行业词仅出现在项目背景、采购需求、证明材料示例或获奖证书名称中，未作为得分条件。",
            "相关要求位于资格条件而非评分标准时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD02-008":
        return common + [
            "股权结构、成立日期、经营年限仅出现在供应商基本情况表、营业执照信息或证明材料格式中。",
            "评分项评价的是项目经验、履约能力或人员能力，未将企业背景指标绑定分值。",
            "相关要求位于资格条件而非评分标准时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD02-009":
        return common + [
            "所在地、地址或本地服务点仅为履约服务响应安排，未按供应商注册地、所在地或组织身份给分。",
            "所有制形式或组织形式仅为供应商基本信息填报、法定定义或证明材料格式。",
            "相关要求位于资格条件而非评分标准时，不按本 NBD 命中。",
        ]
    if plan and plan.nbd_id == "NBD02-010":
        return common + [
            "所有制形式仅为供应商基本情况、企业性质统计、政策填报或证明材料格式。",
            "评分项未因国有、民营、外资、事业单位等身份设置分值差异。",
        ]
    if plan and plan.nbd_id == "NBD02-011":
        return common + [
            "组织形式仅为法定供应商定义、主体资格证明、授权签署、联合体说明或投标文件格式。",
            "评分项未因法人、分支机构、事业单位、公司等组织形式设置分值差异。",
        ]
    if plan and plan.nbd_id == "NBD06-002":
        return common + [
            "保证金属于投标保证金、履约保证金或质量保证金，且由对应 NBD 判断比例或合法性。",
            "候选仅为银行保函、担保、保险、诚信承诺、违约金、赔偿金或合同价款扣减安排。",
            "相关金额只是报价、预算、最高限价、预付款或付款节点，不是保证金。",
        ]
    if plan and plan.nbd_id == "NBD06-005":
        return common + [
            "条款只是质量保证、质量承诺、质保期或保修义务，未收取质量保证金。",
            "工程项目质量保证金比例不超过合同金额 5%。",
            "候选属于履约保证金、投标保证金或质保期，不是质量保证金。",
        ]
    if plan and plan.nbd_id == "NBD06-008":
        return common + [
            "项目不是货物类项目，或期限对象为服务期、维保服务期、设计寿命、耗材有效期、响应时间。",
            "质保期、免费质保期、保修期或质量保证期不超过 24 个月。",
            "超过 24 个月的期限仅为供应商自愿承诺、评分加分上限或非强制性售后方案。",
        ]
    if plan and plan.nbd_id == "NBD06-014":
        return common + [
            "采购文件未要求收取履约保证金。",
            "正式条款已明确履约保证金退还条件、退还时间、退还程序或退还方式中的关键要素。",
            "候选仅为投标保证金或质量保证金退还，不涉及履约保证金。",
        ]
    if plan and plan.nbd_id == "NBD01-002":
        return common + [
            "法人、自然人、非法人组织等表述仅用于政府采购法定义供应商范围、质疑函格式、授权委托书、电子营业执照或投标文件签署说明。",
            "条款只是要求依法登记、具有独立承担民事责任能力、提供营业执照或主体资格证明，未限定特定组织形式。",
            "组织形式要求仅作为联合体成员、分支机构授权或合同签署信息填报，未影响投标资格。",
        ]
    if plan and plan.nbd_id == "NBD01-004":
        return common + [
            "相关财务字段仅出现在中小企业声明函、残疾人福利性单位声明函、财务状况报告、纳税证明、社保缴纳证明或投标文件格式中。",
            "条款只是要求提供依法缴纳税收、社会保障资金、财务状况报告等法定资格证明材料，未设置具体规模门槛。",
            "注册资本、营业收入、从业人员、利润、纳税额等信息仅用于企业类型划分、政策优惠或统计填报，未影响资格审查。",
        ]
    if plan and plan.nbd_id == "NBD02-002":
        return common + [
            "评分项仅要求同类项目、类似项目、同类型项目经验，未限定特定行业、特定部门、特定区域或特定采购人类型。",
            "行业词仅出现在项目名称、采购需求、用户背景、合同履约地点或证明材料示例中，未作为得分条件。",
            "候选位于资格条件而非评分标准时，不按本 NBD 命中，应转由资格类 NBD 判断。",
        ]
    if plan and plan.nbd_id == "NBD02-003":
        return common + [
            "评分项仅按业绩数量、合同份数、用户评价或履约评价计分，未设置合同金额、项目金额、预算规模或累计金额门槛。",
            "金额仅为本项目预算金额、最高限价、合同报价、投标报价或采购需求估算，未绑定业绩评分。",
            "候选位于资格条件而非评分标准时，不按本 NBD 命中，应转由资格类 NBD 判断。",
        ]
    if plan and plan.nbd_id == "NBD06-001":
        return common + [
            "正式条款明确不接受联合体投标。",
            "正式条款接受联合体投标，且已明确各成员合同金额、份额或比例。",
            "相关词仅出现在联合体协议书格式、投标文件格式或通用法律责任条款中。",
        ]
    if plan and plan.nbd_id == "NBD06-010":
        return common + [
            "采购文件已明确验收主体、验收标准、验收程序、验收时间、验收方式或验收责任等履约验收方案要素。",
            "相关词仅出现在评分项、投标文件格式、通用合同模板或政策引用中。",
        ]
    if "履约保证金" in text and "比例" in text:
        return common + [
            "履约保证金比例未超过合同金额 10%，且专门面向中小企业采购项目未超过合同金额 5%。",
            "候选条款仅为履约保证金退还流程，不涉及收取比例或金额超限。",
        ]
    if nbd_type == "明确禁止型":
        return common + ["条款不影响投标资格、资格审查或响应有效性。"]
    if nbd_type == "评分因素型":
        return common + ["条款不位于评分标准，且不存在得分、加分或不得分后果。"]
    if nbd_type == "数值比例型":
        return common + ["对象类型、金额、比例或基数无法确认时，不强行命中，应待人工复核。"]
    if nbd_type == "履约配置型":
        return common + ["仅为通用合同模板、法律责任或禁止转包表述，未允许或配置具体履约安排。"]
    return common


def write_report(generated: list[Path], skipped: list[str], section: str) -> Path:
    by_type = defaultdict(int)
    for path in generated:
        text = path.read_text(encoding="utf-8")
        m = re.search(r"- NBD 类型：(.+)", text)
        if m:
            by_type[m.group(1).strip()] += 1

    report = REPORT_DIR / f"NBD先导批生成记录-{section}-20260428.md"
    lines = [
        "---",
        f"id: nbd-generation-report-{section}-20260428",
        f"title: NBD 先导批生成记录 {section}",
        "page_type: nbd-generation-report",
        "status: draft",
        "last_reviewed: 2026-04-28",
        "---",
        "",
        "上级导航：[[../index|新版 BD 审查点明细库]]",
        "",
        f"# NBD 先导批生成记录 {section}",
        "",
        f"- 生成范围：`{section}`",
        f"- 新增/覆盖页面数：{len(generated)}",
        f"- 跳过页面数：{len(skipped)}",
        "- 默认状态：`draft`",
        "- 生成脚本：`scripts/generate_nbd_from_source.py`",
        "",
        "## 按类型",
        "| 类型 | 数量 |",
        "|---|---:|",
    ]
    for key, count in sorted(by_type.items()):
        lines.append(f"| {key} | {count} |")
    lines.extend(["", "## 生成页面", "| 页面 |", "|---|"])
    for path in generated:
        title = path.stem
        lines.append(f"| [[../items/{title}|{title}]] |")
    if skipped:
        lines.extend(["", "## 跳过页面", "| NBD ID | 原因 |", "|---|---|"])
        for item in skipped:
            lines.append(f"| {item} | maintained 或既有页面保护 |")
    lines.extend(
        [
            "",
            "## 后续验证",
            "- 对生成页面先跑召回预检，检查候选窗口数量、重复率和支持上下文。",
            "- 每类至少抽取 2 个页面跑小模型 smoke。",
            "- smoke 通过前不得升级为 `maintained`。",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", choices=["pilot", "first"], default="pilot")
    parser.add_argument("--force", action="store_true", help="overwrite existing non-maintained generated pages")
    parser.add_argument("--ids", help="comma-separated NBD ids to generate within the selected section")
    args = parser.parse_args()

    plan_rows = parse_plan(args.section)
    if args.ids:
        selected_ids = [item.strip() for item in args.ids.split(",") if item.strip()]
        selected_set = set(selected_ids)
        by_id = {row.nbd_id: row for row in plan_rows}
        for nbd_id in selected_ids:
            if nbd_id not in by_id:
                full = find_full_plan_row(nbd_id)
                if full:
                    by_id[nbd_id] = full
        plan_rows = [by_id[nbd_id] for nbd_id in selected_ids if nbd_id in by_id and nbd_id in selected_set]
    source_rows = load_source_rows()
    generated: list[Path] = []
    skipped: list[str] = []

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    for plan in plan_rows:
        if plan.nbd_id in MAINTAINED_IDS:
            skipped.append(plan.nbd_id)
            continue
        source = source_rows.get(plan.excel_row)
        if not source:
            skipped.append(f"{plan.nbd_id} source-missing")
            continue
        path = ITEMS_DIR / filename_for(plan)
        if path.exists() and not args.force:
            skipped.append(plan.nbd_id)
            continue
        if path.exists() and "status: maintained" in path.read_text(encoding="utf-8"):
            skipped.append(plan.nbd_id)
            continue
        path.write_text(render_page(plan, source), encoding="utf-8")
        generated.append(path)

    report = None
    if generated or args.force:
        report = write_report(generated, skipped, args.section)
    report_part = f" report={report.relative_to(ROOT)}" if report else " report=unchanged"
    print(f"generated={len(generated)} skipped={len(skipped)}{report_part}")
    for path in generated:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
