---
id: rule-external-sop-usage
title: 外部系统-SOP-使用说明
page_type: rule
status: maintained
last_reviewed: 2026-04-24
---

上级导航：[[index]]

## 适用范围
- 本页只说明外部业务系统如何消费本 wiki 中的 `finding SOP`。
- 外部业务系统当前正式可见、可调用的核心对象，是 `wiki/findings/*.md` 中的 `审查逻辑 / SOP`。
- `raw/full-risk-scans/`、`raw/numbered-text/` 属于本库内部生产与验证层，不作为外部业务系统默认可见接口。

## 外部系统主入口
1. 根据业务侧认可的风险点名称，定位到对应 `wiki/findings/*.md`。
2. 读取该页面中的：
   - 风险定义
   - 适用边界
   - 审查逻辑 / SOP
   - 正例 / 反例
   - 法律依据
3. 将 `审查逻辑 / SOP` 交给外部小模型，对业务系统自己的招标文件原文执行审查。

## 使用 finding-SOP 的标准动作
- 先读取目标 finding 的 `审查逻辑 / SOP`，理解当前要找的是哪一类具体条款。
- 再将该 `SOP` 应用于业务系统当前持有的招标文件原文，按 `SOP 2 -> SOP 3 -> SOP 4 -> SOP 5 -> SOP 6 -> SOP 7` 顺序执行。
- 外部系统输出时，应至少包括：
  - 是否命中
  - 命中的条款原文
  - 风险原因
  - 对应的命中条件
  - 若不命中，触发了哪个排除条件或反例边界

## 内部生产与验证说明
- 本库内部在生产 `finding SOP` 时，会使用 `INGEST -> raw -> full-risk-scan -> 回放验证` 的方法。
- 本库内部在验证 `SOP` 时，会使用 `raw/numbered-text/` 和 `raw/full-risk-scans/` 做盲测与对账。
- 这些内部验证材料用于保证 `finding SOP` 质量，不是外部系统当前的主调用接口。

## 禁止做法
- 不要绕过 `finding` 页面，直接从其他内部文件拼接经验性规则。
- 不要只靠关键词命中直接输出风险。
- 不要跳过条款属性判断直接给出命中结论。
- 不要把 `SOP` 写成只能依赖 `raw` 文件才能理解和执行的内部说明。
