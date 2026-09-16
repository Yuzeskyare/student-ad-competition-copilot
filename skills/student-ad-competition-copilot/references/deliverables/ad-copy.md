# 广告文案交付规范

本文件只负责纯文本文案的形态、计数、运行清单和技术提交接口。创作方法读取[文案Playbook](../tracks/ad-copy/playbook.md)，人工关读取[质量门](../tracks/ad-copy/quality-gates.json)，赛事规格读取`references/competitions/ad-copy-profiles.json`。

## 类别与工作子类型

- 大广赛`G 文案类`按当前profile与命题执行，通用快照为100–500内容字符，命题可进一步收窄。
- 学院奖`广告文案`只有在具体命题授权时进入本路径；未规定字数时使用`null`上下限和`not-specified`继续，不把内部工作子类型说成官方新增限制。
- 学院奖图文类不属于本纯文本路径。

每个命题建立符合[约束Schema](../schemas/ad-copy-brief-constraints.schema.json)的`brief-constraints.json`。规则冲突、类别未授权或核心主张无依据时停止；开放长度只产生边界提醒。

## 文件与清单

- 最终文案以UTF-8纯文本保存；系统文本框仍是赛事真实提交位置，TXT是可追溯工作载体。
- 使用`zh-copy-content-codepoints-v1`：UTF-8去BOM、换行统一、NFC归一化，统计非空白Unicode码点；中文、字母、数字和标点计入，空格与换行不计。
- 零宽字符、控制字符、首尾空白、HTML/Markdown图片、表格、字段式作者信息和不允许的emoji按profile处理。
- `ad-copy-run-manifest.json`符合[运行Schema](../schemas/ad-copy-run-manifest.schema.json)，连接3–5份候选、入选稿哈希、命题约束、人工评审、质量门、AIGC使用声明、必要记录、技术结果和运行状态。声明为`no`时不要求空白记录。
- `slogan`与`short-copy`必须有独立声音/朗读记录；其他子类型可按质量门说明豁免声音门，但自然语言检查仍不可省略。

## 技术验证

```powershell
& "<workspace-python>" scripts/validate_ad_copy.py --self-check
& "<workspace-python>" scripts/validate_ad_copy.py --competition <赛事> --subtype <子类型> --input <文案.txt> --brief-constraints <约束.json> --aigc-used <yes|no|unknown> --output <结果.json>
& "<workspace-python>" scripts/validate_ad_copy_run.py --run-dir <运行目录> --output <运行验收.json>
```

机器不判断语义、事实暗示、品牌归属、自然度、原创性或法律结论。真实投稿另使用[投稿就绪合同](../schemas/submission-readiness.schema.json)，复核当前规则、平台实际计数、权利、AI记录、报名字段、上传和回执。
