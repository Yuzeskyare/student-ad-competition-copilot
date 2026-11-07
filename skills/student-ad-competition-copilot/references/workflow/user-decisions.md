# 当前成稿确认、部分系列交付与零生图修正

用户在聊天里明确作出的决定可以推进流程；把真实原话、事件时间和来源保存为 `review_contract.human_source` 接受的记录。独立审稿的原始 JSON、布尔值、观察、问题及来源一律保留，不把用户确认写成独立通过。

## 当前确切成稿的主观存疑

产品记录或核心 assessment 可带 `user_confirmations`，值为登记文件的 path/SHA256 引用数组。

包含这些字段、或不带局部编辑遮罩的整图生产证据，使用视觉证据 `schema_version=2.7.0`。历史分支及所有旧 Schema 定义保留原值；当前生产计划 Schema 定义为 `product_scene_plan_v4_whole_image`，当前生产记录为 `main_visual_production_product_v6_whole_image`，核心为 `core_creative_review_product_v8_user_decisions`。

每个登记文件含：

```json
{
  "kind": "exact-artwork-confirmation",
  "decision": "confirm",
  "question": "label_consistent_readable",
  "independent_raw": {"path": "原始审稿.json", "sha256": "原始文件的实际SHA256"},
  "observation": "原始审稿对应观察的完整原文",
  "reviewed_artifact": {"path": "当前成稿.png", "sha256": "实际SHA256", "version": "当前版本", "units": ["当前作品"]},
  "source": {"path": "真实用户事件.json", "sha256": "实际SHA256"},
  "quote": "用户明确确认的原话",
  "decided_at": "真实事件的带时区ISO时间"
}
```

仅接受产品文字可识别或版面文字完整性等人眼可确认的主观存疑；核心对应问题名是 `product_label_consistent_readable` 或 `layout_readable`。来源必须明确指向当前成稿路径或 SHA256，或含完整 `reviewed_artifact`；确认时间须在该独立检查完成之后。改图即失效。登记文件应由现有真实事件生成，不能补造看图、原话或时间。

新独立返回用 judgment_basis 对应问题注明 subjective-uncertainty 或 verified-error；verified_errors 如提供，为具体已核实错误的字符串数组。类别由独立 AI 判断，不扫描原观察关键词。程序继续阻止结构化已核实错误、读反和合规问题被确认覆盖；原主观提示政策不变。

历史原返回缺类别时，可在新的确认登记中新增 judgment_classification 路径/SHA 引用，复用已有有效用户确认，不改原返回、原话及时间。该文件由一次新的空上下文独立 AI 分类产生，字段为 kind=independent-judgment-classification、independent_raw（原返回路径/SHA）、question、observation（该问完整原观察）、judgment_basis、checker_context=fresh-isolated、author_session_id、checker_session_id、invocation_id、completed_at。检查者须不同于作者，时间为本次真实分类时间。读取完整原返回，只分类原判断，不修改原答案，不重新解释成另一项像素结论；不足以分类则保持待查，不凭词语猜测。已有结构类别不能被该补充替换。

统一检查在保留原判断的基础上计算有效决定；`prepare_handoff.py` 把登记、原判断、原观察和用户来源写入 `handoff.json.user_decisions`，可见且可追溯。

## 明确选择部分系列作品

保留完整 `series_plan`。在 manifest 中添加 `delivery_scope_selection`，引用含以下字段的登记文件：`kind=partial-series-delivery`、`series_plan`（完整计划的 path/SHA256）、`units`（当前交付子集）、`source`、`quote`、`decided_at`。AI 根据完整原话及实际展示的系列上下文解释 units，遵循[自然语言职责边界](natural-language-boundary.md)，不要求用户说内部编号或固定“第一幅”；检查当前成员、角色及交付覆盖时按这个子集投影。未授权的缩小仍失败，完整计划中的后续作品不能冒充已制作或已交付。部分交付不代表完成命题的全系列投稿要求。

## 整图与局部修正

`reference-generate-label` 整图路径不需要 `edit_mask`、接触/开口遮罩或替换图层；仍校验官方参考、实际生成执行记录、当前像素、三联图、像素证明及独立检查。`reference-edit-label-remap` 局部路径继续严格校验所有相关遮罩、替换图层、修正范围和区外零像素变化。

额度限制生图/编辑模型调用。`operation=local` 且 `main_visual_action=local-composite` 或 `layout-only` 的已登记本地命令，可在额度用尽时执行官方像素合成或文字层修正；不得把模型调用登记为 local。它保留原失败交回记录，不增加额度或使用计数，不自动获得内容通过。守卫继续校验真实授权、输入 SHA256、计划、当前主体、未覆盖输出、执行控制与完整回执；执行控制需按已有授权恢复 active。修正后继续像素检查及独立审稿，模型调用仍须停下等待真实追加额度或方向决定。
