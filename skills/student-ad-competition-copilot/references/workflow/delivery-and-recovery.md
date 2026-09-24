# 统一交付与恢复入口

恢复已有运行时，先读实际运行清单，复用同版本的决定与产物；不另建同身份运行。三赛道统一执行：

```powershell
& "<workspace-python>" scripts/validate_run.py --run-dir <运行目录> --manifest <赛道-run-manifest.json> --output <新的统一回执.json> [--handoff <交接目录/handoff.json>]
```

所有参数路径除run-dir外相对运行目录，禁止跨目录逃逸。回执分别给出technical_pass、content_pass、method_validated、submission_ready、完整赛道校验、交接记录与唯一next_action。运行结构有效不等于四项全部通过；正确的concept-only完成不被强制推进投稿。老清单保持legacy-not-verified，不自动升级或补造真实审核。

返工从首个失败的责任层继续。内容决定已存在但记录冲突时先修证据关系，不重新索要相同批准；只有确实缺最终内容判断时展示当前版本和范围，合并为一个低负担审核。原文件和失败版本保留，新修订另存并更新哈希。

## 生成交接记录

最终对象已明确后运行：

```powershell
& "<workspace-python>" scripts/prepare_handoff.py --run-dir <运行目录> --manifest <赛道-run-manifest.json> --output-dir <新的交接目录>
```

生成submission-readiness.json和handoff.json，不覆盖已有目录。它从当前校验结果填入可证明的技术/内容状态，赛事规则、权利、引用、平台披露和真实上传保持待核对，不自动创建审批或回执。真实记录更新后重算handoff中对应文件的SHA-256，再执行统一验证；不可通过把开放项删除来制造完成。

handoff含schema_version 1.0.0、run_id、track、与审核合同完全一致的final_artifacts、readiness文件引用、platform_disclosure、evidence_slots和submission_receipt。文件引用均含path与sha256，作品引用另含version与units。

## 研究与可行性证据的开放路径

缺少真实问卷、访谈、试点或合作点位证明时，可继续有明确假设边界的创作，不能编造受访者、合作方或执行效果。每个evidence_slots条目记录：

- id、affected_units：影响的当前幅号/页码；
- status为hypothesis时：hypothesis、作品中可见的frontstage_label、reversal_trigger，以及required_before（submission、claim-finalization或real-execution）；
- status为verified时：原始evidence引用与provenance（real-first-party或public-source），保留采集范围、来源、时间及限制；
- status为not-applicable时：rationale。

模拟回答、模型预测和公开资料推断不能填成真实一手研究。真实材料到来后先核对假设是否被推翻，再改受影响页面和决定，不能只把状态切为verified。提交前必须回填的槽未完成时submission_ready保持false；只影响未来真实执行的槽可继续作为明确边界保留，不能声称方案已执行落地。机器验证槽与文件关联，不认证研究真实性，也不会从字段推断真实消费者行为。

## 创作母版、后台记录、平台披露分开

作品中不自动添加AI、模型、人工排版等制作说明；后台AIGC记录按真实使用维护，平台申报按当前规则和字段完成。用户要求正文不出现制作说明，不等于免除平台必填披露。如果当前规则要求作品内可见披露，保留有规则原文依据的例外，并在提交前说明冲突。

platform_disclosure.status为pending、complete或not-required。后两者须有rule_evidence与rule_quote；complete还需submitted_evidence，证明相应平台字段实际处理过。不能以后台使用记录替代真实平台申报。

只有真实规则、权利、引用、披露、报名字段、当前文件、内容批准、技术验证、实际提交和回执均完成才可submission_ready=true。handoff.submission_receipt引用JSON，包含run_id、uploaded_artifacts（包括实际提交的文本字段所对应内容对象）和platform_evidence（真实平台回执文件引用）；其范围必须覆盖当前最终对象，不能重用旧版本或其他项目的回执。

验证器核对回执记录和内容哈希，不代替真实平台执行，也不认证上传真伪。没有实际平台证据时保留null，严禁生成假回执“跑绿”。本入口只读验证，不上传、不报名、不发送消息；这些外部操作按用户明确授权执行。
