# LINT

## 1. 目标
- 定期检查法规基础库是否存在断链、缺源、无依据断言、时效风险和来源层级混淆。

## 2. 必查项目
- `sources/` 页面是否包含必备 frontmatter。
- `sources/` 是否存在 raw 原文路径。
- `topics/` 中的制度结论是否能回链 source。
- `concepts/` 中的定义是否能回链 source 或 topic。
- `biz-materials/` 是否显式标注 `source_class: C`，且未被误标为 A 类 source。
- 是否存在绝对路径 wikilink。
- 是否存在把转载件标记为最高权威入口的情况。
- 是否存在 `maintained` 页面仍缺少 `official_url` 或 `raw_paths` 的情况。

## 3. 审计输出
- 缺少来源：写入 `audits/missing-sources.md`。
- 无依据断言：写入 `audits/unsupported-claims.md`。
- 断链：写入 `audits/broken-links.md`。
- 时效风险：写入 `audits/stale.md`。
- 冲突口径：写入 `audits/conflicts.md`。
- 孤儿页面：写入 `audits/orphans.md`。

## 4. 禁止事项
- 不得为了减少审计问题而删除不确定点。
- 不得把 `needs-primary-source-check` 直接改为 `maintained`，除非已经补齐部委或官方原始入口。
- 不得把 raw 原文删除后仍保留 source 页为 maintained。
- 不得把 `raw/biz/` 或 `biz-materials/` 作为 maintained source 的唯一依据。
