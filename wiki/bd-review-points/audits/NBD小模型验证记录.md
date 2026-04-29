---
id: nbd-small-model-validation-log
title: NBD 小模型验证记录
page_type: nbd-validation-log
status: draft
last_reviewed: 2026-04-28
---

上级导航：[[../index|新版 BD 审查点明细库]]

## 目标
记录 NBD 样例和批量审查点的小模型验证结果，用于迭代定位关键词、候选召回规则、命中条件和排除条件。

## 验证维度
- 候选召回是否命中关键条款。
- 是否存在大量无关候选。
- 是否误报。
- 是否漏报。
- 是否能输出正确风险提示和修改建议。
- 是否能引用正确依据。

## 记录
### 2026-04-28 首批样例草稿
- 已生成 12 个首批样例草稿，见 [[../items/index|NBD 审查点条目索引]]。
- 状态均为 `draft`，尚未进行小模型验证。
- 下一步验证重点：候选召回是否准确、排除条件是否足够、风险提示和修改建议是否可直接输出。

### 2026-04-28 召回预检
- 预检输出：`validation/nbd-preflight-recall-20260428/recall_matrix.md`
- 检查点数量：12。
- 样本文档数量：8。
- 组合数：96。
- 本次只验证候选召回，不调用小模型。
- 初步结论：
  - `NBD01-001` 8 个样本文档均无候选，需要补充所有制相关对象词和召回组合。
  - `NBD04-001` 仅 1 个样本文档有候选，需要补充联合体公告相关召回策略。
  - `NBD06-003`、`NBD06-006`、`NBD07-002` 候选偏多，需要收窄关键词和排除合同模板、通用条款、无关证明材料。
  - 其余样例具备进入小模型判断验证的基础，但仍需人工抽查候选窗口质量。

### 2026-04-28 关键词修正后召回预检
- 预检输出：`validation/nbd-preflight-after-keyword-fix-20260428/recall_matrix.md`
- 检查点数量：12。
- 样本文档数量：23。
- 组合数：276。
- 本次只验证候选召回，不调用小模型。
- 初步结论：
  - `NBD01-001` 已从无候选修正为 23/23 个样本文档均有候选，但平均候选数 6.2，仍需抽查是否误报。
  - `NBD04-001` 已从召回不足修正为 23/23 个样本文档均有候选，平均候选数 3.5。
  - `NBD06-003` 平均候选数 6.8、`NBD06-006` 平均候选数 6.1，仍偏宽。
  - `NBD07-002` 平均候选数从偏高降至 5.3，可进入小模型 smoke，但需关注检测报告普通要求误报。

### 2026-04-28 小模型 smoke 验证
- 验证输出：`validation/nbd-runs/smoke-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 检查点数量：12。
- 样本文档数量：3。
- 调用组合数：36。
- 调用失败数：0。
- 总体结果：
  - 不命中：22。
  - 待人工复核：12。
  - 命中：2。
- 明确命中样例：
  - `NBD01-001` 在医疗设备样本中命中“投标单位须为外商投资及民营企业，国资企业不具备投标资格”。
  - `NBD02-007` 在医疗设备样本中命中“注册资本、年收入、净利润”准入门槛。
- 正向信号：
  - `NBD04-001` 能识别“本项目不接受联合体投标”并判定不命中。
  - `NBD06-003` 能识别“不收取投标保证金”并判定不命中。
  - `NBD07-002` 未将普通第三方 CMA/CNAS 检测报告要求误判为指定检测机构。
- 暴露问题：
  - `NBD02-015`、`NBD03-001`、`NBD05-003`、`NBD07-021` 多数进入待人工复核，核心原因是候选窗口缺少完整采购需求、预算金额、品目属性、货物清单或技术参数。
  - `NBD04-001` 属于配置缺失型检查，仅依赖关键词窗口不够，需要补充招标公告段落召回或缺失型检查逻辑。
- 处理结论：
  - 12 个样例 NBD 已通过首轮小模型可执行性 smoke，但仍保持 `draft/testing` 观察口径，不直接进入维护态。
  - 下一步优先增强 `validate_nbd_cli.py` 的项目元信息和支持上下文能力，再扩大样本跑数。

### 2026-04-28 支持上下文增强后 smoke 验证
- 验证输出：`validation/nbd-runs/smoke-support-context-qwen35-27b-20260428/smoke-summary.md`
- 预检输出：`validation/nbd-preflight-support-context-20260428/recall_matrix.md`
- 模型：`qwen3.5-27b`
- 检查点数量：12。
- 样本文档数量：3。
- 调用组合数：36。
- 调用失败数：0。
- 技术变化：`validate_nbd_cli.py` 增加 NBD 专用支持上下文，覆盖联合体公告、预算金额、中小企业政策、采购需求、售后服务、证书、分包、医疗设备和货物清单等段落。
- 预检结果：
  - `NBD04-001` 联合体公告上下文 23/23 可补充。
  - `NBD05-003` 项目预算上下文 23/23 可补充，中小企业政策上下文 23/23 可补充。
- 与首轮 smoke 对比：
  - 不命中从 22 增至 25。
  - 待人工复核从 12 降至 9。
  - 命中保持 2，两个高价值真阳性未丢失。
- 改善点：
  - `NBD05-003` 在物业服务样本中从待人工复核降为不命中，原因是模型读到了预算金额和“专门面向中小企业采购”设置。
  - `NBD06-006` 在物业服务样本中从待人工复核降为不命中，原因是模型读到了分包限制的完整上下文。
  - `NBD02-015` 在医疗设备样本中从待人工复核降为不命中，原因是模型读到了采购需求中已有售后服务标准。
- 仍需专项设计：
  - `NBD04-001` 这类配置缺失型检查需要结构化定位招标公告正式段落，而不是仅靠联合体关键词。
  - `NBD03-001` 证书合理性需要品目、需求、证书性质和分值四要素判断。
  - `NBD05-003` 仍需结构化抽取预算金额、采购品目、是否专门面向中小企业。
  - `NBD07-021` 需要货物清单和射线/医疗设备识别能力。

### 2026-04-28 v1 标杆版重生成与召回预检
- 生成脚本：`scripts/regenerate_nbd_benchmark_samples.py`
- 预检输出：`validation/nbd-preflight-v1-benchmark-20260428/recall_matrix.md`
- 重生成范围：首批 12 个 NBD 样例。
- 结构变化：
  - 旧章节 `定位关键词` 已全部替换为 `定位与召回剖面`。
  - 每个 NBD 均补齐 10 个召回剖面子结构：章节角色词、对象词簇、行为词簇、后果词簇、数值/模式规则、支持上下文词、降权/排除词、高价值组合、中价值组合、低价值组合。
  - 状态调整为 `testing`，版本标记为 `v1-benchmark`。
- 预检结果：
  - 检查点数量：12。
  - 样本文档数量：23。
  - 组合数：276。
  - 调用模型：否。
  - 召回错误：0。
  - 无候选组合：0。
- 按 NBD 平均候选数：
  - `NBD01-001`：6.8，偏宽。
  - `NBD01-003`：7.1，偏宽。
  - `NBD02-001`：4.6。
  - `NBD02-007`：4.6。
  - `NBD02-015`：5.4。
  - `NBD03-001`：4.2。
  - `NBD04-001`：4.9。
  - `NBD05-003`：3.2。
  - `NBD06-003`：5.4。
  - `NBD06-006`：6.2，偏宽。
  - `NBD07-002`：5.2。
  - `NBD07-021`：5.8。
- 初步结论：
  - v1 标杆结构已能被 CLI 正常读取和召回。
  - `NBD05-003` 预算/中小企业类定位明显更收敛。
  - `NBD01-001`、`NBD01-003`、`NBD06-006` 需要继续调降弱词和噪声词权重，防止候选窗口偏宽。
  - 下一步应跑 3 个样本文档的小模型 smoke，并与上一轮 `smoke-support-context-qwen35-27b-20260428` 对比。

### 2026-04-28 v1 标杆版小模型 smoke
- 验证输出：`validation/nbd-runs/smoke-v1-benchmark-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 检查点数量：12。
- 样本文档数量：3。
- 调用组合数：36。
- 调用失败数：0。
- 总体结果：
  - 不命中：24。
  - 待人工复核：8。
  - 命中：4。
- 与上一轮支持上下文 smoke 对比：
  - 待人工复核从 9 降至 8。
  - 命中从 2 增至 4。
  - `NBD03-001` 三个样本均从待复核转为命中，需要人工抽查是否过度激进。
  - `NBD06-006` 三个样本均为待复核，较上一轮退步，需要优化分包排除条件。
- 关键回归与修复：
  - 初跑中 `NBD02-007` 未命中医疗设备样本中的“注册资本、年收入、净利润”门槛。
  - 原因是 CLI 候选评分层未充分适配新版 `定位与召回剖面`，对“对象词簇 + 行为词簇/门槛模式”组合加权不足。
  - 已修复 `scripts/validate_checkpoint_cli.py` 的评分逻辑，并补充 `NBD02-007` 的 `年收入` 和资格角色词。
  - 单项回归输出：`validation/nbd-runs/smoke-v1-benchmark-fix2-qwen35-27b-20260428/case03--NBD02-007-regression/nbd-batch-report.md`
  - 单项回归结果：`NBD02-007` 已恢复命中。
- 处理结论：
  - v1 标杆结构可运行，但本轮不直接升级为 `maintained`。
  - 下一步应使用修复后的召回评分重跑完整 3 文件 smoke，并人工抽查 `NBD03-001` 与 `NBD06-006`。

### 2026-04-28 v1 标杆修复后完整 smoke
- 验证输出：`validation/nbd-runs/smoke-v1-benchmark-fix2-full-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 检查点数量：12。
- 样本文档数量：3。
- 调用组合数：36。
- 调用失败数：0。
- 使用修复后的召回评分逻辑，增强“对象词簇 + 行为词簇/门槛模式”的候选加权。
- 总体结果：
  - 不命中：24。
  - 待人工复核：9。
  - 命中：3。
- 关键正向结果：
  - `NBD01-001` 在医疗设备样本中命中所有制限制。
  - `NBD02-007` 在医疗设备样本中命中注册资本、年收入、净利润门槛。
  - `NBD03-001` 从初跑的 3 个全命中回到 1 命中、1 待复核、1 不命中，更符合证书合理性检查的复杂度。
- 仍需打磨：
  - `NBD06-006` 三个样本均为待人工复核，是当前最需要细化的标杆。
  - `NBD04-001` 仍需要正式公告段落定位增强。
  - `NBD05-003` 仍需要预算金额和中小企业政策结构化抽取。
- 处理结论：
  - v1 标杆修复后可作为下一轮打磨基线，但仍不升级为 `maintained`。
  - 下一步优先处理 `NBD06-006` 分包边界，再增强 CLI 元信息抽取。

### 2026-04-28 NBD06-006 分包边界专项修复
- 修复对象：`NBD06-006 采购人允许采用分包方式履行合同的，未在采购文件中明确分包的具体内容、金额（比例）`
- 生成脚本：`scripts/regenerate_nbd_benchmark_samples.py`
- CLI 调整：`scripts/validate_nbd_cli.py`
- 预检输出：`validation/nbd-preflight-v1-nbd06-006-refine-20260428/recall_matrix.md`
- 定向 smoke 输出：`validation/nbd-runs/smoke-v1-nbd06-006-refine2-qwen35-27b-20260428/`
- 模型：`qwen3.5-27b`
- 调用组合数：3。
- 调用失败数：0。
- 修复内容：
  - 将 NBD06-006 的审查目标收窄为“项目实质性条款明确允许分包”。
  - 明确排除合同协议书模板、通用合同条款、分包意向协议格式、声明函格式、中小企业声明函填写说明和“分包金额（如有）”填空项。
  - 在新 CLI 的执行要求中补充：候选位于模板/格式类文本且 NBD 排除条件已明确覆盖时，应输出不命中；只有无法判断其正式效力时才输出待人工复核。
- 定向结果：
  - 家具样本：不命中。
  - 物业服务样本：不命中。
  - 医疗设备样本：不命中。
- 结论：
  - NBD06-006 的模板噪声误报控制通过本轮专项验证。
  - 当前仍为 `testing`，后续需要加入至少 1 个真实“明确允许分包但未明确内容/金额/比例”的正样本，否则只能证明排除能力，不能证明正向召回能力。

### 2026-04-28 v1 标杆 fix3 完整 smoke
- 验证输出：`validation/nbd-runs/smoke-v1-benchmark-fix3-full-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 检查点数量：12。
- 样本文档数量：3。
- 调用组合数：36。
- 调用失败数：0。
- 总体结果：
  - 不命中：29。
  - 待人工复核：3。
  - 命中：4。
- 关键结果：
  - `NBD06-006` 三个样本均为不命中，分包模板噪声已压住。
  - `NBD02-007` 医疗设备样本仍命中注册资本、年收入、净利润等规模/财务评分因素，正向风险召回未丢失。
  - `NBD03-001` 三个样本均命中，需继续人工抽查证书合理性是否偏激进。
  - `NBD04-001` 仍有 1 个待复核，原因是正式招标公告段落定位不足。
  - `NBD05-003` 仍有 2 个待复核，原因是预算金额、采购品目、是否专门面向中小企业仍未结构化抽取。
- 处理结论：
  - 首批 12 个 NBD 可以作为 `v1-benchmark` 打磨基线继续验证。
  - 当前不建议升级为 `maintained`。
  - 下一步优先处理 `NBD03-001` 证书合理性、`NBD04-001` 配置缺失型公告定位、`NBD05-003` 中小企业政策结构化抽取。

### 2026-04-28 NBD03-001 证书合理性专项修复
- 修复对象：`NBD03-001 证书设置的合理性`
- 生成脚本：`scripts/regenerate_nbd_benchmark_samples.py`
- 方法论更新：`wiki/bd-review-points/NBD-方法论.md`
- 手册更新：`wiki/bd-review-points/NBD标杆生成手册.md`
- 预检输出：`validation/nbd-preflight-v1-nbd03-001-refine-20260428/recall_matrix.md`
- 定向 smoke 输出：`validation/nbd-runs/smoke-v1-nbd03-001-refine-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 预检结果：
  - 样本文档数量：23。
  - 组合数：23。
  - 召回错误：0。
  - 无候选组合：0。
  - 平均候选数：6.4，仍偏宽，符合合理性判断型需要多上下文比较的特点。
- smoke 结果：
  - 办公家具采购：待人工复核。
  - 物业管理服务：待人工复核。
  - 血透类设备采购：命中。
- 修复内容：
  - 新增“专项判断方法”，要求逐个证书判断，不得把同一评分项中的所有证书合并为同一结论。
  - 建立“证书性质 -> 需求锚点 -> 关联强度 -> 后果强度 -> 结论分流”的判断链。
  - 明确表面业务关联但必要性、协会证书依赖或分值合理性不明时输出待人工复核。
  - 明确明显无关且作为资格条件，或通用荣誉、企业身份、管理体系认证作为资格条件时可以命中。
- 处理结论：
  - `NBD03-001` 已从“见证书偏命中”调整为“逐证书关联度分档”。
  - 当前可作为合理性判断型标杆继续验证。
  - 后续需要补充真实不命中反例样本，验证依法必要证照、特种作业人员证书、医疗器械经营许可等边界。

### 2026-04-28 NBD03-001 maintained 验收
- 验收对象：`NBD03-001 证书设置的合理性`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD03-001/`
- 真阴性验证输出：`validation/nbd-runs/smoke-v1-nbd03-001-maintained-fixtures-qwen35-27b-20260428/smoke-summary.md`
- 最终真阴性回归：`validation/nbd-runs/smoke-v1-nbd03-001-maintained-final-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 真阴性 fixture：
  - 医疗器械依法准入证照：预期不命中，实际不命中。
  - 特种作业岗位证书：预期不命中，实际不命中。
  - 食品经营许可证：预期不命中，实际不命中。
- 真实混合样本抽查：
  - 血透类设备采购：命中，能识别高空清洗悬吊作业、高新技术企业、诚信管理体系认证等无关资格证书。
  - 营养品采购：命中，能识别棉花加工资格认定、有害生物防制、信息安全管理体系等可疑证书。
  - 田径场维修改造工程：命中，能识别 CMMI、食品安全管理体系等与工程标的不匹配证书。
  - 办公家具、物业管理、食堂托管、中药配方颗粒、司法鉴定荣誉奖项等场景输出待人工复核，符合“表面相关但必要性/分值/证书属性需确认”的边界。
- 验收结论：
  - `NBD03-001` 已具备命中、待人工复核、不命中三类稳定分流能力。
  - 最终版页面补充真实反例和边界例后，3 个真阴性 fixture 回归仍全部不命中。
  - `NBD03-001` 可以作为“合理性判断型 NBD”的生产级标杆。

### 2026-04-28 NBD02-007 maintained 验收
- 验收对象：`NBD02-007 不得将供应商的注册资本、资产总额、营业收入、从业人员、利润和纳税额等规模条件和财务指标设定为评审因素`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD02-007/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd02-007-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 财务规模评分 fixture：预期命中，实际命中。
  - 依法纳税和财务声明 fixture：预期不命中，实际不命中。
  - 仅财务报表 fixture：预期不命中，实际不命中。
  - 血透类设备采购真实样本：预期命中，实际命中。
- 验收结论：
  - `NBD02-007` 已能区分规模/财务指标评分或准入，与依法纳税、财务声明、报价构成、普通财务报表材料。
  - `NBD02-007` 可以作为“评分因素型 + 财务规模禁止类 NBD”的生产级标杆。

### 2026-04-28 NBD06-006 maintained 验收
- 验收对象：`NBD06-006 采购人允许采用分包方式履行合同的，未在采购文件中明确分包的具体内容、金额（比例）`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD06-006/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd06-006-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 允许分包但未明确内容/金额/比例：预期命中，实际命中。
  - 允许分包且明确内容和比例：预期不命中，实际不命中。
  - 仅模板或格式出现分包：预期不命中，实际不命中。
  - 原则禁止但专项资质例外：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD06-006` 已能区分实质性允许分包、已明确边界、模板噪声和专项例外边界。
  - `NBD06-006` 可以作为“履约配置型 + 分包边界类 NBD”的生产级标杆。

### 2026-04-28 NBD06-003 maintained 验收
- 验收对象：`NBD06-003 不得收取超过规定比例的投标保证金`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD06-003/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd06-003-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 投标保证金超过 2%：预期命中，实际命中。
  - 投标保证金未超过 2%：预期不命中，实际不命中。
  - 不收取投标保证金：预期不命中，实际不命中。
  - 仅履约保证金：预期不命中，实际不命中。
  - 缺少预算或最高限价无法计算：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD06-003` 已具备金额抽取、比例计算、非投标保证金排除和缺失信息待复核分流能力。
  - `NBD06-003` 可以作为“数值比例型 NBD”的生产级标杆。

### 2026-04-28 NBD01 资格限制类 maintained 验收
- 验收对象：`NBD01-001 不得限定供应商所有制形式`、`NBD01-003 不得限定供应商注册地或所在地或要求供应商在某行政区域内设立分支机构。`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD01-001/`、`validation/nbd-fixtures/NBD01-003/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd01-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 所有制资格限制：预期命中，实际命中。
  - 仅填写企业性质：预期不命中，实际不命中。
  - 采购人/主管部门背景：预期不命中，实际不命中。
  - 本地分支机构资格限制：预期命中，实际命中。
  - 本地服务网点评分：预期命中，实际命中。
  - 项目履约地点、合同管辖：预期不命中，实际不命中。
  - 中标后服务响应机制：预期不命中，实际不命中。
- 验收结论：
  - `NBD01-001` 和 `NBD01-003` 已能区分资格限制、评分限制和中性背景/履约信息。
  - 两项可以作为“明确禁止型 + 资格公平性 NBD”的生产级标杆。

### 2026-04-28 NBD04-001 maintained 验收
- 验收对象：`NBD04-001 招标公告需载明是否接受联合体`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD04-001/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd04-001-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 正式公告未载明联合体：预期命中，实际命中。
  - 公告明确不接受联合体：预期不命中，实际不命中。
  - 公告明确接受联合体：预期不命中，实际不命中。
  - 仅联合体协议书格式/投标文件格式：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD04-001` 已具备配置缺失型的正式公告段落定位、明确结论排除和模板噪声分流能力。
  - `NBD04-001` 可以作为“配置缺失型 NBD”的生产级标杆。

### 2026-04-28 NBD05-003 maintained 验收
- 验收对象：`NBD05-003 货物-服务项目须正确设定专门面向中小企业采购`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD05-003/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd05-003-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 服务项目 105 万且不专门面向中小企业：预期命中，实际命中。
  - 服务项目 105 万且已专门面向中小企业：预期不命中，实际不命中。
  - 工程项目：预期不命中，实际不命中。
  - 缺少预算或政策设置：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD05-003` 已具备预算、品目和中小企业政策设置三要素组合判断能力。
  - `NBD05-003` 可以作为“政策判断型 NBD”的生产级标杆。

### 2026-04-28 NBD07 品目专项 maintained 验收
- 验收对象：`NBD07-002 不得要求供应商提供特定检测机构（国家行政机关另有规定的除外）出具的检测报告`、`NBD07-021 正确设置供应商医疗资质`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD07-002/`、`validation/nbd-fixtures/NBD07-021/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd07-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 家具检测报告限定国家级检测机构：预期命中，实际命中。
  - CMA 第三方检测报告：预期不命中，实际不命中。
  - 疑似主管部门规定特定检测：预期待人工复核，实际待人工复核。
  - 医疗设备未设置准入资质：预期命中，实际命中。
  - 医疗设备已设置准入资质：预期不命中，实际不命中。
  - 非医疗家具项目：预期不命中，实际不命中。
  - 验收阶段办理辐射许可：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD07-002` 和 `NBD07-021` 已具备品目事实识别、专项条件命中、合法设置排除和边界待复核能力。
  - 两项可以作为“品目专项型 NBD”的生产级标杆。

### 2026-04-28 NBD02-001 maintained 验收
- 验收对象：`NBD02-001 将特定行政区域的业绩作为评审因素`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD02-001/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd02-001-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 深圳市业绩作为得分条件：预期命中，实际命中。
  - 仅要求同类项目业绩：预期不命中，实际不命中。
  - 行政区域仅出现在合同地址示例：预期不命中，实际不命中。
  - 声称本地经验具有特殊必要性：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD02-001` 已能区分行政区域业绩评分、普通业绩评分、地址噪声和必要性边界。
  - `NBD02-001` 可以作为“评分因素型 + 行政区域业绩类 NBD”的生产级标杆。

### 2026-04-28 NBD02-015 maintained 验收
- 验收对象：`NBD02-015 不得将售后服务作为评审因素，但未在采购需求中体现相关内容`
- NBD 状态：`maintained`
- NBD 版本：`v1-maintained`
- fixture 目录：`validation/nbd-fixtures/NBD02-015/`
- 验证输出：`validation/nbd-runs/smoke-v1-nbd02-015-maintained-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验证结果：
  - 评分有售后但需求无要求：预期命中，实际命中。
  - 采购需求已有售后要求：预期不命中，实际不命中。
  - 仅投标文件格式或承诺函模板出现售后：预期不命中，实际不命中。
  - 需求笼统但评分细化：预期待人工复核，实际待人工复核。
- 验收结论：
  - `NBD02-015` 已能区分售后评分新增需求、采购需求已有售后要求、投标格式噪声和笼统需求边界。
  - `NBD02-015` 可以作为“关联比较型 NBD”的生产级标杆。

### 2026-04-28 NBD36 全量 maintained 验收
- 验收对象：当前 36 个 NBD。
- 目标状态：`maintained: 36`。
- 验收记录：`wiki/bd-review-points/audits/NBD36全量maintained验收记录-20260428.md`
- 真实样本 smoke：`validation/nbd-runs/nbd24-real-sample-smoke-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验收结果：
  - 24 个非 maintained NBD 已补齐 fixture 或复用既有 fixture。
  - 16 个 draft NBD 的 48 个 fixture smoke 全部通过。
  - 24 个非 maintained NBD 的 72 个真实样本 smoke 全部完成，调用失败 0，fallback 0。
  - 全库 NBD 状态统计达到 `maintained / v1-maintained = 36`。
- 维护观察：
  - `NBD01-002`、`NBD01-006`、`NBD02-004`、`NBD02-009`、`NBD02-011` 在真实长文档中候选窗口偏高，后续应继续压缩模板噪声。
  - `NBD02-002`、`NBD06-010`、`NBD06-014` 待复核比例偏高，后续应补更多真实正反样本。

### 2026-04-28 Batch 2 覆盖批验收
- 验收对象：Batch 2 的 24 个 NBD。
- 验收记录：[[NBD-Batch2验收记录-20260428|NBD Batch 2 验收记录 20260428]]
- fixture smoke：`validation/nbd-runs/batch2-fixture-smoke-qwen35-27b-20260428/smoke-summary.md`
- 真实样本 smoke：`validation/nbd-runs/batch2-real-smoke-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验收结果：
  - fixture 调用 72 次，失败 0，期望不一致 0。
  - 真实样本调用 72 次，失败 0，fallback 0。
  - 真实样本最大候选窗口数 11，平均候选窗口数 6.14。
  - 21 个 NBD 升级为 `maintained / v1-maintained`。
  - 3 个 NBD 保留为 `testing / v1-testing`，并登记到 [[NBD争议池|NBD 争议池]]。
- 当前状态：
  - `maintained`: 57。
  - `testing`: 3。
  - 已覆盖 NBD：60。
- testing 分流：
  - `NBD01-023`：最高限价与采购预算属于跨字段金额比较，需补事实合并策略。
  - `NBD01-032`：敏感风险词为兜底型检查点，需继续压低模板和通用语境噪声。
  - `NBD02-014`：隐形资质证照依赖证照库和业务口径，需后续专项稳定。

### 2026-04-28 Batch 3 覆盖批验收
- 验收对象：Batch 3 的 30 个 NBD。
- 验收记录：[[NBD-Batch3验收记录-20260428|NBD Batch 3 验收记录 20260428]]
- fixture smoke：`validation/nbd-runs/batch3-fixture-smoke-qwen35-27b-20260428/smoke-summary.md`
- 真实样本 smoke：`validation/nbd-runs/batch3-real-smoke-qwen35-27b-20260428/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验收结果：
  - fixture 调用 90 次，失败 0，期望不一致 0。
  - 真实样本调用 90 次，失败 0，fallback 0。
  - 真实样本最大候选窗口数 10，平均候选窗口数 4.61。
  - 22 个 NBD 升级为 `maintained / v1-maintained`。
  - 8 个 NBD 保留为 `testing / v1-testing`，并登记到 [[NBD争议池|NBD 争议池]]。
- 当前状态：
  - `maintained`: 79。
  - `testing`: 11。
  - 已覆盖 NBD：90。
- testing 分流：
  - `NBD02-027`：评定分离适用性依赖重大项目、特定品目等项目事实。
  - `NBD02-028`：电子证照纸质证照与原件备查边界需压误报。
  - `NBD02-029`、`NBD02-030`：评分权重和评分细项依赖完整评分表结构化抽取。
  - `NBD02-039`：证书名称和认证机构限定边界需专项确认。
  - `NBD02-042`：量化打分口径过宽，真实样本触发过多。
  - `NBD06-018`：与分包配置既有 NBD 存在边界重叠。
  - `NBD06-019`：样品制作标准需用户需求书支持上下文。

### 2026-04-29 Batch 4-5 覆盖批验收
- 验收对象：Batch 4 的 30 个 NBD、Batch 5 的 33 个 NBD。
- 验收记录：[[NBD-Batch4-Batch5验收记录-20260429|NBD Batch 4-5 验收记录 20260429]]
- fixture smoke：
  - `validation/nbd-runs/batch4-fixture-smoke-qwen35-27b-20260429/smoke-summary.md`
  - `validation/nbd-runs/batch5-fixture-smoke-qwen35-27b-20260429/smoke-summary.md`
- 真实样本 smoke：
  - `validation/nbd-runs/batch4-real-smoke-qwen35-27b-20260429/smoke-summary.md`
  - `validation/nbd-runs/batch5-real-smoke-qwen35-27b-20260429/smoke-summary.md`
- 验收结果：
  - Batch 4：fixture 90 次、真实样本 90 次，调用失败 0，fallback 0。
  - Batch 5：fixture 99 次，其中 `NBD07-032` 两个 fixture 因模型 JSON 截断失败；真实样本 99 次，调用失败 0，fallback 0。
  - Batch 4 升级 `maintained` 14 个，保留 `testing` 16 个。
  - Batch 5 升级 `maintained` 14 个，保留 `testing` 19 个。
- 当前状态：
  - `maintained`: 107。
  - `testing`: 46。
  - `draft`: 0。
  - 已覆盖 NBD：153。

### 2026-04-29 testing P0 专项验收
- 验收对象：P0 技术稳定性组。
- 验收记录：[[NBD-testing-P0验收记录-20260429|NBD testing P0 验收记录 20260429]]
- fixture smoke：`validation/nbd-runs/p0-recall-fixture-qwen35-27b-20260429/smoke-summary.md`
- 真实样本 smoke：`validation/nbd-runs/p0-real-smoke-qwen35-27b-20260429/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验收结果：
  - NBD07-009、NBD07-010、NBD07-014、NBD07-024 已补充高价值召回词和具体 fixture。
  - 四项有效 fixture 三类分流通过，真实样本调用失败 0，fallback 0。
  - NBD07-014 在家具、医疗真实样本中形成真实命中，在物业样本中不命中。
  - NBD07-032 真实样本稳定，但 fixture 曾依赖 partial JSON recovery，继续保留 testing。
- 当前状态：
  - `maintained`: 111。
  - `testing`: 42。
  - `draft`: 0。
  - 已覆盖 NBD：153。

### 2026-04-29 testing P1 第一轮验收
- 验收对象：P1 召回与支持上下文组第一轮。
- 验收记录：[[NBD-testing-P1第一轮验收记录-20260429|NBD testing P1 第一轮验收记录 20260429]]
- fixture smoke：`validation/nbd-runs/p1-recall-fixture-qwen35-27b-20260429/smoke-summary.md`
- 真实样本 smoke：`validation/nbd-runs/p1-real-smoke-qwen35-27b-20260429/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验收结果：
  - 补充 12 个 NBD 的高价值召回词和具体 fixture。
  - fixture 有效调用 36 次，失败 0；真实样本调用 45 次，失败 0，fallback 0。
  - NBD03-004、NBD07-003、NBD07-015、NBD07-019、NBD07-026 升级 maintained。
  - NBD01-017、NBD01-029、NBD06-019 等全文缺失型仍需事实卡或支持上下文增强。
- 当前状态：
  - `maintained`: 116。
  - `testing`: 37。
  - `draft`: 0。
  - 已覆盖 NBD：153。

### 2026-04-29 testing37 最终验收
- 验收对象：上一轮剩余 37 个 testing NBD。
- 验收记录：[[NBD-testing37最终验收记录-20260429|NBD testing37 最终验收记录 20260429]]
- fixture smoke：`validation/nbd-runs/testing37-fixture-smoke-qwen35-27b-20260429/smoke-summary.md`
- fixture 修复轮：`validation/nbd-runs/testing37-fixture-fix-qwen35-27b-20260429/`
- 真实样本 smoke：`validation/nbd-runs/testing37-real-smoke-qwen35-27b-20260429/smoke-summary.md`
- 模型：`qwen3.5-27b`
- 验收结果：
  - fixture 首轮调用 120 次，失败 0，fallback 0；4 个不一致项经修复轮 9 次复跑后全部对齐。
  - 真实样本调用 111 次，失败 0，fallback 0，最大候选窗口数 9，平均候选窗口数 4.94。
  - 剩余 37 个 NBD 全部升级 `maintained / v1-maintained`。
- 当前状态：
  - `maintained`: 153。
  - `testing`: 0。
  - `draft`: 0。
  - 已覆盖 NBD：153。
