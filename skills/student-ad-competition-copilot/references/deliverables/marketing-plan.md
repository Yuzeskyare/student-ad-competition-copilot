# 营销策划交付规范

默认完成边界：交付作品。当前赛事规则、实际提交规格与外部研究引用在完成前核对；素材/字体使用依据、AIGC后台记录及平台申报仅完成后提醒，报名身份、上传和回执不阻断作品完成。
本文件只负责策划案文件、页面角色、manifest和技术提交接口。策略与生产读取[策划Playbook](../tracks/marketing-plan/playbook.md)，人工关读取[质量门](../tracks/marketing-plan/quality-gates.json)，赛事规格读取`references/competitions/marketing-plan-profiles.json`。

## 赛事交付形态

| 赛事 | 当前通用交付快照 | 页数口径 |
| --- | --- | --- |
| 大广赛`F 策划案类` | 单个PDF，16:9或A4，100MB以内 | 正文最多30页，封面和封底计入；附件最多10页 |
| 学院奖`策划类` | A4逐页JPG，300dpi、RGB、单页20MB以内 | 正文与附录合计10–30页；封面、封底、目录不计 |

具体命题必须建立`marketing-plan-brief-constraints.json`，可收窄通用范围，不能静默扩大。PPTX是可编辑母版；PDF和逐页JPG是赛事导出，不代替原生表格、品牌屋、路线、预算与KPI对象。

`marketing-plan-run-manifest.json`必须记录`visual_generation_capability`。直接生成或按前检协议核验的外部资产均可支持生产；等待回传不能宣称高保真样稿或整本完成。充分的资产不要求宿主虚报`available`，而以可选`external_supply`核对文件、哈希、覆盖范围和复核依据。明确接受受限模式时仍仅允许`concept-only`，不能用占位图冒充高保真策划生产。

五页样稿和整本`content_pass`必须通过反卡片化人工检查：页面结构由数据、因果、流程、空间、时间、对比或视觉任务决定，不能把无语义的网页卡片、仪表盘和重复圆角容器当作统一模板；有真实对象或内容关系依据的容器或完整真实界面须有语义范围、理由与评审证据，仅必要性不清楚时比较替代结构。

## 页面与交付manifest

`marketing-plan-delivery-manifest.json`符合[交付Schema](../schemas/marketing-plan-delivery-manifest.schema.json)，按最终顺序记录：

- `sequence`、相对`artifact`路径和PDF内部`page_number`；
- `role`：`cover`、`toc`、`body`、`appendix`或`back-cover`；
- `section_id`、文件哈希与赛事所需提交字段；
- 外部研究引用登记、预算/KPI契约；素材/字体使用依据与AIGC记录/平台申报在交付后提醒。

大广赛正文与附件分别计数；学院奖只把`body`与`appendix`计入10–30页。学院奖另准备策划书摘要、核心主张、目标人群、核心传播场景与媒介、创意亮点阐述，并在真实提交时按平台当前字符限制复核。

外部数据或事实进入证据登记；第三方图片、字体、音乐、视频、数据集与合作方名称进入权利清单。预算算术、KPI字段和引用路径可机器检查，但报价真实性、指标合理性、授权有效性和洞察质量仍由人工判断。

## 技术验证

命令中的解释器占位符、路径和不同 shell 写法见[统一执行约定](../workflow/image-tool-adaptation.md#python-与命令执行约定)。

```powershell
& "<workspace-python>" scripts/validate_marketing_plan.py --self-check
& "<workspace-python>" scripts/validate_marketing_plan.py --competition <赛事> --input-dir <交付目录> --delivery-manifest <清单.json> --brief-constraints <约束.json> --output <结果.json>
& "<workspace-python>" scripts/validate_marketing_plan_run.py --run-dir <运行目录> --output <运行验收.json>
```

当前完整交付的`artifacts.technical_validation`指向聚合报告，不能把导出报告直接当作PPTX报告：

1. 用当前可用的演示文稿工具打开/渲染实际PPTX，并导出实际PDF/JPG。导出时保存`presentation-export-record-v1`：`source`为母版path+sha256，`outputs`为本次实际导出文件path+sha256数组，`producer`为实际应用/命令说明，`completed_at`为实际完成时间。不得把另一份导出回填为当前母版产物。
2. 使用现有演示文稿检查工具目录（包含下述三个脚本）检查母版。此目录由宿主依赖清单取得，不硬编码个人路径；缺工具则说明技术检查未完成，不虚构报告。
3. 用上面的赛事命令检查导出，再运行聚合命令；所有相对路径以运行目录为基准，导出目录及约束文件也须在该目录内。

```powershell
& "<workspace-python>" scripts/validate_marketing_native.py --input <母版.pptx> --presentation-tools <现有演示工具目录> --output <母版技术报告.json>
& "<workspace-python>" scripts/bind_marketing_reports.py --run-dir <运行目录> --source <母版相对路径.pptx> --native-report <母版技术报告.json> --export-report <赛事导出技术报告.json> --export-record <实际导出记录.json> --output <聚合技术报告.json>
```

母版包装器调用现有`inspect_presentation_package_integrity.py`、`inspect_presentation_layout_geometry.py`、`native_table_arithmetic_gate.py`，绑定真实输入及工具摘要。它检查结构、几何与表格算术，不替代实际渲染、字体呈现或AI内容/视觉审核。聚合报告同时核对两类报告及源/导出对应关系；原有母版报告读取仍保留供历史合同使用，新完整交付不得省略导出检查。

机器不判断研究能否支持洞察、策略是否专业、创意是否品牌独占、活动能否落地或视觉是否优秀。作品交付前使用交付证据合同核对当前赛事规则、实际提交规格与外部研究引用。素材/字体使用依据与AIGC/平台申报在完成后提醒；报名、上传、回执不在默认范围。

## 新运行的版本与审核绑定

新运行使用0.4.0运行清单，并执行[版本与审核合同](../workflow/version-bound-review.md)：生产调用前运行校验，绑定真实决定、作品哈希和覆盖范围；交付时核对最终对象与跨文件状态。已有明确生产授权直接复用，生产授权不能替代最终内容批准。旧清单保持历史口径，不能自动宣称通过新合同。

最终母版及其完整审稿范围须对应成功的 full-deck 生产输出；样页即使拥有完整人审记录，也不能作为全稿生产完成证据。已有内容可作为新请求输入，按仍有效的授权继续生产；不得给旧请求或回执补填阶段追认历史放行。失败尝试保留，当前最终文件仍须独立匹配成功输出。

## 最终像素证据

生产代表稿与最终交付必须执行[最终画面验收](../workflow/final-pixel-review.md)，绑定实际目标渲染与当前文件哈希，覆盖全部适用页面并主动核验关键内容；仅在看不清或有实际疑点时补局部视图和对象测量，不要求逐对象建档。保留有内容依据的设计例外。技术规格通过不能替代视觉判断。

## 统一交付与恢复

按[交付与恢复入口](../workflow/delivery-and-recovery.md)运行三赛道统一验证，自动生成保守交接记录并按实际证据回填；以作品交付为完成边界；外部研究引用在完成作品前核对，素材/字体依据和AIGC/平台申报仅交付后提醒。

赛事要求的作品摘要、核心主张、目标受众等属于作品内容与实际提交规格，交付前完成；报名身份、作者信息、平台账号等行政字段不作为作品交付条件。
