# 作品交付与恢复

默认终点是完成并交付作品，以`delivery_complete=true`确认本Skill完成。当前赛事规则与实际提交规格、外部研究及数据引用必须在交付前完成核验；不得用报名、素材或字体权利手续、AIGC记录、平台申报、上传和回执扩大作品任务。

## 统一检查

```powershell
& "<workspace-python>" scripts/validate_run.py --run-dir <运行目录> --manifest <运行清单.json> --handoff <交接目录/handoff.json> --output <新回执.json>
```

技术检查、当前版本真实内容批准、适用视觉/创意质量门及运行证据保持有效。完成作品需要这些检查通过，且交接证据中的当前赛事规则与实际规格已核对、外部研究引用已完成或有真实的不适用理由。`status=passed`仅表示运行记录有效；`delivery_complete`表示作品交付完成。`submission_ready`是独立投稿兼容字段，默认不作为用户可见完成条件。

## 交接证据

```powershell
& "<workspace-python>" scripts/prepare_handoff.py --run-dir <运行目录> --manifest <运行清单.json> --output-dir <新交接目录> [--readiness-input <已有证据.json>]
```

默认`method_scope=artwork-delivery`。传入已有证据时保留已核对的规则与引用，验证项目身份；未提供时生成待填项，不能自动声称核实完成。生成器复用当前真实人工批准和技术结果，不重置已批准作品、不伪造审批。修改证据后更新交接记录的SHA-256再验证。

交接绑定`run_id`、`track`、当前最终作品的路径/版本/哈希/页范围与证据文件。完成状态只取决于作品交付条件。`post_delivery_reminders`向用户简短提醒：使用前自行核对素材与字体的使用依据；按实际使用整理AIGC后台记录并按平台要求申报。提醒不构成待完成质量门，也不要求用户回复确认。

## 研究与引用

外部研究、统计及可验证论断在制作过程中建立对应关系，交付前完成校对。官方品牌事实与命题依据保留后台；外部研究在作品中提供适合评委阅读的脚注或可定位附录。无外部引用时说明真实的不适用理由。

`evidence_slots`可保留明确标记的方案假设，包含`id`、`status`、`affected_units`。假设须有`hypothesis`、`frontstage_label`、`reversal_trigger`和`required_before`；`claim-finalization`槽必须在完成相关论断前解决。未来真实执行的预算报价、点位实测等不能冒充已发生，但明确的方案假设不要求先把活动实际执行一遍才交付作品。核实槽须绑定真实一手或公开证据，模拟结果不可充当实测。

## 独立投稿兼容

只有用户另行要求实际投稿时才检查报名、平台字段、权利手续、披露、上传与回执；这些外部操作需要相应授权。旧`real-submission`记录仍按其历史字段验证，不自动把旧状态改为通过。作品完成不代表已经投稿、取得授权或完成平台申报。

正文不自动增加AI、工具或排版制作说明。赛事规则若明确规定作品本身必须包含某元素，属于交付前规则检查；平台后台申报手续属于交付后提醒。两者不可混同。
