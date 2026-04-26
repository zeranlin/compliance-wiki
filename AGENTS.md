# AGENTS

## 1. 适用范围
- 本 vault 用于政府采购招标文件合规审查。
- `wiki/` 是知识层。
- `raw/` 是证据层。
- `law-wiki/` 是本库内置的法规基础库，通过 `wiki/legal-bridges/` 接入。
- `validation/` 是验证与模拟运行层，承载 CLI 盲测、小模型对账、业务系统调用模拟产物。
- 外部业务系统当前直接消费的是 `wiki/findings/` 中的 `审查逻辑 / SOP`。
- `wiki/projects/`、`raw/full-risk-scans/`、`raw/numbered-text/` 主要属于本库内部生产、治理与验证层。
- 本库默认工作模式为“LLM 主审查型 ingest”，不是“脚本规则识别型编译”。

## 2. 标准主链
- 标准检索链：`wiki/projects/ -> wiki/findings/ -> wiki/legal-bridges/ -> law-wiki/ -> raw/full-risk-scans/ -> raw/numbered-text/`
- `projects` 负责项目入口与导航。
- `findings` 负责标准风险规则。
- `legal-bridges` 负责法规锚定。
- `audits` 负责治理、覆盖率和全库质量校验。
- `validation` 负责小模型 SOP 验证、批量跑数、接口调试和业务系统模拟，不进入知识主链。
- `full-risk-scans` 负责单文件主审查结果页，是项目风险识别的第一落点。
- `numbered-text` 负责行号证据。
- 外部系统当前不依赖独立发布层，直接沿 `projects -> findings -> legal-bridges -> law-wiki -> raw` 主链取数与回证。

## 3. 目录职责
- `wiki/index.md`：总入口。
- `wiki/projects/`：项目级入口页。
- `wiki/findings/`：标准风险规则页。
- `wiki/legal-bridges/`：法规桥接页。
- `law-wiki/`：法规基础库，承载法源、概念、主题与法规审计页。
- `wiki/rules/`：表达、证据、SOP 方法论与外部使用说明。
- `wiki/audits/`：覆盖率、孤儿节点、治理页。
- `wiki/patterns/`、`wiki/faq/`、`wiki/playbooks/`：辅助层。
- `validation/`：CLI 运行过程文件、验证结果文件、业务系统模拟审查结果。
- `raw/source-files/`：源文件归档。
- `raw/full-risk-scans/`：逐文件全风险扫描。
- `raw/numbered-text/`：带行号全文快照。
- `raw/manifests/`：项目级结构化索引层，服务本库内部批量筛查与治理。
- `raw/extracted-comments/`：人工埋点辅助层，保留原始批注并补充结构化信号。

## 4. 主工作原则
- 先由 LLM 完成实质审查，再进行结构化入库。
- 风险识别、风险归因、法规映射、证据边界说明属于 LLM 责任，不属于脚本责任。
- 脚本只负责文本抽取、编号、链接维护和治理审计。
- `raw/full-risk-scans/` 应当承载“本项目真实风险点”，而不是“规则命中列表”。
- `wiki/findings/` 是跨项目稳定规则沉淀层，不得替代单文件主审查。
- `wiki/findings/` 中的 `审查逻辑 / SOP` 是外部业务系统复用本库能力的核心接口。

## 5. 强制规则
- 先审查，后入库。
- 先生成 `raw/full-risk-scans/`，后生成 `wiki/projects/`。
- 先完成 `wiki/` 与 `raw/` 主链，再考虑是否需要额外发布层。
- 主查询优先级固定为：`projects -> findings -> legal-bridges -> audits`。
- 无 `raw/numbered-text/` 不得输出行号证据。
- 不得将 `raw/extracted-comments/` 替代正文证据使用。
- 不得将脚本命中、关键词命中、旧标题回填直接作为风险结论。
- 不得将 CLI 运行过程文件、接口验证结果、批量模拟输出写入 `wiki/audits/`。
- `raw/manifests/` 必须可用于按风险数、批注数、优先级和项目属性检索。
- `raw/extracted-comments/` 必须同时保留结构化信号和原始批注。
- 无 `legal-bridges` 支撑，不得包装为权威规则页。
- 项目页不得替代规则页。
- 规则页不得替代 raw 证据页。
- vault 内部链接统一使用相对 wikilink。
- 不得使用 vault 内绝对路径 wikilink。

## 6. 结论表达规则
- 必须区分：法定禁止、高风险、规则支持、编制建议、待人工复核。
- 不得把批注建议直接写成确定违法结论。
- 不得把单项目经验直接上升为普遍规则。
- 不得脱离采购类型、品目、项目事实和地域口径泛化结论。
- 必须优先回答“本项目具体风险是什么、证据在哪里、为什么构成风险”。
- 只有在跨项目稳定时，才回答“它属于哪条标准 finding”。
- 若 `full-risk-scan` 仍含“第二轮增强”“规则识别结果”“首轮扫描主题回填”等表述，应视为过渡产物而非最终主审查页。

## 7. 状态定义
- `reviewed`：已完成 LLM 实质审查，风险点、法规依据、证据行号和边界说明齐备。
- `needs-review`：已入库但尚未完成高质量 LLM 主审查，或关键证据仍不足。
- `maintained`：规则页或桥接页进入维护态。
- `draft`：仅允许用于未完成辅助页，不用于对外结论。

## 8. INGEST 执行口径
- 本库处理单文件时，默认先读 `raw/numbered-text/`、源文件批注和相关法规基础，再产出 `raw/full-risk-scans/`。
- 本库不得把“先建项目页再回头补风险”作为默认流程。
- 当标准 finding 无法充分覆盖项目特有风险时，应先写入项目级扫描页，再决定是否升级标准规则。
- 面向外部业务系统时，正式暴露的是 `wiki/findings/` 中的 `审查逻辑 / SOP`，而不是 raw 层内部文件。

## 9. 控制文件
- `INGEST.md`：入库标准。
- `QUERY.md`：查询路由标准。
- `LINT.md`：治理审计标准。
