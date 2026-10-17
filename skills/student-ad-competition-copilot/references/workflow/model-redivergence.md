# 模型自动重新发散：三次与实质变化

新运行默认声明 `direction_redivergence_contract=print-model-redivergence-v1`。初始一轮之外，模型在委托模式下全部偏弱或需改锁定声明时，合计最多自动重新发散3次（最多4轮），跨已采用声明共用该上限。第四次拒绝；不得靠换run名、新bundle或用户改向记录清空已用模型次数。用户明确重新发散/改向仍按用户决定走原异常入口，不受此次数限制。

用户改向本身不占模型次数；用户改向后再由模型改声明，仍沿保留的用户快照和模型采用历史累计原已用次数。历史采用条数不当作模型次数，避免多次用户决定误占模型额度。

初始bundle也保存 `redivergence: {"transitions": []}`；单轮方向不增加检查调用。旧运行在用户改向的原生入口中可用 `--redivergence-contract print-model-redivergence-v1` 接续新合同，新bundle同样先登记空 transitions，再按实际发生的自动轮次追加。

每次新轮在 bundle.redivergence.transitions 绑定一份变化登记，含 previous_round/current_round（实际相邻独立检查路径/hash）、registered_at、changes（axis=starting-point-type/visual-language/core-mechanism，before/after）和 independent_check。变化需具体到本题实际方向：起点类型、视觉语言或核心机制至少一项实质变化；只改措辞、名称或颜色不够。登记在上轮返回后、本轮输入准备前。

原方向盲评保持固定输入和判断。另用 `direction_redivergence_contract.request` 的固定请求让空上下文独立检查者对照两轮实际方向句、排序和登记变化，返回每项实质变化判断及每个保留方向的核心机制、与上轮机制的对应关系。保存真实会话/调用、请求、原始返回/hash和原样result，不由作者自评代替。检查至少一项变化成立；本轮所有保留机制都在上轮出现（即整轮只是重复）时拒绝该轮，即使改了视觉风格。允许保留个别旧机制，但整轮必须出现新的核心机制，不把重排、换ID或同义改写当新轮。程序核验记录及明显相同描述，语义重复仍由真实独立检查判断，不声称机器能认证审美或来源真实性。

不合格轮次原样保留，不计为合格的新一轮，期间不能继续派发或自动出图；不得通过删除该轮藏起已执行的尝试。需保留失败检查并修正为确有实质变化的新候选后重新检查，不能把重复结果改成通过。守卫不因轮次不合格而额外赠送自动次数。

三次后仍 all_weak 时，在 bundle.redivergence.exhausted_handoff 绑定 state=stopped、全部轮次的 round/ranking/trope_screen 原样记录及 user_facing_copy（路径/hash）。实际交给用户的文本必须包含各轮ID、排序与原理由；停在方向阶段，不自动采用或出图。用户后续明确选择/改向按原用户决定规则处理。

历史无此合同的记录按原定义读取（一次上限），不补造过去的变化登记。旧运行接续三次模式时保存新清单，在新bundle的 redivergence.legacy_manifest 绑定旧有效清单并完整保留其轮次前缀；原已用次数照计，只有接续的新轮增加变化登记和检查。不得覆盖旧清单或新开运行绕过计数。这个入口只用于实际再发散，常规单轮方向不增加检查调用。
