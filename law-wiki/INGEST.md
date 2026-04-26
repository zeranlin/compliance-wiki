# INGEST

## 1. 目标
- 将政府采购法规、规章、规范性文件、官方通知和专项整治文件转化为可检索、可回链、可被 LLM 和 Obsidian 同时使用的法规知识页。
- 本库 ingest 的完成标准，不是“保存了文件”，而是“已形成 source 页、主题链接、概念链接、raw 原文证据和审计状态”。

## 2. 必备输入
- 官方原始页面、PDF、Word 或正式发布文本。
- 发文机关、文号、发布日期、施行日期或执行时间。
- 适用范围、核心制度问题和与政府采购合规审查的关系。

## 3. 必备输出
- `raw/downloads/`：原始下载文件。
- `raw/sources/`：可检索文本抽取结果。
- `raw/laws/`：本地法规原文归档。
- `raw/biz/`：本地业务材料原文归档。
- `raw/biz-extracted/`：业务表格或文档的可检索抽取结果。
- `sources/*.md`：来源页。
- `biz-materials/*.md`：C 类业务材料摘要页。
- 必要时更新 `topics/*.md`。
- 必要时更新 `concepts/*.md`。
- 必要时更新 `audits/missing-sources.md`、`audits/unsupported-claims.md` 或 `audits/stale.md`。
- `log.md`。

## 4. source 页必备字段
- `id`
- `title`
- `aliases`
- `tags`
- `source_type`
- `evidence_level`
- `status`
- `issuer`
- `doc_no`
- `issued_date`
- `effective_date`
- `official_url`
- `raw_paths`
- `summary_confidence`

## 5. source 页正文结构
- 上级导航。
- 关联主题。
- 文档摘要。
- 关键断言。
- 对合规审查的作用。
- 适用范围。
- 效力与时效。
- 原文证据。
- 关联主题。
- 交叉引用。
- 不确定点。

## 6. 强制规则
- 无 raw 原文或官方入口，不得标记为 `maintained`。
- 只有地方转载件但未找到部委原始入口时，状态必须为 `needs-primary-source-check`。
- 不得大段复制全文到 source 页；全文应放入 `raw/sources/` 或 `raw/downloads/`。
- source 页只写摘要、关键断言和本库使用方式。
- topic 页不得替代 source 页。
- concept 页不得替代 source 页。
- 业务材料不得替代 source 页。
- `biz-materials/` 页面必须显式标注 `source_class: C`。
- C 类材料只能用于补充 SOP、关键词、正反例和业务表达；新增标准风险点仍必须回到 A 类或 B 类来源校正。
- 主题页上的每个制度结论应能回链到至少一个 source 页。

## 7. 与合规审查 wiki 的关系
- 本库为合规审查 wiki 提供 A 类法源和官方规范底座。
- 合规审查 wiki 的 `wiki/findings/` 不应直接引用未入库 raw 文件，应优先通过本库 `sources/`、`topics/` 或主库 `wiki/legal-bridges/` 取得依据。
- 当主库发现风险点缺少权威依据时，应先补本库 source，再回到主库生成或修订 finding。
