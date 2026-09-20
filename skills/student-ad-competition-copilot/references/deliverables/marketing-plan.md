# 营销策划交付规范

本文件只负责策划案文件、页面角色、manifest和技术提交接口。策略与生产读取[策划Playbook](../tracks/marketing-plan/playbook.md)，人工关读取[质量门](../tracks/marketing-plan/quality-gates.json)，赛事规格读取`references/competitions/marketing-plan-profiles.json`。

## 赛事交付形态

| 赛事 | 当前通用交付快照 | 页数口径 |
| --- | --- | --- |
| 大广赛`F 策划案类` | 单个PDF，16:9或A4，100MB以内 | 正文最多30页，封面和封底计入；附件最多10页 |
| 学院奖`策划类` | A4逐页JPG，300dpi、RGB、单页20MB以内 | 正文与附录合计10–30页；封面、封底、目录不计 |

具体命题必须建立`marketing-plan-brief-constraints.json`，可收窄通用范围，不能静默扩大。PPTX是可编辑母版；PDF和逐页JPG是赛事导出，不代替原生表格、品牌屋、路线、预算与KPI对象。

`marketing-plan-run-manifest.json`必须记录`visual_generation_capability`。没有可调用生图能力时，只有用户明确接受并记录受限模式才可继续`concept-only`研究、策略与线框；`production-candidate`和`delivery-candidate`必须为`available`且操作包含`generate`，不能用占位图或纯排版冒充高保真策划生产。

五页样稿和整本`content_pass`必须通过反卡片化人工检查：页面结构由数据、因果、流程、空间、时间、对比或视觉任务决定，不能把网页卡片、仪表盘和重复圆角容器当作统一模板；真实界面/物件或内容关系需要的局部例外须有理由与评审证据。

## 页面与交付manifest

`marketing-plan-delivery-manifest.json`符合[交付Schema](../schemas/marketing-plan-delivery-manifest.schema.json)，按最终顺序记录：

- `sequence`、相对`artifact`路径和PDF内部`page_number`；
- `role`：`cover`、`toc`、`body`、`appendix`或`back-cover`；
- `section_id`、文件哈希与赛事所需提交字段；
- 证据登记、权利清单、预算/KPI契约、AIGC使用声明与使用时的记录路径。

大广赛正文与附件分别计数；学院奖只把`body`与`appendix`计入10–30页。学院奖另准备策划书摘要、核心主张、目标人群、核心传播场景与媒介、创意亮点阐述，并在真实提交时按平台当前字符限制复核。

外部数据或事实进入证据登记；第三方图片、字体、音乐、视频、数据集与合作方名称进入权利清单。预算算术、KPI字段和引用路径可机器检查，但报价真实性、指标合理性、授权有效性和洞察质量仍由人工判断。

## 技术验证

```powershell
& "<workspace-python>" scripts/validate_marketing_plan.py --self-check
& "<workspace-python>" scripts/validate_marketing_plan.py --competition <赛事> --input-dir <交付目录> --delivery-manifest <清单.json> --brief-constraints <约束.json> --output <结果.json>
& "<workspace-python>" scripts/validate_marketing_plan_run.py --run-dir <运行目录> --output <运行验收.json>
```

机器不判断研究能否支持洞察、策略是否专业、创意是否品牌独占、活动能否落地或视觉是否优秀。真实投稿另使用[投稿就绪合同](../schemas/submission-readiness.schema.json)，复核当前规则、权利、引用、AI记录、报名字段、最终导出、上传和回执。
