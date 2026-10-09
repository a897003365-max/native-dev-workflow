# 派发与审计协议

只约束使用本技能的派发，不修改全局模型、速度、权限或其他会话。主版本由平台文档定义；共享入口指向同一目录，修改后核验链接目标及所有交付文件哈希。工具调用仍由主 Agent 完成，脚本不能自动拦截或创建 Agent。

## 逐子任务留档

在当前任务证据目录保存 UTF-8 JSON；无项目入口时用任务独有临时目录，不能写入其他任务目录。每次派发使用独立任务编号和凭证，包括重派；失败预算沿用原 root_cause。先保留修改前快照，不提交个人会话日志。

- `task.json`：从 [输入示例](task.example.json) 填真实目标、读写边界、验收、角色、难度与风险证据。`parent_model` 来自本次会话 `turn_context.model` 或其他明确运行记录，来源单独留档；仅证明报告值。`reasoning_need` 必填 `routine` 或 `deep_comparison`，后者另填 `reasoning_evidence`。不能按角色或父模型固定路由。
- `capabilities.json`：主 Agent 阅读当前 `collaboration.spawn_agent` schema 后保存 `source`、`parameters` 和 `catalog`。结构为 `{"source":"本次会话工具 schema，核验日期 YYYY-MM-DD","parameters":["task_name","message","fork_turns","model","reasoning_effort"],"catalog":{"<本次支持的模型>":["<本次支持的推理档>"]}}`。这里只保存相关工具能力，不保存凭据或无关消息。过期/不可选即停止，不回退默认继承。
- `dispatch.json`：将路由输出的 `dispatch` 四个字段原样复制，增加展开的完整 `message`。例如示例 L1 路由为 `task_name="smoke_1"`、`model="gpt-6-luna"`、`reasoning_effort="xhigh"`、`fork_turns="none"`；替换示例任务后以实际输出为准。禁止额外添加速度、权限或角色字段。

6 系列标准为 6.1 Sol/high；5.6 标准为 Terra/high。6.1 的 `deep_comparison` 使用 max；不要为了测试矩阵或多模型比例批量派发。

## 执行顺序

先按 [Windows](windows.md#运行路由与验证) 或 [macOS](macos.md#运行路由与验证) 定义脚本和任务绝对路径。下面是 Python 脚本的参数顺序，路径占位符必须替换为真实绝对路径；Windows 使用 `python -X utf8 -B`，macOS 使用 `python3 -X utf8 -B`。

```text
workflow.py <task.json> --output <route.json>
workflow.py <task.json> --dispatch-file <dispatch.json> --capabilities <capabilities.json> --output <preflight.json>
```

第一步查看分级、风险、路由、缺失条件及 `dispatch`。第二步重新计算路由，拒绝不可派发任务、漏参、额外参数、与路由不一致的值、空消息和当前 schema 不支持的组合；将消息 SHA-256、校验时间及任务/配置/能力快照哈希写入凭证。只有真实退出码为 0 才调用工具。未来角色配置需两步都传 `--role-config` 并单独保存配置证据。

主 Agent 检查完整共同行为、单一角色与真实契约已在消息中；脚本不理解这些文本的语义，也不验证人工分级是否正确。真实 `spawn_agent` 调用必须显式包含上述模型、推理档和 none；校验不会替主 Agent 操作工具。请求后记录真实返回值；失败不能伪造 Agent ID，重新派发须重新路由并保留原失败计数。

当前桌面可能只返回规范代理路径 `task_name`。此时先保存真实返回路径，再用明确定位的子日志 `session_meta.agent_path`、`id` 和 `parent_thread_id` 关联；不得自行编造 ID 或把其他主任务的同名子代理日志当作本任务证据。

```text
workflow.py --audit-rollout <本任务主会话.jsonl> --records <preflight-1.json> <preflight-2.json> --child-rollout <指定子代理.jsonl> --output <audit.json>
```

`--child-rollout` 可重复；不可观测时省略，`runtime_status` 保持 `unknown`。脚本只读取调用者指定的文件：主日志的 spawn 请求/返回字段，子日志的 session ID 和 turn_context 模型/推理字段。主日志所有实际 spawn 均纳入，不能只导出符合要求的调用。凭证必须先于真实调用，不能事后补填制造已执行的路由。路由脚本的真实 CLI 调用与退出码另由主 Agent 记录，不能只凭 JSON 推断脚本已执行。

审计退出码 0 表示给定日志和凭证无协议违规；退出码 1 表示存在违规；参数或读写错误退出码 2。记录完整输出与命令。无真实派发记录不会通过。运行日志缺失或只有部分字段时，即使协议通过，也必须列为运行配置未核验。日志报告值不一致时记录 `runtime_request_mismatch`，不得把请求值抄成实际值。JSONL 损坏应明确失败，不自动忽略损坏行。

指定子日志的所有 `turn_context` 逐条保留在 `runtime_records`，任一可比字段不符即报差异；后续匹配不能覆盖早期差异。任一 context 字段缺失时整体记为未知。结论只覆盖审计当时已写入的记录，任务运行中不视为最终核验。

某些桌面日志将消息正文保存为 `gAAAA` 开头的不透明封装。此时不能比较明文消息哈希：输出 `message_status="unverifiable_opaque_log"` 并列入 `unverified`，不解密、不把封装变化误报为明文变更，也不声称内容匹配。其他明文日志正常比较哈希。该前缀只是可观察格式判断，不是内容或密码学真实性证明。协议通过仍须逐项陈述 `unverified`；消息源文件只证明预备内容。

## 证据与违规处置

分别记录：路由决策与依据 → 真实工具请求参数 → 返回 Agent ID → 运行日志报告值及文件/行号 → 已核验映射（没有则未知）→ 底层模型身份（没有独立上游证据则未知）。审计输出从不据日志自动确认底层身份或 Fast/权限生效。

漏参、无路由、消息变化、重复使用凭证、凭证晚于派发、文件哈希变化或运行记录不符时，暂停后续依赖该子任务的派发/验收，保留原记录，重新判断影响及有效结果；主 Agent 可继续无依赖工作。修复后用新的有界派发与独立审查补证据，不能把原违规改写成通过。缺日志单列未核验范围。

这套机制是派发前检查与事后检测。主 Agent 若跳过脚本仍可能直接调用工具；目前没有工具级强制机制。本地凭证可编辑、schema 快照由主 Agent 提供，审计不防恶意伪造，不证明未提供日志中的行为；不得以此扩大完成声明。
