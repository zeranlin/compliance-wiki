---
id: nbd36-maintained-acceptance-20260428
title: NBD36 全量 maintained 验收记录 20260428
page_type: nbd-validation-output
status: maintained
last_reviewed: 2026-04-28
---

上级导航：[[../index|新版 BD 审查点明细库]]

# NBD36 全量 maintained 验收记录 20260428

## 目标
将当前 36 个 NBD 从 `maintained: 12 / testing: 8 / draft: 16` 推进到 `maintained: 36`。

## 验收输入
- 既有 maintained 标杆：12 个。
- 第一组 testing fixture smoke：`validation/nbd-runs/pilot-draft-smoke-group1-qwen35-27b-20260428/smoke-summary.md`。
- 16 个 draft fixture smoke：`validation/nbd-runs/pilot-draft-smoke-all-drafts-qwen35-27b-20260428/`。
- 24 个非 maintained NBD 真实样本 smoke：`validation/nbd-runs/nbd24-real-sample-smoke-qwen35-27b-20260428/smoke-summary.md`。

## 验收结果
| 项目 | 数量 | 结果 |
|---|---:|---|
| 既有 maintained | 12 | 保持 |
| testing 升级 maintained | 8 | 通过 |
| draft 补 fixture 后升级 maintained | 16 | 通过 |
| fixture smoke 调用 | 63 | 0 失败 |
| 真实样本 smoke 调用 | 72 | 0 失败 |
| 最终 maintained | 36 | 达成 |

## 本轮关键修正
- 补齐 16 个 draft NBD 的专项判断链。
- 新增 48 个 fixture，覆盖命中、不命中、待复核或明确不命中边界。
- 增强定位词簇：持续经营、本地服务机构、供应商性质、组织形式、担保/保险、免费质保期、服务期限等。
- 将先导批 24 个 NBD 升级为 `maintained / v1-maintained`。

## 维护观察项
- 候选窗口偏高：`NBD01-002`、`NBD01-006`、`NBD02-004`、`NBD02-009`、`NBD02-011`。
- 待复核比例偏高：`NBD02-002`、`NBD06-010`、`NBD06-014`。
- 后续全量扩展时，应继续按“fixture 正反边界 + 真实样本 smoke + 窗口控制”的流程推进。

## 结论
截至 2026-04-28，本库 36 个 NBD 全部进入 `maintained`。
