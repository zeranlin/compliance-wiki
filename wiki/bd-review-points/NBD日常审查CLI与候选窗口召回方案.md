---
id: nbd-daily-review-cli-and-recall-design
title: NBD 日常审查 CLI 与候选窗口召回方案
page_type: nbd-methodology
status: draft
last_reviewed: 2026-04-29
---

# NBD 日常审查 CLI 与候选窗口召回方案

## 1. 核心定位

NBD 日常审查 CLI 的定位是：

```text
NBD SOP 执行器
```

它不是规则引擎，不是强模型审查器，也不是第二套 BD。

职责边界：

```text
NBD：定义风险点、召回剖面、审查 SOP、命中条件、排除条件。
CLI：抽取文件、寻找候选窗口、拼 prompt、调用小模型、汇总结果。
小模型：基于 NBD SOP + 候选窗口执行判断。
```

本阶段主要矛盾是：

```text
如何从未知采购文件中，为每个 NBD 找到准、全、少重复的候选窗口。
```

候选窗口不准，小模型再强也只能误判、漏判或输出待复核。

## 2. 设计原则

1. NBD 是唯一业务知识单元。
2. NBD 必须自包含，不依赖 NBD 专属 YAML 或第二套配置。
3. CLI 只实现通用召回算法，不保存 `if NBDxx` 这类专属业务逻辑。
4. 候选窗口质量优先于 prompt 技巧。
5. 日常审查链路只调用小模型；中间抽取、召回、去重、聚类默认不调用 LLM。
6. 轻事实摘要可以进入 prompt，但不得单独构成命中证据。
7. 召回质量必须可审计、可复盘、可调试。

## 3. 标准链路

```text
待审文件
-> 文档抽取
-> 文档结构化：line_view + block_view
-> 读取 NBD
-> 解析 NBD 召回剖面
-> block-aware 候选召回
-> 候选窗口扩展、去重、排序
-> 生成 prompt
-> 小模型输出 JSON
-> 汇总 NBD 结果
-> 生成业务报告
```

默认只有“小模型单点审查”调用 LLM。

## 3.1 当前小模型运行配置

后续日常审查链路默认使用以下小模型配置；历史验证目录和历史报告中记录的旧模型名称保留为当时运行证据，不回写修改。

```text
base_url: http://112.111.54.86:10011/v1
api_key: bssc
model: qwen3.6-35b-a3b
jobs: 20
timeout: 1800
temperature: 0
max_tokens: 6144
```

标准运行命令模板：

```bash
python3 scripts/nbd_review/main.py run \
  --review-file "<待审文件.docx>" \
  --output-dir "validation/nbd-runs/<时间戳>-<样本名>-full-qwen36" \
  --base-url "http://112.111.54.86:10011/v1" \
  --api-key "bssc" \
  --model "qwen3.6-35b-a3b" \
  --jobs 20 \
  --timeout 1800 \
  --temperature 0 \
  --max-tokens 6144 \
  --no-resume \
  --no-reuse-raw-response
```

## 4. NBD 自包含要求

每个 NBD markdown 应包含：

```text
审查目标
适用范围
定位与召回剖面
候选窗口要求
上下文读取规则
命中条件
排除条件
易误报场景
风险提示
修改建议
法规依据
```

候选窗口相关信息也应写入 NBD：

```text
必召章节
高价值关键词
对象词
行为词
后果词
支持上下文词
降权章节
窗口完整性要求
```

NBD 专属召回词、命中条件、排除条件、风险解释和修改建议不得拆到额外 YAML 中。

## 5. 文档结构化

CLI 应保留两套视图：

```text
line_view：用于证据行号。
block_view：用于召回和窗口扩展。
```

block 标准结构：

```json
{
  "block_id": "b0081",
  "block_type": "paragraph|table|heading",
  "line_start": 81,
  "line_end": 103,
  "section_path": ["第一册 专用条款", "评标信息"],
  "section_role": "scoring",
  "section_role_confidence": 0.86,
  "section_role_reason": [
    "上级标题包含：评标信息",
    "表格含：评审因素、权重、评分准则"
  ],
  "text": "..."
}
```

### 5.1 section_role 的定位

`section_role` 是文档块的功能身份标签，用于帮助候选窗口排序、降噪和分主次。

它不是风险判断结果，也不是强规则。

常见角色：

```text
announcement        招标公告/采购公告
qualification       申请人资格要求/投标人资格要求
scoring             评标信息/评分标准/评分细则
user_requirement    用户需求书/采购需求/技术要求/服务要求
business_terms      商务要求
contract_special    合同专用条款/补充条款
contract_template   合同条款及格式/合同模板
bid_format          投标文件格式/承诺函/声明函
common_terms        通用条款
catalog             目录
unknown             未识别
```

`section_role` 应按弱标签处理：

```text
关键词相关性为主；
section_role 只做加权和降噪；
低置信度时回退普通关键词召回；
不得因为 role 低就硬删除候选。
```

### 5.2 section_role 的识别依据

识别信号包括：

```text
标题/章节路径
表格表头
结构特征
负向章节特征
```

示例：

```text
评标信息 + 评审因素/权重/评分准则
=> scoring，高置信度

投标文件格式 + 承诺函
=> bid_format，中高置信度

第二册 通用条款
=> common_terms，中高置信度
```

## 6. 结构词初始化边界

CLI 可以初始化少量“文档结构类同义词”，用于识别章节角色。

例如：

```text
评标信息 = 评分标准 / 评审因素 / 评分细则 / 评分办法 / 综合评分表
用户需求书 = 采购需求 / 服务需求 / 技术要求 / 项目需求 / 需求清单
商务要求 = 商务条款 / 商务条件 / 合同商务要求
资格要求 = 申请人的资格要求 / 投标人资格要求 / 资格条件
合同模板 = 合同条款及格式 / 合同格式 / 合同范本 / 合同文本
投标文件格式 = 响应文件格式 / 投标文件组成 / 承诺函 / 声明函
```

这些词只用于结构识别，不用于具体风险判断。

具体风险相关词应写入对应 NBD，例如：

```text
本地经营服务网点
副省级奖项
安全生产标准化证书
付款 10 个工作日
```

NBD 是编译后的可运行知识，具体审查点的召回策略必须进入 NBD 文件本身，不能硬编码在 `engine.py`。CLI 只能解释 NBD，不得维护 `NBDxx-xxx -> 召回词` 的代码字典。

标准 NBD 应同时包含：

```text
人可读 SOP：审查目标、命中条件、排除条件、判断分流、风险提示、修改建议。
机可读召回：主召回词、正式证据词、降权噪声词、窗口扩展参数。
```

机可读召回统一写为：

```md
## 机器召回配置
### 主召回词
- ...

### 正式证据词
- ...

### 降权噪声词
- ...

### 窗口扩展
- 召回原因：...
- 标题后继块数：2
```

解释口径：

```text
主召回词：CLI 用于补充召回候选窗口。
正式证据词：命中后升权，优先进入 primary window。
降权噪声词：命中后降权，不应挤占正式证据窗口。
标题后继块数：命中短标题时向后合并正文块，避免只召回标题。
```

## 7. 候选窗口召回算法

核心改造目标：

```text
从 line-based topK
升级为
block-aware + section-role-aware + completeness-aware
```

### 7.1 初始命中

CLI 从 NBD 的召回剖面读取词组，对 block 打分。

打分因素：

```text
关键词命中
对象词命中
行为词命中
后果词命中
高价值组合命中
section_role 加权
表格完整性加权
正式章节加权
模板/目录/通用条款降权
重复扣分
```

示例：

```text
评标信息 + 本地经营 + 服务网点 + 得分 + 不得分
=> 高分 primary 窗口

承诺函模板 + 本地经营 + 服务网点
=> support 窗口，不应优先于正式评分项
```

### 7.2 章节角色加权

默认优先级：

```text
scoring
qualification
announcement
user_requirement
business_terms
contract_special
contract_template
bid_format
common_terms
catalog
unknown
```

正式章节优先，模板、通用条款、目录降权。

### 7.3 窗口扩展

命中 block 后，不机械取前后固定行，而是按窗口类型扩展。

评分项窗口尽量包含：

```text
评分项名称
权重
评分内容
评分依据
证明材料
备注
```

公告/资格窗口尽量包含：

```text
项目基本情况
申请人资格要求
联合体/进口产品
资格证明资料
```

商务要求窗口尽量包含：

```text
条款标题
条款正文
地点/期限/付款/验收等子条款
```

表格窗口尽量包含：

```text
表头
命中行
同一评分项或同一采购包相关行
```

### 7.4 primary/support 分离

候选窗口分为：

```text
primary_windows：可作为风险判断主证据。
support_windows：只补事实、格式、证明材料、承诺函。
```

示例：

```text
正式评分项 = primary
对应承诺函 = support
通用条款 = support 或降权
目录 = 通常排除
```

建议默认窗口预算：

```text
max_primary_windows = 5
max_support_windows = 3
```

避免重复模板挤掉主证据。

### 7.5 去重排序

去重依据：

```text
同一 section_role
同一评分项名称
同一 line range overlap
同一 normalized text
同一 block_id
```

排序依据：

```text
窗口分数
章节角色
窗口完整性
是否正式约束条款
是否重复
```

## 8. 候选窗口输出格式

给小模型的窗口应带元信息：

```text
[候选窗口 1]
window_type: primary
section_role: scoring
section_role_confidence: 0.86
section_path: 第一册 > 评标信息 > 商务部分
line_anchor: 0186-0189
score: 92
recall_reason: 命中“本地经营 / 服务网点 / 得分 / 不得分”，位于正式评分表
recall_quality: good
completeness:
- 评分项名称: yes
- 权重: yes
- 评分内容: yes
- 评分依据: yes

原文：
...
```

小模型据此能区分正式评分项、承诺函模板、通用条款和支持上下文。

## 9. 轻事实摘要

prompt 中可以加入轻事实摘要，但必须受限：

```text
只作背景和低级误报防护，不得单独构成命中证据。
```

可包含：

```text
项目类型
采购方式
评标方法
是否接受联合体
是否接受进口产品
标的所属行业
投标保证金
履约担保
评分权重合计
服务/交货/履约地点
合同/服务期限
```

风险命中仍必须来自候选窗口。

## 10. Prompt 结构

每个 NBD 的 prompt 固定为：

```text
1. 系统角色
2. 输出 JSON schema
3. NBD 标准检查点说明书
4. 轻事实摘要
5. 候选窗口 primary/support
6. 审查要求
```

小模型必须遵守：

```text
只能基于候选窗口作风险命中。
事实摘要只能辅助排除明显不适用。
候选不足时输出待人工复核或不命中。
不得把模板、通用条款、目录直接当正式风险。
```

## 11. 召回质量

召回质量是 CLI 的一等公民。

每个 NBD 应输出 `recall_quality`：

```text
good：主证据完整
partial：候选相关但缺上下文
noisy：主要是模板/通用条款
miss：未找到有效候选
```

`recall_matrix.md` 应展示：

```text
NBD
候选数
primary 数
support 数
最高分窗口 role
正式章节占比
模板章节占比
重复率
窗口完整性
recall_quality
缺失原因
```

调试顺序：

```text
先看召回质量，再看模型 verdict。
```

## 12. 主题组合

主题组合不依赖 YAML，只维护 NBD 列表。

示例：

```md
---
id: nbd-theme-discrimination
title: 采购文件歧视条款检查主题
nbd_ids:
  - NBD01-003
  - NBD02-002
  - NBD02-004
---
```

CLI 支持：

```bash
nbd-review run --theme wiki/nbd-themes/采购文件歧视条款检查主题.md
nbd-review run --nbd NBD01-003,NBD02-002
```

## 13. 最小工程结构

第一版保持极简：

```text
scripts/nbd_review/
  main.py
  engine.py
```

职责：

```text
main.py：命令行入口。
engine.py：文档抽取、结构化、NBD 解析、召回、prompt、模型调用、输出。
```

如果后续 `engine.py` 复杂度过高，再按职责拆分模块。

旧的 `scripts/validate_nbd_cli.py` 可作为兼容入口，但不再继续加入 NBD 专属硬编码。

## 14. 标准输出目录

```text
validation/nbd-runs/{run-id}/
  run.json
  batch.log
  nbd-results.json
  recall_matrix.json
  recall_matrix.md
  business-report.md
  prompts/
    NBD01-003.md
  raw-responses/
    NBD01-003.json
  items/
    NBD01-003/
      result.json
      summary.md
```

## 15. 验收标准

以当前物业管理服务文件作为第一基线：

1. 153 个 NBD 全量跑通。
2. 本地服务网点召回正式评分项和承诺函支持窗口。
3. 权重总和 NBD 召回完整评分大项，包括诚信 5。
4. 联合体 NBD 优先召回公告/资格要求，不被通用条款干扰。
5. 服务地点 NBD 能识别履约地点、项目位置、院区地址，不只依赖“服务地点”字样。
6. 货物类 NBD 不因服务期限误命中。
7. 候选窗口重复率明显下降。
8. `recall_matrix.md` 能解释每个候选窗口为什么被召回。
9. 真风险不丢，模板噪声下降。

## 16. 最终结论

当前阶段采用：

```text
NBD 自包含
+ CLI 通用候选窗口召回
+ 轻事实摘要防低级误报
+ 小模型按 NBD SOP 判断
```

不引入 NBD 专属 YAML，不建立第二套规则库，不把 CLI 写成规则引擎。

候选窗口质量是当前工程目标。
