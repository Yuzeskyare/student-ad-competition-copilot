# 用户明确改向或修改方向句

“累计最多重新发散3次”仅约束模型自行发起。用户聊天中明确要求重新发散、换方向、修改已锁方向句或给出自己的方向时，不受此次数限制，无需新开运行。泛指“继续”、既有委托或模型自己的建议不能冒充新改向决定。不得伪造、补写或无法追溯地登记用户决定。

仅在发生这种例外时保存 `user-direction-change` JSON：`kind`、`action`（rediverge/change-direction/amend-statement/provided-direction）、`source`（现有 human source 路径/SHA256）、`quote`（原话）、`decided_at`（原消息时间）、`previous_manifest`（改向前清单路径/SHA256）。来源、原话与时间须一致；有 host_event 时也核对原用户消息。程序检查证据一致性，不能认证被伪造的整套宿主记录；来源真实性由宿主原始事件承担。

新方向使用同版本正常独立检查：固定输入、空上下文身份、套路/反例、可画性、因果、产品意义及传播目的提示全部保留。用户自带或修改的方向句可只检查这一项，不强迫额外发散或凑三类起点；后台 method_id=null，复用原方法检索证据。用户要求模型重新发散时仍按正常方向组检查。结果仅提示用户，真实确认后使用现有 selection_record（需要时保留 user_override 和完整原判），锁定检查输入中的原句。不得先锁后补审、复用旧检查或用更容易通过的声明审新稿。

`direction_adoption.user_direction_change` 绑定该决定，`previous_adoptions` 原样追加改向前 adoption；旧清单、旧bundle、旧锁、旧稿和全部审稿均保留。新bundle不覆盖旧bundle；后续完整稿与新锁对照，旧稿仍对照其旧锁。新用户决定不重置模型已用次数，也不改变生图额度、生产授权、停止控制或最终批准。

可用原生入口生成新快照（仅核验并写清单，不生产）：

```powershell
python scripts/direction_change_contract.py --run-dir <run> --previous-manifest <old.json> --adoption <new-adoption.json> --decision <user-change.json> --output <new-manifest.json>
```

输出必须是新路径；入口在独立检查、真实用户确认和声明一致性全部核验后才保存。没有新用户决定时，模型不得通过切bundle、改句或换方向重置三次上限。


自动发散与改声明使用[三次上限和换思路检查](model-redivergence.md)，每次必须保存相对上一轮的变化及独立核验；整轮机制重复拒绝，三次后仍弱交回各轮排序与理由，不自动出图。用户明确改向仍不受此限。
