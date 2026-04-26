# QUERY

## 1. 查询目标
- 优先回答法规依据、制度边界、概念定义、适用范围和时效状态。
- 不直接输出项目级风险结论；项目级风险结论应由合规审查 wiki 的 `raw/full-risk-scans/` 和 `wiki/findings/` 承担。

## 2. 查询路由
- 查法规原文：先查 `sources/`，再查 `raw/sources/` 和 `raw/downloads/`。
- 查制度主题：先查 `topics/`，再回链 `sources/`。
- 查术语概念：先查 `concepts/`，再回链 `topics/` 和 `sources/`。
- 查业务检查点或地方整理经验：查 `biz-materials/`，再回到 `sources/` 或 `topics/` 校正。
- 查缺源或不确定：查 `audits/missing-sources.md`、`audits/unsupported-claims.md`、`audits/stale.md`。

## 3. 回答口径
- 必须区分：
  - 法律
  - 行政法规
  - 部门规章
  - 规范性文件
  - 官方专项整治口径
  - 政策解读或转载材料
- 如仅有转载件，应明确“当前为转载入口，仍需核验部委原始入口”。
- 如使用 `biz-materials/`，应明确其为 C 类辅助材料，不是法源。
- 如问题涉及地方标准、地方目录、地方采购限额，应说明本库是否已入库相应地方来源。

## 4. 禁止事项
- 不得把没有 source 页支撑的结论当作本库权威结论。
- 不得把 topic 页中的综合判断当作原文条款。
- 不得脱离适用范围泛化政策。
- 不得把已废止、过期或需核验的文件当作现行有效依据。
