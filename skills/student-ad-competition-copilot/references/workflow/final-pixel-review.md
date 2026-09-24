# 最终像素与多尺度审核

平面和策划的0.4.0运行在`production-candidate`和`delivery-candidate`阶段，`artifacts.visual_review`指向[视觉证据模板](../templates/visual-review.template.json)。生产阶段覆盖请求中的代表样稿，交付阶段逐幅/逐页覆盖审核合同的全部最终对象。技术规格、反卡片检查和联系表不能替代最终像素判断。

## 从当前原生渲染生成审核视图

先用实际目标应用渲染当前文件，并保存工具/命令执行记录、应用版本和字体替代信息。PPT最终在PowerPoint交付时须包含PowerPoint原生复核；其他目标按实际应用记录。只有字体名合法、框在页内，或`native_font_rendering_verified=false`时，不得声称字体最终呈现通过。无法取得目标渲染时保存技术结果并保留视觉待审。

每幅/页记录单个`artifact`（path、sha256、version、一个unit），由确定性工具从原生PNG/JPEG生成缩略图和高风险区域裁切：

```powershell
& "<workspace-python-with-Pillow>" scripts/prepare_visual_views.py --run-dir <运行目录> --source <最终文件相对路径> --version <版本> --unit <幅号或页码> --native <原生渲染相对路径> --renderer <实际应用及版本> --execution-evidence <实际渲染执行记录> --target-renderer-verified --crop <左,上,右,下像素> --output-dir <新的审核视图目录>
```

只有实际验证了目标应用才加`--target-renderer-verified`。需要多处局部时重复`--crop`；默认2倍，通常150%—200%。缩略图检验阅读轴和小尺寸可读性，原尺寸看空间与画面关系，局部看字形、换行、标签归属、边缘及接触。裁切工具不会评定视觉质量。输出的`render-record.json`包含来源与哈希、实际renderer、执行证据和视图引用，放入该单元的`render_record`。

缩略图/裁切保存为PNG，校验器重新从当前native像素推导并比较，避免只有文件名更新、视图仍是旧版。原生渲染确实来自该作品，需要渲染执行证据支持；机器不认证执行记录或真人身份。

## 逐单元的可观察结论

每项观察保存`check`、`status: pass|not-applicable`、具体`observation`和对应`views` ID。发现缺陷保持fail/pending并修复，不能改字段求通过；不适用要说明画面中为何无该对象。下列基础检查覆盖当前单元：

| check | 看最终像素时回答的问题 |
|---|---|
| composition | 主阅读轴与空间关系是否清楚？ |
| occlusion | 实际字形/产品/人物是否互相遮挡？ |
| text-legibility | 缩略、全屏及局部是否清楚，是否出现孤字、标点行首、短尾或意外重叠？ |
| residue | 底图还有空白便签、伪字、幽灵对象、重复元素、修补接缝吗？原生文字移走后原承载面应同步清理 |
| frontstage-role | 每个可见元素给受众什么信息？删除后不损失判断的内部制作/评委操作说明应删除 |
| source-visibility | 外部研究与数据是否有适合评委阅读的脚注或可定位附录，单位是否完整？品牌与命题依据是否正确保留在后台，未变成前台制作说明？ |
| crop-safety | 是否切断脸、手、关节、视线、动作对象或群体关系？ |
| positive-art-direction | 除了避错，画面在层级、节奏、材质、品牌归属上具体好在哪里？ |

平面另做`visual-only-meaning`（遮标题仍可辨关系）、`three-second-recall`（记录观看者实际复述，不代填）、`visible-element-delete-test`（逐个可见元素的必要性）。策划另做`orientation-comparison`：在布局锁定前比较内容密度、图像横纵比和目标场景，再选择横竖版；比较记录可跨页复用，禁止把本案例横版推广成通用要求。

多段文字落在明暗变化的照片上时，先调整共同光区、负空间、统一渐变或构图；不要逐框套卡片。真实票券、界面、商品对象或有语义必要性的容器仍可使用，保留内容形态门规定的理由与评审。画布与源图比例不合时先重排、换图或有依据地扩展背景，再采用不会破坏动作关系的裁切。

## 文字与底图容器

`visible_elements`逐项清点原生及位图里的可见文字、内嵌标签、产品和其他元素，记录`id`、`kind`和面向受众的`role`。文字另记实际`text`。事实声明记`claim: true`，先区分来源角色，不能把“后台可追溯”一律变成“同页露出来源”：

- 品牌身份、官方产品事实、命题给定场景：`source_kind: brand-brief`、`citation_placement: backend`，`claim_scope`分别为`brand-identity`、`product-fact`、`brief-scenario`；保存`primary_source`及绑定哈希的`source_evidence`，不填`visible_source`。参赛前台不要写“来源：命题资料”“按赛题要求”等过程说明；品牌资料不能替代外部统计或效果证据。
- 外部论文、调研、统计或比较性数据：`source_kind: external-research`。适合短脚注时用`citation_placement: same-page`，记录`visible_source`、`primary_source`、`source_evidence`和当前`source_view`；适合研究附录时用`citation_placement: appendix`，另绑定确切附录页`citation_artifact`、其图像`citation_view`与评委可用的`reader_locator`，不能只有后台文件路径。未指定新字段的旧外部事实仍按同页脚注校验。

附录路径另用`citation_render_record`绑定同一当前作品中的确切附录页，`citation_view`必须属于该页当前渲染记录。引用服务于评委理解与核验，不展示内部命题解析、工具或审核流程。摘录完整单位与限定条件，不擅自加强比较。明确的赛事规则或用户要求另行保留为规则依据，不套用统一页脚模板。

每个文字对象都有`typography`记录：`element_id`、`detail_view`、`glyphs_complete`、`optical_alignment`、`actual_lines`、`max_lines`、`no_wrap`、`orphan_or_bad_break`。诗性短行可用`intentional_line_exception`给出`design_reason`和覆盖当前对象的真实内容`decision_id`；不把创作性断行一律误杀。孤字等默认问题只有实际观察成立才返工。

底图纸片、招牌、气泡等每个`embedded-label`另列`containers`：`element_id`、`container_bounds`、`safe_bounds`、`text_bounds`均用当前原生渲染像素坐标；另有`font_size`、`minimum_font_size`、`actual_lines`、`expected_lines`、`alignment`、`center_tolerance`、`semantic_anchor_verified`、`detail_view`。`text_bounds`记录可见字面占用，不以PPT对象矩形冒充字形范围。居中对齐计算字面中心与安全区中心之差；阈值、字号和行数按具体项目确定，不复用案例中的21pt或1pt。

发现一个同类对象失败，清点同页/同系列的全部同类对象；每张纸片分别测量，不能把同风格当成同尺寸。适配顺序是删无用字、精简、自然断行、调整容器内空间，最后才小调字号。禁止以小到难读、强描边、重阴影或移出承载面换取“不溢出”。

## 产品、生成几何与返工隔离

每个产品在`products`列出`element_id`、`official_asset`、`expected_count/actual_count`、`allowed_aspect_ratio/actual_aspect_ratio`、`allowed_relative_scale/actual_relative_scale`。允许区间在生产前依据官方轮廓与场景参照确定，不按生成错误反向放宽。分别记录`perspective`、`light-material`、`contact-shadow`、`occlusion`、`mechanism-role`、`official-label-fidelity`六项像素观察。

高保真场景优先通过实际generate/edit迭代空间关系；Logo、精确包装标签和强制图标使用可追溯官方资产或确定性合成。产品“出现了”不等于融入空间。镜头中的接触、尺度、光材、遮挡及创意作用同时成立，才可提交人工内容门。

用户已确认的区域在局部修复中冻结。整页未改可比较渲染哈希；局部保护在`preserved_regions`记录`before/after`图片引用和`bounds`，脚本比较该区域像素。允许变更的区域不要填为冻结区域；确需更改时先明确影响范围，重新审核受影响部分。

## 前后台语言与使用披露

创作母版、后台AIGC使用记录、报名平台披露分别保存。工具、提示词、版本号、制作流程和评委指令默认不进入前台。若官方当前规则明确要求作品内可见披露，在对应元素使用`role: required-disclosure`并绑定`rule_evidence`和`rule_quote`；这是规则驱动例外，不能一律删除。后台记录和平台申报没有完成时保持相应开放状态，不据此改写作品创意或宣称已投稿。

三赛道原有内容、技术及投稿状态继续独立。`final-pixel-evidence`通过只表示视图、测量和记录关系成立；最终内容通过仍依赖版本与范围一致的真实人工决定。
