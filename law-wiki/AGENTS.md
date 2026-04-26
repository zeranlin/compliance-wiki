# AGENTS

## 1. 适用范围
- 本库是政府采购法规基础库，是独立的 Obsidian-first LLM wiki。
- 本库服务对象包括：
  - 当前政府采购招标文件合规审查 wiki。
  - 企业业务系统。
  - 业务系统中的小模型或审查智能体。
- 本库只回答法规、概念、主题、制度边界和法源支撑问题，不直接替代项目级招标文件审查。

## 2. 目录职责
- `sources/`：法规、规章、规范性文件、官方通知、官方专项整治文件的来源页。
- `topics/`：跨来源的制度主题页。
- `concepts/`：可复用法规概念页。
- `biz-materials/`：地方业务整理、内部检查表和辅助检查点页面，只作为 C 类材料使用。
- `audits/`：缺源、断链、冲突、过期和无依据断言审计。
- `raw/laws/`：本地法规原文 Word/PDF 等文件。
- `raw/biz/`：本地业务人员上传的检查表、问题清单等材料。
- `raw/downloads/`：下载的官方原始文件，包括 html、pdf 等。
- `raw/sources/`：从原始文件抽取出的可检索文本。
- `index.md`：总入口。
- `log.md`：变更日志。

## 3. 主链
- 标准查询链：`topics/ -> concepts/ -> sources/ -> raw/sources/ -> raw/downloads/ / raw/laws/`
- 辅助材料链：`biz-materials/ -> raw/biz-extracted/ -> raw/biz/`
- 当外部合规审查 wiki 需要法规依据时，应优先链接 `sources/` 或 `topics/`，再回到 raw 原文。
- `sources/` 是权威入口；`raw/` 是原文证据，不作为人工阅读的首选入口。

## 4. 工作原则
- 先下载或确认官方来源，再生成 source 页。
- 先 source，后 topic，再 concept。
- 不得凭记忆补法规结论。
- 不得把地方转载件直接包装为财政部原站来源；如暂用转载件，必须显式标注。
- 不得把政策解读、地方材料、业务经验等同于法源。
- `raw/biz/` 和 `biz-materials/` 不得进入 A 类 source 层；只能用于补充检查点、SOP、正反例和业务表达。
- 所有页面优先使用 Obsidian wikilink。
- 本库内部链接不得写绝对路径。

## 5. 状态定义
- `maintained`：已完成来源核验、摘要和链接，可作为法规依据引用。
- `needs-current-validity-check`：来源存在，但需要时效或现行有效性核验。
- `needs-primary-source-check`：内容可信但原始入口不是最高权威入口，需要继续核验。
- `draft`：草稿页，不得作为正式依据。

## 6. 控制文件
- `INGEST.md`：来源入库标准。
- `QUERY.md`：查询路由标准。
- `LINT.md`：治理审计标准。
