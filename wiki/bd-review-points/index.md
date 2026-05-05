---
id: bd-review-points-index
title: 新版 BD 审查点明细库
page_type: bd-review-point-index
status: maintained
last_reviewed: 2026-04-30
---

上级导航：[[../index|政府采购招标文件合规审查工作台]]

## 定位
- 本目录承载新版详细 BD 审查点。
- 本目录与旧版 [[../checkpoints/index|B层标准检查点产品库]] 完全隔离。
- 本目录优先吸收新版需求材料中的“审查点、审查规则、审查逻辑、风险提示及修改建议、审查依据、案例”等结构。
- 本目录可复用 [[../boundaries/index|A类法源边界库]] 与 [[../checkpoint-domains/index|BD 问题域调度层]]，但不替代二者。

## 命名规则
- 新版审查点文件统一使用 `NBDxx-yyy 审查点名称.md`。
- `NBD` 表示新版 BD 审查点，避免与旧版 `BDxx-yyy` 检查点混用。
- `xx` 优先继承或映射现有 BD 问题域编号；若新版方案重排问题域，应先在本页或映射页说明。
- `yyy` 为同一问题域下的三位序号。

## 层级关系
```text
A 法源边界：为什么能查
BD 问题域：这一类问题怎么组织和调度
NBDxx-yyy 审查点：新版详细审查点，负责具体怎么查、怎么判、怎么提示修改
```

## 当前状态
- 目录已建立。
- 已建立方法论、页面模板、问题域骨架、建设清单和首批 36 个 `v1-maintained` 标杆样例。
- 当前 36 个样例已全部完成本轮验收，状态为 `maintained`。
- 已完成 maintained 的类型标杆包括：明确禁止、评分因素、关联比较、合理性判断、配置缺失、政府采购政策、数值比例、履约配置、品目专项。
- 已完成全量分型计划，并完成 Batch 2、Batch 3、Batch 4、Batch 5 的 NBD 生成、fixture smoke 与真实样本 smoke。
- 当前已覆盖 151 个 NBD：`maintained` 151 个，`testing` 0 个，`draft` 0 个。
- Batch 2 中 21 个升级为 `maintained / v1-maintained`，3 个进入 `testing / v1-testing`。
- Batch 3 中 22 个升级为 `maintained / v1-maintained`，8 个进入 `testing / v1-testing`。
- Batch 4 中 14 个升级为 `maintained / v1-maintained`，16 个进入 `testing / v1-testing`。
- Batch 5 中 14 个升级为 `maintained / v1-maintained`，19 个进入 `testing / v1-testing`。
- testing P0 专项调试中 4 个升级为 `maintained / v1-maintained`，`NBD07-032` 保留 `testing / v1-testing`。
- testing P1 第一轮中 5 个升级为 `maintained / v1-maintained`，10 个保留 `testing / v1-testing`。
- testing37 最终验收中剩余 37 个全部升级为 `maintained / v1-maintained`。
- 2026-04-30 已完成 NBD 瘦身与 IR 拆分治理：151 个 maintained NBD 均可编译出 NBD IR、Recall IR、Prompt IR、Governance IR。
- 日常 CLI prompt 已切换为读取 Prompt IR 可执行 SOP，不再读取整页 NBD markdown；0044-A P4 回归 151 个模型结果，失败数 0。
- maintained 页面已清理历史治理噪声：`待 smoke / 待预检 / 待验证`、空样例占位、`调试备注`、`小模型可执行性自检` 均不得保留在页面主体。

## 方法论
- [[NBD-方法论|NBD 方法论]]
- [[NBD标杆生成手册|NBD 标杆生成手册]]
- [[NBD类型标杆手册|NBD 类型标杆手册]]
- [[NBD可运行知识与CLI运行时协议设计|NBD 可运行知识与 CLI 运行时协议设计]]
- [[NBD日常审查CLI与候选窗口召回方案|NBD 日常审查 CLI 与候选窗口召回方案]]
- [[NBD可迭代质量工程体系方案|NBD 可迭代质量工程体系方案]]
- [[NBD小模型链路提升清单-20260429|NBD 小模型链路提升清单 20260429]]

## 目录
- [[templates/NBD页面模板|NBD 页面模板]]
- [[domains/index|NBD 问题域索引]]
- [[items/index|NBD 审查点条目索引]]
- [[audits/NBD建设清单|NBD 建设清单]]
- [[audits/NBD全量分型计划|NBD 全量分型计划]]
- [[audits/NBD先导批召回预检记录-20260428|NBD 先导批召回预检记录 20260428]]
- [[audits/NBD先导批小模型smoke记录-20260428|NBD 先导批小模型 smoke 记录 20260428]]
- [[audits/NBD06履约支付配置类testing记录-20260428|NBD06 履约支付配置类 testing 记录 20260428]]
- [[audits/NBD资格评审保证金第一组testing记录-20260428|NBD 资格评审保证金第一组 testing 记录 20260428]]
- [[audits/NBD36全量maintained验收记录-20260428|NBD36 全量 maintained 验收记录 20260428]]
- [[audits/NBD-Batch2验收记录-20260428|NBD Batch 2 验收记录 20260428]]
- [[audits/NBD-Batch3验收记录-20260428|NBD Batch 3 验收记录 20260428]]
- [[audits/NBD-Batch4-Batch5验收记录-20260429|NBD Batch 4-5 验收记录 20260429]]
- [[audits/NBD-testing-P0验收记录-20260429|NBD testing P0 验收记录 20260429]]
- [[audits/NBD-testing-P1第一轮验收记录-20260429|NBD testing P1 第一轮验收记录 20260429]]
- [[audits/NBD-testing37最终验收记录-20260429|NBD testing37 最终验收记录 20260429]]
- [[audits/NBD第一阶段153maintained生成复盘-20260429|NBD 第一阶段 153 maintained 生成复盘 20260429]]
- [[audits/NBD状态流转准入标准-20260429|NBD 状态流转准入标准 20260429]]
- [[audits/NBD153真实文件全量验证记录-20260429|NBD153 真实文件全量验证记录 20260429]]
- [[audits/NBD瘦身与IR拆分任务清单-20260430|NBD 瘦身与 IR 拆分任务清单 20260430]]
- [[audits/NBD争议池|NBD 争议池]]
- [[audits/NBD小模型验证记录|NBD 小模型验证记录]]
- [[audits/NBD法规映射缺口|NBD 法规映射缺口]]

## 建设计划
- 当前计划数量：151 个 NBD 执行单元，对应 151 个审查点页面。
- 初始来源：`casesrc/01-合规性审查需求分析（新版架构）.xlsx` 的 `通用（深圳）` sheet。
- 第一阶段：完成 36 个代表性 NBD 标杆样例，并全部升级为 `maintained`。
- 第二阶段：用类型标杆手册继续固化各类 NBD 的 SOP、fixture 和验收门槛。
- 第三阶段：按类型批量生成剩余 NBD，并逐步完成 fixture 与真实样本验收。
