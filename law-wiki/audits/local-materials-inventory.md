# local-materials-inventory

## 结论
- `raw/laws/` 当前承载 7 份本地法规 Word 原文，均已抽取为 `raw/sources/*-docx全文.txt`，并补入对应 `sources/` 页的 `raw_paths`。
- `raw/biz/` 当前承载 2 份业务检查表，均已抽取为 `raw/biz-extracted/*.md`，并建立 `biz-materials/` 页面。
- `raw/biz/` 与 `biz-materials/` 统一作为 C 类辅助材料，不进入 A 类 source 权威层。

## raw/laws
- `raw/laws/中华人民共和国政府采购法.docx` -> `raw/sources/中华人民共和国政府采购法-docx全文.txt` -> [[中华人民共和国政府采购法]]
- `raw/laws/中华人民共和国政府采购法实施条例.docx` -> `raw/sources/中华人民共和国政府采购法实施条例-docx全文.txt` -> [[中华人民共和国政府采购法实施条例]]
- `raw/laws/政府采购信息发布管理办法.docx` -> `raw/sources/政府采购信息发布管理办法-docx全文.txt` -> [[政府采购信息发布管理办法]]
- `raw/laws/政府采购框架协议采购方式管理暂行办法.docx` -> `raw/sources/政府采购框架协议采购方式管理暂行办法-docx全文.txt` -> [[政府采购框架协议采购方式管理暂行办法]]
- `raw/laws/政府采购货物和服务招标投标管理办法.docx` -> `raw/sources/政府采购货物和服务招标投标管理办法-docx全文.txt` -> [[政府采购货物和服务招标投标管理办法]]
- `raw/laws/政府采购质疑和投诉办法.docx` -> `raw/sources/政府采购质疑和投诉办法-docx全文.txt` -> [[政府采购质疑和投诉办法]]
- `raw/laws/政府采购非招标采购方式管理办法.docx` -> `raw/sources/政府采购非招标采购方式管理办法-docx全文.txt` -> [[政府采购非招标采购方式管理办法]]

## raw/biz
- `raw/biz/四川2023年关于政府采购文件典型问题预计处理0828.xlsx` -> `raw/biz-extracted/四川2023年关于政府采购文件典型问题预计处理0828.md` -> [[四川2023年政府采购文件典型问题清单]]
- `raw/biz/采购文件歧视条款检查点.xlsx` -> `raw/biz-extracted/采购文件歧视条款检查点.md` -> [[采购文件歧视条款检查点]]

## 后续治理
- 若继续拷贝法规原文到 `raw/laws/`，应同步抽取全文并补入对应 source 页。
- 若继续拷贝业务检查表到 `raw/biz/`，应同步生成 `raw/biz-extracted/` 和 `biz-materials/` 摘要页。
- 业务材料中的检查点如要进入 `wiki/findings/`，必须先回到 A 类来源或 B 类官方检查口径进行校正。

