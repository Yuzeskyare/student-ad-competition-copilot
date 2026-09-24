# 版本、审核范围与稳定文案合同

用于三赛道的新运行及明确迁移的旧运行。运行清单使用`schema_version: 0.4.0`，`review_contract`指向运行目录内的[审核合同模板](../templates/review-contract.template.json)，结构见[Schema](../schemas/review-contract.schema.json)。旧清单仍按旧规则复测，但输出`legacy-not-verified`；历史通过不自动升级为本合同通过，不补造审核、时区或事件时间。

## 先保存真实决定，再计算状态

由模型维护后台记录，用户只看作品并给自然反馈。一个文件引用是`{path, sha256}`；作品引用另有`version`和非空`units`。路径相对运行目录，哈希为实际文件的SHA-256。`units`逐项列出实际看过的候选、系列成员或页码；策划页码使用`"1"`、`"2"`等字符串。旧文件保留为不可变快照，新版另存，禁止原地改写后沿用旧哈希。

每个决定含：`id`、`stage`（direction / representative / final / production-authorization）、`decision`（pass / reject）、`checked_at`、`source`、`quote`、`reviewed_artifacts`。`checked_at`使用原始事件带时区的时间；`source`引用保存的真实消息或评审记录，JSON含`actor_type: human`、`kind: user-message|human-review`、可回查的`event_id`、`occurred_at`和原文`text`，`quote`须为原文片段。相同时间的冲突决定先核对来源，不能用列表顺序取胜。

这些字段证明记录可追溯与未变化，不认证人类身份，也不证明审美质量。模型不得编造消息、事件ID、时间或把模拟评审写成真人；现有来源不足时保持pending并说明证据缺口。可以从可回查消息导出原文记录，不能把自己写的“审核通过”作为来源。测试中的合成消息只用于代码测试，不能用于真实作品验收。

同版本、同范围已有决定直接复用。代表样本通过只授权声明的后续生产；最终内容状态逐个作品单元取最新`final`决定：缺决定为pending，存在当前reject为fail，全部明确通过才为pass。批准后的实质修改只重开受影响版本与单元。`run-status.json`记录`content_review_status`和实际生效的`review_decision_ids`，必须与合同的`content_status`一致。技术、规则、权利和真实投稿状态单独保留。

## 生产前实际执行

高清、批量或全稿生产前保存一个请求JSON：`id`、`operation`、明确的`output_scope`、`representatives`作品引用；本地命令另含`command`字符串数组（不用shell）。代表内容通过或明确生产授权的决定，通过`production_request_sha256`绑定整个请求。请求的工具、提示、参数、输出范围或本地命令变化后重新核对，不能重用旧请求哈希。

用户已明确授权在本轮范围内继续生产时，使用`production-authorization`并引用原消息；不能因为Skill默认检查点再询问同一权限。该授权不等于看过成品或内容通过。源消息只有生产授权时`content_pass`仍为pending。

在**实际生产调用之前**运行（路径均按运行目录解释；`--output`须为新的回执文件）：

```powershell
& "<workspace-python>" scripts/guard_production.py --run-dir <运行目录> --manifest <赛道-run-manifest.json> --request-id <请求ID> --output 05-reviews/preproduction-001.json
```

外部生图/文档工具仅在返回authorized后立即调用，参数须与被绑定请求一致；不得隔着改稿复用回执。将回执的路径和哈希加入`production_receipts`。该脚本不能拦截任意外部工具，执行者必须按此入口调用；它也不替代资产、事实、权利或工具能力前检。

本地已获授权命令使用同一入口增加`--execute`：脚本在启动前重新读取并核对请求和决定，通过后才用无shell的子进程执行，记录是否执行、返回码和时间。拒绝时不运行命令。外部调用模式回执中的`executed: false`表示脚本未代调工具，不能声称生产成功。回执仅证明生产前校验，不证明文件质量或调用结果；产物仍须各自验证。

生产及交付范围必须有匹配请求的回执，最终补录的内容批准不能追认缺失的生产前校验。后续撤回会影响当前动作/内容状态，已发生的有效生产历史原样保留。

## 文案稳定基线与反馈

进入已有定稿的冲奖、局部修订或继续优化时，`revision_mode`设为`challenge`。先在`stable_copy`保存`artifact`、真实内容批准的`decision_id`，保持原稿可恢复。初创阶段沿用现有候选流程；挑战阶段可以只保留稳定稿，不为满足数量补造弱候选。

口号或短文案另保存`prosody_snapshot`引用。其JSON绑定`copy_sha256`，记录`syllables`（音节/节拍）、`pauses`、`stresses`、`rhyme`和`reading_evidence`文件引用。无押韵或无异常重读可明确写“无”，不能缺字段，也不能把未实际朗读写成已验证。机器只检查记录存在且绑定版本，实际声音判断仍由人或有来源的朗读证据支持。

已解决反馈放入`resolved_feedback`：每项有`id`、真实`source`与`quote`、`affected_artifact`、`layer`、`resolved_sha256`、`resolution_decision_id`、`reopen_trigger`。旧版问题只影响它指向的版本和层；批准解决后，后续默认继承解决状态。只有新版本出现对应可观察失败或明确新要求时才重开，并另记证据，不能反复拿旧反馈证明当前稿有同一问题。

挑战稿不直接覆盖基线。决定替换时保存`challenge`：`baseline_sha256`、`trigger_kind`（observed-failure / explicit-user-change / award-ceiling-review）、`trigger_evidence`、`comparison`和`replacement_decision_id`。对照JSON绑定`baseline_sha256`与`challenger_sha256`，分别写`clarity_delta`、`mechanism_delta`、`brand_delta`、`voice_delta`、`explanation_cost_delta`。增益不成立则保留基线；确需替换时，必须有晚于基线批准且覆盖新稿的最终内容决定。冲奖判断的创作准则另由文案Playbook处理，机器不能通过“字段齐全”评定增益成立。

## 最终对象与状态同步

文案交付先按命题在`brief_constraints`明确`creative_explanation_required`布尔值。`copy_delivery`含`copy`、需要时的`explanation`、最终`submission`三个作品引用，以及`submission_layout`。例如`[{"artifact":"copy"}, "\n\n", {"artifact":"explanation"}]`按顺序精确拼接；每个组成对象只能出现一次。实际投稿复制文本必须与拼接结果完全一致。无解说要求时可只包含正文。解说作为独立内容对象审核，更新正文后不能借旧哈希/旧批准交付。

合同`final_artifacts`恰好覆盖上述实际交付对象；`candidate_review.manual_content_review`的`status`、`review_decision_ids`与运行状态和合同一致。同范围仍有pending或内容边界时，不得写无条件pass；无关权利/平台边界放到相应状态，不能混进内容结论。

平面交付manifest增加`final_artifacts`作品引用数组，必须与合同中的最终集合完全相同。既有逐文件尺寸、DPI、格式、角色等记录继续保留，预览不混入实际参赛集合。策划合同绑定运行清单`final_artifact`的实际路径、哈希和全部`1..slide_count`页，五页样稿批准不能外推全稿。

`validate_ad_copy.py`只输出`content_review_assessment: not-performed-by-technical-validator`，不会把“不评内容”再写成项目待审状态。读取它的消费者使用该字段描述工具能力；实际内容状态只取上述决定链。三条赛道运行校验器会在0.4.0运行中核对本合同；任一来源、版本、范围、组成文本或状态冲突都使合同检查失败。
