# Codex 桌面版生图宿主证据

Codex Desktop（会话元数据 `originator=Codex Desktop`、`source=vscode`）的内置生图可在原生 rollout JSONL 中留下一个聚合的完成事件，未必逐条返回 CLI 形式的 started/returned/saved。已核对的形态是：外层 `type=event_msg`；`payload.type=item_completed`；`payload.item.type=Extension`、`kind=image_gen.generation`、`status=completed`、`failure=null`。`item.id` 是真实调用 ID；`payload.started_at_ms` 和 `completed_at_ms` 是宿主毫秒时间；`item.savedPath` 是实际保存路径；`item.result` 是原始 PNG 的 base64 负载。不能用 ImageView、作者消息、read_thread 的文本摘要或观察时间替代。

在运行内部保存原始 rollout 的逐字节副本，并保留其来源路径及 SHA256。审核合同 `production_events` 追加一个绑定 JSON 的文件引用：

```json
{
  "profile": "codex-desktop-imagegen-v1",
  "request_id": "<原生产请求ID>",
  "request_sha256": "<原生产请求SHA256>",
  "call_id": "<item.id原值>",
  "evidence": {"path": "<运行内原始rollout.jsonl>", "sha256": "<原日志SHA256>"},
  "outputs": [{"path": "<请求声明的原输出文件>", "sha256": "<实际输出SHA256>"}]
}
```

此绑定不填写 `occurred_at`、`started_at` 或 `previous`。程序从原生事件派生 started_at、occurred_at、state=saved，检查唯一调用、会话与 turn、成功状态、实际时间顺序、请求准备时间、原保存路径文件名 `<call_id>.png`，以及图像负载与请求输出的实际字节 SHA256。离线核验依靠原日志中的图像负载，不要求仍能访问原机器的 generated_images 目录。单次该形态只支持一个 PNG 输出；其他形态继续走已有协议或保持未核验，不猜测补齐。

缺调用 ID、缺原始时间或图像负载、输出名/字节不匹配、失败或重复事件、自填时间替代原事件均拒绝。原日志、原请求、原 guard 分派回执与旧失败报告保持不变；只新增绑定和新检查报告，不重新执行历史生图。已开始的调用不能重新派发或当作启动前取消。

这是对宿主记录与字节的一致性核验；SHA256 不能认证一份被整体伪造的日志。来源须是可追溯的原生宿主记录，作者手填的状态链不能充当本协议的原始证据。该协议不产生人工内容确认，也不授予后续生产或交付批准。
