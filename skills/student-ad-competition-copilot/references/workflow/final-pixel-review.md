# 最终画面验收

平面和策划的 0.4.0 运行通过 artifacts.visual_review 引用视觉证据。新记录用视觉协议 2.1.0；旧 1.0.0 / 2.0.0 按原合同验证，不静默改写历史结论。生产阶段覆盖代表稿，交付阶段覆盖全部最终页面。五页样稿和联系表不能外推为全稿通过。

## 默认检查与停止条件

阅读全文并查看每页最终画面，核对内容逻辑、阅读层级、字形与可读性、遮挡、残留、裁切和前后台语言。关键文字、品牌产品、核心数据和外部引用主动核验，不能等自动扫描报警后才检查。

全部范围已检查、关键内容与规格通过、影响交付的已知问题已解决，且交付版本与批准范围一致时完成。没有逐对象台账、固定数量裁切或历史生产前数值容差，不单独构成未完成；规则、关键事实、引用依据和未检查的页面仍须补齐。审美偏好和可选优化不自动触发返工。

检查器只核验证据关系，不能证明模型真的看过画面，不能认证视觉质量或人工身份。不得以机器通过替代真实内容判断。

### 判断方法与证据边界

平面新记录以 communication-clarity 代替 three-second-recall。通过时写 assessment_method：author-inspection 表示作者观察；user-acceptance 表示当前作品得到用户定性认可，另以 human_decision 引用同版本、同范围真实决定。作者观察不产生 content_pass，用户认可不表示做过计时、盲测或复述实验。该一般观察不能作为下方 print-core-v4 独立核心检查的通过依据。其余适用检查仍需记录，不能用同一句“通过”代替产品、字形、残留等独立观察。

可选 audience_tests 是文件引用数组（path、sha256）。每份实测记录含 artifact、method（timed-recall / untimed-comprehension）、prompt、blinded、responses（participant_id、response）和 source 原始记录引用；计时测试另有真实 exposure_seconds。没有进行就不建实测记录，不用“通过”补造受众回答。旧 three-second 字段的通过只按原始证据解释，不自动认证实验。

验收同时对照已选[视觉风格](visual-style-direction.md)：检查线条、造型、色彩、纹理、空间或密度等实际适用特征是否落在最终图像中，不能只凭提示词含风格名称判定成功。平面化、夸张、无摄影阴影或密集细节不自动失败；信息遮蔽、无意结构缺陷与品牌错误仍须修正。修复后复看关键风格特征，避免修得更像照片却偏离已选方向。

## 平面核心创意逐项检查

print-core-v4 在采用方向时保存 direction_adoption.claim_lock（$defs.core_claim_lock），statement 原样等于已采用方向的盲评一句话，statement_sha256=claim_digest(statement)。锁绑定 direction_id、adopted_at、blind_review。改声明必须回方向重新发散和盲评，previous_adoptions 最多1项；新bundle保存原首轮引用再追加新轮，与全部偏弱共用最多1次重新发散额度。旧失败稿引用旧锁，当前稿引用新采用锁，不能事后修改旧声明。方向锁须在渲染前形成。

每稿新增 direction_id、core_claim_sha256。对照记录 independent_core_check_v4 和原始返回 core_comparison_return_v4 都含 core_claim_sha256，必须等于该稿采用时锁定的 statement_sha256。盲读 blind_core_read_v2 的原始返回 blind_core_return_v2 新增 explanatory_devices 数组和 relation_without_devices；对照 comparison 新增逐字清单及 device_removal={blind_observation,relation_still_holds,observation}。去掉说明手段后产品关系不成立，第1/3/4问必须false，三项答案必须引用 explanatory_devices 与 device_removal。具体判据及超现实/速度线正反例见Playbook。


新平面运行使用 print-core-v4 / print-direction-v7 / print-product-v2 / print-ad.0.16.0；历史核心、方向及 print-ad.0.1.0—0.14.0 按原定义解析。每个完整稿（包括首稿、失败稿及每次返工/修订）由独立检查者查看实际图。五问及宿主优先路径见[平面 Playbook](../tracks/print-ad/playbook.md#独立核心检查与宿主路径)，作者自答不能作为新合同通过依据。

沿用 `core_creative_review.assessments`：每幅保存 id、artifact（path/hash/version/单个 unit）、render_record、observed_image（该渲染 native 视图）、official_product_asset、core_action（一句）、checked_at、assessment_method=independent-review、independent_check（独立记录 path/hash）与 answers。五项为 product_in_core_relation、action_depicted_without_copy、claimed_relation_depicted、creative_scene_not_generic、product_action_understood_in_three_seconds，分别给 boolean answer 和像素 observation；所有字段以 true 表示通过，第4原问“是否普通场景”答是时 creative_scene_not_generic=false。模板 null 是待查，不是通过。

同一 review 的 `completed_draft_render_records` 是完整稿渲染引用清单；稿完成即登记，必须与 assessments 的渲染一一对应，不另建审核台账。current_assessment_ids 覆盖 visual_review 的当前图与全部范围。已有完整稿即使 run_scope=concept-only 也检查；尚无成图的概念可省略。交付时现有 delivery_manifest 记录真实 `delivered_at`，所有独立检查及 checked_at 不得晚于它；未真正交付不提前虚填时间，缺时间不能验证为交付通过。

先盲读、后对照，沿用同一 assessment 和五问，不能另建一套通过结论。盲读只给成图；官方图也留到第二步。第一步在接收作者声明之前完成并保存：按像素写动作/变化（包括方向）、产品作用（看不出就写“看不出”）、所有可能两种读法的地方。图内标题文案不能代替像素动作。

independent_check 仍引用独立记录，现在是对照记录 `$defs.independent_core_check_v4`：沿用原字段，rubric_version=print-core-v4、checker_context=fresh-isolated，新增 blind_read（盲读记录path/sha256）。盲读 `$defs.blind_core_read_v2` 沿用相同身份、时间、inputs/request/raw_return字段，rubric_version=print-core-blind-v2，增加 input_prepared_at、saved_at、input_manifest_sha256。真实会话/调用标识不能与作者相同；宿主不提供则null且在unavailable_metadata逐项说明，不能伪造。第一步须全新隔离；第二步允许同一检查者继续或另一独立调用，每个新完整稿须新盲读调用。

盲读 inputs 精确一项 {role:artwork,file:{path,sha256}}，同 observed_image；input_manifest_sha256 为 inputs 数组按 UTF-8、ensure_ascii=False、sort_keys=True、separators=(',',':') 序列化的SHA256（脚本 blind_input_digest）。任何作者声明/说明或额外输入均无效。request绑定实际发送文本，严格等于 INDEPENDENT_BLIND_RUBRIC_V2；raw_return为原始JSON {action,product_role,ambiguities,explanatory_devices,relation_without_devices}，不能存作者摘要。时间为 render.created_at ≤ input_prepared_at ≤ started_at ≤ completed_at ≤ saved_at < 对照.started_at ≤ 对照.completed_at ≤ assessment.checked_at。saved_at必须是实际保存边界，不倒填时间。

对照 inputs 精确三项：artwork（同成图）、official-product-asset（同官方可读产品图）、core-action（UTF-8一句原文，同core_action），另以 blind_read 引用已冻结的第一步记录。实际request严格为 INDEPENDENT_COMPARE_RUBRIC_V4 + "\n核心动作/关系：" + core_action + "\n盲读记录SHA256：" + blind_read.sha256 + "\n锁定声明SHA256：" + core_claim_sha256。保存真实原始返回及hash：{blind_read_sha256,core_claim_sha256,comparison,answers}，结构见 `$defs.core_comparison_return_v4`。comparison逐一对照action、change_direction、product_role，各含matches布尔、blind_observation（逐字引用盲读action或product_role）、claim_observation；ambiguities与盲读原列表顺序/数量一致，逐项保存blind_ambiguity、affects_main_relation布尔、aspect、observation。产品角色/动作方向/接触/其他主关系用product-role/action-direction/contact/other-main，只有次要歧义用secondary。

动作、变化/因果方向、产品角色任一不一致，第3问必须false；盲读看不出产品作用，第1问必须false；主关系歧义使第5问必须false。次要歧义仅记录、不判失败。每个答案保留answer/像素observation，新增blind_read_sha256和非空comparison_evidence键清单（action/change_direction/product_role/ambiguities/explanatory_devices/device_removal），引用盲读和原始对照记录；主清单answers须与对照raw_return逐字一致。原五问及有意超现实允许、常规创意拒绝、三秒项未实测仅预测的边界保持。CLI事件可另保存，但原始返回是实际final message。不能用声明重写盲读，不能让作者替检查者补写判断。

任一归一 answer=false 即核心失败。保留原记录和原始返回，回到 direction 或 main-visual-generation 完整返工；排字、蒙版、裁切、页脚、字号、产品挪位等局部修整不能冲销。失败行 rework 沿用 kind=full-rebuild、return_to_stage、started_at/completed_at、relation_before/after、production_input、新 rebuilt_main_visual（path/hash）及 rechecked_assessment_id。新版本、新主图、新独立调用均必需；失败的新图继续完整返工链，末稿五项全 true 才解决。

校验核对结构、声明输入、原始返回一致性、顺序、字节与覆盖，不能认证宿主记录/时间真实性、官方资产权威或自动判断审美；无法发现作者完全未登记的未知稿件，也不能排除输入文件内部/图内夹带的恶意说明。因此运行时必须保持实际隔离并保留真实宿主证据，不能仅填字段冒充独立。历史认可不转移到新图。

## 当前渲染与视图

用实际目标应用导出最终画面，保存真实渲染执行记录、应用版本和字体替换情况。PowerPoint 交付需要目标应用复核；字体名合法、对象框在页内不能证明字形正常。无法取得必要画面时保留视觉待审。

使用 scripts/prepare_visual_views.py 的既有参数生成视图。只有实际验证目标应用后才加 --target-renderer-verified。默认生成原生视图引用与缩略图，不自动放大全页。普通阅读尺度看不清关键文字、瓶标、图表单位、边缘或修复效果时，用 --crop 左,上,右,下 生成必要细节，可重复指定。--full-page-detail 仅在确有需要或生成旧协议视图时使用。

每个 unit 保存 artifact（路径、哈希、版本、一个页码）、render_record、checks、critical_review、issues。提供的缩略和细节图继续做像素派生验证。没有细节图本身不失败，但必要放大未做不能通过。不得只更新文件名冒充当前画面。

正式visual_review从[现有模板](../templates/visual-review.template.json)构建，身份、run_scope与units绑定当前请求/作品；实际观察填入成员的checks、critical_review和issues，引用真实派生视图。自然语言报告可摘要这些记录，不把自建单artifact笔记映射为正式协议。旧观察复用前核对对象、覆盖和视图；自定义“通过但有限制”等文字不是新状态值，按实际证据使用协议现有状态，不能机械转pass。结构补齐不证明缺少的观察、引用或人审已完成。

## 先看当前合成，再记录观察

先依据实际图文描述最自然的理解，再核对预期表达；作者意图不是图中证据。明确核心误读或承诺的主关系/字图职责缺失时记fail并回到责任阶段实改，不能只修局部后带着已知缺陷推荐。关系清楚、艺术语言可辨与具体创意贡献分别判断；尚不确定的审美沿用既有代表稿判断。包装保真、线端接触、风格落图或自绘笔画只证明各自制作事实，不能覆盖关系失败。暂遮字只作诊断，完整图文可以共同成立；静态表达按实际核心关系检查；平面 print-core-v1 仍须逐项确认产品参与和承诺动作/关系在像素中可见，不能以静态为由豁免。

先取得当前版本目标渲染，从同一渲染派生视图；独立字稿只证明构形，不能代替背景上的阅读效果。按阅读路径扫读本稿实际存在的标题、支持句、场景词、产品信息、限定/提示及出处，包含位图字和路径字。按[文字用途](typography-direction.md)对应的阅读条件检查真实字面、细笔画/内白、间距、背景纹理/亮线、旋转透视、边缘距离与归属；疑点放大定位后回相应尺度确认。整幅缩略与原生细读互不替代，必要时约420px宽只作诊断，不是通用合规尺寸；系列还需并排比较。

看过相应文字与视图后才记录结论：observation可合并描述实际覆盖的文字组、区域与观看条件，issues定位具体失败，不新增逐字表格或固定裁切数。已观察失败记fail，未看保持待查；标题通过不代表全部key-text通过，局部检查不冒充整稿检查。内容正确、白字深底、OCR、源字号、导出DPI或视图存在均不单独证明可读。

修可读性保留已认可骨架，按成因选择动作：字面太小则增加实际字面并重排空间；细笔画或内白问题调整字重/字形和间距；纹理或亮线干扰先找安静落位，必要时在授权内处理局部背景；读序和归属问题调整分组与位置，场景变形问题调整角度及透视。保留必要限定、出处与已定文案；长引用预留可细读空间，不擅删条件。统一扩边可能堵复杂字，逐成员复核，不把加底板、阴影、压暗或全部加粗当通用答案。修后回看整幅及系列；增导出像素或DPI不改变同宽显示的字面。区分透明画布、alpha墨迹与允许修改区，不扩大窗口掩盖越界。

## 简短具体观察

checks 可用单个 check，或用 covers 将相关检查合并到一条观察。保存 status（pass 或 not-applicable）、具体 observation 和当前 views ID。不适用须说明原因，不用“全部正常”替代观察；失败或待查不能改字段求通过。

基础检查名沿用 composition、occlusion、text-legibility、residue、frontstage-role、source-visibility、crop-safety、positive-art-direction。组合记录减少重复文字，不减少实际范围。

平面保留 visual-only-meaning、communication-clarity、visible-element-delete-test；旧协议的 three-second-recall 仅按旧证据解释。观看者复述必须真实，不代填；元素必要性在画面层面判断，不逐对象建档。策划保留 orientation-comparison，方向依据可跨页复用，不要求已合理选择的版式重做横竖稿或补造历史实验。

critical_review 每页有三项：

| kind | 主动核验 |
|---|---|
| key-text | 标题及本稿存在的支持句、场景词、产品信息、限定/提示和出处；含生成字与路径字，按用途检查字形、换行、归属及实际阅读效果 |
| brand-product | 品牌、包装、瓶标、数量、比例、各处裁切缩放遮挡与场景融合 |
| data-citations | 核心数字、单位、限定条件、外部引用与正文主张对应 |

每项保存 status、具体 observation、views 和 detail_required，按实际说明通过或不适用。确需放大时 detail_required 为 true 并引用细节图，不能为省截图谎填 false。缩略图单独不能证明关键内容可读。适用的品牌/产品和数据/引用项用 evidence 引用既有路径与 SHA-256 依据，不重写事实总表。

品牌身份、官方产品事实和命题场景依据留后台，不写“来源：命题资料”等前台过程说明。外部研究与统计交付前完成完整对应，用适合评委阅读的脚注或可定位附录；data-citations 的 reader_locator 指明阅读入口，不能仅给后台路径。依据应能定位当前主张、原始出处和适用边界，不能用任意文件凑哈希。

同一官方资产的身份依据可以复用，各个位置的呈现仍逐页检查。生成包装不能因为存在参考图就宣称精确保真。数值测量仅用于实际疑点或明确规格，不倒推阈值迎合错误画面。创意母版不自动加入 AI、工具或制作过程标签；若投稿规则要求图内披露，记录规则与母版的区别，按用户明确要求另存投稿版本，不覆写母版。素材字体使用依据、后台 AIGC 记录和平台申报仍只是交付后提醒。

品牌核验同时检查命题明确要求的配套标识及其适用范围；一页出现过不能自动证明其他适用页面满足要求，也不能无依据扩展为所有页面必须重复标识。远景产品按实际展示尺度与源资产核验，不要求从不存在的像素读出全部包装微小文字；可见的品牌失真仍须修复，证据不足与已确认失真分开记录。

数据项区分外部观测、项目计算和规划假设。外部研究核对原始出处与阅读引用；预算计算核对公式、单位和明细，目标值核对假设标识与执行含义。不要为预算假设强索论文，也不要把计算正确当成真实报价或已实现效果。

## 问题触发复查

未发现问题时 issues 可为空。发现问题记录 id、problem、affected_scope 和真实 status；修复后记录 observation、views、detail_required，状态为 resolved。不得删掉未解决的问题来取得通过。需要数值判断时附 measurements：reason、unit、actual、minimum、maximum。底图容器适配查看实际字形，不能只凭对象框判断。

- 局部截断：检查同页及同类排版；反复出现则扩大范围。
- 字体、全局模板或渲染方式变化：复查全稿最终呈现。
- 产品失真：检查相关产品图，不同使用位置不能自动继承呈现通过。
- 引用或计算错误：检查同源与同一计算链涉及的主张。
- 局部修复：检查修改区域和受影响的相邻内容；影响不明时扩大复查。

已通过且有证据证明不受影响的部分复用结论。preserved_regions 可核验局部像素一致，但不能把未检查内容变成已检查，也不证明引用语义不变。首次接手旧稿整幅扫读明显继承缺陷，后续检查修改及影响区域：已授权的可读性修复直接做；明确锁定窗口外的问题记录并报告，不自行扩改或认证通过。完整交付不能用旧认可豁免已发现的必要文字失败。保留历史反馈，复用来源、版本和范围可追溯；不重复同版本人审，不为填记录反复改作品。

## 关系、载体与透明素材的复查

保真、可读与视觉关系成立分别判断：产品身份正确不代表参与机制；文字字形正确不代表沿真实纸面横线、透视或语义锚点对齐。实际看到接续生硬时检查根部、切线、宽度和整体动势；填满空隙、同源素材或提示词符合不是修复通过依据。局部补片失效时回到最近关系阶段重建受影响整段，不规定必须生图或强加摄影物理标准。

先理解官方包装的文字阅读方向，再按动作选择倾斜、透视或适度变形；比较朝向是诊断方法，不是横平竖直的硬规则。实际检查品牌/品类识别、镜像、遮挡和失真；原生尺寸核对关键文字，缩略尺度核对品牌与主体关系，不要求全部包装细字可读。检查整段连接与完整轮廓，包括重复端帽、残留生成产品和悬空接触；工具未落实落位要求时记录实际偏差，不能用提示词承诺代替像素。

排版先按限定条件、动作、数字与单位、完整词组的语义分组，再判断层级和间距。系列统一字体、色彩与传播逻辑，不强制行数、字高或底部齐平。必要时测量实际字形墨迹边界以发现碰撞，区别组内距与组间距；数学等距不是审美通过条件。字体子集收集最终实际文本及空白、标点（包括U+0020），并以真实渲染检查；失败与重试原样留档，渲染成功后仍看实际排版。

透明预览先在计划背景合成再判断；alpha为0的RGB颜色不可见，不能据此要求清理。纸口、产品与人物的接触边缘按实际疑点放大，不增加固定裁切数量或逐对象台账。pending／not-run观察填写待查原因并绑定当前视图；机器尚未核验的关键文字、品牌或数据项先完成独立检查，真实失败记fail及问题范围，不能改为pending。

主要文字还须按[文字设计](typography-direction.md)在实际画面中核对：字形或字组是否兑现本次具体动作、情绪或关系；字体本身的主题反馈是否真正改变字形而非只加图文互动，与图像形成何种读序、重心与留白关系。沿用已有observation、views和issues，描述看到的特征；字体名、转曲、OCR或字段完整不证明表达成立。辅助信息按上方用途与阅读条件检查，不强制艺术化；官方包装细字的缩略阅读边界不豁免广告另加的说明。未做手机或印刷验证如实保留边界。

## 合成、中文与系列字版的实际失败

再次编辑包含包装的场景时，复查需要保真的可见包装面是否被重新生成；合成保真与产品参与意义分别判断。主形、纤维边缘或毛刺增强后，复看相邻标题和整组留白，并判断问题与照顾分别从何处产生，避免柔软保护面反而长出尖刺等语义倒置。疑似丢Logo先核原图及单图显示，撤销不成立的诊断，不改正常像素。

来源hash正确、抠图干净、采样清晰、接触成立分别判断。透明预览疑似光晕先看alpha和计划底色合成；确认是假象就撤回错误观察，不做无用编辑。真实白边/matte残留再局部修。检查手指托接位置、透明瓶水体与瓶形、完整中文字笔画；源码有“净”或产品图来自原包不能代替看到完整字形。

旋转导致阶梯边时，在足够源分辨率上做适合素材的刚性变换并尽量只缩回一次；提高导出DPI不能补回源像素。替换材质后重新确认对象有没有变成帽子/台座等错误读法，实际发丝是否仍违背选定画风；提示词改了不表示像素改了。

保留真实失败及临时方案被后续反馈推翻的历史；可读性修复按上方成因和观看顺序复核，不以新说明覆盖旧失败。

原生源、主场景位图、生成调用与当前预览核验见[当前作品集合](current-artwork-set.md)。源文字扫描仅提供候选，不识别路径字/位图中文字，也不证明可见性或排版质量；始终看实际渲染。

## 产品合成与局部像素合同

新运行使用 print-ad.0.16.0、product_contract=print-product-v2；保留 print-core-v4 的锁定声明与原盲读，第二步对照改用模块常量 INDEPENDENT_COMPARE_RUBRIC_PRODUCT_V2，增加第6问：“产品上的品牌/品类文字是否与官方一致、正向可读（不倒置、不镜像、无伪字）？”answers.product_label_consistent_readable 引用 comparison.product_label，逐稿保留原始返回；为否则核心失败，当前稿不得交付，回生产修正文字/合成并重新独立检查。原动作/因果问题仍执行完整返工合同。不得把作者检查填成独立确认。

visual-review 使用2.3.0，沿用2.1.0单位字段，增加 product_present、product_presence_observation 和 product_integration（所有可见产品逐一登记；无产品时明确观察并给空数组）。记录结构由 visual-review.schema.json 的 $defs.product_integration_v2 定义，运行时由 visual_review_contract.inspect_product_record 核验：

- contract、element_id、role（scene-object/display-object）、method（reference-edit-label-remap/official-asset-composite）、choice_reason；official、before、final均为实际path/sha256引用。scene-object必须走参考编辑与标签回贴，独立展示可用官方原图。
- geometry登记rotation_degrees（官方图层全部旋转的累计净角度）、flip_horizontal、flip_vertical、perspective_matrix（额外透视3×3按行展开，含全部透视步骤）、official_reading_vector、label_sample_points（覆盖文字区域的实际采样点）和mapping_record。曲面逆映射参数留在mapping_record，矩阵与采样检验不能代替曲面文字的像素检查。glyphs_changed、colors_changed必须false；occlusion_observation记录实际可见字与遮挡。
- triptych引用JSON：panels按official/generated/final各登记source、bounds、zoom（1.5—4），image是按此顺序横排的原样放大图；text_checks逐项记录kind=brand/category/mark、official_text、final_text、status、generated_observation与observation。品牌必须pass且文字一致；其他项允许如实absent-on-official或occluded，不能补造官方没有的字。生成与最终两个阶段都核对，不能只证明来源正确。
- independent_confirmation引用真实独立记录：fresh-isolated、author_session_id、checker_session_id、invocation_id、started_at、completed_at、official、final、triptych、raw_return与result。result原样等于raw_return，含label_consistent_readable及label_observation；场景编辑另含residue_absent/residue_observation、scene_integration/scene_observation。透视、遮挡、接触、光影和旧图残留仍由独立像素检查判断。
- 几何风险为倒置/镜像时，orientation_correction必须有reason与detail（source=当前final、image、bounds、zoom），独立记录引用corrected_detail且原始result.corrected_orientation_readable=true。此例外必须针对修正后的可见文字；旧旋转或镜像失败记录不得删除。
- pixel_proof含before、after、allowed_mask及changed_pixels、outside_changed_pixels、difference_bounds。必须重算，outside_changed_pixels=0；允许蒙版为二值、同尺寸，比较全部原生通道，不把小变化、alpha变化或色彩容差忽略。
- 参考编辑另登记generated、generation_reference=official、edit_execution、edit_mask、container_contact_mask、opening_mask、replacement_layer和boundary_on_natural_edge=true。edit_mask完整覆盖container_contact_mask；opening_mask在容器内；replacement_layer为同尺寸RGBA最终合成层，开口alpha全255且开口RGB与final一致。透明度证明与独立残留观察都通过，防止不透明层本身仍有旧图。

已有 prepare_visual_views.py 提供可复用 product-triptych 与 pixel-proof 操作（见脚本 --help）；输出均写当前run内新目录。不运行生图。机器验证真实字节、几何风险与记录关系，不以结构通过认证品牌字、透视或艺术质量。独立第6问与局部确认均不替代最终人工认可。

阅读向量必须对应官方位图内实际字序，不能把电池长轴当字序、也不能默认所有文字沿x轴。脚本把官方阅读向量经过累计旋转/翻转及透视映射后，相对正常左到右阅读轴判定净偏转；例如官方图内文字朝下[0,1]，图层旋转57°得到147°倒置，不能因图层旋转小于90°放行。270°与-90°按同一可见朝向处理，不按累计转圈数判错。曲面映射留下真实参数，仍需独立成图核读。

### 产品在场景中的独立第七问

新print-product-v2与visual-review 2.3.0沿用既有三联像素合同，独立对照额外回答：“产品是否真正处于场景中（透视、遮挡、接触、光影一致），而非贴片？”对每个场景内产品绑定官方/生成/最终三联局部，记录comparison.product_scene，汇总为product_in_scene。失败为核心失败，不可被作者自评或其它检查冲销。仅产品问题可局部返工，保留失败与新生产计划、区外零变化证明，再取得新独立检查；缺返回校验失败。

方向因果提示使用print-direction-v7。独立因果提示检查分两步：① 核心创意关系直接由什么产生？② 是否建立在产品自己做的事上？本职是用户买它要它做的事及正常直接结果。给其他对象提供能量、原料或功能的赋能型产品，其赋能对象因此做到的事也算本职结果。由本职/正常结果/赋能结果产生的核心效果合格；来自产品未参与的另一系统或环境、产品只是前提或触发者的效果不合格。不以同类或其它手段也能完成本职拒绝，不虚构产品能力。理由写明本职、赋能对象及提供的东西、核心直接来源与结果归属。多品类示例仅用于说明：设备靠电池供电发光投影、玩具车行驶、点火后的烹饪蒸汽合格（电池不加热汤）；遥控借车辆自身车灯、开门借独立走廊灯投影不合格；药品/健康品缓解症状后的恢复状态、饮料/食品补水或口感/成分带来的变化合格，只作场景道具且效果来自别处不合格，均须产品说明支持。逐条填写core_creative_relation_direct_source、core_relation_still_holds_without_product布尔、reason；旧布尔字段名为负向提示标记，第②步是→false合格，否→true不合格。不设按品类的规则分支。 因果一问是提示项，用于提醒“创意是否借用了产品没参与的效果”，不作为门槛。逐条保留直接来源、结论与理由，方向选择清单原样展示且在用户选择前可见；rows保留去重后可选排名，causal_advisories覆盖本轮全部输入（含去重项），不改变可选排名；缺字段、覆盖不全或清单遗漏提示仍须拒绝。因果结论不参与合格排序、可画前列、all_weak、自动采用（含委托）、user_override需求、版本迁移承接或生产守卫决策；因果不合格无需用户覆盖。排序与all_weak只按既有套路/可画性规则判断，不能按因果结论压排序或变更采用。新增causal_check覆盖全部输入，包括去重项；检查者不代替用户选择，其余v6返回字段保持。 既有成图核心检查与产品进场景要求继续执行，不能将方向因果提示当作成图失败。

## 次级文案：可用，也可不用（print-ad.0.16.0）

按[次级文案原则与文字角色范围](typography-direction.md#次级文案可用也可不用print-ad0160)决定是否使用，并在现有作品记录中登记一句理由；未使用不算缺项。新成图使用 `print-secondary-copy-v2` 与visual-review `2.5.0`；全部旧合同与文案/排版检查保留。

每稿用 `text_elements` 登记标题、次级文案、页脚事实限定或必需信息、品牌/产品标识、场景文字。只有角色为 `secondary-copy` 的元素进入本原则的内容、字号/字重、420px可读、系列及独立语义检查。独立输入用实际文字/位置及scope hash明确范围；其他文字区的意见只留作信息，不触发次级文案返工。页脚限定是否解释画面不由本原则判断，页脚小字不套420px下限，既有页脚检查原样执行。

使用时只补画面与标题未给出的官方事实或命题信息，语气克制、不复述或解释画面，层级低于标题并合成一个阅读区。脚本和独立检查失败只返工文字层，保留旧返回，局部修改后绑定新图及文字蒙版、区外零变化并取得新独立检查；核心/产品失败继续独立处理。“产品名｜卖点”只是一种例子，不是默认或必需格式。
