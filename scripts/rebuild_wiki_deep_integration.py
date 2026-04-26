#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("/Users/linzeran/code/2026-zn/test_target/compliance-wiki")
RAW = ROOT / "raw"
SCAN_DIR = RAW / "full-risk-scans"
NUMBERED_DIR = RAW / "numbered-text"
MANIFEST_DIR = RAW / "manifests"
SOURCE_DIR = RAW / "source-files" / "深圳10个品目批注文件"
WIKI = ROOT / "wiki"
PROJECT_DIR = WIKI / "projects"
FINDING_DIR = WIKI / "findings"
BRIDGE_DIR = WIKI / "legal-bridges"
RULE_DIR = WIKI / "rules"
AUDIT_DIR = WIKI / "audits"
LOG_PATH = WIKI / "log.md"
INDEX_PATH = WIKI / "index.md"
EXPORT_DIR = ROOT / "exports"

LAW_WIKI_ROOT = ROOT / "law-wiki"
TODAY = "2026-04-21"

ITEM_TYPE_PREFIXES = {
    "信息化设备",
    "信息技术服务",
    "其他服务",
    "医疗设备",
    "家具",
    "教学仪器",
    "物业管理",
    "用具",
    "社会治理服务",
    "装具",
}

ITEM_TYPE_TO_PROCUREMENT = {
    "信息化设备": "货物",
    "医疗设备": "货物",
    "家具": "货物",
    "教学仪器": "货物",
    "用具": "货物",
    "装具": "货物",
    "信息技术服务": "服务",
    "其他服务": "服务",
    "物业管理": "服务",
    "社会治理服务": "服务",
}


LEGAL_BRIDGES = {
    "中华人民共和国政府采购法": {
        "bridge_type": "source",
        "authority_level": "law",
        "law_target": LAW_WIKI_ROOT / "sources" / "中华人民共和国政府采购法.md",
        "positioning": "政府采购的基础法律，负责定义供应商条件、差别待遇边界和基本采购程序。",
        "review_uses": [
            "审查供应商资格条件设置是否合法。",
            "判断是否存在差别待遇、歧视待遇和不合理门槛。",
        ],
        "focus_points": ["第二十二条", "第二十三条", "第二十五条"],
    },
    "中华人民共和国政府采购法实施条例": {
        "bridge_type": "source",
        "authority_level": "administrative-regulation",
        "law_target": LAW_WIKI_ROOT / "sources" / "中华人民共和国政府采购法实施条例.md",
        "positioning": "采购需求、差别待遇、采购文件编制和监督责任的核心行政法规。",
        "review_uses": [
            "审查采购需求是否完整明确。",
            "审查评分条件是否与项目特点和实际需要相适应。",
        ],
        "focus_points": ["第十五条", "第二十条", "第三十二条"],
    },
    "政府采购货物和服务招标投标管理办法": {
        "bridge_type": "source",
        "authority_level": "ministerial-measure",
        "law_target": LAW_WIKI_ROOT / "sources" / "政府采购货物和服务招标投标管理办法.md",
        "positioning": "货物和服务公开招标场景下，评标方法、评审因素、招标文件内容的专门规章。",
        "review_uses": [
            "审查综合评分法是否量化、细化、与采购需求对应。",
            "审查资格条件与评分因素边界。",
        ],
        "focus_points": ["第二十条", "第二十二条", "第五十五条", "第五十七条"],
    },
    "采购需求": {
        "bridge_type": "concept",
        "authority_level": "concept",
        "law_target": LAW_WIKI_ROOT / "concepts" / "采购需求.md",
        "positioning": "采购需求是评分标准、技术条款、履约要求和验收安排的起点。",
        "review_uses": [
            "核对评分因素是否真正对应采购需求。",
            "核对参数、清单、履约要求是否完整闭环。",
        ],
        "focus_points": ["完整", "明确", "需求与评分对应"],
    },
    "资格审查": {
        "bridge_type": "concept",
        "authority_level": "concept",
        "law_target": LAW_WIKI_ROOT / "concepts" / "资格审查.md",
        "positioning": "资格审查决定供应商能否进入后续评审阶段，是资格与评分边界的核心概念。",
        "review_uses": [
            "识别资格条件是否重复进入评分。",
            "区分资格性要求和评审因素。",
        ],
        "focus_points": ["资格条件", "资格审查", "边界错位"],
    },
    "招标投标": {
        "bridge_type": "topic",
        "authority_level": "topic",
        "law_target": LAW_WIKI_ROOT / "topics" / "招标投标.md",
        "positioning": "公开招标场景下的综合程序主题，用于串联公告、文件、开评标和中标结果处理。",
        "review_uses": [
            "从程序角度理解评分、资格、澄清修改和中标结果告知的关系。",
        ],
        "focus_points": ["程序链条", "评标", "中标结果"],
    },
    "政府采购当事人": {
        "bridge_type": "topic",
        "authority_level": "topic",
        "law_target": LAW_WIKI_ROOT / "topics" / "政府采购当事人.md",
        "positioning": "说明采购人、代理机构、供应商、评审专家各自的职责边界。",
        "review_uses": [
            "判断采购人或代理机构设置条件是否越界。",
        ],
        "focus_points": ["采购人", "代理机构", "供应商"],
    },
    "监督检查与法律责任": {
        "bridge_type": "topic",
        "authority_level": "topic",
        "law_target": LAW_WIKI_ROOT / "topics" / "监督检查与法律责任.md",
        "positioning": "用于说明违规设置条件、违规编制采购文件可能触发的责任后果。",
        "review_uses": [
            "在风险结论后补足责任层面的理解入口。",
        ],
        "focus_points": ["责任", "监督检查", "违规后果"],
    },
}


FINDING_SPECS = {
    "评分项未细化量化": {
        "finding_type": "scoring",
        "risk_level": "high-risk",
        "definition": "评分标准存在主观弹性、横向比较或优良中差等表达，未形成可执行、可复核的量化闭环。",
        "risk_nature": "规则支持的高风险",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应当细化和量化。",
            "《中华人民共和国政府采购法实施条例》第十五条：采购需求应当完整、明确。",
        ],
        "legal_bridge_ids": ["政府采购货物和服务招标投标管理办法", "中华人民共和国政府采购法实施条例", "采购需求"],
        "scope": [
            "适用于综合评分法评分表、方案分、履约能力分等条款审查。",
            "特别关注“优良中差”“横向比较”“专家综合评价”等表达。",
        ],
        "trigger_patterns": ["优加/良加/中加/差不加分", "横向比较", "综合评价但未列明量化区间"],
        "counter_examples": ["采用固定区间、固定分值、固定扣分逻辑的评分条款。"],
        "review_actions": ["核对是否量化到区间和对应分值。", "核对评分因素是否与采购需求逐项对应。"],
    },
    "法定资格条件进入评分": {
        "finding_type": "qualification-boundary",
        "risk_level": "high-risk",
        "definition": "将独立承担民事责任、无重大违法记录、依法缴纳税收和社保等法定资格条件写入评分因素。",
        "risk_nature": "规则支持的高风险",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：资格条件不得作为评审因素。",
            "《中华人民共和国政府采购法》第二十二条、第二十三条：资格条件和资格审查应依法设置并进行审查。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法", "政府采购货物和服务招标投标管理办法", "资格审查"],
        "scope": ["适用于法定资格条件、诚信记录、纳税社保等资格性事项被写入评分的条款。"],
        "trigger_patterns": ["独立承担民事责任进入评分", "无重大违法记录进入评分", "法定资格不满足则本项不得分"],
        "counter_examples": ["仅在资格审查表核验法定资格，不进入评分的写法。"],
        "review_actions": ["先识别是否属于法定资格条件。", "属于资格门槛的，应回收到资格审查。"],
    },
    "特定许可证或准入资质进入评分": {
        "finding_type": "qualification-boundary",
        "risk_level": "high-risk",
        "definition": "将特定许可证、备案凭证、经营资质等本应先审查是否具备的准入性条件写入评分因素。",
        "risk_nature": "规则支持的高风险",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：资格条件不得作为评审因素。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与项目特点和实际需要相适应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "资格审查"],
        "scope": ["适用于医疗器械许可、行业准入许可证、备案凭证、强制资质等入分条款。"],
        "trigger_patterns": ["许可证进入评分", "经营备案凭证进入评分", "不满足某准入资质则本项不得分"],
        "counter_examples": ["法律法规明确要求且仅在资格审查阶段核验的准入资质。"],
        "review_actions": ["区分准入许可与履约能力评价。", "准入资质原则上只做资格审查，不宜再评分。"],
    },
    "证书设置与项目相关性不足": {
        "finding_type": "qualification-scoring",
        "risk_level": "high-risk",
        "definition": "证书、认证、体系、软著等要求与采购标的性能、服务质量或履约能力之间的关联度不足。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与项目特点和实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与货物服务质量、履约能力等相关。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "招标投标"],
        "scope": ["适用于体系认证、职业资格、信息安全认证、荣誉证书等打分条款。"],
        "trigger_patterns": ["ISO/IEC 体系认证", "职业资格证书", "认证范围要求过窄"],
        "counter_examples": ["法律法规明确要求或直接对应法定准入的强制资质。"],
        "review_actions": ["说明证书与标的质量、服务水平、履约能力的直接关系。", "不能说明关系的，删除或降级处理。"],
    },
    "检测报告要求与评审必要性不匹配": {
        "finding_type": "proof-material",
        "risk_level": "high-risk",
        "definition": "要求提供大量检测报告、原材料检验报告或指定标识检测报告，但未充分说明其与本项目评审必要性的关系。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购需求应完整明确，并符合技术、服务、安全等要求。",
            "《政府采购货物和服务招标投标管理办法》第二十二条：样品和检测报告要求需有明确必要性与标准。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于检测报告、原材料检验报告、CMA/CNAS 报告等条款。"],
        "trigger_patterns": ["CMA/CNAS 检测报告", "原材料检验报告", "投标时提供检测报告"],
        "counter_examples": ["法律法规明确要求或确需验证关键安全性能且标准、项目、机构边界清晰的情形。"],
        "review_actions": ["核对检测报告是否直接服务于本项目核心评审。", "不能说明必要性的，不宜叠加检测报告门槛。"],
    },
    "原件备查与评审可操作性不足": {
        "finding_type": "proof-material",
        "risk_level": "rule-backed",
        "definition": "大量使用原件备查、证明材料不清晰即不得分、专家无法判断即不得分等写法，削弱评审可操作性和稳定性。",
        "risk_nature": "规则支持的中高风险",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应细化量化并与采购需求对应。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与项目特点和实际需要相适应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于原件备查、无法判断不得分、证明文件不清晰不得分等条款。"],
        "trigger_patterns": ["原件备查", "专家无法判断不得分", "不清晰导致无法判断不得分"],
        "counter_examples": ["对关键资格材料作有限核验，但不直接放大为普遍性评分障碍的写法。"],
        "review_actions": ["区分合理核验与过度证明。", "优先改为清晰、稳定、可远程核验的评分口径。"],
    },
    "原厂授权或厂家证明要求过严": {
        "finding_type": "proof-material",
        "risk_level": "high-risk",
        "definition": "以原厂授权、厂家证明、背书文件等作为普遍性评分或投标证明要求，可能超出项目必要范围。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于原厂授权、厂家授权、厂商证明、厂商背书等条款。"],
        "trigger_patterns": ["原厂授权", "厂家授权", "厂商证明", "厂商背书"],
        "counter_examples": ["法律法规明确要求或涉及专有维保责任、兼容性责任且必要性充分说明的少数情形。"],
        "review_actions": ["核对是否存在品牌锁定或渠道限制。", "能以功能承诺和履约责任替代的，不宜要求原厂背书。"],
    },
    "查询截图或平台核验要求过细": {
        "finding_type": "proof-material",
        "risk_level": "rule-backed",
        "definition": "要求提供多平台查询截图、网站状态截图或特定页面截图，容易把形式性核验放大为评分门槛。",
        "risk_nature": "规则支持的中高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：条件设置应与项目特点和实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于认e云、学信网、官网状态截图、平台查询截图等条款。"],
        "trigger_patterns": ["查询截图", "认e云", "网站状态为有效", "官网截图"],
        "counter_examples": ["少量必要核验且采购人、评审系统可自行查询验证的情形。"],
        "review_actions": ["核对是否能由采购人或评审系统自行核验。", "避免把截图形式要求写成直接得分门槛。"],
    },
    "固定月份社保作为评分条件": {
        "finding_type": "labor-proof",
        "risk_level": "high-risk",
        "definition": "以投标截止日前固定月份、连续月数或指定时间段社保证明作为评分前提，容易形成不合理限制。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "政府采购当事人"],
        "scope": ["适用于团队成员、项目负责人、自有员工要求中按固定月份或连续时长提交社保的条款。"],
        "trigger_patterns": ["近3个月社保", "2023年3月至5月社保", "连续缴纳若干月社保"],
        "counter_examples": ["仅用于核验劳动关系真实性，且不与固定月份、连续月数或评分门槛绑定的写法。"],
        "review_actions": ["区分劳动关系核验与评分门槛。", "避免把固定时间段社保写成得分前提。"],
    },
    "自有员工或社保绑定评分条件": {
        "finding_type": "labor-proof",
        "risk_level": "high-risk",
        "definition": "要求项目负责人或团队成员必须为投标人自有员工，且以社保作为直接评分前提，容易对供应商形成组织方式限制。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：不得设置与履约无关或其他不合理条件。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与服务水平、履约能力等相关。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "政府采购当事人"],
        "scope": ["适用于自有员工、以社保为准、拟派人员必须为本单位缴纳社保等评分条款。"],
        "trigger_patterns": ["拟派人员须为自有员工", "以社保为准", "不满足则本项不得分"],
        "counter_examples": ["仅要求中标后建立稳定服务团队，未把社保或自有员工状态直接写入评分门槛的情形。"],
        "review_actions": ["先看是否真正影响履约。", "能以履约承诺、驻场安排、响应责任替代的，不宜直接绑定社保得分。"],
    },
    "中小企业政策口径与所属行业需明确": {
        "finding_type": "policy-application",
        "risk_level": "rule-backed",
        "definition": "中小企业声明、所属行业、价格扣除口径或优惠主体范围表述不完整，容易引发政策适用分歧。",
        "risk_nature": "规则支持的中风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第六条：政府采购应落实促进中小企业发展等政策。",
            "《政府采购货物和服务招标投标管理办法》第五条：招标投标活动中应落实促进中小企业发展等政府采购政策。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "招标投标"],
        "scope": ["适用于价格扣除、专门面向中小企业采购、所属行业判断等条款。"],
        "trigger_patterns": ["本项目是否专门面向中小企业", "所属行业", "价格扣除 10%"],
        "counter_examples": ["已完整写明标的所属行业、优惠主体、计算方式和声明资料要求的条款。"],
        "review_actions": ["核对标的所属行业是否明确。", "核对优惠主体、计算方式、声明资料是否一致。"],
    },
    "荣誉或评级级别要求过高且口径不清": {
        "finding_type": "award-rating",
        "risk_level": "high-risk",
        "definition": "以国家级、省级、市级荣誉、评级、示范单位等作为评分依据，且层级、认定机关或边界口径不清。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（四）项：不得以特定行政区域或者特定行业的奖项作为加分条件。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应细化量化并与采购需求对应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "招标投标"],
        "scope": ["适用于荣誉、评级、标准化示范单位、试点单位等条款。"],
        "trigger_patterns": ["国家级/省级/市级", "示范单位", "试点单位", "副省级口径不清"],
        "counter_examples": ["法律法规明确要求或项目履约成果确需特定等级支撑的极少数情形。"],
        "review_actions": ["核对是否构成与项目无关的存量资源加分。", "核对层级、认定机关和评分边界。"],
    },
    "服务采购不宜按买人或无关资历堆砌逻辑组织评分": {
        "finding_type": "service-design",
        "risk_level": "high-risk",
        "definition": "服务采购中大量围绕人员学历、职称、培训证书、团队人数等堆砌分值，弱化对真实服务能力的评价。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购需求应当完整、明确。",
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项：评分条件应与履约需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与服务水平、履约能力等相关。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于社工服务、咨询服务、物业服务等服务采购。"],
        "trigger_patterns": ["至少20人", "副高及以上", "团队成员证书堆砌", "买人化评分"],
        "counter_examples": ["与项目履约组织直接对应、人数边界明确且必要性充分说明的安排。"],
        "review_actions": ["先回到服务目标和服务流程。", "围绕结果、流程、响应机制重构评分逻辑。"],
    },
    "现场踏勘或样品要求不宜直接进入评分": {
        "finding_type": "sample-demo",
        "risk_level": "high-risk",
        "definition": "将样品、现场演示、方案讲解、踏勘等程序性安排转化为评分或隐性门槛。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第二十二条：一般不得要求样品，特殊情形需明确标准和方法。",
            "《政府采购货物和服务招标投标管理办法》第二十六条：现场考察、答疑应统一组织。",
        ],
        "legal_bridge_ids": ["政府采购货物和服务招标投标管理办法", "招标投标", "采购需求"],
        "scope": ["适用于样品、演示、讲解、现场踏勘和答辩条款。"],
        "trigger_patterns": ["样品", "现场演示", "方案讲解", "踏勘"],
        "counter_examples": ["仅凭书面方式不能准确描述采购需求时，已明确评审标准和方法的情形。"],
        "review_actions": ["说明书面评审为何不足。", "若确需样品或演示，写明标准、方法、条件和验收衔接。"],
    },
    "服务网点或经营场地要求与项目相关性不足": {
        "finding_type": "regional-service",
        "risk_level": "high-risk",
        "definition": "要求供应商在特定地域设常驻机构、办公场所或服务网点，容易形成地域性门槛。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条第（二）项、第（八）项：不得设置与项目特点和实际需要不相适应的条件。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购当事人", "招标投标"],
        "scope": ["适用于服务便利性、本地网点、本地场所证明等条款。"],
        "trigger_patterns": ["深圳市内设有常驻服务机构", "办公场所租赁合同", "本地服务网点"],
        "counter_examples": ["以中标后响应时效、服务承诺替代本地场所门槛的写法。"],
        "review_actions": ["改写为响应时效或驻场承诺。", "避免以地域和经营场地直接评分。"],
    },
    "评标方法模板切换不完整": {
        "finding_type": "template-residue",
        "risk_level": "high-risk",
        "definition": "同一文件中出现互相冲突的评标方法、采购方式、模板残留或版本错配条款。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购文件应围绕完整、明确的采购需求编制。",
            "《政府采购货物和服务招标投标管理办法》第二十条：招标文件应载明评标方法、评标标准和投标无效情形。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "招标投标"],
        "scope": ["适用于模板复用、采购方式切换、评分方法切换不彻底的文件。"],
        "trigger_patterns": ["综合评分法与其他方法残留并存", "模板条款未清理", "版本错配"],
        "counter_examples": ["同一方法下仅作说明性解释且不冲突的条款。"],
        "review_actions": ["逐章核对采购方式、评标方法、投标无效情形是否一致。", "清理草稿残留和跨模板内容。"],
    },
    "货物项目价格分设置过低": {
        "finding_type": "price-weight",
        "risk_level": "high-risk",
        "definition": "货物项目价格分低于法定底线，直接改变综合评分法的法定结构。",
        "risk_nature": "规则支持的高风险",
        "legal_basis": [
            "《政府采购货物和服务招标投标管理办法》第五十五条：货物项目价格分值占总分值的比重不得低于30%。",
        ],
        "legal_bridge_ids": ["政府采购货物和服务招标投标管理办法", "招标投标"],
        "scope": ["适用于货物项目综合评分法的价格分权重设置。"],
        "trigger_patterns": ["货物项目价格权重小于30%"],
        "counter_examples": ["固定价格采购或执行国家统一定价标准且价格不列为评审因素的法定例外。"],
        "review_actions": ["核对项目属性是否确属货物。", "核对价格分比例是否达到法定底线。"],
    },
    "特定组织形态或评级要求可能构成差别待遇": {
        "finding_type": "organization-form",
        "risk_level": "high-risk",
        "definition": "将社会组织评估等级、协会身份、特定组织形态等作为得分前提，可能形成差别待遇。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法》第二十二条：不得以不合理条件对供应商实行差别待遇或者歧视待遇。",
            "《中华人民共和国政府采购法实施条例》第二十条：不合理条件限制或者排斥潜在供应商。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法", "中华人民共和国政府采购法实施条例", "政府采购当事人"],
        "scope": ["适用于社会工作服务、协会资质、社会组织等级等条款。"],
        "trigger_patterns": ["社会组织评估等级", "协会登记状态", "特定组织身份"],
        "counter_examples": ["法律法规明确要求某类组织身份才能承接的特殊事项。"],
        "review_actions": ["核对组织形态与履约能力之间的直接关系。", "避免把组织身份当作一般性加分条件。"],
    },
    "不得设置特定金额业绩门槛": {
        "finding_type": "performance-threshold",
        "risk_level": "high-risk",
        "definition": "以单个项目金额、累计业绩规模或高额金额阈值作为评分前提，可能放大对既有大项目供应商的偏好。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条：设定条件应与项目特点和实际需要相适应。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与采购需求对应。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于业绩评分、业绩门槛、业绩加分条款。"],
        "trigger_patterns": ["业绩金额不低于", "单个项目金额达到", "高额门槛"],
        "counter_examples": ["金额不是门槛，只作为参考且与项目规模充分对应的少数情形。"],
        "review_actions": ["先看项目规模和履约复杂度。", "不能证明必要性的，不设金额阈值。"],
    },
    "采购清单与技术参数表达不闭环": {
        "finding_type": "spec-closure",
        "risk_level": "high-risk",
        "definition": "采购清单、技术参数、偏离表、评分表和验收要求之间表达不闭环，导致投标响应和评审执行脱节。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第十五条：采购需求应完整、明确。",
            "《政府采购货物和服务招标投标管理办法》第二十条：招标文件应体现采购项目实施要求和采购需求。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "采购需求"],
        "scope": ["适用于清单、参数、偏离表、评分表、验收表之间的一致性审查。"],
        "trigger_patterns": ["清单项与参数项不一致", "评分要求找不到对应参数", "验收口径缺失"],
        "counter_examples": ["虽分散表述，但存在明确交叉索引和一致引用关系的文件。"],
        "review_actions": ["按清单、参数、评分、验收四张表做一致性核对。", "缺项或错位的，回到采购需求整体重构。"],
    },
    "格式性事项不得作为评分条件": {
        "finding_type": "format-non-substantive",
        "risk_level": "high-risk",
        "definition": "装订、排序、位置标注、格式完整性等非实质性事项被直接写成评分条件或扣分条件。",
        "risk_nature": "高风险",
        "legal_basis": [
            "《中华人民共和国政府采购法实施条例》第二十条：不得以其他不合理条件限制供应商。",
            "《政府采购货物和服务招标投标管理办法》第五十五条：评审因素应与质量、服务水平、履约能力等相关。",
        ],
        "legal_bridge_ids": ["中华人民共和国政府采购法实施条例", "政府采购货物和服务招标投标管理办法", "招标投标"],
        "scope": ["适用于装订、排序、位置标注、格式模板完整性等条款。"],
        "trigger_patterns": ["格式位置错误扣分", "未按指定排序不得分", "装订要求入分"],
        "counter_examples": ["仅作投标提示、不进入评审分值或废标条件的格式说明。"],
        "review_actions": ["区分非实质性格式要求和实质性响应要求。", "格式要求一般不入分、不入废标。"],
    },
}


RULE_PAGES = {
    "依据分层说明.md": """---
id: rule-layering
title: 依据分层说明
page_type: rule-meta
status: maintained
last_reviewed: 2026-04-20
---

上级导航：[[index]]

## 分层
- 法律
- 行政法规
- 部门规章
- 地方条例、实施细则、交易规则
- 编制指引、模板口径、易发问题清单
- 实务建议

## 使用原则
- 结论必须标注依据层级。
- 实务建议不得表述为法定禁止。
- 同一结论优先引用上位法，再补程序性规章和实务规则。
""",
    "风险分级规则.md": """---
id: rule-risk-level
title: 风险分级规则
page_type: rule
status: maintained
last_reviewed: 2026-04-20
---

上级导航：[[index]]

## 分级
- `high-risk`：有明确法条或规章锚点，且常直接影响公平竞争、评审结果或程序合法性。
- `rule-backed`：有明确制度方向和规则支撑，但仍需结合项目事实判断适用边界。
- `medium-risk`：更多是可执行性、审查可操作性或表达不清问题，需要结合上下文研判。

## 适用原则
- 涉及资格与评分边界、差别待遇、价格分底线、评标方法冲突的，优先列为高风险。
- 涉及政策口径、证明材料适配性、表达闭环问题的，可列为规则支持或中风险。
""",
    "finding-编写规范.md": """---
id: rule-finding-authoring
title: finding-编写规范
page_type: rule
status: maintained
last_reviewed: 2026-04-20
---

上级导航：[[index]]

## 必备字段
- 风险定义
- 风险性质
- 法律依据
- 直接法源 / 概念桥接
- 适用边界
- 常见触发模式
- 审查动作
- 典型项目

## 编写原则
- finding 不写成项目摘要，要写成可复用规则。
- 必须至少链接一个 `legal-bridges/` 页面。
- 典型项目必须来自当前库真实项目页。
""",
    "证据强弱规则.md": """---
id: rule-evidence-strength
title: 证据强弱规则
page_type: rule
status: maintained
last_reviewed: 2026-04-20
---

上级导航：[[index]]

## 证据强度
- 强：扫描页已给出明确触发文本、行号、法规依据，且原文上下文一致。
- 中：扫描页已有风险命中，但主要依赖首轮主题回填，需要人工继续核实。
- 弱：仅有项目摘要或人工批注，没有稳定行号和触发文本。

## 使用要求
- 对外输出结论时优先使用强证据。
- 中证据可用于初筛，不宜直接下确定违法结论。
""",
    "合规结论表达规范.md": """---
id: rule-conclusion-language
title: 合规结论表达规范
page_type: rule
status: maintained
last_reviewed: 2026-04-20
---

上级导航：[[index]]

## 表达原则
- 充分依据时，可表述为“存在高风险”“存在边界错位风险”。
- 依据不足时，应表述为“可能存在”“建议进一步核验”。
- 不得把实务建议直接写成法定禁止。

## 推荐格式
- 风险点
- 风险原因
- 证据位置
- 法律依据
- 结论边界
""",
    "Agent-使用规范.md": """---
id: rule-agent-usage
title: Agent-使用规范
page_type: rule
status: maintained
last_reviewed: 2026-04-20
---

上级导航：[[index]]

## 推荐检索顺序
1. 从 `wiki/projects/` 进入项目页。
2. 查看项目命中的 `wiki/findings/`。
3. 从 finding 跳到 `wiki/legal-bridges/`。
4. 必要时继续跳到 `law-wiki/` 法规基础库。
5. 回到 `raw/full-risk-scans/` 和 `raw/numbered-text/` 取证。

## 禁止做法
- 不要绕过 `finding` 直接用项目页替代规则。
- 不要跳过 `raw/numbered-text/` 直接引用不带行号的结论。
""",
}


FINDING_REFINEMENT_HINTS = {
    "证书设置与项目相关性不足": [
        "建议继续拆分为：体系认证加分、人员资格/职称证书加分、软著/知识产权证明。",
        "当前命中范围仍偏大，容易把一般认证和人员证书混在一起。",
    ],
    "现场踏勘或样品要求不宜直接进入评分": [
        "建议拆分为：样品入分、现场演示入分、方案讲解/答辩入分、一般性踏勘提示。",
        "当前规则容易把允许踏勘或样品清退说明误识别为风险。",
    ],
    "固定月份社保作为评分条件": [
        "建议继续区分：固定月份社保、连续月数社保、指定险种社保。",
        "当前与劳动关系真实性核验的边界仍需继续压实。",
    ],
    "自有员工或社保绑定评分条件": [
        "建议继续区分：项目负责人自有员工、团队成员自有员工、退休返聘替代证明。",
        "当前与履约阶段上岗安排、团队稳定性承诺仍需继续细化。",
    ],
    "法定资格条件进入评分": [
        "建议继续区分：法定资格条件入分、诚信记录入分、纳税社保合规入分。",
        "当前与一般商务能力评价边界仍需继续细化。",
    ],
    "特定许可证或准入资质进入评分": [
        "建议继续区分：医疗器械许可、行业准入许可、备案凭证或特种经营许可入分。",
        "当前与证书类能力加分仍需保持边界清晰。",
    ],
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def obsidian_link_target(path_like: str | Path) -> str:
    path = Path(path_like)
    try:
        rel = path.resolve().relative_to(ROOT.resolve())
    except Exception:
        return str(path_like)
    return str(rel.with_suffix("")).replace("\\", "/")


def extract_risk_titles(scan_text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^### \d+\. (.+)$", scan_text, re.M)]


def extract_risk_blocks(scan_text: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current_title = ""
    for raw in scan_text.splitlines():
        heading = re.match(r"^### \d+\. (.+)$", raw.strip())
        if heading:
            current_title = heading.group(1).strip()
            blocks.setdefault(current_title, [])
            continue
        if current_title:
            blocks[current_title].append(raw)
    return {title: "\n".join(lines).strip() for title, lines in blocks.items()}


def resolve_vault_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return ROOT / path


def vault_metadata_path(path_like: str | Path) -> str:
    path = resolve_vault_path(path_like)
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path_like)


def vault_markdown_path(path_like: str | Path) -> str:
    path = Path(vault_metadata_path(path_like))
    return str(path.with_suffix(".md")).replace("\\", "/")


INVALID_TITLE_EXACT = {
    "",
    "备注：",
    "序号",
    "采购人",
    "项目规模",
    "项目规模（金额）",
    "项目规模(金额)",
    "项目内容：",
    "项目编号：",
    "项目名称：",
    "项目类型：",
    "预算金额：（元）",
    "合同编号：",
    "合同总价：",
    "中标供应商名称",
    "甲　　方：",
    "乙　　方：",
    "联系人：",
    "电话：",
    "QQ号码：",
    "评分项",
    "评分因素",
    "权重",
    "权重(%)",
    "价格",
    "商务部分",
    "技术部分",
    "内容",
    "说明",
}

INVALID_TITLE_CONTAINS = (
    "替换专用",
    "模板草稿",
    "招标文件信息",
    "采购需求申报书",
    "修订明细表",
    "请务必清晰填写",
)

PROJECT_TITLE_HINTS = ("项目", "采购", "服务", "建设", "改造", "系统", "设备", "工程", "平台", "咨询", "审计", "物业", "家具", "实验")


def is_invalid_title_candidate(title: str) -> bool:
    normalized = title.strip()
    if not normalized:
        return True
    if normalized in INVALID_TITLE_EXACT:
        return True
    if any(token in normalized for token in INVALID_TITLE_CONTAINS):
        return True
    if re.fullmatch(r"[A-Za-z]?", normalized):
        return True
    if re.fullmatch(r"\d+(\.\d+)?", normalized):
        return True
    if normalized.endswith("：") and len(normalized) <= 8:
        return True
    return False


def looks_like_project_title(title: str) -> bool:
    normalized = title.strip()
    if is_invalid_title_candidate(normalized):
        return False
    return any(token in normalized for token in PROJECT_TITLE_HINTS)


def score_title(title: str) -> tuple[int, int, int, str]:
    prefixed = 1 if any(title.startswith(f"{prefix}-") for prefix in ITEM_TYPE_PREFIXES) else 0
    generic = 1 if is_invalid_title_candidate(title) or any(token in title for token in ("合同编号", "合同总价", "项目名称：", "联系人：", "电话：", "QQ号码：")) else 0
    noisy = 1 if any(token in title for token in ("-docx版", "（版本", "版本1", "案例", "模板草稿", "中标供应商名称", "替换专用")) else 0
    return (generic, prefixed, noisy, len(title), title)


def choose_canonical_project_title(candidates: list[dict[str, str]]) -> str:
    titles = [candidate["title"].strip() for candidate in candidates if candidate.get("title") and not is_invalid_title_candidate(candidate["title"])]
    if not titles:
        return "未命名项目"
    return sorted(titles, key=score_title)[0]


def select_primary_project_title(numbered_title: str, source_title: str, scan_title: str, old_titles: list[dict[str, str]]) -> str:
    if numbered_title and not is_invalid_title_candidate(numbered_title):
        if looks_like_project_title(numbered_title):
            return numbered_title
        if not source_title and not scan_title:
            return numbered_title

    for candidate in (source_title, scan_title):
        if candidate and not is_invalid_title_candidate(candidate):
            if candidate.startswith("案例") and scan_title:
                return scan_title
            return candidate
    if source_title.startswith("案例") and scan_title:
        return scan_title
    return choose_canonical_project_title(old_titles)


def slug_title_from_scan(scan_title: str) -> str:
    title = scan_title.replace(" 全风险点扫描（第二轮增强）", "").replace(" 全风险点扫描", "")
    if "-" in title:
        maybe_prefix, rest = title.split("-", 1)
        if maybe_prefix in ITEM_TYPE_PREFIXES:
            return rest
    return title


def normalize_source_file(source_file: str) -> str:
    path = resolve_vault_path(source_file)
    if path.exists() and str(path.resolve()).startswith(str(SOURCE_DIR.resolve())):
        return str(path.resolve())
    basename_matches = list(SOURCE_DIR.rglob(path.name))
    if len(basename_matches) == 1:
        return str(basename_matches[0].resolve())
    stem_matches = [candidate for candidate in SOURCE_DIR.rglob("*") if candidate.is_file() and candidate.suffix.lower() in {".doc", ".docx"} and candidate.stem == path.stem]
    if len(stem_matches) == 1:
        return str(stem_matches[0].resolve())
    return source_file


def cleaned_title_from_source(source_file: str) -> str:
    name = Path(source_file).stem
    name = re.sub(r"^\[[^\]]+\]", "", name).strip()
    name = re.sub(r"^\d+[.\-_、]", "", name).strip()
    name = re.sub(r"\s*\(\d+\)$", "", name).strip()
    name = re.sub(r"-测试用$", "", name).strip()
    name = re.sub(r"-docx版$", "", name).strip()
    name = name.replace("项目采购需求书", "采购项目").replace("需求书", "").strip()
    return name if not is_invalid_title_candidate(name) else "未命名项目"


def parse_numbered_lines(numbered_file: str) -> list[str]:
    path = resolve_vault_path(numbered_file)
    if not path.exists():
        return []
    lines = []
    for raw in read_text(path).splitlines():
        match = re.match(r"^\d{4}:\s?(.*)$", raw)
        if match:
            lines.append(match.group(1).strip())
    return lines


def next_nonempty(lines: list[str], idx: int) -> str:
    for pos in range(idx + 1, min(len(lines), idx + 5)):
        if lines[pos].strip():
            return lines[pos].strip()
    return ""


def parse_numbered_metadata(numbered_file: str) -> dict[str, str]:
    lines = parse_numbered_lines(numbered_file)
    meta: dict[str, str] = {}
    for idx, line in enumerate(lines):
        if line in {"项目名称：", "项目名称"}:
            candidate = next_nonempty(lines, idx)
            if candidate and candidate not in {"替换专用XXXX", "项目名称："} and not is_invalid_title_candidate(candidate):
                meta["title"] = candidate
        elif line in {"项目编号：", "项目编号"}:
            candidate = next_nonempty(lines, idx)
            if candidate and candidate not in {"**********", "项目编号："}:
                meta["project_code"] = candidate
        elif line in {"项目类型：", "项目类型"}:
            candidate = next_nonempty(lines, idx)
            if "货物" in candidate:
                meta["procurement_type"] = "货物"
            elif "服务" in candidate:
                meta["procurement_type"] = "服务"
    if "title" not in meta:
        for line in lines[:20]:
            if (
                line
                and "招标文件" not in line
                and "采购需求申报书" not in line
                and "修订明细表" not in line
                and line not in {"项目名称：", "项目编号：", "招标文件信息"}
                and not is_invalid_title_candidate(line)
            ):
                meta["title"] = line
                break
    return meta


def make_project_page_name(title: str, source_file: str, used_names: set[str]) -> str:
    base = title.strip() or "未命名项目"
    candidate = base
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    project_code = parse_project_code(source_file)
    if project_code != "unknown":
        candidate = f"{base}__{project_code}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate

    stem = Path(source_file).stem
    stem = re.sub(r"^\[[^\]]+\]", "", stem).strip()
    stem = re.sub(r"[\\/:\*\?\"<>\|]", "_", stem)
    candidate = f"{base}__{stem}"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    index = 2
    while True:
        candidate = f"{base}__{index}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = read_text(path)
    if not text.startswith("---\n"):
        return {}
    _, fm, _ = text.split("---", 2)
    data = {}
    for raw in fm.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def parse_manifest_page(path: Path) -> dict[str, object]:
    meta: dict[str, str] = {}
    sections: dict[str, list[str]] = defaultdict(list)
    current_section = ""
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        if line.startswith("- "):
            body = line[2:].strip()
            if current_section:
                sections[current_section].append(body)
                continue
            if ":" in body:
                key, value = body.split(":", 1)
                meta[key.strip()] = value.strip()

    source_file = meta.get("source_file", "")
    normalized_source = normalize_source_file(source_file) if source_file else ""
    return {
        "title": path.stem,
        "source_file": normalized_source,
        "item_type": meta.get("item_type", ""),
        "project_code": meta.get("project_code", ""),
        "procurement_type": meta.get("procurement_type", ""),
        "review_basis": meta.get("review_basis", ""),
        "has_comments": meta.get("has_comments", "no"),
        "comment_count": int(meta.get("comment_count", "0") or 0),
        "risk_count": int(meta.get("risk_count", "0") or 0),
        "priority": meta.get("priority", ""),
        "evidence_status": meta.get("evidence_status", ""),
        "scan_status": meta.get("scan_status", ""),
        "top_findings": sections.get("top_findings", []),
        "current_focus": sections.get("current_focus", []),
    }


def build_manifest_index() -> dict[str, dict[str, object]]:
    manifests: dict[str, dict[str, object]] = {}
    for path in sorted(MANIFEST_DIR.glob("*.md")):
        manifest = parse_manifest_page(path)
        source_file = str(manifest.get("source_file", ""))
        if source_file:
            manifests[source_file] = manifest
    return manifests


def group_records_by_source_file(records: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in records:
        grouped[record["source_file"]].append(record)
    return dict(grouped)


def parse_project_code(source_file: str) -> str:
    name = Path(source_file).name
    match = re.search(r"\[([^\]]+)\]", name)
    return match.group(1) if match else "unknown"


def build_old_project_records() -> list[dict[str, str]]:
    records = []
    for path in PROJECT_DIR.glob("*.md"):
        meta = parse_frontmatter(path)
        source_file = meta.get("source_file")
        title = meta.get("title")
        if source_file and title:
            records.append(
                {
                    "path": str(path),
                    "source_file": normalize_source_file(source_file),
                    "title": title,
                    "project_code": meta.get("project_code", ""),
                    "procurement_type": meta.get("procurement_type", ""),
                    "item_type": meta.get("item_type", ""),
                    "region": meta.get("region", "深圳"),
                    "status": meta.get("status", "needs-review"),
                }
            )
    return records


def build_canonical_projects() -> list[dict[str, object]]:
    old_records = build_old_project_records()
    old_by_source = group_records_by_source_file(old_records)
    project_records = []

    for scan_path in sorted(SCAN_DIR.glob("*.md")):
        scan_text = read_text(scan_path)
        source_match = re.search(r"^- source_file: (.+)$", scan_text, re.M)
        item_match = re.search(r"^- item_type: (.+)$", scan_text, re.M)
        numbered_match = re.search(r"^- numbered_snapshot: (.+)$", scan_text, re.M)
        if not source_match or not item_match or not numbered_match:
            continue

        source_file = normalize_source_file(source_match.group(1).strip())
        item_type = item_match.group(1).strip()
        numbered_file = str(resolve_vault_path(numbered_match.group(1).strip()))
        numbered_meta = parse_numbered_metadata(numbered_file)
        risk_titles = []
        for title in extract_risk_titles(scan_text):
            if title in FINDING_SPECS and title not in risk_titles:
                risk_titles.append(title)
        raw_title = scan_text.splitlines()[0].lstrip("# ").strip()
        source_title = cleaned_title_from_source(source_file)
        scan_title = slug_title_from_scan(raw_title)
        title = select_primary_project_title(numbered_meta.get("title", ""), source_title, scan_title, old_by_source.get(source_file, []))
        if title == "未命名项目":
            fallback_title = source_title
            title = fallback_title if fallback_title != "未命名项目" else scan_title

        valid_old = [item for item in old_by_source.get(source_file, []) if not is_invalid_title_candidate(item["title"])]
        old_meta = sorted(valid_old, key=lambda item: score_title(item["title"]))[0] if valid_old else {}
        procurement_type = old_meta.get("procurement_type") or numbered_meta.get("procurement_type") or ITEM_TYPE_TO_PROCUREMENT.get(item_type, "未知")
        region = old_meta.get("region") or "深圳"
        status = "reviewed" if risk_titles else "needs-review"
        legal_bridge_ids = []
        for risk_title in risk_titles:
            for bridge in FINDING_SPECS[risk_title]["legal_bridge_ids"]:
                if bridge not in legal_bridge_ids:
                    legal_bridge_ids.append(bridge)

        project_records.append(
            {
                "title": title,
                "project_code": old_meta.get("project_code") or numbered_meta.get("project_code") or parse_project_code(source_file),
                "procurement_type": procurement_type,
                "item_type": item_type,
                "region": region,
                "status": status,
                "source_file": source_file,
                "scan_file": str(scan_path),
                "numbered_file": numbered_file,
                "risk_titles": risk_titles,
                "legal_bridge_ids": legal_bridge_ids,
                "scan_stem": scan_path.stem,
            }
        )

    canonical: dict[str, dict[str, object]] = {}
    for record in project_records:
        source_file = str(record["source_file"])
        if source_file not in canonical:
            canonical[source_file] = record
            continue
        current = canonical[source_file]
        best_title = choose_canonical_project_title([{"title": str(current["title"])}, {"title": str(record["title"])}])
        canonical[source_file] = current if current["title"] == best_title else record
    projects = sorted(canonical.values(), key=lambda item: (str(item["title"]), str(item["source_file"])))
    used_page_names: set[str] = set()
    for project in projects:
        project["page_name"] = make_project_page_name(str(project["title"]), str(project["source_file"]), used_page_names)
        project["canonical_title"] = project["title"]

    title_counts = Counter(str(project["title"]) for project in projects)
    for project in projects:
        if title_counts[str(project["title"])] == 1:
            project["display_title"] = project["title"]
            continue
        project_code = str(project["project_code"])
        stem = Path(str(project["source_file"])).stem
        stem = re.sub(r"^\[[^\]]+\]", "", stem).strip()
        suffix = project_code if project_code != "unknown" else stem
        if suffix == str(project["title"]):
            suffix = stem
        project["display_title"] = f"{project['title']}（区分：{suffix}）"
    return projects


def render_project_page(project: dict[str, object], finding_specs: dict[str, dict[str, object]]) -> str:
    risk_links = []
    for title in project["risk_titles"]:
        if title in finding_specs:
            risk_links.append(f"- [[findings/{title}|{title}]]")
        else:
            risk_links.append(f"- {title}")

    bridge_links = [f"- [[legal-bridges/{bridge}|{bridge}]]" for bridge in project["legal_bridge_ids"]]

    scan_link = obsidian_link_target(str(project["scan_file"]))
    numbered_link = obsidian_link_target(str(project["numbered_file"]))

    return "\n".join(
        [
            "---",
            f"id: project-{project['page_name']}",
            f"title: {project['display_title']}",
            f"canonical_title: {project['title']}",
            f"page_name: {project['page_name']}",
            f"project_code: {project['project_code']}",
            f"procurement_type: {project['procurement_type']}",
            f"item_type: {project['item_type']}",
            f"region: {project['region']}",
            f"status: {project['status']}",
            f"source_file: {vault_metadata_path(str(project['source_file']))}",
            f"scan_file: {vault_metadata_path(str(project['scan_file']))}",
            f"numbered_file: {vault_metadata_path(str(project['numbered_file']))}",
            "last_reviewed: 2026-04-20",
            "---",
            "",
            "上级导航：[[index]]",
            "",
            "## 项目概览",
            "- 当前页面为标准化项目入口页，只负责连接风险规则、证据和法规依据。",
            f"- 项目编号：`{project['project_code']}`",
            f"- 采购类型：{project['procurement_type']}",
            f"- 品目：{project['item_type']}",
            "",
            "## 审查入口",
            f"- [[{scan_link}|full-risk-scan]]",
            f"- [[{numbered_link}|numbered-text]]",
            "",
            "## 命中风险",
            *(risk_links or ["- 当前扫描页未命中标准 finding，需人工复核。"]),
            "",
            "## 法规依据入口",
            *(bridge_links or ["- 当前未建立法规桥接，需人工补链。"]),
            "",
            "## 证据边界 / 不确定点",
            "- 项目页只做导航与归集，具体证据以 raw 层扫描页和带行号正文为准。",
            "- 结论表达应优先依据 `findings/` 和 `legal-bridges/` 页面，不直接以项目页替代规则页。",
            "",
        ]
    )


def render_finding_page(title: str, spec: dict[str, object], projects: list[dict[str, str]]) -> str:
    legal_links = [f"- [[legal-bridges/{bridge}|{bridge}]]" for bridge in spec["legal_bridge_ids"]]
    project_links = [f"- [[projects/{project['page_name']}|{project['display_title']}]]" for project in projects]
    return "\n".join(
        [
            "---",
            f"id: finding-{title}",
            f"title: {title}",
            f"finding_type: {spec['finding_type']}",
            f"risk_level: {spec['risk_level']}",
            "status: maintained",
            "last_reviewed: 2026-04-20",
            "---",
            "",
            "上级导航：[[index]]",
            "",
            "## 风险定义",
            str(spec["definition"]),
            "",
            "## 风险性质",
            f"- {spec['risk_nature']}",
            "",
            "## 法律依据",
            *[f"- {item}" for item in spec["legal_basis"]],
            "",
            "## 直接法源 / 概念桥接",
            *legal_links,
            "",
            "## 适用边界",
            *[f"- {item}" for item in spec["scope"]],
            "",
            "## 常见触发模式",
            *[f"- {item}" for item in spec["trigger_patterns"]],
            "",
            "## 常见误判 / 反向例外",
            *[f"- {item}" for item in spec["counter_examples"]],
            "",
            "## 审查动作",
            *[f"- {item}" for item in spec["review_actions"]],
            "",
            "## 典型项目",
            *(project_links or ["- 待补充"]),
            "",
            "## 证据边界 / 不确定点",
            "- finding 页是标准规则节点，不替代项目扫描页和原文行号证据。",
            "",
        ]
    )


def render_legal_bridge_page(title: str, spec: dict[str, object]) -> str:
    finding_links = [f"- [[findings/{name}|{name}]]" for name in spec["finding_titles"]]
    review_uses = [f"- {item}" for item in spec["review_uses"]]
    focus_points = [f"- {item}" for item in spec["focus_points"]]
    law_target = spec["law_target"]
    law_link = f"[[{obsidian_link_target(law_target)}|{title}]]"
    return "\n".join(
        [
            "---",
            f"id: bridge-{title}",
            f"title: {title}",
            f"bridge_type: {spec['bridge_type']}",
            f"authority_level: {spec['authority_level']}",
            "status: maintained",
            f"law_target: {vault_metadata_path(law_target)}",
            "---",
            "",
            "上级导航：[[index]]",
            "",
            "## 桥接定位",
            spec["positioning"],
            "",
            "## 当前库审查用途",
            *review_uses,
            "",
            "## 高频条款 / 高频关注点",
            *focus_points,
            "",
            "## 关联风险点",
            *finding_links,
            "",
            "## 法规基础库入口",
            f"- {law_link}",
            "",
        ]
    )


def cleanup_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.md"):
        path.unlink()


def build_bridge_specs() -> dict[str, dict[str, object]]:
    usage = defaultdict(list)
    for finding_title, spec in FINDING_SPECS.items():
        for bridge in spec["legal_bridge_ids"]:
            usage[bridge].append(finding_title)

    bridge_specs = {}
    for title, spec in LEGAL_BRIDGES.items():
        bridge_specs[title] = dict(spec)
        bridge_specs[title]["finding_titles"] = sorted(usage.get(title, []))
    return bridge_specs


def write_legal_bridges(bridge_specs: dict[str, dict[str, object]]) -> None:
    cleanup_directory(BRIDGE_DIR)
    for title, spec in bridge_specs.items():
        write_text(BRIDGE_DIR / f"{title}.md", render_legal_bridge_page(title, spec))


def write_rules() -> None:
    for filename, content in RULE_PAGES.items():
        write_text(RULE_DIR / filename, content)


def write_findings(projects: list[dict[str, object]]) -> None:
    cleanup_directory(FINDING_DIR)
    project_by_finding: dict[str, list[dict[str, str]]] = defaultdict(list)
    for project in projects:
        for risk_title in project["risk_titles"]:
            project_by_finding[risk_title].append(
                {"title": str(project["title"]), "display_title": str(project["display_title"]), "page_name": str(project["page_name"])}
            )

    for title, spec in FINDING_SPECS.items():
        linked_projects = sorted(project_by_finding.get(title, []), key=lambda item: (item["title"], item["page_name"]))[:12]
        write_text(FINDING_DIR / f"{title}.md", render_finding_page(title, spec, linked_projects))


def write_projects(projects: list[dict[str, object]]) -> None:
    cleanup_directory(PROJECT_DIR)
    for project in projects:
        write_text(PROJECT_DIR / f"{project['page_name']}.md", render_project_page(project, FINDING_SPECS))


def render_finding_to_law_coverage(projects: list[dict[str, object]]) -> str:
    counter = Counter()
    for project in projects:
        counter.update(project["risk_titles"])
    lines = [
        "# finding-to-law-coverage",
        "",
        "## 说明",
        "- 本页核对每个标准风险页是否已经映射到法规桥接层，并统计其命中项目数。",
        "",
        "## 覆盖情况",
    ]
    for title, spec in FINDING_SPECS.items():
        lines.append(f"- {title} | 项目数：{counter.get(title, 0)} | 法规桥接：{'、'.join(spec['legal_bridge_ids'])}")
    return "\n".join(lines)


def render_project_to_finding_coverage(projects: list[dict[str, object]]) -> str:
    lines = [
        "# project-to-finding-coverage",
        "",
        "## 总体状态",
        f"- 项目页数：{len(projects)}",
        f"- 源目录文件数：{len([p for p in SOURCE_DIR.rglob('*') if p.is_file() and p.suffix.lower() in {'.doc', '.docx'}])}",
        "",
        "## 覆盖明细",
    ]
    for project in projects:
        findings = "、".join(project["risk_titles"]) if project["risk_titles"] else "未命中标准 finding"
        lines.append(f"- [[projects/{project['page_name']}|{project['display_title']}]] | 风险数：{len(project['risk_titles'])} | {findings}")
    return "\n".join(lines)


def render_duplicate_project_entries(old_records: list[dict[str, str]]) -> str:
    grouped = group_records_by_source_file(old_records)
    lines = [
        "# duplicate-project-entry-candidates",
        "",
        "## 说明",
        "- 本页记录历史项目页中同一 `source_file` 对应多个项目入口的情况，便于清理兼容页和旧入口。",
        "",
    ]
    count = 0
    for source_file, records in sorted(grouped.items()):
        titles = sorted({record["title"] for record in records})
        if len(titles) <= 1:
            continue
        count += 1
        lines.append(f"## {count}. {Path(source_file).name}")
        lines.append(f"- source_file: {vault_metadata_path(source_file)}")
        for title in titles:
            lines.append(f"- 历史入口：{title}")
        lines.append("")
    if count == 0:
        lines.append("- 未发现重复项目入口。")
    return "\n".join(lines)


def render_raw_risk_orphans(projects: list[dict[str, object]]) -> str:
    known = set(FINDING_SPECS)
    raw_only = []
    for scan_path in sorted(SCAN_DIR.glob("*.md")):
        titles = extract_risk_titles(read_text(scan_path))
        unknown = [title for title in titles if title not in known]
        if unknown:
            raw_only.append((scan_path.name, unknown))
    lines = [
        "# raw-risk-orphans",
        "",
        "## 说明",
        "- 本页列出 raw 层扫描页里出现、但当前标准 finding 体系尚未吸收的风险标题。",
        "",
    ]
    if not raw_only:
        lines.append("- 当前 raw 层风险标题均已映射到标准 finding。")
    else:
        for filename, titles in raw_only:
            lines.append(f"- {filename} | 未映射风险：{'、'.join(titles)}")
    return "\n".join(lines)


def render_full_risk_scan_index(projects: list[dict[str, object]]) -> str:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for project in projects:
        grouped[str(project["item_type"])].append(project)
    lines = [
        "# full-risk-scan-index",
        "",
        "## 说明",
        "- 本页汇总标准化项目入口与 raw 扫描页的对应关系，供按品类检索。",
        "",
    ]
    for item_type in sorted(grouped):
        lines.append(f"## {item_type}")
        for project in sorted(grouped[item_type], key=lambda item: str(item["title"])):
            main = "、".join(project["risk_titles"][:3]) if project["risk_titles"] else "待人工复核"
            scan_link = obsidian_link_target(str(project["scan_file"]))
            lines.append(
                f"- [[projects/{project['page_name']}|{project['display_title']}]] | [[{scan_link}|scan]] | 主要风险：{main}"
            )
        lines.append("")
    return "\n".join(lines)


def render_source_coverage(projects: list[dict[str, object]]) -> str:
    sources = {str(p.resolve()) for p in SOURCE_DIR.rglob("*") if p.is_file() and p.suffix.lower() in {".doc", ".docx"}}
    project_sources = {str(project["source_file"]) for project in projects}
    missing = sorted(sources - project_sources)
    lines = [
        "# source-coverage",
        "",
        "## 总体状态",
        f"- 源目录文件数：{len(sources)}",
        f"- 项目入口覆盖数：{len(project_sources & sources)}",
        f"- 未覆盖数：{len(missing)}",
        "",
    ]
    if missing:
        lines.append("## 未覆盖源文件")
        for item in missing:
            lines.append(f"- {item}")
    else:
        lines.append("- 当前 145 个源文件均已具备标准项目入口。")
    return "\n".join(lines)


def render_ingest_backlog(projects: list[dict[str, object]]) -> str:
    incomplete = [project for project in projects if not project["risk_titles"]]
    lines = [
        "# ingest-backlog",
        "",
        "## 当前状态",
        f"- 无标准 finding 的项目数：{len(incomplete)}",
        "",
    ]
    if incomplete:
        lines.append("## 待补项目")
        for project in incomplete:
            lines.append(f"- [[projects/{project['page_name']}|{project['display_title']}]]")
    else:
        lines.append("- 当前项目入口均已映射到标准 finding。")
    return "\n".join(lines)


def render_corpus_risk_scan(projects: list[dict[str, object]]) -> str:
    counter = Counter()
    for project in projects:
        counter.update(project["risk_titles"])
    lines = [
        "# corpus-risk-scan",
        "",
        "## 说明",
        "- 本页是标准 finding 维度的全库总览，不替代单文件 `full-risk-scan`。",
        "",
        "## 高频风险",
    ]
    for title, count in counter.most_common():
        lines.append(f"- {title}：{count}")
    return "\n".join(lines)


def render_fallback_evidence_hotspots() -> str:
    lines = [
        "# fallback-evidence-hotspots",
        "",
        "## 说明",
        "- 本页统计仍依赖“首轮扫描主题回填”或过于泛化证据的扫描页，用于第二轮质量回炉。",
        "",
    ]
    rows: list[tuple[str, int, int]] = []
    for scan_path in sorted(SCAN_DIR.glob("*.md")):
        text = read_text(scan_path)
        fallback_count = text.count("首轮扫描主题回填")
        generic_count = sum(text.count(marker) for marker in ("位置：评标信息", "位置：招标文件信息", "触发文本：综合评分法", "触发文本：评标信息"))
        if fallback_count or generic_count >= 3:
            rows.append((scan_path.stem, fallback_count, generic_count))
    lines.append(f"- 扫描页总数：{len(list(SCAN_DIR.glob('*.md')))}")
    lines.append(f"- 存在回填或泛化证据的扫描页数：{len(rows)}")
    lines.append("")
    if not rows:
        lines.append("- 当前未发现明显依赖回填证据的扫描页。")
        return "\n".join(lines)
    lines.append("## 热点清单")
    for stem, fallback_count, generic_count in sorted(rows, key=lambda item: (-item[1], -item[2], item[0])):
        lines.append(
            f"- [[raw/full-risk-scans/{stem}|{stem}]] | 回填证据：{fallback_count} | 泛化证据标记：{generic_count}"
        )
    return "\n".join(lines)


def render_project_title_anomalies(projects: list[dict[str, object]]) -> str:
    lines = [
        "# project-title-anomalies",
        "",
        "## 说明",
        "- 本页用于发现项目标题抽取污染、字段名误识别和伪项目名残留。",
        "",
    ]
    anomalies = []
    for project in projects:
        title = str(project["title"]).strip()
        if is_invalid_title_candidate(title) or title in {"采购人", "项目规模", "项目规模（金额）", "项目规模(金额)"}:
            anomalies.append(project)
    lines.append(f"- 项目总数：{len(projects)}")
    lines.append(f"- 标题异常项目数：{len(anomalies)}")
    lines.append("")
    if not anomalies:
        lines.append("- 当前未发现明显标题污染项目。")
        return "\n".join(lines)
    lines.append("## 异常项目")
    for project in anomalies:
        lines.append(
            f"- [[projects/{project['page_name']}|{project['display_title']}]] | canonical_title：{project['title']} | source：{vault_metadata_path(str(project['source_file']))}"
        )
    return "\n".join(lines)


def render_finding_refinement_backlog(projects: list[dict[str, object]]) -> str:
    counter = Counter()
    for project in projects:
        counter.update(project["risk_titles"])
    lines = [
        "# finding-refinement-backlog",
        "",
        "## 说明",
        "- 本页不是风险结论页，而是标准规则体系的质量优化待办。",
        "",
        "## 零命中 finding",
    ]
    zero_hits = [title for title in FINDING_SPECS if counter.get(title, 0) == 0]
    if zero_hits:
        for title in zero_hits:
            lines.append(f"- [[findings/{title}|{title}]] | 当前命中项目数：0 | 建议复核是否继续保留为标准规则。")
    else:
        lines.append("- 当前无零命中 finding。")

    lines.extend(["", "## 高覆盖 finding（建议拆细）"])
    high_coverage = [(title, counter.get(title, 0)) for title in FINDING_SPECS if counter.get(title, 0) >= 100]
    if high_coverage:
        for title, count in sorted(high_coverage, key=lambda item: (-item[1], item[0])):
            lines.append(f"- [[findings/{title}|{title}]] | 命中项目数：{count}")
            for hint in FINDING_REFINEMENT_HINTS.get(title, []):
                lines.append(f"  - {hint}")
    else:
        lines.append("- 当前无需要优先拆细的高覆盖 finding。")

    lines.extend(["", "## 新增候选 finding"])
    lines.append("- 健康证明/健康证要求：已纳入 `health-certificate-watchlist` 专项审计，先区分投标阶段前置证明与中标后上岗前履约材料，再决定是否升级为标准 finding。")
    lines.append("- 原件备查与评审可操作性：区分可合理核验与过度证明要求。")
    lines.append("- 履约阶段上岗资质前置：区分上岗条件、资格条件和评分条件。")
    lines.append("- 样品清退说明与样品入分：区分交易中心通用条款和真实风险条款。")
    return "\n".join(lines)


def render_finding_quality_overview(projects: list[dict[str, object]]) -> str:
    project_counter = Counter()
    fallback_counter = Counter()
    for project in projects:
        scan_path = resolve_vault_path(project["scan_file"])
        if not scan_path.exists():
            continue
        blocks = extract_risk_blocks(read_text(scan_path))
        for title in project["risk_titles"]:
            project_counter[title] += 1
            if "首轮扫描主题回填" in blocks.get(title, ""):
                fallback_counter[title] += 1

    lines = [
        "# finding-quality-overview",
        "",
        "## 说明",
        "- 本页用于判断各 finding 当前是否适合作为企业系统和业务智能体的权威规则入口。",
        "- 这里的“待拆细”不代表 finding 无效，而是代表当前颗粒度过粗、覆盖过宽，直接用于确定性结论存在误判风险。",
        "",
        "## 状态分层",
        "- `可直接用于规则问答`：命中分布相对稳定，且明显弱证据比例不高。",
        "- `可用于初筛，结论需回证据`：规则可用，但项目证据中存在一定比例回填或弱证据，需要回到 `raw/full-risk-scans` 和 `raw/numbered-text`。",
        "- `待拆细 / 待补证据`：命中项目过多或回填占比较高，当前更适合作为召回入口，不宜直接输出确定性结论。",
        "- `零命中待复核`：当前库没有命中项目，需复核保留必要性。",
        "",
        "## finding 状态表",
    ]

    for title in sorted(FINDING_SPECS):
        count = project_counter.get(title, 0)
        fallback = fallback_counter.get(title, 0)
        ratio = (fallback / count) if count else 0.0
        if count == 0:
            status = "零命中待复核"
            action = "确认该规则是否仍应保留在标准规则层。"
        elif count >= 100:
            status = "待拆细 / 待补证据"
            action = "优先拆分子 finding，并补强更具体的条款证据。"
        elif ratio >= 0.3:
            status = "可用于初筛，结论需回证据"
            action = "可用于召回，但输出结论前必须回看扫描页和原文行号。"
        else:
            status = "可直接用于规则问答"
            action = "可作为业务系统规则入口，同时保留证据回链。"
        lines.append(
            f"- [[findings/{title}|{title}]] | 命中项目数：{count} | 回填证据项目数：{fallback} | 回填占比：{ratio:.0%} | 当前状态：{status} | 建议动作：{action}"
        )
    return "\n".join(lines)


def classify_health_certificate_clause(context: str) -> str:
    if any(token in context for token in ("评分", "得分", "评审", "评标", "资格要求", "资格审查", "投标文件", "证明文件", "不得分")):
        return "投标/评审前置，重点复核"
    if any(token in context for token in ("中标后", "签订合同后", "开展工作前", "上岗前", "履约", "服务期间", "配置", "须按照相关法律要求")):
        return "履约或上岗阶段要求，通常不直接作为投标风险"
    return "待人工判断"


def render_health_certificate_watchlist(projects: list[dict[str, object]]) -> str:
    pattern = re.compile(r"健康证|健康证明|职业健康体检")
    entries: list[dict[str, object]] = []
    for project in projects:
        numbered_path = resolve_vault_path(project["numbered_file"])
        if not numbered_path.exists():
            continue
        for raw in read_text(numbered_path).splitlines():
            match = re.match(r"^(\d{4}):\s?(.*)$", raw)
            if not match:
                continue
            line_no = int(match.group(1))
            line = match.group(2).strip()
            if not pattern.search(line):
                continue
            if "基本健康信息" in line:
                continue
            context = line
            status = classify_health_certificate_clause(context)
            entries.append(
                {
                    "project": project,
                    "line_no": line_no,
                    "line": line,
                    "status": status,
                }
            )

    lines = [
        "# health-certificate-watchlist",
        "",
        "## 说明",
        "- 本页专项跟踪招标文件中的健康证明、健康证、职业健康体检条款。",
        "- 该类条款在政府采购中边界很敏感：如果被前置到投标、资格或评分阶段，可能构成不合理限制；如果仅作为中标后上岗前或履约阶段要求，则通常需要结合项目场景进一步判断。",
        "",
        "## 总体情况",
        f"- 命中条款数：{len(entries)}",
        f"- 涉及项目数：{len({str(item['project']['page_name']) for item in entries})}",
        f"- 投标/评审前置：{sum(1 for item in entries if item['status'] == '投标/评审前置，重点复核')}",
        f"- 履约或上岗阶段要求：{sum(1 for item in entries if item['status'] == '履约或上岗阶段要求，通常不直接作为投标风险')}",
        f"- 待人工判断：{sum(1 for item in entries if item['status'] == '待人工判断')}",
        "",
    ]
    if not entries:
        lines.append("- 当前库未识别到健康证明/健康证相关条款。")
        return "\n".join(lines)
    lines.extend(
        [
            "## 命中清单",
        ]
    )
    for item in entries:
        project = item["project"]
        lines.append(
            f"- [[projects/{project['page_name']}|{project['display_title']}]] | 行号：{item['line_no']} | 判断：{item['status']} | 触发文本：{item['line']}"
        )
    lines.extend(
        [
            "",
            "## 使用建议",
            "- 若业务系统收到“投标中要求提供健康证明是否可以”类问题，先查本页判断条款处于投标阶段还是履约阶段。",
            "- 若属于投标/评分前置，应继续回到项目扫描页、项目正文和 `law-wiki/` 判断是否与项目特点和法定要求相适应。",
            "- 若属于中标后上岗前要求，不宜直接输出“违法”结论，应结合行业监管要求、服务场景和条款位置进一步判断。",
        ]
    )
    return "\n".join(lines)


def write_audits(projects: list[dict[str, object]], old_records: list[dict[str, str]]) -> None:
    write_text(AUDIT_DIR / "finding-to-law-coverage.md", render_finding_to_law_coverage(projects))
    write_text(AUDIT_DIR / "project-to-finding-coverage.md", render_project_to_finding_coverage(projects))
    write_text(AUDIT_DIR / "duplicate-project-entry-candidates.md", render_duplicate_project_entries(old_records))
    write_text(AUDIT_DIR / "raw-risk-orphans.md", render_raw_risk_orphans(projects))
    write_text(AUDIT_DIR / "full-risk-scan-index.md", render_full_risk_scan_index(projects))
    write_text(AUDIT_DIR / "source-coverage.md", render_source_coverage(projects))
    write_text(AUDIT_DIR / "ingest-backlog.md", render_ingest_backlog(projects))
    write_text(AUDIT_DIR / "corpus-risk-scan.md", render_corpus_risk_scan(projects))
    write_text(AUDIT_DIR / "fallback-evidence-hotspots.md", render_fallback_evidence_hotspots())
    write_text(AUDIT_DIR / "project-title-anomalies.md", render_project_title_anomalies(projects))
    write_text(AUDIT_DIR / "finding-refinement-backlog.md", render_finding_refinement_backlog(projects))
    write_text(AUDIT_DIR / "finding-quality-overview.md", render_finding_quality_overview(projects))
    write_text(AUDIT_DIR / "health-certificate-watchlist.md", render_health_certificate_watchlist(projects))


def cleanup_export_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.json"):
        path.unlink()


def export_schema_dir() -> Path:
    return EXPORT_DIR / "schema"


def build_project_export_record(project: dict[str, object], manifest: dict[str, object] | None) -> dict[str, object]:
    source_path = vault_metadata_path(str(project["source_file"]))
    scan_path = vault_metadata_path(str(project["scan_file"]))
    numbered_path = vault_metadata_path(str(project["numbered_file"]))
    top_findings = list(manifest.get("top_findings", [])) if manifest else list(project["risk_titles"])
    current_focus = list(manifest.get("current_focus", [])) if manifest else []
    return {
        "id": f"project:{project['page_name']}",
        "page_name": project["page_name"],
        "title": project["title"],
        "display_title": project["display_title"],
        "canonical_title": project["canonical_title"],
        "project_code": project["project_code"],
        "procurement_type": project["procurement_type"],
        "item_type": project["item_type"],
        "region": project["region"],
        "status": project["status"],
        "project_page": f"wiki/projects/{project['page_name']}.md",
        "source_file": source_path,
        "scan_file": scan_path,
        "numbered_file": numbered_path,
        "risk_titles": list(project["risk_titles"]),
        "risk_count": len(project["risk_titles"]),
        "legal_bridge_ids": list(project["legal_bridge_ids"]),
        "legal_bridge_count": len(project["legal_bridge_ids"]),
        "priority": manifest.get("priority") if manifest else "",
        "review_basis": manifest.get("review_basis") if manifest else "",
        "has_comments": manifest.get("has_comments") if manifest else "no",
        "comment_count": manifest.get("comment_count") if manifest else 0,
        "evidence_status": manifest.get("evidence_status") if manifest else "",
        "scan_status": manifest.get("scan_status") if manifest else str(project["status"]),
        "top_findings": top_findings,
        "current_focus": current_focus,
        "query_route": [
            f"wiki/projects/{project['page_name']}.md",
            *[f"wiki/findings/{title}.md" for title in project["risk_titles"]],
            *[f"wiki/legal-bridges/{title}.md" for title in project["legal_bridge_ids"]],
            scan_path,
            numbered_path,
        ],
        "evidence": {
            "scan_file": scan_path,
            "numbered_file": numbered_path,
        },
    }


def build_finding_exports(projects: list[dict[str, object]]) -> list[dict[str, object]]:
    project_by_finding: dict[str, list[dict[str, str]]] = defaultdict(list)
    for project in projects:
        for risk_title in project["risk_titles"]:
            project_by_finding[risk_title].append(
                {
                    "page_name": str(project["page_name"]),
                    "title": str(project["title"]),
                    "display_title": str(project["display_title"]),
                    "project_page": f"wiki/projects/{project['page_name']}.md",
                }
            )

    exports = []
    for title, spec in sorted(FINDING_SPECS.items()):
        linked_projects = sorted(project_by_finding.get(title, []), key=lambda item: (item["title"], item["page_name"]))
        exports.append(
            {
                "id": f"finding:{title}",
                "title": title,
                "finding_page": f"wiki/findings/{title}.md",
                "finding_type": spec["finding_type"],
                "risk_level": spec["risk_level"],
                "risk_nature": spec["risk_nature"],
                "definition": spec["definition"],
                "legal_basis": list(spec["legal_basis"]),
                "legal_bridge_ids": list(spec["legal_bridge_ids"]),
                "scope": list(spec["scope"]),
                "trigger_patterns": list(spec["trigger_patterns"]),
                "counter_examples": list(spec["counter_examples"]),
                "review_actions": list(spec["review_actions"]),
                "project_count": len(linked_projects),
                "projects": linked_projects,
            }
        )
    return exports


def build_legal_bridge_exports(bridge_specs: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    exports = []
    for title, spec in sorted(bridge_specs.items()):
        exports.append(
            {
                "id": f"legal-bridge:{title}",
                "title": title,
                "bridge_page": f"wiki/legal-bridges/{title}.md",
                "bridge_type": spec["bridge_type"],
                "authority_level": spec["authority_level"],
                "law_target": vault_metadata_path(spec["law_target"]),
                "law_target_page": vault_markdown_path(spec["law_target"]),
                "positioning": spec["positioning"],
                "review_uses": list(spec["review_uses"]),
                "focus_points": list(spec["focus_points"]),
                "finding_titles": list(spec["finding_titles"]),
            }
        )
    return exports


def build_audit_exports(projects: list[dict[str, object]]) -> dict[str, object]:
    finding_counter = Counter()
    for project in projects:
        finding_counter.update(project["risk_titles"])
    source_files = [p for p in SOURCE_DIR.rglob("*") if p.is_file() and p.suffix.lower() in {".doc", ".docx"}]
    backlog = [str(project["page_name"]) for project in projects if not project["risk_titles"]]
    return {
        "summary": {
            "project_count": len(projects),
            "source_file_count": len(source_files),
            "reviewed_project_count": sum(1 for project in projects if project["status"] == "reviewed"),
            "needs_review_count": sum(1 for project in projects if project["status"] == "needs-review"),
            "finding_count": len(FINDING_SPECS),
            "legal_bridge_count": len(LEGAL_BRIDGES),
        },
        "top_findings": [{"title": title, "count": count} for title, count in finding_counter.most_common()],
        "ingest_backlog": backlog,
        "audit_pages": {
            "project_to_finding_coverage": "wiki/audits/project-to-finding-coverage.md",
            "finding_to_law_coverage": "wiki/audits/finding-to-law-coverage.md",
            "full_risk_scan_index": "wiki/audits/full-risk-scan-index.md",
            "source_coverage": "wiki/audits/source-coverage.md",
            "ingest_backlog": "wiki/audits/ingest-backlog.md",
            "corpus_risk_scan": "wiki/audits/corpus-risk-scan.md",
            "fallback_evidence_hotspots": "wiki/audits/fallback-evidence-hotspots.md",
            "project_title_anomalies": "wiki/audits/project-title-anomalies.md",
            "finding_refinement_backlog": "wiki/audits/finding-refinement-backlog.md",
            "finding_quality_overview": "wiki/audits/finding-quality-overview.md",
            "health_certificate_watchlist": "wiki/audits/health-certificate-watchlist.md",
        },
    }


def build_graph_export(
    projects: list[dict[str, object]],
    finding_exports: list[dict[str, object]],
    bridge_exports: list[dict[str, object]],
) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(node_id: str, node_type: str, title: str, path: str, **extra: object) -> None:
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)
        node = {"id": node_id, "type": node_type, "title": title, "path": path}
        node.update(extra)
        nodes.append(node)

    def add_edge(source: str, target: str, relation: str) -> None:
        key = (source, target, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": source, "target": target, "relation": relation})

    for export in finding_exports:
        add_node(export["id"], "finding", str(export["title"]), str(export["finding_page"]), risk_level=export["risk_level"])

    for export in bridge_exports:
        add_node(
            export["id"],
            "legal-bridge",
            str(export["title"]),
            str(export["bridge_page"]),
            authority_level=export["authority_level"],
        )
        law_node_id = f"law:{export['title']}"
        add_node(
            law_node_id,
            "law-source",
            str(export["title"]),
            str(export["law_target_page"]),
            authority_level=export["authority_level"],
        )
        add_edge(str(export["id"]), law_node_id, "anchors")
        for finding_title in export["finding_titles"]:
            add_edge(f"finding:{finding_title}", str(export["id"]), "supported_by")

    for project in projects:
        project_id = f"project:{project['page_name']}"
        add_node(
            project_id,
            "project",
            str(project["display_title"]),
            f"wiki/projects/{project['page_name']}.md",
            item_type=project["item_type"],
            procurement_type=project["procurement_type"],
            status=project["status"],
        )
        scan_node_id = f"evidence:scan:{project['page_name']}"
        numbered_node_id = f"evidence:numbered:{project['page_name']}"
        add_node(scan_node_id, "raw-scan", str(project["display_title"]), vault_markdown_path(project["scan_file"]))
        add_node(numbered_node_id, "numbered-text", str(project["display_title"]), vault_markdown_path(project["numbered_file"]))
        add_edge(project_id, scan_node_id, "has_scan")
        add_edge(project_id, numbered_node_id, "has_numbered_text")
        for title in project["risk_titles"]:
            add_edge(project_id, f"finding:{title}", "has_risk")
            add_edge(scan_node_id, f"finding:{title}", "scan_hits")
        for bridge in project["legal_bridge_ids"]:
            add_edge(project_id, f"legal-bridge:{bridge}", "needs_bridge")

    return {
        "nodes": sorted(nodes, key=lambda item: (str(item["type"]), str(item["id"]))),
        "edges": sorted(edges, key=lambda item: (str(item["source"]), str(item["target"]), str(item["relation"]))),
    }


def write_exports(projects: list[dict[str, object]], bridge_specs: dict[str, dict[str, object]]) -> None:
    cleanup_export_directory(EXPORT_DIR)
    manifest_index = build_manifest_index()
    project_exports = [build_project_export_record(project, manifest_index.get(str(project["source_file"]))) for project in projects]
    finding_exports = build_finding_exports(projects)
    bridge_exports = build_legal_bridge_exports(bridge_specs)
    audit_exports = build_audit_exports(projects)
    graph_export = build_graph_export(projects, finding_exports, bridge_exports)
    write_json(
        EXPORT_DIR / "index.json",
        {
            "generated_at": TODAY,
            "vault": "compliance-wiki",
            "query_priority": [
                "wiki/projects/",
                "wiki/findings/",
                "wiki/legal-bridges/",
                "wiki/audits/",
                "law-wiki/",
                "raw/full-risk-scans/",
                "raw/numbered-text/",
            ],
            "stats": audit_exports["summary"],
            "datasets": {
                "projects": "exports/projects.json",
                "findings": "exports/findings.json",
                "legal_bridges": "exports/legal-bridges.json",
                "audits": "exports/audits.json",
                "graph": "exports/graph.json",
            },
        },
    )
    write_json(EXPORT_DIR / "projects.json", project_exports)
    write_json(EXPORT_DIR / "findings.json", finding_exports)
    write_json(EXPORT_DIR / "legal-bridges.json", bridge_exports)
    write_json(EXPORT_DIR / "audits.json", audit_exports)
    write_json(EXPORT_DIR / "graph.json", graph_export)
    write_export_contracts()


def build_export_schemas() -> dict[str, dict[str, object]]:
    path_type = {"type": "string", "description": "vault 内相对路径，不使用绝对路径。"}
    project_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "compliance-wiki/exports/schema/projects.schema.json",
        "title": "项目发布表",
        "type": "array",
        "items": {
            "type": "object",
            "required": [
                "id",
                "page_name",
                "title",
                "display_title",
                "project_code",
                "procurement_type",
                "item_type",
                "status",
                "project_page",
                "scan_file",
                "numbered_file",
                "risk_titles",
                "legal_bridge_ids",
                "priority",
            ],
            "properties": {
                "id": {"type": "string"},
                "page_name": {"type": "string"},
                "title": {"type": "string"},
                "display_title": {"type": "string"},
                "canonical_title": {"type": "string"},
                "project_code": {"type": "string"},
                "procurement_type": {"type": "string", "enum": ["货物", "服务", "未知"]},
                "item_type": {"type": "string"},
                "region": {"type": "string"},
                "status": {"type": "string", "enum": ["reviewed", "needs-review", "maintained", "draft"]},
                "project_page": path_type,
                "source_file": path_type,
                "scan_file": path_type,
                "numbered_file": path_type,
                "risk_titles": {"type": "array", "items": {"type": "string"}},
                "risk_count": {"type": "integer", "minimum": 0},
                "legal_bridge_ids": {"type": "array", "items": {"type": "string"}},
                "legal_bridge_count": {"type": "integer", "minimum": 0},
                "priority": {"type": "string", "enum": ["P1", "P2", "P3", ""]},
                "review_basis": {"type": "string"},
                "has_comments": {"type": "string", "enum": ["yes", "no"]},
                "comment_count": {"type": "integer", "minimum": 0},
                "evidence_status": {"type": "string"},
                "scan_status": {"type": "string"},
                "top_findings": {"type": "array", "items": {"type": "string"}},
                "current_focus": {"type": "array", "items": {"type": "string"}},
                "query_route": {"type": "array", "items": path_type},
                "evidence": {
                    "type": "object",
                    "required": ["scan_file", "numbered_file"],
                    "properties": {
                        "scan_file": path_type,
                        "numbered_file": path_type,
                    },
                },
            },
        },
    }
    finding_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "compliance-wiki/exports/schema/findings.schema.json",
        "title": "风险规则发布表",
        "type": "array",
        "items": {
            "type": "object",
            "required": [
                "id",
                "title",
                "finding_page",
                "finding_type",
                "risk_level",
                "risk_nature",
                "definition",
                "legal_basis",
                "legal_bridge_ids",
                "project_count",
            ],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "finding_page": path_type,
                "finding_type": {"type": "string"},
                "risk_level": {"type": "string"},
                "risk_nature": {"type": "string"},
                "definition": {"type": "string"},
                "legal_basis": {"type": "array", "items": {"type": "string"}},
                "legal_bridge_ids": {"type": "array", "items": {"type": "string"}},
                "scope": {"type": "array", "items": {"type": "string"}},
                "trigger_patterns": {"type": "array", "items": {"type": "string"}},
                "counter_examples": {"type": "array", "items": {"type": "string"}},
                "review_actions": {"type": "array", "items": {"type": "string"}},
                "project_count": {"type": "integer", "minimum": 0},
                "projects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["page_name", "title", "display_title", "project_page"],
                        "properties": {
                            "page_name": {"type": "string"},
                            "title": {"type": "string"},
                            "display_title": {"type": "string"},
                            "project_page": path_type,
                        },
                    },
                },
            },
        },
    }
    bridge_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "compliance-wiki/exports/schema/legal-bridges.schema.json",
        "title": "法规桥接发布表",
        "type": "array",
        "items": {
            "type": "object",
            "required": [
                "id",
                "title",
                "bridge_page",
                "bridge_type",
                "authority_level",
                "law_target",
                "law_target_page",
                "finding_titles",
            ],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "bridge_page": path_type,
                "bridge_type": {"type": "string"},
                "authority_level": {"type": "string"},
                "law_target": path_type,
                "law_target_page": path_type,
                "positioning": {"type": "string"},
                "review_uses": {"type": "array", "items": {"type": "string"}},
                "focus_points": {"type": "array", "items": {"type": "string"}},
                "finding_titles": {"type": "array", "items": {"type": "string"}},
            },
        },
    }
    audits_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "compliance-wiki/exports/schema/audits.schema.json",
        "title": "治理摘要发布表",
        "type": "object",
        "required": ["summary", "top_findings", "ingest_backlog", "audit_pages"],
        "properties": {
            "summary": {
                "type": "object",
                "required": [
                    "project_count",
                    "source_file_count",
                    "reviewed_project_count",
                    "needs_review_count",
                    "finding_count",
                    "legal_bridge_count",
                ],
                "properties": {
                    "project_count": {"type": "integer", "minimum": 0},
                    "source_file_count": {"type": "integer", "minimum": 0},
                    "reviewed_project_count": {"type": "integer", "minimum": 0},
                    "needs_review_count": {"type": "integer", "minimum": 0},
                    "finding_count": {"type": "integer", "minimum": 0},
                    "legal_bridge_count": {"type": "integer", "minimum": 0},
                },
            },
            "top_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["title", "count"],
                    "properties": {"title": {"type": "string"}, "count": {"type": "integer", "minimum": 0}},
                },
            },
            "ingest_backlog": {"type": "array", "items": {"type": "string"}},
            "audit_pages": {
                "type": "object",
                "additionalProperties": path_type,
            },
        },
    }
    graph_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "compliance-wiki/exports/schema/graph.schema.json",
        "title": "图谱发布表",
        "type": "object",
        "required": ["nodes", "edges"],
        "properties": {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "title", "path"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "title": {"type": "string"},
                        "path": path_type,
                    },
                },
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["source", "target", "relation"],
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "relation": {"type": "string"},
                    },
                },
            },
        },
    }
    index_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "compliance-wiki/exports/schema/index.schema.json",
        "title": "系统发布索引",
        "type": "object",
        "required": ["generated_at", "vault", "query_priority", "stats", "datasets"],
        "properties": {
            "generated_at": {"type": "string"},
            "vault": {"type": "string"},
            "query_priority": {"type": "array", "items": {"type": "string"}},
            "stats": audits_schema["properties"]["summary"],
            "datasets": {
                "type": "object",
                "required": ["projects", "findings", "legal_bridges", "audits", "graph"],
                "properties": {
                    "projects": path_type,
                    "findings": path_type,
                    "legal_bridges": path_type,
                    "audits": path_type,
                    "graph": path_type,
                },
            },
        },
    }
    return {
        "index.schema.json": index_schema,
        "projects.schema.json": project_schema,
        "findings.schema.json": finding_schema,
        "legal-bridges.schema.json": bridge_schema,
        "audits.schema.json": audits_schema,
        "graph.schema.json": graph_schema,
    }


def build_query_contract() -> dict[str, object]:
    return {
        "version": TODAY,
        "primary_entrypoints": [
            "exports/projects.json",
            "exports/findings.json",
            "exports/legal-bridges.json",
            "exports/audits.json",
            "exports/graph.json",
        ],
        "recommended_filters": {
            "projects": {
                "exact_match": ["project_code", "procurement_type", "item_type", "region", "status", "priority", "has_comments"],
                "contains_any": ["risk_titles", "legal_bridge_ids", "top_findings"],
                "range": ["risk_count", "comment_count", "legal_bridge_count"],
            },
            "findings": {
                "exact_match": ["title", "finding_type", "risk_level"],
                "contains_any": ["legal_bridge_ids", "trigger_patterns"],
                "range": ["project_count"],
            },
            "legal_bridges": {
                "exact_match": ["title", "bridge_type", "authority_level"],
                "contains_any": ["finding_titles", "focus_points"],
            },
        },
        "query_presets": [
            {
                "name": "高风险货物项目",
                "dataset": "exports/projects.json",
                "filters": {"procurement_type": "货物", "risk_count_gte": 8},
            },
            {
                "name": "有批注且高优先项目",
                "dataset": "exports/projects.json",
                "filters": {"has_comments": "yes", "priority": "P1"},
            },
            {
                "name": "按法规桥接回查项目",
                "dataset": "exports/projects.json",
                "filters": {"legal_bridge_ids_contains": "采购需求"},
            },
            {
                "name": "命中项目最多的风险规则",
                "dataset": "exports/findings.json",
                "filters": {"project_count_gte": 50},
            },
        ],
        "evidence_resolution": {
            "rule_question": ["exports/findings.json", "exports/legal-bridges.json", "law-wiki/"],
            "project_question": ["exports/projects.json", "raw/full-risk-scans/", "raw/numbered-text/"],
            "graph_question": ["exports/graph.json"],
        },
    }


def render_export_api_doc() -> str:
    return "\n".join(
        [
            "# exports 接口契约",
            "",
            "`exports/` 是给业务 Web 系统和业务智能体消费的标准发布层。",
            "",
            "## 标准数据集",
            "- `index.json`：系统入口与统计总表。",
            "- `projects.json`：项目级检索主表。",
            "- `findings.json`：风险规则主表。",
            "- `legal-bridges.json`：法规桥接主表。",
            "- `audits.json`：治理与覆盖摘要。",
            "- `graph.json`：图谱节点与边关系。",
            "",
            "## 推荐过滤字段",
            "- 项目表：`project_code`、`procurement_type`、`item_type`、`status`、`priority`、`has_comments`、`risk_titles`、`legal_bridge_ids`、`risk_count`。",
            "- 风险规则表：`title`、`finding_type`、`risk_level`、`legal_bridge_ids`、`project_count`。",
            "- 法规桥接表：`title`、`bridge_type`、`authority_level`、`finding_titles`。",
            "",
            "## 过滤约定",
            "- 精确匹配使用字段原名，如 `priority=P1`。",
            "- 多值包含建议使用 `_contains` 或 `_contains_any` 语义，如 `risk_titles_contains=评分项未细化量化`。",
            "- 数值范围建议使用 `_gte` / `_lte` 语义，如 `risk_count_gte=8`。",
            "",
            "## 证据回链约定",
            "- 项目风险详情先取 `projects.json`，再回到 `scan_file` 与 `numbered_file`。",
            "- 一般规则问答先取 `findings.json`，再回到 `legal-bridges.json` 与 `law-wiki/`。",
            "- 图谱展示直接使用 `graph.json` 的 `nodes` 与 `edges`。",
            "",
        ]
    )


def write_export_contracts() -> None:
    schema_dir = export_schema_dir()
    schema_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in build_export_schemas().items():
        write_json(schema_dir / filename, payload)
    write_json(EXPORT_DIR / "query-contract.json", build_query_contract())
    write_text(EXPORT_DIR / "API.md", render_export_api_doc())


def render_index(projects: list[dict[str, object]]) -> str:
    top_projects = sorted(projects, key=lambda item: (-len(item["risk_titles"]), str(item["title"])))[:20]
    lines = [
        "# 政府采购招标文件合规审查工作台",
        "",
        "这是当前 vault 的总入口。当前库负责项目、风险规则、法规桥接、证据导航和治理；`law-wiki/` 作为库内权威法源底座，与项目知识层和证据层共同组成闭环。",
        "",
        "## 快速入口",
        "- [[audits/project-to-finding-coverage|项目到风险覆盖]]",
        "- [[audits/finding-to-law-coverage|风险到法规覆盖]]",
        "- [[audits/full-risk-scan-index|逐项目扫描索引]]",
        "- [[audits/source-coverage|源文件覆盖]]",
        "- [[audits/fallback-evidence-hotspots|回填证据热点]]",
        "- [[audits/project-title-anomalies|标题异常项目]]",
        "- [[audits/finding-refinement-backlog|finding 细化待办]]",
        "- [[audits/finding-quality-overview|finding 质量总览]]",
        "- [[audits/health-certificate-watchlist|健康证明专项审计]]",
        "",
        "## Legal Bridges",
    ]
    for title in LEGAL_BRIDGES:
        lines.append(f"- [[legal-bridges/{title}|{title}]]")

    lines.extend(["", "## Rules"])
    for filename in RULE_PAGES:
        title = filename.replace(".md", "")
        lines.append(f"- [[rules/{title}|{title}]]")

    lines.extend(["", "## Findings"])
    for title in sorted(FINDING_SPECS):
        lines.append(f"- [[findings/{title}|{title}]]")

    lines.extend(["", "## Representative Projects"])
    for project in top_projects:
        lines.append(f"- [[projects/{project['page_name']}|{project['display_title']}]]")

    lines.extend(
        [
            "",
            "## Existing Knowledge Pages",
            "- [[playbooks/审查清单|审查清单]]",
            "- [[faq/高频问答|高频问答]]",
            "- [[patterns/评分标准不可执行|评分标准不可执行]]",
            "- [[patterns/供应商能力要求与采购标的相关性不足|供应商能力要求与采购标的相关性不足]]",
            "- [[patterns/非实质性条件或准入性条件错位进入评分|非实质性条件或准入性条件错位进入评分]]",
            "- [[patterns/证明材料要求导致评审不可操作|证明材料要求导致评审不可操作]]",
            "- [[patterns/模板条款误用或草稿残留|模板条款误用或草稿残留]]",
            "",
            "## Log",
            "- [[log|变更日志]]",
        ]
    )
    return "\n".join(lines)


def update_log() -> None:
    current = read_text(LOG_PATH) if LOG_PATH.exists() else "# 变更日志\n"
    line = "- 2026-04-20：完成深度集成方案 Plus 一次性重构，重建 `wiki/projects/`、`wiki/findings/`、`wiki/legal-bridges/`、核心 `wiki/rules/` 与治理 `wiki/audits/`，建立 `项目 -> 风险规则 -> 法规桥接 -> law-wiki -> raw 证据` 主链。"
    if line not in current:
        current = current.rstrip() + "\n" + line + "\n"
    export_line = "- 2026-04-21：新增 `exports/` 系统发布层，输出项目、风险规则、法规桥接、治理摘要与图谱 JSON，供业务 Web 系统与业务智能体直接消费。"
    if export_line not in current:
        current = current.rstrip() + "\n" + export_line + "\n"
    quality_line = "- 2026-04-21：启动质量回炉，新增回填证据热点、标题异常项目、finding 细化待办三类治理页，用于识别泛扫、标题污染与规则颗粒度不足问题。"
    if quality_line not in current:
        current = current.rstrip() + "\n" + quality_line + "\n"
    governance_line = "- 2026-04-21：新增 `finding-quality-overview` 与 `health-certificate-watchlist`，把规则可用性分层和健康证明条款边界纳入持续治理。"
    if governance_line not in current:
        current = current.rstrip() + "\n" + governance_line + "\n"
    write_text(LOG_PATH, current)


def main() -> None:
    old_records = build_old_project_records()
    bridge_specs = build_bridge_specs()
    projects = build_canonical_projects()
    write_legal_bridges(bridge_specs)
    write_rules()
    write_findings(projects)
    write_projects(projects)
    write_audits(projects, old_records)
    write_exports(projects, bridge_specs)
    write_text(INDEX_PATH, render_index(projects))
    update_log()


if __name__ == "__main__":
    main()
