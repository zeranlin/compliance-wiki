"""NBD daily review runtime module.

Business knowledge must stay in NBD markdown/IR; this module only interprets generic runtime data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DOCUMENT_IR_SCHEMA = "document-ir/v1"
NBD_IR_SCHEMA = "nbd-ir/v1"
NBD_RECALL_IR_SCHEMA = "nbd-recall-ir/v1"
NBD_PROMPT_IR_SCHEMA = "nbd-prompt-ir/v1"
NBD_GOVERNANCE_IR_SCHEMA = "nbd-governance-ir/v1"
CANDIDATE_WINDOW_SCHEMA = "candidate-window/v1"
CANDIDATE_SET_SCHEMA = "candidate-set/v1"
MODEL_REVIEW_RESULT_SCHEMA = "model-review-result/v1"
RUNTIME_SCHEMA = "nbd-runtime/v1"


@dataclass
class DocumentBlock:
    block_id: str
    block_type: str
    order_index: int
    line_start: int
    line_end: int
    text: str
    lines: list[str]
    section_path: list[str] = field(default_factory=list)
    section_role: str = "unknown"
    section_role_confidence: float = 0.0
    section_role_reason: list[str] = field(default_factory=list)
    table: dict[str, Any] = field(default_factory=dict)


@dataclass
class CandidateWindow:
    schema_version: str
    nbd_id: str
    window_id: str
    window_type: str
    section_role: str
    section_role_confidence: float
    section_path: list[str]
    line_anchor: str
    score: float
    recall_reason: list[str]
    recall_quality: str
    completeness: dict[str, bool]
    text: str
    block_ids: list[str]
    hit_words: dict[str, list[str]]
    source: dict[str, Any]


@dataclass
class NBDItem:
    nbd_id: str
    title: str
    path: Path
    markdown: str
    meta: dict[str, Any]
    keyword_groups: dict[str, list[str]]
    recall_profile: dict[str, Any]
    compact_text: str


SECTION_ROLE_PRIORITY = {
    "scoring_primary": 11,
    "scoring": 10,
    "qualification_primary": 10,
    "qualification": 9,
    "announcement": 8,
    "technical_primary": 8,
    "user_requirement": 7,
    "business_primary": 7,
    "business_terms": 6,
    "contract_primary": 6,
    "sample_requirement": 6,
    "contract_special": 5,
    "contract_template": 2,
    "template_support": 2,
    "policy_support": 2,
    "bid_format": 2,
    "common_terms": 1,
    "catalog": 0,
    "unknown": 3,
}


STRUCTURE_PATTERNS: list[tuple[str, list[str], list[str]]] = [
    ("announcement", ["招标公告", "采购公告", "磋商公告", "谈判公告", "询价公告"], []),
    ("qualification_primary", ["申请人的资格要求", "投标人资格要求", "供应商资格要求", "供应商资格条件", "资格条件", "资格性审查表", "资格审查表", "特定资格要求"], []),
    ("qualification", ["资格要求", "资格条件", "资格审查", "合格供应商"], []),
    ("scoring_primary", ["评标信息", "评分标准", "评审因素", "评分细则", "评分办法", "综合评分表"], ["评审因素", "权重", "评分准则"]),
    ("scoring", ["评审", "评分"], ["评审因素", "权重", "评分准则"]),
    ("technical_primary", ["技术要求", "技术需求", "技术参数", "技术规格", "货物清单", "服务内容"], []),
    ("sample_requirement", ["样品要求", "样品递交", "样品提交", "样品评审", "样品制作", "样品标准", "样品评分"], ["样品", "外观", "工艺"]),
    ("user_requirement", ["用户需求书", "采购需求", "服务需求", "技术要求", "项目需求", "需求清单"], []),
    ("business_primary", ["商务要求", "商务条款", "商务条件", "报价要求", "付款方式", "履约地点", "履约期限", "验收要求"], []),
    ("business_terms", ["商务", "报价", "付款", "验收"], []),
    ("contract_primary", ["合同专用条款", "合同主要条款", "通用条款补充", "通用条款的补充", "补充条款", "付款条款", "验收条款"], []),
    ("contract_template", ["合同条款及格式", "合同格式", "合同范本", "合同文本"], []),
    ("template_support", ["投标文件格式", "响应文件格式", "投标文件组成", "承诺函", "声明函", "格式模板"], []),
    ("bid_format", ["投标文件格式", "响应文件格式", "投标文件组成", "承诺函", "声明函"], []),
    ("policy_support", ["政策引用", "政府采购政策", "中小企业声明函", "残疾人福利性单位声明函"], []),
    ("common_terms", ["通用条款", "第二册"], []),
    ("catalog", ["目录"], []),
]
