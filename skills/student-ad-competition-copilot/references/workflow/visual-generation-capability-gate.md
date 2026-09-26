# 视觉生产路径前检

用于平面广告与营销策划。确定赛道后、承诺产出质量前检查；恢复或换宿主时核对当前能力与实际文件。高保真、高质量指完成度和内容准确性，不限定照片感；图片面貌按[风格选择](visual-style-direction.md)，工具输入按[工具与宿主适配](image-tool-adaptation.md)。

## 区分直接能力与生产资产

`visual_generation_capability`继续如实记录当前宿主：`status`为`available`、`unavailable`或`unknown`；`provider`为实际可直接调用的提供方，不可得为null；`operations`区分generate/edit；checked_at与evidence记录当前检查依据。提供方不限，名称和模型知识不等于实际工具。

只能搜索图片、截图、查看图片、输出提示词、HTML/SVG、图表，或只有未连接的插件，都不构成直接生图能力。已有图像也不使宿主凭空获得工具。但足够的外部生产资产可以让作品继续，不必把无直接工具视为永久质量降级。

## 三条可行路径

1. **直接生成：**status=available、operations包含generate，user_decision=use-available-capability。按当前入口生成或编辑真实图像，不能通过前检后改交占位图。
2. **外部生成回传：**用户已选外部执行则复用决定，user_decision=use-external-assets；保留宿主真实status。提供提示词、设置、相关参考分工与输出要求，等实际图像回传后复核。
3. **充分已有资产：**用户已提供可承担当前范围的视觉资产时，也用use-external-assets，kind=provided-assets。检查这些资产的任务覆盖与可用性；一张产品图不能自动覆盖整本策划的全部视觉需要。

只有确实没有可行生产路径时，说明缺什么及影响：启用/切换环境、选择外部生成回传，或明确接受低保真受限模式。已有决定不重复问；用户只说“继续”不等于接受质量降级。先完成不依赖该缺口的工作，不静默用图库、占位图或纯排版冒充所需生成视觉。

## 外部供给的最小记录

0.4.0清单支持可选的external_supply；既有直接运行不需补字段。将[外部供给模板](../templates/visual-external-supply.template.json)作为visual_generation_capability.external_supply，不作为独立的新运行清单。字段由助手维护：

- kind：external-generation或provided-assets；status：awaiting-assets或ready。
- scope：本次资产支持的production-candidate或delivery-candidate；从代表稿扩到完整作品时重新核对覆盖。
- evidence：用户选择或提供资产的依据、目标工具/入口（已知时）、资产对应的任务和充分性说明。不记录凭证，不另设用户审批表。
- assets：实际收到的位图文件，每项为相对运行目录的path与sha256；路径使用正斜线。等待回传时为空。
- review：已有或简短JSON资产复核记录的path与sha256；等待回传时为null。JSON根对象或其external_asset_review小节包含status（pass/fail）、scope、assets（与供给记录相同的有序文件列表）及observation（风格/品牌/可读性与当前任务覆盖观察）。可以复用允许附加小节的已有审核材料，不新增人审关卡或逐对象清单。

ready必须已经查看图像并复核，文件可读取且哈希匹配。机器校验只确认文件、记录绑定和范围，不证明艺术质量，也不代替既有最终内容审核。不能填一个通过值后跳过图像查看。若文件改变或任务范围扩大，原ready失效，重新复核并更新记录。

等待图像时，可以在concept-only这一准备阶段继续独立的研究、策略和方向工作；这是当前阶段，不代表用户接受低保真交付。所依赖的高保真生产与最终交付仍待图像，不能把提示词或待执行任务记成作品完成。生产/交付范围检查只有ready且当前scope相符才通过。

## 受限与完成边界

user_decision=pending或enable-or-switch-environment且无其他有效路径时，保留对应阻塞。明确accept-limited-mode并impact_acknowledged=true时，只允许concept-only，生产/交付检查仍不通过。外部执行不要求用户接受这种降级。

回传的资产只解决当前范围的视觉供给问题；平面成稿、策划五页样稿/全稿继续遵守原生交付、最终像素、规则规格、引用及既有人工内容审核。机器通过、文件到达或风格名称正确都不等于作品完成。广告文案不因本协议自动阻塞，除非任务同时要求视觉交付。
