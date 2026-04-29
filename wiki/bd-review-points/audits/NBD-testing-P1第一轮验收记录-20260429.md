---
id: nbd-testing-p1-round1-acceptance-20260429
title: NBD testing P1 第一轮验收记录 20260429
page_type: nbd-audit
status: maintained
last_reviewed: 2026-04-29
---

上级导航：[[../index|新版 BD 审查点明细库]]

## 验收范围

- P1 召回与支持上下文组第一轮：15 个 NBD。
- 本轮具体调试 12 个：NBD01-017、NBD03-003、NBD03-004、NBD03-005、NBD04-003、NBD06-009、NBD07-003、NBD07-004、NBD07-015、NBD07-019、NBD07-026、NBD02-044。
- 继续沿用前序 fixture 的 3 个：NBD01-028、NBD01-029、NBD06-019。
- fixture smoke：`validation/nbd-runs/p1-recall-fixture-qwen35-27b-20260429/smoke-summary.md`
- 真实样本 smoke：`validation/nbd-runs/p1-real-smoke-qwen35-27b-20260429/smoke-summary.md`
- 模型：`qwen3.5-27b`

## 调整内容

- 补充交货时间、交货地点、服务期限、所属行业、付款方式、CMA、检验检测报告时间、技术参数区间、物业服务范围、燃气具安装维修资质、技术评审项等召回词。
- 将对应 fixture 改为正式条款样式，避免抽象标题无法形成候选窗口。
- NBD07-015 额外补强“技术要求 + 区间值 + 负偏离/实质性响应”表达，解决首轮候选分数不足。

## 验证结果

| 指标 | 结果 |
|---|---:|
| fixture 有效调用 | 36 |
| fixture 调用失败 | 0 |
| 真实样本调用 | 45 |
| 真实样本调用失败 | 0 |
| 真实样本 fallback | 0 |
| 真实样本最大候选窗口数 | 9 |
| 真实样本平均候选窗口数 | 3.93 |

## 状态分流

| 状态 | NBD |
|---|---|
| maintained | NBD03-004、NBD07-003、NBD07-015、NBD07-019、NBD07-026 |
| testing | NBD01-017、NBD01-028、NBD01-029、NBD03-003、NBD03-005、NBD04-003、NBD06-009、NBD06-019、NBD07-004、NBD02-044 |

## 当前状态

- maintained：116。
- testing：37。
- draft：0。
- 总覆盖：153。

## 后续

- 对 NBD01-017、NBD01-029、NBD06-019 这类全文缺失型，下一轮优先建立“应有配置项事实卡 + 缺失确认”支持上下文。
- 对 NBD01-028、NBD04-003、NBD07-004 的真实样本命中，先核验真实条款是否为真阳性，再决定升级或收窄。
