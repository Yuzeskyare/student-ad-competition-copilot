# 标准生图入口与原选择承接

## 生产入口

本 Skill 的原生生图使用 `scripts/standard_production_entry.js`。该文件是可执行函数体，在同一次宿主调用内先让 `standard_production_entry.py` 用 `review_state.snapshot` 建立不可覆盖请求，再以独立进程实际运行本包 `guard_production.py`，成功后才调用宿主 `image_gen.imagegen`。不得拆成“读守卫说明→手工生图”，也不得在失败后直接调用原生工具重试。

配置只含 `python`、`skill`、`runDir`、`manifest`、`payload`、`snapshot` 六个路径；前三项为绝对路径，后三项为运行内相对路径。`payload` 沿用 review-state 的 request/input_paths/decision 结构；request 写入实际 `tool: image_gen.imagegen` 与 `parameters`。参数里的每个本地参考图必须同时列入 input_paths。不新增审批，沿用已有有效授权。

先只读本包 JS 文件内容，然后在 functions.exec 中直接执行：

```javascript
// source 为刚读取的本包 scripts/standard_production_entry.js 原文，不能改写函数体。
const result = await new Function('tools', 'config', source)(tools, config);
if (result.status === 'native-returned') generatedImage(result.generated);
else text({status:result.status, checked:result.checked, error:result.error, recovery:result.recovery});
```

同一个函数内部等待真实守卫完成；非零退出、超时、缺失或损坏返回、未授权回执均抛错，生图调用次数为零。提示词与参数只取守卫核对的请求，不接受调用处覆盖。其他宿主/工具尚无此适配时，停止受影响的生图步骤，不自行退回裸调；已有外部回传流程照常保留，不能冒称经此入口生成。

返回 checked 与 generated 后，仍按现有原生事件回填、实际产物 SHA 绑定和成图审核流程处理；“准备完成”或 native 工具成功不等于完成放行。`review_state --action project`、成图审核与正式交付继续要求 `verify_artwork_release`，缺少真实执行记录或本包有效完成放行的产物不能进入正式交付。不得给旧图补造历史放行。

原生参数沿用工具 schema：参考路径与最近图片数量允许缺省/null；本地路径须为绝对路径并绑定输入，最近图片数量如提供须为 1–5 的整数，transparent_background 如提供须为 boolean。非法参数在生成请求快照前拒绝；传入 null 不会改写成另一个提示词或参考机制。

守卫通过后、调用工具前，标准入口在运行内 `standard-dispatch-intents/` 原子创建按 run_id/request_id 唯一的派发意图。换 snapshot、重启调用或并发也不能再次派发同一请求。意图只说明已预留一次派发，native_execution 保持 unknown，不能冒称工具已开始、失败、完成或正式放行；它不是生产回执。

工具抛错时返回 `native-result-unknown`，保留 checked.manifest、checked.receipt、checked.dispatch_intent 与错误。停止自动重试，从该新 manifest 及宿主真实事件核对执行结果；不能删除意图、沿旧 manifest 换目录或换 request ID 逃过恢复。若实际事件证明已完成，绑定真实产物继续原放行流程；若原生事件明确为 failed，使用同一 codex-desktop-imagegen-v1 适配器，核对原调用参数、nonce、intent、call ID 和生命周期时间；失败终态不得声明保存输出。确认后保留旧记录，在新状态链登记新请求与输出路径，沿用仍适用的已有授权。只有作者声明“未执行”、工具抛错或缺少终态时仍保持未知，不能用取消记录替代真实终态。缺证据时保持未知，不补造 started/failed 事件。进程在返回前中断时，重复入口的 blocked 返回也会给出已有意图和可读取的 checked 信息，供恢复而非重新生图。

边界：此入口保证标准路径先检查再调用；Skill 文本和脚本不能撤销宿主仍暴露的原生工具权限，不能声称所有直接调用在技术上均不可发生。无需服务、密钥代理或全局 hook。

平面请求的 `production_stage` 由 AI 根据实际工作填写：`artwork`（缺省值）检查命题证据、方向区分和视觉关系原型前置门；`prototype` 只用于原型门尚未完成时的原型生成；`prototype-repair` 只用于已有原型门失败后的修复。后两者仍检查命题和方向前置门，其输出只能用于原型审核或后续生产输入，不能直接进入正式成稿审核、采用或交付。原型通过后以新 `artwork` 请求继续；成图后审核不提前要求完成，现有主观提示规则不变。脚本不根据提示词或文件名推断阶段。

## 已明确选择的记录承接

已有“选 A”等明确选择，原候选和原句都未改变，但旧探索记录未形成正式选择链时，使用 `direction_change_contract.py` 的 `recover-selection` 事件；保留 source/quote/decided_at/previous_manifest，并新增 `selection_recovery` 的 SHA 引用。不是用户提供新创意，不重复要求用户选一次。

承接文件包含 candidate_id、label、basis_type、candidates、choice_list_source、mapping_quote、author_notes、exploratory_review、native_user_event、recovered_at 和 interpretation。既有表格路径保持原格式及校验不变。原生用户事件必须与原用户消息、ID、原文和实际时间一致。

标题和段落的旧清单使用 prose_projection：AI 阅读完整原展示、原用户话语和上下文，保留明确选定的方向，以当前时间编制用于正式检查的投影；投影不是历史原句，可纳入用户授权后当前编制并逐项绑定的具体文案，不得冒称历史原文。choice_list_source 是实际展示的完整原文，prose_projection.native_choice_event 是对应完整原生 assistant 消息的 SHA 引用，文本须完全相同且展示时间不晚于用户选择。mapping_quote 是所选原始标题及段落的完整连续摘录，source_quotes 为映射范围内逐字且唯一的支持摘录。候选映射由本次 AI 建立，不冒称历史原表，记录唯一 id、statement（等于 mapping_quote）、starting_point（当前合同类别）、starting_point_quote（原文摘录）。ID、标签、原句、依据与当前投影的语义对应由 AI 审查；脚本只验证精确引用、唯一性、结构、时间和哈希。

prose_projection 字段为 actor=assistant、candidate（direction_id、statement、basis_type、basis，满足现行单句合同）、source_quotes（数组）、recorded_at（真实当前编制时间）、native_choice_event（path/sha256）、details（数组，可为空）。每个详情含 source（path/sha256）、quote、recorded_at；来源须在 interpretation.context 中，引用逐字唯一，详情记录时间晚于用户选择且不晚于投影时间，并明确是当前制作细化。basis_type 与承接文件一致。投影记录须晚于用户选择且不晚于本次正式审核输入准备时间；recovered_at 须晚于该审核真实返回，不能回填过去。interpretation 仍包含 actor、source、context、decision、label、candidate_id、scope_note、recorded_at；context 须绑定完整原清单，记录当前解释并保留原选择，不能用脚本猜用户意图。

若旧探索从未形成正式方向采用，previous_manifest 是同一 run 和合同的当前基线，不能含虚构的 direction_adoption；previous_adoptions 为空。它不是历史通过证据，当前方法检索使用真实记录、不得冒充历史检索，正式独立检查、提示清单、claim lock 和后续生产守卫照常执行。已有正式采用的普通变更与旧表格恢复路径继续验证其完整历史。blind bundle 的 origin 使用当前 AI 对原方向的 starting_point 分类、method_id=null，不伪造方法来源。

`version-migration-choice-carryover` 只适用于正式 Skill 版本迁移且选择记录为 `user-choice-carryover` 的情况。`recover-selection` 是既有选择的来源承接，不是版本迁移；该检查应记为不适用，不能伪造迁移材料或标记通过。发生正式版本迁移时，仍按现有 carryover 守卫核验版本、原选择、原句和新的审核。

原始引用、事件时间、哈希或候选映射不一致即拒绝承接。正式检查产生需明确 override 的硬失败时，不得将旧选择冒充对新判断的知情覆盖；主观提示不升级为硬拦。脚本的通过不证明 AI 语义解释正确，也不授予生图、安装或发布权限。排序与主观审核规则不变。

## 原生调用与完成证据绑定

标准入口为每个新请求生成唯一 dispatch_nonce，把追踪元数据附在实际 prompt 末尾。content_parameters 精确恢复创意提示。完成绑定从原生日志核对 call_id、实际参数、不可变请求、标准意图、守卫回执、会话、时间及输出字节。同一调用只绑定一个请求。

有原生 function_call 时，按既有规则逐项核对其参数。桌面标准入口只留下 Extension 完成事件时，适配器可以用该事件中实际保存的参数建立绑定。revisedPrompt 须与守卫核对的完整 prompt（含 nonce）逐字一致。inputImages 须按顺序对应已绑定的本地参考图路径和哈希，并核对透明背景及本次所有支持的参数。最近会话图片、无法核对的参数、缺失字段或不一致的证据保持 unknown 及互斥。新增核验记录按当前时间保存，引用原生事件及实际发生时间，保留历史记录。

文案和营销策划的正式dispatch同样执行现有概念前置门；类别关闭、前置hard失败或策划视觉能力未解决时不会执行生产。前置检查不要求尚未产生的成稿/终审材料，正常修订可保留未通过的后续门。concept-only仅作准备，不能据此授权完整生产。

未知原生imagegen调用也不能通过取消记录解除互斥：当前没有可核验的原生“未执行”事件适配器，普通JSON中的executed=false/host_event_id不算证明。真实取消意图仍保留并停止后续工作，但不能据此断言宿主未执行、换ID重试或补造历史完成。只有与原intent核验成功的终态才能关闭未知调用。
