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

## 真实事件与已有反馈

```text
review_state.py --run-dir <运行根> --manifest <清单.json> --action event --payload <事件输入.json> --destination <新快照目录>
review_state.py --run-dir <运行根> --manifest <清单.json> --action decision --payload <决定.json> --destination <新快照目录>
```

事件输入为`{"request_id":"实际请求ID","evidence":{"path":"宿主证据.json","sha256":"实际hash"}}`。先保存宿主实际返回/转录的紧凑投影，保留原来源；其call_id、state、occurred_at必须来自实际事件，saved还需实际outputs。明确秒/毫秒或ISO时间后可用execution_contract.normalize_event转换，缺失ID/时间保持未知，不造值。工具自动绑定请求hash、previous与production_events，重复同一证据不新增调用；不要写成lifecycle_events后声称验收已登记。

decision输入沿用review_contract已有决定对象，包括真实source、原文quote、checked_at、stage、decision、reviewed_artifacts以及适用时的具体请求hash。工具对同一源事件和相同范围幂等登记；不同成员可由同一真实事件覆盖。重叠且冲突的投影须依据原反馈明确阶段/范围，在新合同中协调并保留旧记录，不改时间伪造先后，不让用户机械批准同一件事。工具不判断自然语言“通过”覆盖哪些未展示作品。

started/running只恢复宿主返回的同一调用；returned仅表示返回，核实际输出后才saved。运行或失败依赖未完成，不调用后续裁切、拼版或交付。任何工具返回的实际文件清单优先于猜测文件名。

## 可见文字、视图及导出

[edit_svg_text.py](../../scripts/edit_svg_text.py)接受`--spec`：`{"source":{"path":"原.svg","sha256":"原hash"},"changes":[{"id":"准确text或tspan的ID","before":"原可见文字","after":"新文字"}]}`，以及新的`--output`。优先定位唯一ID的叶文字节点；若现有源仅有group ID，须另给零起始text_index和expected_text_nodes，精确定位组内叶文字并核对数量及原文，不能整组字符串替换。拒绝metadata、重复ID和预期文字不符；复杂文本/CSS/路径字使用原生编辑工具。结果为source-edited-render-required，必须从新源回渲染并看图，再更新当前集合。不能将源写入成功等同于画面完成。

[prepare_visual_views.py](../../scripts/prepare_visual_views.py)的`--source`指源文件，`--native`指已存在的PNG/JPEG等实际栅格渲染。`--crop LEFT,TOP,RIGHT,BOTTOM`是边界坐标；宽高数据使用显式`--crop-xywh LEFT,TOP,WIDTH,HEIGHT`，不自动猜测转换。stdout返回实际文件引用，细节路径从files/render_record读取，不猜detail-01。读取SVG或宿主大JSON时只投影ID、尺寸、hash、路径和需要的文字，不打印base64；截断部分继续定点读取，不能当已读。

[export_current_artwork.py](../../scripts/export_current_artwork.py)默认`--package-kind evidence`保留递归关联证据。面向作品交付可选`--package-kind current-files`，仅收当前图片、SVG、预览、主图与扫描到的本地依赖；输出明确不含完整审计证据，原运行仍保留。轻量模式只支持依赖已检查的SVG；不把它当可重验完整审核链的证据包。字体许可、重建脚本等非直接渲染依赖按实际交付需求另外收录，不能宣称扫描自动发现所有许可材料。任何模式均需复制后检查目标软件打开/回渲染及依赖，保留源PPI和位图文字编辑边界。
