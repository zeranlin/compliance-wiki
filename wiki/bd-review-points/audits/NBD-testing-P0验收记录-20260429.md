---
id: nbd-testing-p0-acceptance-20260429
title: NBD testing P0 验收记录 20260429
page_type: nbd-audit
status: maintained
last_reviewed: 2026-04-29
---

上级导航：[[../index|新版 BD 审查点明细库]]

## 验收范围

- P0 技术稳定性组：NBD07-009、NBD07-010、NBD07-014、NBD07-024、NBD07-032。
- fixture smoke：`validation/nbd-runs/p0-recall-fixture-qwen35-27b-20260429/smoke-summary.md`
- 真实样本 smoke：`validation/nbd-runs/p0-real-smoke-qwen35-27b-20260429/smoke-summary.md`
- 模型：`qwen3.5-27b`

## 调整内容

- 为 NBD07-009 补充 `CNAS`、`CNAS标识`、`CNAS资质`、`检测报告`、`国际互认`、`非进口项目` 等召回词。
- 为 NBD07-010 补充 `国际标准`、`ISO`、`ASTM`、`BIFMA`、`BS`、`检测标准`、`国内同等标准` 等召回词。
- 为 NBD07-014 补充 `检测报告数量`、`检测报告份数`、`五份`、`5份`、`6份` 等召回词。
- 为 NBD07-024 补充 `会计师事务所`、`律师事务所`、`事务所`、`执业年限`、`评审因素`、`得分` 等召回词。
- 将四项品目专项 fixture 从抽象描述改为可定位的正式条款样式。
- `NBD07-032` 保留 CLI partial JSON recovery 兜底，但不据此升级 maintained。

## 验证结果

| NBD ID | fixture 结果 | 真实样本结果 | 状态分流 |
|---|---|---|---|
| NBD07-009 | 三类分流通过 | 3 份真实样本均不命中，失败 0，fallback 0 | maintained |
| NBD07-010 | 三类分流通过 | 3 份真实样本均不命中，失败 0，fallback 0 | maintained |
| NBD07-014 | 三类分流通过 | 家具、医疗样本命中，物业样本不命中，失败 0，fallback 0 | maintained |
| NBD07-024 | 补强 boundary 后三类分流通过 | 3 份真实样本均不命中，失败 0，fallback 0 | maintained |
| NBD07-032 | positive/boundary 曾触发截断 JSON，已由 parser recovery 兜底 | 3 份真实样本均不命中，失败 0，fallback 0 | testing |

## 当前状态

- maintained：111。
- testing：42。
- draft：0。
- 总覆盖：153。

## 后续

- 下一轮进入 P1 召回与支持上下文组，优先处理候选窗口为空或正式章节召回不足的 NBD。
- `NBD07-032` 后续单独治理输出长度、候选摘录压缩和 JSON 协议稳定性。
