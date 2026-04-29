---
id: nbd-batch4-batch5-acceptance-20260429
title: NBD Batch 4-5 验收记录 20260429
page_type: nbd-audit
status: maintained
last_reviewed: 2026-04-29
---

上级导航：[[../index|新版 BD 审查点明细库]]

## 验收范围

- Batch 4：30 个 NBD，覆盖目标从 90 到 120。
- Batch 5：33 个 NBD，覆盖目标从 120 到 153。

## 验收结果

| 批次 | NBD 数 | fixture 调用 | 真实样本调用 | 调用失败 | fallback | 升级 maintained | 保留 testing |
|---|---:|---:|---:|---:|---:|---:|---:|
| Batch 4 | 30 | 90 | 90 | 0 | 0 | 14 | 16 |
| Batch 5 | 33 | 99 | 99 | 2 fixture JSON 截断；真实样本 0 | 0 | 14 | 19 |

## 当前总状态

| 状态 | 数量 |
|---|---:|
| maintained | 107 |
| testing | 46 |
| draft | 0 |
| 总覆盖 | 153 |

## 结论

153 个 NBD 已全部覆盖，且全部至少达到 `testing`。稳定项已升级为 `maintained`，争议项继续留在 testing 池，后续集中做口径、召回和真实样本专项调试。
