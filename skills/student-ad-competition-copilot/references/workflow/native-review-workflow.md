# 原生审稿、系列确认与交付编排

新稿使用 `scripts/review_workflow.py`，不要手写内部 ID、快照路径和审稿时间。旧记录保留原字节和披露，不迁改独立原结论。以下命令均以 `--run-dir` 限定运行目录，`--payload` 是运行内 JSON。

## 盲读与固定对照

1. 用 `prepare_visual_views.py` 从实际渲染准备视图。`product-triptych --element-id <真实产品ID>` 返回 `record`（审稿投影）及 `author_record`（后台自查原件）。产品生产记录使用 author_record；交给检查者的元数据只用 record。投影精确白名单为图片引用、裁切/倍率、element_id、哈希；后台保存双向绑定。不得把 `_review-private`、作者 text_checks 或含作者结论的记录交给检查者。
2. `review_workflow.py --action prepare`，payload 为 `{row, author_session_id}`。row 来自当前完整稿的原生结构，包含 render_record、observed_image、official_product_asset、core_action、core_claim_sha256、direction_id、product_triptychs、required_brand_assets、proposition_message 等真实引用。程序分配唯一审稿 ID/目录、记录准备时间并输出盲读请求和图片输入。
3. 用空上下文检查者执行输出的固定盲读请求，保存原返回。`--action blind-save` 的 payload 为 `{state, host}`；二者都是 `{path,sha256}` 引用。host 是从实际宿主调度/返回记录导出的对象，恰含 checker_context、author_session_id、checker_session_id、invocation_id、started_at、completed_at、raw_return。缺真实身份/时间时保留失败，不能用本机观察时间补造。该文件的哈希证明输入一致，不能认证被整体伪造的宿主记录。
4. 程序冻结盲读，生成产品审稿投影，并返回固定对照请求和绑定的 `response_schema`。将该文件交给独立宿主的结构化输出参数；使用 `codex exec` 时传 `--output-schema`。当前宿主无法绑定 Schema 时，改用具备该能力的独立入口，或如实记录待审核。只传既定输入，不附作者说明。请求分别列出 product_scene、product_label 与本稿必需品牌资产的准确 element_ids；`required_brand_assets=[]` 时返回 `brand_asset_review=[]`。
5. `--action compare-save`，payload 为 `{state,host,manifest}`。接入层仅补齐缺失的固定哈希/产品元数据引用；已有冲突引用拒绝。原始返回保留，answers、observation、理由分类不改写，绑定副本和差异范围另存。原生 validate_return 验证通过后创建新 manifest 快照。无效返回沿现有 review_state 作废/替代入口办理，每张同图最多两次；不增加额度、不删除 adverse verdict。

复查已有同一版本成图时，`compare-verify` 使用相同 payload 与原生校验，另存本次独立审稿证据。当前审核选择、已有审稿和用户确认仍由原有入口管理。

错误回执给出字段、当前值、合法来源与失败恢复 token。若宿主只提供原始 rollout，应先从实际事件导出上述字段并保留原文件；本工具不凭作者声明认证宿主。每个阶段重新调用都自动分配新路径，已取消/失败的路径不复用。记录绑定成功不等于创意验收或用户最终批准。

## 整组方向一次确认

`series_workflow.py --action prepare` 的 payload 为 `{members:[{unit,manifest}],plan}`。plan 只放成员、顺序、方向/文案/机制与范围依据，不能带 status/progress/updated_at。members 顺序精确对应 plan.units。每个候选 manifest 先绑定实际独立方向 rounds、方法来源、choice_list 和待选方向；可尚无 selection_record/claim_lock，adopted_at 暂为准备时刻。程序对全部成员执行正常方向检查的选择前部分，不伪造用户选择。失败成员修正后才能提交整组，集中展示原句、全部原判断和风险。

实际用户看完后明确确认整组，由 AI 结合完整对话解释其范围，不要求复述原句。`--action confirm` 的 payload 为 `{batch_ref,source_ref,quote,overrides:[]}`，source_ref 绑定该真实消息，其 reviewed_batch 绑定已展示 batch_ref（含顺序和原句）；程序逐成员生成标准 user-choice 与 claim-lock，全部绑定同一消息/实际时刻，再执行完整正常方向校验。需 user_override 的项由 AI 确认用户对已展示原判断的知情选择并列入 overrides，不靠“知悉”或 risk 词面判断；已知硬拦与真实来源约束照常执行。用户自带方向沿既有 user-direction-change/provided-direction 来源登记，不能改成模型方法卡来源。

后续原句、文案、核心机制或成员范围发生实质变化，或出现新硬风险时，只对受影响成员重新检查和确认；未改变成员继续引用本批锁和原消息。普通进度更新不得重开整组。最终确切像素仍需既有真实最终批准，可一次整组批准。

方向推荐的补充展示用 `series_workflow.py --action recommend`，payload 为 `{manifest}`，manifest 是 `{path,sha256}` 引用。程序先校验绑定的真实方向记录，再从原输入、原返回和来源投影清单，不接受作者另外传入的候选与评分。并列保留传播清晰度、目的契合、新颖度、制作风险及原方向来源，未测项如实写未测；不从新颖度推算清晰度，不改原排序、已知反例硬拦和 user_override。

## 成图整组增量审核

本节落实已有 `print-ad.series-increment`，不新增创意分数、排序或每幅审批。生产前的方向确认与逐幅八问继续独立保留。只有首幅完成时继续制作其余授权成员；全组齐备后，实际并排查看全图与单幅，比较共同机制、真实变化、每幅新增信息。换构图不自动算增量，共同画风或影子手法也不自动算重复。模型/作者观察仅作预查，不能标成人工判断。

`series_workflow.py --action review-prepare` 的 payload 为 `{manifest,matrix}`，均为运行内 `{path,sha256}` 引用；入口从当前成员自动生成并排预览，返回记录中的 contact_sheet 用于展示。可选 contact_sheet 只接受与该确定性布局完全一致的既有预览。成员由现有 `current_assessment_ids` 按有效系列计划派生；明确部分交付沿原 scope selection 投影，不另建当前名单。contact_sheet 及 preview_build 绑定成员图像哈希、顺序和布局；所有消费者重算核对像素，单图、漏图、旧成员或手写关联字段不能替代全组预览。该核验不判断创意与同质化；matrix 的 `kind=series-invariant-variable-increment-matrix-v1`，含与派生成员完全一致的 `members`、`observer_type=author/independent-model`、逐成员 `observations:[{unit,visible_relation,increment,pixel_evidence,compared_with}]`；compared_with 列其他当前成员。`checks` 恰为 `shared-mechanism/real-variation/information-increment`，每项 `{status:supported/concern,observation}`。独立模型观察另绑定真实返回来源 `provenance`。可用 `series_review_contract.current_members` 取得准确绑定结构；不填虚构观察。

程序写出不可变 `print-series-evidence-v1` 记录、新质量门和清单快照，状态为整组待人工确认。展示真实全组及必要增量/重复提示，复用既有一次最终内容确认。`review-decide` 接收 `{manifest,source,quote,checks}`，source 为真实人类消息的绑定引用，导出的消息上下文须以 `reviewed_series` 指向已展示的 prepared review。用户无需输入哈希或后台字段；系统绑定实际展示范围。checks 使用同样三项，每项 `{passed:布尔,observation:真实判断及范围依据}`。不能把用户未判断的事项补为通过，不能将模型意见冒充人审；保留模型 concern，人类不同判断按真实来源登记，不改原返回。

每次登记均写新文件，不覆盖旧稿、旧门或旧决定。已有同版本完整整组记录直接复用；历史“通过”仍保留为当时认可，缺少比较记录不能追写为当时已完成新版审核。恢复后的新审核/内容通过/交付统一消费当前整组证据，删除修订字段不会降级放行。换图、有效成员范围或顺序变化须重新绑定整组；未变单幅的八问不重做。

系列回执状态由当前证据推导：成员未齐、整组未审、整组待确认、通过、失败或证据无效。自由 stage 文本不能升级状态。内容通过及最终交付使用同一检查；预查 concern 不自动变成 hard，真实人类判断的重复问题按既有系列门返回处理。机器验证覆盖、字节与来源关系，不认证人的身份或审美质量。

## 平面原型的制作输入与首图观察

选定面貌由[视觉制作笔记](../templates/visual-direction-note.template.md)承接方向卡，把方向里选定的具体面貌和画面关系写进笔记正文，通过下述 prepare 进入实际工具参数。首图作者观察对照这些要求和实际像素；笔记不送入匿名核心检查。

`scripts/prototype_workflow.py --action prepare` 的 payload 为 `{manifest,visual_direction,scene_prompt,references}`。前两项是 `{path,sha256}` 引用；visual_direction 是选定且已展示面貌的 UTF-8 笔记，scene_prompt 描述本稿场景，references 为 `[{role,file}]`，file 同样是绑定引用。程序校验现有方向采用记录，返回 `{prepared,prompt,inputs}`；系列 `series_plan.shared_art_direction` 非空且逐字进入 prompt。按工具入口实际提交返回的完整 prompt 与参考输入；准备不等于调用完成。

看过实际图像后运行 `--action observe`，payload 为 `{prepared,actual_request,artifact,observation,style_matches}`。prepared、actual_request、artifact 均为绑定引用；actual_request 是从实际工具参数保存的 JSON `{prompt,references:[{role,file}]}`，不能把准备内容另抄一份伪装实际提交。程序与准备内容逐字比对，绑定图像并再次校验当前方向。observation 按[风格兑现与创意表现](visual-style-direction.md#将风格落实到提示词和画面)分别写看图依据，并说明已有方向弱点在实际画面中的状态。style_matches 为严格布尔，只记录风格观察：false 返回 `needs-correction`，不据此扩展系列；true 返回 `style-observed`，只代表作者本次风格观察。创意表现仍按正文判断和既有确认流程处理。首图自动展示不等于完成复核。

两种风格观察均不决定系列生产许可；能否继续沿既有代表稿内容确认和真实授权判断。语义 claim_lock 与匿名独立检查保持原范围，面貌仅作制作侧输入。宿主原生事件可取得时沿既有事件机制保存；本地 JSON 不认证被整体捏造的实际请求，也不能阻止宿主绕过入口直调工具。不新增审美硬门、独立审核轮或风格禁令，完整稿和交付仍走既有检查。

## 进度、计时与唯一当前入口

`review_workflow.py --action status`：`{manifest,member,changes}`。manifest 是绑定引用；changes 仅允许 status/note/artifact/last_error，status 为 pending/in-progress/blocked/reviewed/completed。写到 manifest.artifacts.run_status 的 member_progress；不改 series_plan，也不授予质量门或交付通过。已有不可变计划内的 status 仅视作历史进度，不纳入实质计划比较；保留原计划原字节。

原生编排每次执行自动记录阶段开始/结束、失败耗时。额外阶段用 `timing-start` 的 `{stage,recovery_of?}` 和 `timing-end` 的 `{stage,token,outcome}`，outcome 为 passed/failed/cancelled，recovery_of 必须引用真实已记录失败 token。`timing-summary` 汇总阶段、失败和恢复耗时。只记录，不改判断，也不把等待都称为浪费。

每阶段用 `receipt` 写 `{manifest_path,stage,report?,handoff?}`。根 README 只链接 CURRENT.md；CURRENT.json 是唯一机器指针，CURRENT.md 显示同一当前清单。旧根说明先存 entry-history。stage=completed 必须原生 validate_run 得到 delivery_complete=true，需实际 handoff 时传其运行相对路径。`check-entry` 检查人可见入口与当前清单哈希一致；不得用根级状态覆盖分支历史。

现行平面单幅 `stage=awaiting-user-review` 写入前和 `check-entry` 读取时，从现有 `visual_review` 复用文字角色检查，核对广告主文案绑定当前完整稿的实际渲染。作者看图判断文案承担的作用，脚本核对角色与稿件引用。阶段用语和待补项按[阶段回执协议](user-stage-receipts.md#状态用语边界)记录。

## 小交付包与完整审计档

`export_current_artwork.py --package-kind user-delivery --handoff <原生交接记录>` 仅导出通过原生交付校验的当前成品、哈希索引和必要说明；完整 evidence 包继续单独保留，导出不发布/投稿。不能把未批准稿、拒绝稿或只过技术检查的稿放进 user-delivery。

桌面证据可用 `freeze_shared_evidence.py`，payload 为 `{bindings:[{binding,request}],destination}`：先用原生生命周期验证每份绑定，将相同 SHA256 的完整冻结 rollout 存一次，再为成员输出共享对象引用，最后重验每条新绑定。不同内容的累计日志不冒充同一对象。该版选择共享完整冻结日志，未实现裁剪最小事件包；不删除既有守卫依赖，不省略原图负载、事件或时间核验。完整审计导出保留私人绑定及原件以便投影复核。

共享日志可选传 shared_rollout 的冻结文件引用；每个原绑定先验证，再将指定共享原件逐调用重验。共享原件必须包含所有对应真实完成事件和原图负载，缺事件或错图仍拒绝。


整组确认以最后原子写入的 confirmed.json 为提交点。新 batch-v2 的所有成员必须绑定同一个 commit_path；整组全部校验及写入完成前，不得将任何部分 selection、claim lock 或 manifest 当作正式采用。后段校验、磁盘错误或中断留下的记录只供排查；消费者必须验证完整批次。历史成功批次只读兼容，不补写历史确认。

标准原生和本地生产共用 run/output_scope 派发登记，检查与登记在同一运行锁内完成。相同 request ID 仅派发一次；换 ID、输出路径或快照不能消除同一成员的未决派发。继续时恢复原 manifest，保留原请求及已绑定的真实 saved/failed 事件或本地终态回执；非原生调用若确认从未执行，既有取消记录必须另绑定 not_executed_evidence（原 request_sha256、dispatch_intent 路径与哈希、executed=false、实际 host_event_id 和 occurred_at）。仅写“已取消”不是未执行证据。未知原生imagegen当前没有可验证的未执行事件适配器，不能靠普通JSON取消摘要释放互斥；保留取消意图，但不得推断宿主未执行。不同且无依赖的成员仍可继续。工具返回未知时不编造成功、失败或取消；恢复已有证据，不要求用户重复原选择。

完成入口：`receipt(stage=completed)` 保存交接文件 SHA；`check-entry` 重新核验交接、报告和当前交付依赖。依赖失效即返回失败，不返回可用 completed；旧 completed 缺交接绑定时重新验证并写新回执，不补造旧记录。磁盘上的原回执保留为历史，读取方须执行 check-entry，不能直接把旧 stage 字符串当当前通过。
