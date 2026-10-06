# 新生产与当前交付的执行入口

开始新生产、恢复实际调用或形成当前平面交付时读取；普通方向讨论不要求建全套记录。旧记录继续只读核验，新生产不能借旧字段缺省获得执行资格。按需读参考，不一次合读全部长文件再假定全文已进入上下文。

## 新生产

当前平面技术检查优先使用`validate_submission.py --competition <赛事> --run-dir <运行根> --manifest <当前相对清单> --output <新报告>`。入口核验当前绑定并读取原始文件，不复制改名、不将PNG检查套给JPEG；旧目录入口保留。当前清单不完整时修复真实来源，不通过另建副本绕过。技术检查不产生内容认可。

复用运行清单和真实授权。新请求使用[生产请求模板](../templates/production-request.template.json)，execution_profile=bound-production-v1，声明input_files、具体output_files及brand_asset_mode。本地脚本与命令文件参数必须绑定；纯文本/内联代码确无文件输入时说明no_file_inputs_reason，代码由请求hash绑定。restricted给出asset_scope的原始范围依据、允许原件和使用原件；派生文件仍绑定input_files。not-used只用于实际未用品牌资产并写brand_asset_reason，不是绕过白名单的选项。

运行清单声明execution_control，依据[控制模板](../templates/execution-control.template.json)填写实际run_id、active/stopped/unresolved及not-requested/active/revoked监测状态。模板默认未解除，执行者依据已有授权和实际停止事实填写，不把字段变成新审批。未要求监测不查额度。主动监测的latest_signal绑定实际JSON，包含decision=continue/stop/unknown及basis；先单独读信号再决定工作，不能在无分支的读取批次内继续制作。停止或未知信号不能分派。

guard_production每次都做严格分派检查；review_contract.preflight不带for_dispatch只核历史授权，dispatch_checked=false不能替代分派回执。恢复旧运行另存新请求，复用确实覆盖该动作的真实授权并重绑，不篡改原决定、不重复要求机械确认。实质扩大范围仍依真实授权处理。

输入、已存在输出和已绑定作品不覆盖；每次派生稿、脚本修订、回执使用新路径。守卫完成本地命令后核所有声明输出存在并保存hash，返回0但缺输出仍failed。检查不是操作系统沙箱，无法发现任意脚本未声明读取或约束宿主直调；实际输入必须如实声明，不能声称全面拦截。

技术检查输入从当前作品集合派生，逐文件绑定路径与hash。审稿PNG、另存JPEG及最终交付件分别记录；JPEG独立通过不能套给PNG，旧PNG批准不自动批准新JPEG。预计导出在原有最终展示前准备；旧稿已经获认可时保留它与真实失败，不为修报告重复索取同版本批准或静默替换集合。错配诊断用于定位目标，不放宽集合与哈希要求。

## 已授权局部修订的短流程

先读取当前有效清单、图源和真实反馈。双品牌分别使用明确命题身份的运行，外层仅聚合导航。保留原批准版，按本轮范围新建稿，不把字体修改当重开全部创意。

1. 有效合同上用[request操作](review-state-tools.md#准备新的生产请求)保存具体动作和既有适用授权；同一真实授权可覆盖多个明确请求，不机械重问。坏合同先恢复真实证据或建立有效的新起点，不能用该操作自动洗成通过。
2. 实际生产前用返回的新清单运行guard；本地可--execute，外部调用保留真实事件链。一外部调用一请求；代表稿和其余成员分开调用时分别绑定。本地单命令可声明多个输出。
3. 新图源回渲染并看图，再按真实反馈登记decision、按当前对象project。始终使用工具返回的新清单，旧稿、请求和回执保留。

request准备不授予新权限，不替代前检或内容验收；正式来源不可得时只继续独立准备，保留缺项，不把已发生的失败改为探索成功。

## 异步与时间

仅当用户约定额度重置停止时，active监测设monitor_kind=usage-reset。latest_signal除decision/basis，还绑定baseline、reading、必要的confirmation三份原读数投影，保留account_id、limit_id、window_minutes、used_percent、resets_at；不能只保留一个自填continue。守卫用evaluate_usage_signal重新比较，同账号同窗口用量回落且重置时间推进、复查确认才stop，缺字段/不一致/未复查为unknown。其他用户条件用monitor_kind=user-condition，按真实条件判断，不自动套额度规则。辅助函数不查询账号、不建立定时任务，也不能中断宿主内任意批次。

本地--execute记录running/completed/failed及实际输出。外部工具由宿主调用，guard的executed:false只表示未代调。审核合同production_events追加不可变事件：request_id、request_sha256、真实call_id、occurred_at、state、evidence，以及后续事件的previous文件引用。evidence保留宿主返回/转录，含相同call_id/state/occurred_at。

链从started到running或returned/failed；returned后文件确已保存核验才saved，outputs与宿主保存证据及请求output_files对应。真实时间/ID缺失保持未核，不为满足字段捏造；检查不能认证转录者身份。恢复先看链和真实宿主状态，已开始不能再次分派同一请求。开始后不能改称启动前取消；未运行取消沿用原机制。停止后只保存不可避免返回与最小交接，不再编辑测试；撤销监测后不查询。

execution_contract.normalize_event仅按明确seconds/milliseconds/iso和message/turn/review-event转换时间，保留original_event/original_time；原ID缺失仍空。human_source继续检查真实来源条件，观察时间不能顶替发送时间，turn依据保留原turn_id和turn_started_at。

## 当前平面集合

在审核合同final_artifacts原成员引用内增加current_source，不建立第二套最终名单：

| 字段 | 实际含义 |
|---|---|
| native、preview | 准确文件引用；每成员一个独立作品，格式副本不增加units |
| purpose | creative-master或用户明确要求的submission-version；后者绑定purpose_authorization原文与purpose_quote，命题页不能充用户授权 |
| scene | 有位图主场景时给node_id、file、call_id、provenance；provenance含真实调用的call_id/output。无主场景写no_scene_reason，不拿logo代场景 |
| render_record | source等于native；execution_evidence绑定渲染执行；render为实际回渲染图；compared_artifact为该成员path/sha256/version/units；correspondence=matched及observation来自实际比较，不强求不同渲染器逐像素零差 |
| process_review | render为同一回渲染图，status=clear及observation来自看图；SVG候选逐项candidate_dispositions含text、classification与reason。只有确为not-visible或non-production-copy才记录；真正制作字局部修复，不能标required-disclosure绕过 |
| dependency_root | 明确运行内依赖根，`.`表示运行根；允许根内兄弟字体。不自动放宽到磁盘 |
| native_inspection | 非SVG另给evidence与实际observation。路径字、位图字仍需看图，扫描不证明全覆盖 |

series_plan沿用有效units；member_roles逐项unit、benefit_or_action与contribution，shared_art_direction描述共同美术，scope_basis引用实际命题/用户范围。记录存在不证明语义增量与美术统一，仍并排看全组。后来的三幅要求从生效时继承，不倒推此前违规。

统一平面交付自动调用current_artwork_contract及SVG扫描，未解决的源关系/制作字候选不能通过。旧运行不自动追认新能力。展示、续作和归档从此集合取文件。`scripts/export_current_artwork.py --run-dir <运行根> --manifest <运行相对清单> --destination <新目录>`仅复制已核当前图源、预览、关联证据及实际依赖，生成CURRENT-ARTWORKS.json；目标已有则拒绝。失败选择保留，不重绘认可稿掩盖错选；复制不授予批准，不等于投稿发布。

## 已知缺陷后的动作

创意失败按[反馈进入创作](feedback-to-creation.md)重新进入方法、关系与艺术选择；登记/派生当前状态按[工具入口](review-state-tools.md)使用已有合同。两者各司其职：记录与字段齐全不能代替实际视觉判断。

先看作品再看作者解释。实际观察到机制、受众、品牌、系列、接触/字形/排版失败，写入现有visual_review.issues的problem、affected_scope、return_stage；不能只在文字里承认失败却把checks填pass。开放问题优先修复，resolved须引用当前视图和修复观察。

机制问题不以修蒙版代替；已授权修复不自限一版后标pending。需要用户偏好的取舍才等待，已认可局部与已放弃方向继续继承。结构检查不能理解自由文字矛盾；必须实际评读，不把结构通过宣传为创意自动认证。
