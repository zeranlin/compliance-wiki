# LINT

## 1. 目标
- 保证当前 vault 在内部生产侧可检索、可回链、可追证、可治理。
- 保证对外消费侧能够稳定输出 `wiki/findings/*.md` 中可执行的 `审查逻辑 / SOP`。

## 2. 目录检查
- `wiki/` 仅允许存在：`audits`、`faq`、`findings`、`legal-bridges`、`patterns`、`playbooks`、`projects`、`rules`
- `raw/` 仅允许存在证据层与中间产物层目录
- `raw/` 核心目录应为：`source-files`、`full-risk-scans`、`numbered-text`
- `raw/` 升级目录应为：`manifests`、`extracted-comments`
- 不应存在空目录
- 不应存在绝对路径镜像残留目录，如 `Users/`
- 不应继续保留 `raw/extracted-text/`
- 不应存在 `.DS_Store`
- 根目录不应再假定存在 `exports/`

## 3. 必备审计页
- `wiki/audits/project-to-finding-coverage.md`
- `wiki/audits/finding-to-law-coverage.md`
- `wiki/audits/full-risk-scan-index.md`
- `wiki/audits/full-risk-scan-second-pass-index.md`
- `wiki/audits/source-coverage.md`
- `wiki/audits/ingest-backlog.md`
- `wiki/audits/raw-risk-orphans.md`
- `wiki/audits/duplicate-project-entry-candidates.md`
- `wiki/audits/corpus-risk-scan.md`
- `wiki/audits/unmapped-findings.md`
- `wiki/audits/fallback-evidence-hotspots.md`
- `wiki/audits/project-title-anomalies.md`
- `wiki/audits/finding-refinement-backlog.md`
- `wiki/audits/finding-quality-overview.md`
- `wiki/audits/health-certificate-watchlist.md`

## 4. 必备复用面
- `wiki/findings/` 中每个 `maintained` finding 必须包含 `## 审查逻辑`
- `wiki/projects/` 中每个项目页必须能回到 `raw/full-risk-scans/`
- `raw/full-risk-scans/` 中每个项目必须能回到 `raw/numbered-text/`
- 外部系统可直接消费的最小复用链必须成立：`finding -> 审查逻辑 / SOP`
- `wiki/audits/finding-sop-validation.md` 与 `wiki/playbooks/小模型-SOP-验证闭环.md` 应保持一致口径

## 5. 结构检查
- 每个项目页必须链接 `raw/full-risk-scans/` 和 `raw/numbered-text/`
- 每个项目页必须链接至少 1 个 `finding` 或标注待复核
- 每个 `finding` 必须链接至少 1 个 `legal-bridge`
- 每个 `legal-bridge` 必须指向 `law-wiki/`
- 每个 `raw/full-risk-scans` 必须回链项目页和对应 findings
- 每个 `raw/manifests` 必须包含 `project_page`、`full_risk_scan`、`numbered_text`、`risk_count`、`priority`
- 每个 `raw/extracted-comments` 必须包含 `suggested_findings`、`structured_signals`、`comments`
- 每个 `maintained` finding 必须包含可供小模型复现的 `## 审查逻辑`
- 每个 `maintained` finding 的 `## 审查逻辑` 中必须包含 `SOP 1` 到 `SOP 7`
- vault 内部页面不得继续使用绝对路径 wikilink

## 6. 覆盖检查
- 每个源文件都应有项目页
- 每个源文件都应有 `full-risk-scan`
- 每个源文件都应有 `numbered-text`
- `full-risk-scans` 与 `manifests` 数量不一致时必须排查残留文件
- `extracted-comments` 中 `comment_count` 与 `has_comments` 不一致时必须修复生成器
- 命中项目数为 0 的 finding 需要复核保留必要性
- `full-risk-scans` 中未映射到标准 finding 的标题必须进入审计页
- 外部系统要直接使用的 finding，其 `审查逻辑 / SOP` 必须至少有正例和反例
- 高频 maintained finding 应逐步纳入“内部盲测 -> 与 `full-risk-scan` 对账 -> 反向修 SOP”的闭环审计

## 7. 质量检查
- 高风险结论必须写明法规依据与证据边界
- 项目页不得退化为规则页
- finding 页不得退化为项目摘要
- 审计页不得继续引用已删除目录或旧结构
- 首页与规则页不得把 `patterns/faq/playbooks` 作为主路由
- 不得再把 `exports/` 当作当前正式结构
- 外部复用口径不得脱离 `wiki/` 与 raw 主链单独编造结论
- 若 `finding` 被标记为 maintained，但长期没有项目级盲测或对账记录，应进入审计待办

## 8. 问题处理
- 孤儿项目页、孤儿 finding、孤儿 bridge：补链，不放行
- 绝对路径式 vault 内链接：改为相对 wikilink
- 标题污染、模板残留、重复入口：记录审计页并优先修生成器
- `extracted-text` 残留目录：删除，不放行
- 只有批注、没有正文证据的高风险结论：降级为待复核表达
- 若文档仍引用 `exports/`：改回当前主链口径，不放行
