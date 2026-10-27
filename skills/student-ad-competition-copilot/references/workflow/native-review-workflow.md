# 原生审稿、系列确认与交付编排

新稿使用 `scripts/review_workflow.py`，不要手写内部 ID、快照路径和审稿时间。旧记录保留原字节和披露，不迁改独立原结论。以下命令均以 `--run-dir` 限定运行目录，`--payload` 是运行内 JSON。

## 盲读与固定对照

1. 用 `prepare_visual_views.py` 从实际渲染准备视图。`product-triptych --element-id <真实产品ID>` 返回 `record`（审稿投影）及 `author_record`（后台自查原件）。产品生产记录使用 author_record；交给检查者的元数据只用 record。投影精确白名单为图片引用、裁切/倍率、element_id、哈希；后台保存双向绑定。不得把 `_review-private`、作者 text_checks 或含作者结论的记录交给检查者。
2. `review_workflow.py --action prepare`，payload 为 `{row, author_session_id}`。row 来自当前完整稿的原生结构，包含 render_record、observed_image、official_product_asset、core_action、core_claim_sha256、direction_id、product_triptychs、required_brand_assets、proposition_message 等真实引用。程序分配唯一审稿 ID/目录、记录准备时间并输出盲读请求和图片输入。
3. 用空上下文检查者执行输出的固定盲读请求，保存原返回。`--action blind-save` 的 payload 为 `{state, host}`；二者都是 `{path,sha256}` 引用。host 是从实际宿主调度/返回记录导出的对象，恰含 checker_context、author_session_id、checker_session_id、invocation_id、started_at、completed_at、raw_return。缺真实身份/时间时保留失败，不能用本机观察时间补造。该文件的哈希证明输入一致，不能认证被整体伪造的宿主记录。
4. 程序冻结盲读，生成仅含图片/裁切的产品审稿投影，输出固定对照请求。请求分别列出 product_scene、product_label 与本稿必需品牌资产的准确 element_ids；`required_brand_assets=[]` 明确要求 `brand_asset_review=[]`。正常多产品不能加入冗余品牌资产行。先完整保存盲读，再执行对照；投影阶段不重新写盲读。
5. `--action compare-save`，payload 为 `{state,host,manifest}`。接入层仅补齐缺失的固定哈希/产品元数据引用；已有冲突引用拒绝。原始返回保留，answers、observation、理由分类不改写，绑定副本和差异范围另存。原生 validate_return 验证通过后创建新 manifest 快照。无效返回沿现有 review_state 作废/替代入口办理，每张同图最多两次；不增加额度、不删除 adverse verdict。

错误回执给出字段、当前值、合法来源与失败恢复 token。若宿主只提供原始 rollout，应先从实际事件导出上述字段并保留原文件；本工具不凭作者声明认证宿主。每个阶段重新调用都自动分配新路径，已取消/失败的路径不复用。记录绑定成功不等于创意验收或用户最终批准。

## 整组方向一次确认

`series_workflow.py --action prepare` 的 payload 为 `{members:[{unit,manifest}],plan}`。plan 只放成员、顺序、方向/文案/机制与范围依据，不能带 status/progress/updated_at。members 顺序精确对应 plan.units。每个候选 manifest 先绑定实际独立方向 rounds、方法来源、choice_list 和待选方向；可尚无 selection_record/claim_lock，adopted_at 暂为准备时刻。程序对全部成员执行正常方向检查的选择前部分，不伪造用户选择。失败成员修正后才能提交整组，集中展示原句、全部原判断和风险。

实际用户看完后，一条消息按顺序逐行写 `unit | 原句` 并确认整组。`--action confirm` 的 payload 为 `{batch_ref,source_ref,quote,overrides:[]}`，source_ref 绑定该真实消息；程序逐成员生成标准 user-choice 与 claim-lock，全部绑定同一消息/实际时刻，再执行完整正常方向校验。需 user_override 的项必须在消息中明确知悉风险并列入 overrides；已知硬拦与真实来源约束照常执行。用户自带方向沿既有 user-direction-change/provided-direction 来源登记，不能改成模型方法卡来源。

后续原句、文案、核心机制或成员范围发生实质变化，或出现新硬风险时，只对受影响成员重新检查和确认；未改变成员继续引用本批锁和原消息。普通进度更新不得重开整组。最终确切像素仍需既有真实最终批准，可一次整组批准。

方向推荐的补充展示用 `series_workflow.py --action recommend`，payload 为 `{manifest}`，manifest 是 `{path,sha256}` 引用。程序先校验绑定的真实方向记录，再从原输入、原返回和来源投影清单，不接受作者另外传入的候选与评分。并列保留传播清晰度、目的契合、新颖度、制作风险及原方向来源，未测项如实写未测；不从新颖度推算清晰度，不改原排序、已知反例硬拦和 user_override。

## 平面原型的制作输入与首图观察

`scripts/prototype_workflow.py --action prepare` 的 payload 为 `{manifest,visual_direction,scene_prompt,references}`。前两项是 `{path,sha256}` 引用；visual_direction 是选定且已展示面貌的 UTF-8 笔记，scene_prompt 描述本稿场景，references 为 `[{role,file}]`，file 同样是绑定引用。程序校验现有方向采用记录，返回 `{prepared,prompt,inputs}`；系列 `series_plan.shared_art_direction` 非空且逐字进入 prompt。按工具入口实际提交返回的完整 prompt 与参考输入；准备不等于调用完成。

看过实际图像后运行 `--action observe`，payload 为 `{prepared,actual_request,artifact,observation,style_matches}`。prepared、actual_request、artifact 均为绑定引用；actual_request 是从实际工具参数保存的 JSON `{prompt,references:[{role,file}]}`，不能把准备内容另抄一份伪装实际提交。程序与准备内容逐字比对，绑定图像并再次校验当前方向。observation 写真实可见差异，style_matches 为严格布尔：false 返回 `needs-correction`，不据此扩展系列；true 返回 `style-observed`，只代表作者本次观察，不授予内容通过或用户批准。首图自动展示不等于完成复核。

两种风格观察均不决定系列生产许可；能否继续沿既有代表稿内容确认和真实授权判断。语义 claim_lock 与匿名独立检查保持原范围，面貌仅作制作侧输入。宿主原生事件可取得时沿既有事件机制保存；本地 JSON 不认证被整体捏造的实际请求，也不能阻止宿主绕过入口直调工具。不新增审美硬门、独立审核轮或风格禁令，完整稿和交付仍走既有检查。

## 进度、计时与唯一当前入口

`review_workflow.py --action status`：`{manifest,member,changes}`。manifest 是绑定引用；changes 仅允许 status/note/artifact/last_error，status 为 pending/in-progress/blocked/reviewed/completed。写到 manifest.artifacts.run_status 的 member_progress；不改 series_plan，也不授予质量门或交付通过。已有不可变计划内的 status 仅视作历史进度，不纳入实质计划比较；保留原计划原字节。

原生编排每次执行自动记录阶段开始/结束、失败耗时。额外阶段用 `timing-start` 的 `{stage,recovery_of?}` 和 `timing-end` 的 `{stage,token,outcome}`，outcome 为 passed/failed/cancelled，recovery_of 必须引用真实已记录失败 token。`timing-summary` 汇总阶段、失败和恢复耗时。只记录，不改判断，也不把等待都称为浪费。

每阶段用 `receipt` 写 `{manifest_path,stage,report?,handoff?}`。根 README 只链接 CURRENT.md；CURRENT.json 是唯一机器指针，CURRENT.md 显示同一当前清单。旧根说明先存 entry-history。stage=completed 必须原生 validate_run 得到 delivery_complete=true，需实际 handoff 时传其运行相对路径。`check-entry` 检查人可见入口与当前清单哈希一致；不得用根级状态覆盖分支历史。

## 小交付包与完整审计档

`export_current_artwork.py --package-kind user-delivery --handoff <原生交接记录>` 仅导出通过原生交付校验的当前成品、哈希索引和必要说明；完整 evidence 包继续单独保留，导出不发布/投稿。不能把未批准稿、拒绝稿或只过技术检查的稿放进 user-delivery。

桌面证据可用 `freeze_shared_evidence.py`，payload 为 `{bindings:[{binding,request}],destination}`：先用原生生命周期验证每份绑定，将相同 SHA256 的完整冻结 rollout 存一次，再为成员输出共享对象引用，最后重验每条新绑定。不同内容的累计日志不冒充同一对象。该版选择共享完整冻结日志，未实现裁剪最小事件包；不删除既有守卫依赖，不省略原图负载、事件或时间核验。完整审计导出保留私人绑定及原件以便投影复核。

共享日志可选传 shared_rollout 的冻结文件引用；每个原绑定先验证，再将指定共享原件逐调用重验。共享原件必须包含所有对应真实完成事件和原图负载，缺事件或错图仍拒绝。
