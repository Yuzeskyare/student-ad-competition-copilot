# 平面广告交付规范

本文件只负责平面作品的文件、运行清单和技术提交接口。创作方法读取[平面Playbook](../tracks/print-ad/playbook.md)，人工关读取[质量门](../tracks/print-ad/quality-gates.json)，赛事规格读取`references/competitions/submission-profiles.json`。

## 交付范围

`print-ad-run-manifest.json`符合[平面运行Schema](../schemas/print-ad-run-manifest.schema.json)，并声明：

- `visual_generation_capability`：当前会话实际可调用的生图提供方、操作范围、检查依据与缺失时的用户决定；
- `concept-only`：命题、方向、概念门、质量门结果和运行状态；
- `production-candidate`：另含官方资产、生产来源、人工视觉、技术结果和`aigc_used`声明；仅当声明为`yes`时要求AIGC记录；
- `delivery-candidate`：再含最终交付manifest。

概念范围因官方资产缺失而正确停止，不等于运行损坏；但后续关必须保持`not-run`，不得宣称成稿或投稿就绪。
生图能力为`unavailable`或`unknown`时，只有用户明确接受并记录受限模式才可完成`concept-only`；生产和交付候选必须为`available`且操作包含`generate`。
`content_pass`还必须包含当前质量门中的反卡片化人工检查：无语义的网页卡片、UI面板、仪表盘或重复圆角容器不能作为通用构图骨架；有真实对象或内容关系依据的局部例外须留下理由与评审证据。

## 最终文件

- 只把实际参赛作品计入数量；联系表、盲测板、预览图和过程图不得混入提交集合。
- 格式、像素、方向、分辨率、色彩模式、大小和系列数量以当前赛事profile与命题为准。
- 最终产品、Logo、包装和强制文字可追溯到官方素材；中文、数字与精确版式使用确定性对象。
- 交付manifest逐文件记录相对路径、SHA-256、尺寸、格式、模式、DPI、字节数与作品角色。
- 用`aigc_used: yes|no|unknown`声明生成式AI使用情况。使用时保存工具、可获得的模型信息、关键交互、生成层、初始/否决输出、人工合成与修改记录；未使用时不要求空白记录；交付候选不得保留`unknown`。精确模型标识不可得时不得猜测。

## 技术验证

```powershell
& "<workspace-python>" scripts/validate_submission.py --self-check
& "<workspace-python>" scripts/validate_submission.py --competition <赛事> --input-dir <成稿目录> --include <实际作品glob> --aigc-used <yes|no|unknown> [--aigc-record <记录>] --output <结果.json>
& "<workspace-python>" scripts/validate_print_ad_run.py --run-dir <运行目录> --output <运行验收.json>
```

机器结果只证明文件规格、路径、哈希和记录完整性。真实投稿另建立[投稿就绪合同](../schemas/submission-readiness.schema.json)，复核当前规则、报名字段、素材与字体权利、AIGC要求、真实上传及回执。
