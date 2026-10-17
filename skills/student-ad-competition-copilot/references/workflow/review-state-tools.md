# 当前集合与事件的操作入口

多轮修订、系列延展或恢复时按所需操作使用。本页所有`--manifest`、`--payload`、`--destination`、`--spec`、`--output`路径均相对`--run-dir`；Python和工具脚本使用环境中实际已成功的绝对路径。不要猜脚本名称，不重复探测已可用的解释器或安装无关库。

## 当前文件与审核摘要

运行[review_state.py](../../scripts/review_state.py)的`--action inspect`取得稳定JSON：`status`、`members`、`results`、`production_states`。不再假设内部validate_current返回dict；底层列表仍保留兼容。工具只核结构和源绑定，不认证画面审美或人工身份。概念门显式evidence引用另列ancillary_checks；旧hash不符时inspect为checked-with-warnings，统一运行检查会标失败。不能把源关系通过当全部文档一致，也不自动重绑旧证据追认通过。

```text
review_state.py --run-dir <运行根> --manifest <清单.json> --action inspect
review_state.py --run-dir <运行根> --manifest <清单.json> --action project --destination <新的快照目录>
```

project从合同的final_artifacts生成当前索引、审核摘要、交付成员与仅含当前图片的technical-inputs目录，供validate_submission的`--input-dir`使用，避免宽glob混入裁切/旧稿/格式副本。必要时`--payload`指定`{"final_artifacts":[真实当前引用],"series_plan":有效计划}`；原生源、渲染、主场景等仍按原合同提供，不能用文本准备对象充当像素。所有原路径仍相对同一运行根。

新快照内manifest.json最后写入，是可继续使用的入口；成功后后续操作使用工具返回的清单，不沿用根目录旧别名。失败没有完成入口时保留失败目录，另选新路径恢复。原清单、已认可图、旧合同均不覆盖。派生content_status不等于整体质量/交付通过，质量门与当前视觉检查仍须如实完成，工具不会自动填人审或将失败改pending。

生产候选的像素检查默认兼容旧规则，覆盖所有非取消请求的代表对象。恢复多轮生产而只检查当前请求时，可在运行清单显式设置`visual_review_request_ids`为实际当前请求ID；旧请求及回执保留，指定ID不得缺失、重复或已取消。它只选择生产代表审核范围，不豁免历史生产回执或扩大人审。交付候选始终覆盖全部final_artifacts，不读取此选择。不能为了消除错误随意换run_scope；完成生产、进入当前作品交付检查后才按实际阶段切换。

## 准备新的生产请求

`review_state.py --run-dir <运行根> --manifest <有效清单> --action request --payload <请求输入.json> --destination <新快照目录>`

输入为`{"request":{生产请求模板的实际字段},"input_paths":[实际运行内文件路径],"decision":{已有合同格式的真实生产授权决定}}`。request中不要另填input_files，由input_paths计算实际hash；无文件依赖时传空列表并在request说明no_file_inputs_reason。decision明确提供来源、原话、代表对象及范围，stage只能为production-authorization或representative，decision为pass；工具填production_request_sha256，不推断自然语言授权或扩大范围。来源、代表对象及品牌范围引用仍需真实hash，不能刷新旧hash掩盖变化。

输出保留旧合同、生成不可变production-request.json及新合同快照；请求ID、输入、输出路径、代表覆盖和来源须有效。新请求不能覆盖已有文件或预订其他请求输出。准备成功不是authorized或completed；下一步仍用新manifest做实际guard。同源新请求可复用已有授权，超出原文范围须由执行者核对。输入文件清单无法自动发现脚本隐含依赖，需如实提供。

## 真实事件与已有反馈

```text
review_state.py --run-dir <运行根> --manifest <清单.json> --action event --payload <事件输入.json> --destination <新快照目录>
review_state.py --run-dir <运行根> --manifest <清单.json> --action decision --payload <决定.json> --destination <新快照目录>
```

事件输入为`{"request_id":"实际请求ID","evidence":{"path":"宿主证据.json","sha256":"实际hash"}}`。先保存宿主实际返回/转录的紧凑投影，保留原来源；其call_id、state、occurred_at必须来自实际事件，saved还需实际outputs。明确秒/毫秒或ISO时间后可用execution_contract.normalize_event转换，缺失ID/时间保持未知，不造值。工具自动绑定请求hash、previous与production_events，重复同一证据不新增调用；不要写成lifecycle_events后声称验收已登记。

decision输入沿用review_contract已有决定对象，包括真实source、原文quote、checked_at、stage、decision、reviewed_artifacts以及适用时的具体请求hash。工具对同一源事件和相同范围幂等登记；不同成员可由同一真实事件覆盖。重叠且冲突的投影须依据原反馈明确阶段/范围，在新合同中协调并保留旧记录，不改时间伪造先后，不让用户机械批准同一件事。工具不判断自然语言“通过”覆盖哪些未展示作品。

started/running只恢复宿主返回的同一调用；returned仅表示返回，核实际输出后才saved。运行或失败依赖未完成，不调用后续裁切、拼版或交付。任何工具返回的实际文件清单优先于猜测文件名。

## 可见文字、视图及导出

### 完整稿无效返回与替代

仅用于当前完整稿核心独立返回自身违反返回约定的异常恢复；不改变八问、hint 真值一致性、独立原结论或常规审稿流程。输入声明重复、源图/诊断图像素不对应等输入失败不能作为作废理由。登记用真实返回协议校验报错；生产与统一检查仍按各自原有边界校验输入和像素，新替代另须完整输入/像素校验，不能借恢复入口新增历史稿通过要求。

1. 用 `review_state.py --action invalidate-core-return --payload <登记.json> --destination <新快照>`（仍带 `--run-dir`、`--manifest`）。输入 `{"assessment_id":"原审稿ID","validator_error":"校验器实际报错的原字符串"}`。工具先核验原输入、声明锁、独立身份、时间、固定 rubric 与原文件哈希，再真实执行返回校验，自动保存原 raw_return 路径/SHA256 和登记时间。有效但不利的结论、伪造报错及重复登记均拒绝。原 assessments 和原文件保持。
2. 新开空上下文独立会话，对同一成稿 SHA256 重新先盲读、冻结后对照，保存新的原返回和独立元数据。用同一工具 `--action replace-core-return`，输入 `{"assessment_id":"已登记无效ID","replacement":{新的完整assessment}}`，输出新的快照。必须能观察到新的会话/调用 ID，输入不得含旧结论；新盲读准备时间严格晚于无效登记。同稿原输入、render、锁定句均一致，不继承旧返回的用户确认。新返回若仍违规，保留该尝试并按其真实报错登记，期间守卫仍阻断，不能隐藏尝试。

每个成稿 SHA256 最多登记 2 条无效返回并各启动一次替代，第三次拒绝并停止，交用户决定。没有有效替代时不能继续派发。守卫、核心检查、统一检查及交付仅消费最新有效返回，无效原件与原因在 `invalid_returns`、原生检查的 `invalid_core_returns`、交接的同名字段可见。这里核验的是证据一致性，程序不能认证宿主声称的隔离身份或视觉判断。

用户对原稿的 reject/要求修改继续生效，不需先把该稿审成通过才能派发下一稿；后续派发仍须额度、A4、产品计划、实际输入、既有生产授权和 active 执行控制等全部原有守卫放行。包升级不会让旧检查器哈希自动变成新版回执；历史回执按原约定核验，不能补写或冒充当时放行。

[edit_svg_text.py](../../scripts/edit_svg_text.py)接受`--spec`：`{"source":{"path":"原.svg","sha256":"原hash"},"changes":[{"id":"准确text或tspan的ID","before":"原可见文字","after":"新文字"}]}`，以及新的`--output`。优先定位唯一ID的叶文字节点；若现有源仅有group ID，须另给零起始text_index和expected_text_nodes，精确定位组内叶文字并核对数量及原文，不能整组字符串替换。拒绝metadata、重复ID和预期文字不符；复杂文本/CSS/路径字使用原生编辑工具。结果为source-edited-render-required，必须从新源回渲染并看图，再更新当前集合。不能将源写入成功等同于画面完成。

[prepare_visual_views.py](../../scripts/prepare_visual_views.py)的`--source`指源文件，`--native`指已存在的PNG/JPEG等实际栅格渲染。`--crop LEFT,TOP,RIGHT,BOTTOM`是边界坐标；宽高数据使用显式`--crop-xywh LEFT,TOP,WIDTH,HEIGHT`，不自动猜测转换。stdout返回实际文件引用，细节路径从files/render_record读取，不猜detail-01。读取SVG或宿主大JSON时只投影ID、尺寸、hash、路径和需要的文字，不打印base64；截断部分继续定点读取，不能当已读。

[export_current_artwork.py](../../scripts/export_current_artwork.py)默认`--package-kind evidence`保留递归关联证据。面向作品交付可选`--package-kind current-files`，仅收当前图片、SVG、预览、主图与扫描到的本地依赖；输出明确不含完整审计证据，原运行仍保留。轻量模式只支持依赖已检查的SVG；不把它当可重验完整审核链的证据包。字体许可、重建脚本等非直接渲染依赖按实际交付需求另外收录，不能宣称扫描自动发现所有许可材料。任何模式均需复制后检查目标软件打开/回渲染及依赖，保留源PPI和位图文字编辑边界。


终局拒绝稿、旧包回执与新对照请求按[审稿恢复与运行升级](review-recovery.md)处理；原返回及独立判断不改写。
