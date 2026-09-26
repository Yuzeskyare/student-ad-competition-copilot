# 广告文案交付规范

默认完成边界：交付作品。当前赛事规则、实际提交规格与外部研究引用在完成前核对；素材/字体使用依据、AIGC后台记录及平台申报仅完成后提醒，报名身份、上传和回执不阻断作品完成。
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
- `ad-copy-run-manifest.json`符合[运行Schema](../schemas/ad-copy-run-manifest.schema.json)，连接实际通过内部筛选的1–5份候选（challenge模式可只保留稳定稿、0份新稿）、入选稿哈希、命题约束、人工评审、质量门、AIGC使用声明、必要记录、技术结果和运行状态。声明为`no`时不要求空白记录。
- `slogan`与`short-copy`必须有独立声音/朗读记录；其他子类型可按质量门说明豁免声音门，但自然语言检查仍不可省略。

## 技术验证

命令中的解释器占位符、路径和不同 shell 写法见[统一执行约定](../workflow/image-tool-adaptation.md#python-与命令执行约定)。

```powershell
& "<workspace-python>" scripts/validate_ad_copy.py --self-check
# 未使用AIGC时，不需要创建空记录。
& "<workspace-python>" scripts/validate_ad_copy.py --competition <赛事> --subtype <子类型> --input <文案.txt> --brief-constraints <约束.json> --aigc-used no --output <结果.json>
# 已有AIGC记录可随附；缺失时只作交付后提醒。
& "<workspace-python>" scripts/validate_ad_copy.py --competition <赛事> --subtype <子类型> --input <文案.txt> --brief-constraints <约束.json> --aigc-used yes --aigc-record <AI记录.json> --output <结果.json>
& "<workspace-python>" scripts/validate_ad_copy_run.py --run-dir <运行目录> --output <运行验收.json>
```

AIGC使用情况与后台记录仅作为交付后提醒；记录缺失、未知或平台未申报不使技术验证失败，不阻断已批准文案交付。可以提供真实已有记录，不为填字段补造记录，也不把制作说明写入口号或创意解说。

投稿就绪记录中的证据路径统一相对于该次验证的`--run-dir`。尚未取得的证据可保留`null`和开放状态；一旦填写路径，即使对应事项仍为`incomplete`也必须可解析。`--self-check`仅检查工具自身能力声明，不代替对实际记录的校验。

机器不判断语义、事实暗示、品牌归属、自然度、原创性或法律结论。作品交付前使用交付证据合同核对当前赛事规则、实际提交规格与外部研究引用。素材/字体使用依据与AIGC/平台申报在完成后提醒；报名、上传、回执不在默认范围。

## 新运行的版本与审核绑定

新运行使用0.4.0运行清单，并执行[版本与审核合同](../workflow/version-bound-review.md)：生产调用前运行校验，绑定真实决定、作品哈希和覆盖范围；交付时核对最终对象与跨文件状态。已有明确生产授权直接复用，生产授权不能替代最终内容批准。旧清单保持历史口径，不能自动宣称通过新合同。

## 统一交付与恢复

按[交付与恢复入口](../workflow/delivery-and-recovery.md)运行三赛道统一验证，自动生成保守交接记录并按实际证据回填；以作品交付为完成边界；外部研究引用在完成作品前核对，素材/字体依据和AIGC/平台申报仅交付后提醒。
