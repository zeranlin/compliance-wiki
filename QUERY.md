# QUERY

## 1. 目标
- 优先从结构化知识节点回答，并保留回到原文证据的能力。
- 面向外部业务系统时，正式调用入口是 `wiki/findings/` 中的 `审查逻辑 / SOP`。
- `raw/full-risk-scans/`、`raw/numbered-text/` 主要属于本库内部生产、验证和回证层，不作为外部业务系统默认可见接口。

## 2. 路由顺序
1. `wiki/projects/`
2. `wiki/findings/`
3. `wiki/legal-bridges/`
4. `wiki/audits/`
5. `law-wiki/`
6. `raw/full-risk-scans/`
7. `raw/numbered-text/`
8. `wiki/rules/`
9. `wiki/patterns/`、`wiki/faq/`、`wiki/playbooks/` 仅作辅助

## 2.1 外部系统优先级
1. `wiki/findings/` 的 `审查逻辑 / SOP`
2. `wiki/legal-bridges/`
3. `law-wiki/`
4. `wiki/rules/`
5. `wiki/audits/`

## 3. 路由规则
- 查询项目风险：从 `wiki/projects/` 进入
- 查询风险规则：从 `wiki/findings/` 进入
- 查询法条锚点：从 `wiki/legal-bridges/` 进入
- 查询覆盖率、漏项、治理状态：从 `wiki/audits/` 进入
- 外部业务系统需要复现风险识别时：直接读取对应 finding 的 `审查逻辑 / SOP`
- 外部业务系统需要确认某风险点的边界时：继续读取该 finding 的适用边界、正例 / 反例和法律依据
- 本库内部如需查询原文证据、行号、触发文本：从 `raw/full-risk-scans/` 与 `raw/numbered-text/` 进入
- 本库内部如需验证某 finding 是否真的可用：进入 [[wiki/playbooks/小模型-SOP-验证闭环|小模型 SOP 验证闭环]] 与 [[wiki/audits/finding-sop-validation|findings SOP 验证方法]]

## 4. 标准回答结构
- 简明结论
- 风险级别 / 风险性质
- 风险原因
- 法规依据 / 桥接页
- 证据位置
- 适用边界 / 项目差异
- 修改建议
- 不确定点 / 待复核点

## 5. 证据规则
- 行号只能来自 `raw/numbered-text/`
- 项目命中风险优先引用项目页与 `full-risk-scan`
- 一般规则优先引用 `finding`
- 权威法源优先通过 `legal-bridges` 跳转 `law-wiki/`
- 外部业务系统当前正式消费的是 `finding` 页面中的 `审查逻辑 / SOP`，并将其应用到业务系统自己的招标文件原文
- 本库内部如需做 SOP 验证，才继续使用 `project -> full-risk-scan -> numbered-text` 取证和对账

## 6. 禁止事项
- 不得绕过 `findings` 用项目页回答规则性问题
- 不得绕过 `raw/numbered-text` 给出行号型证据
- 不得把项目经验上升为普遍法规则
- 不得在 `wiki/` 支撑不足时隐式从 raw 直接下确定结论
- 不得把本库内部 `raw` 层验证链误写成外部业务系统的正式调用链

## 7. 必须区分的结论层级
- 明确法定禁止
- 高风险
- 规则支持的风险
- 编制建议
- 待进一步核验
