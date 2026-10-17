# 审稿一致性、终局拒绝与运行升级

## 新成稿的固定请求

新返回使用 `print-ad-run-manifest.schema.json#/$defs/core_comparison_return_product_rc4`，历史定义保持原字节语义。新对照请求统一调用 `validate_print_ad_run.comparison_request(row, blind_ref, locked_claim)`，不手拼旧 rubric。它固定输出一致性规则、正反例和从 assessment 推导的三联 JSON 绑定表。输入观看 PNG，返回的 `triptych` 则复制绑定表中的 JSON 元数据引用。历史精确请求仍可读取，不能借此改写旧返回或声明旧稿通过。

`aspect` 是歧义分类依据，`affects_main_relation` 逐项等于 `aspect != secondary`。原五问失败码只对应同问 false 和逐字观察。整体成立但局部可改善时，检查者可保留 true，另登记 `severity=hint, question=local-detail, reason_code=local-detail`，明确局部位置和影响；不计作整问失败，不触发同因创意失败计数，也不豁免任何硬性问题。原来的 true + claim-unfulfilled、other-main + false、PNG 冒充 JSON 仍无效；作者不得把旧错误码换成新局部类别来修返回。

产品文字由独立检查者对照官方素材逐项核对，必要时放大并旋正，记录每个产品的官方字样、所见字样、镜像/倒置/错字/伪字四项布尔及检查过程。新固定请求下缺项或漏产品不能通过记录校验。任一可核实文字错误必须第6问 false，并保留 hard/label；作者自查不能替代独立结果。程序验证记录与答案一致性，不冒充像素识字或新的独立审稿。

## 用户看稿后终局否决

沿用 `review_state.py --action decision` 的 final/reject，绑定成稿原 SHA256、原话、真实消息时间与来源。它对相同字节（包括改名副本）终局有效，不因后来出现 true 返回转成通过。所有审稿、无效登记、原返回和失败回执保持可见。

`core_return_contract.review_state` 把终局拒绝稿及其渲染投影为 `terminal_rejection_audit`，明确 `content_pass_granted=false`，保留原返回引用。下一稿不再要求这个已拒绝稿补出有效核心返回或消耗第三次替代；没有终局拒绝的完整稿仍须有效独立返回。拒绝发生前的渲染、消息来源及字节绑定仍真实校验。拒绝不赠送生图额度，不激活 stopped 控制，不替代下一稿生产授权。交付范围包含这些像素一律拒绝。

## 同一运行升级包

在新的运行快照中加 `package_upgrades`，引用不可覆盖的 JSON，结构如下。每份安装 ZIP 保存在运行内并绑定 SHA256；`from_version`、`to_version` 必须与 ZIP 的 version.json 一致。登记真实安装时间；测试或回放中的假设时间、控制变化统一放 SIMULATED 目录，不能冒充安装事实。

```json
{
  "kind": "package-upgrade-chain",
  "run_id": "当前运行ID",
  "upgrades": [{
    "from_version": "旧版本",
    "to_version": "当前版本",
    "upgraded_at": "带时区的真实升级时间",
    "from_package": {"path": "packages/old.zip", "sha256": "旧安装ZIP的SHA256"},
    "to_package": {"path": "packages/current.zip", "sha256": "新安装ZIP的SHA256"}
  }]
}
```

链条须连续、时间递增，最终与实际执行包全部脚本哈希相同。程序校验每个 ZIP 的安全路径、清单、大小和全部文件哈希，不信任手填检查器身份。旧放行必须绑定当前 run_id、原请求及输入、原授权、原 active 控制和成稿输出字节；回执时间须在对应升级之前。伪造身份、不在链中、安装包损坏、绑定不一致或只预检而冒充完成均拒绝。

升级后先对原像素、原记录运行：

```text
python scripts/recheck_history.py --run-dir RUN --manifest NEW-MANIFEST --output NEW-HISTORY-RECEIPT.json
```

该入口重跑本包原生生产回执绑定、成稿放行、原图技术检查和缩略/局部视图像素派生检查，保存带当前检查器身份与来源版本的新回执；技术失败如实写入，不转成内容通过。不能重演的生图前放行只作为已绑定的历史授权接受；不再执行旧生产命令，不生图、不改原像素、不伪造事后放行。新派发 guard 也会重新核对升级链与全部历史放行绑定。技术或记录结果不能代替新成稿的独立内容审稿。

来源真实性仍由原始宿主事件和受保护证据承担：本地校验可拒绝可检测的伪造与绑定矛盾，不能认证被整体替换且所有内容一致的宿主历史。
