# 能力基线与来源

以下是 2026-09-26 核验的文档与源码基线，不代表所有安装环境。每次使用前核对当前原生工具参数、可用模型、权限和配置层级；不要把示例路由当作账号可用性证明。

本技能不附带个人配置、账号信息或会话日志。角色规则是行为约束，不能替代真实沙箱；上游模型身份无法证实时应记录为未知。

## 2026-10-28 模型路由重评

当前 `collaboration.spawn_agent` 已提供 `gpt-6.1-terra`，支持 low、medium、high、xhigh、max、ultra；6 与 5.6 系列其余目录项亦按当次工具枚举复核。公开 API 的 none 与工具枚举不同，不加入本工具的派发目录。Ultra 的工具可选性与本工作流禁止子代理自动继续委派的策略分开记录。

官方依据：[2026-10-26 Terra 发布](https://learn.chatgpt.com/docs/whats-new/october-26-30-2026)、[模型选型](https://developers.openai.com/api/docs/guides/model-selection)、[GPT-6 使用指导](https://developers.openai.com/api/docs/guides/latest-model)、[Work/Codex 模型与推理](https://learn.chatgpt.com/docs/models)。定位为 Terra 视觉理解和精确电脑操作、Sol 复杂编码与持续工作、Astra 最难的推理和专业工作；官方建议 Terra 从 medium 开始。本技能按用户本次明确要求，将 GPT-6.1 Terra 视觉专长配置改为 max；此前 medium 的单样例对照保留为历史证据，不作为 max 的性能证据。

三档通用路由、Terra 专长、代码行为审查下限与 Sol/max 的具体规则只维护在 SKILL.md 和 routing.json。Luna/xhigh 暂保留，缺少本机同条件证据时不宣称统一降档质量不变。官方定位不是本机性能排名；单次隔离界面对照只能证明该样例的识别和操作表现，耗时与可观测用量需另记，不能外推整体优势。

## 路由模型核验

2026-10-09 当前 `collaboration.spawn_agent` 工具 schema 包含 `gpt-6.1-sol`，支持 low/medium/high/xhigh/max/ultra；本地 catalog 记录这个客户端枚举，不据此证明底层模型身份或账户调用成功。[6.1 Sol 官方 API 页面](https://developers.openai.com/api/docs/models/gpt-6.1-sol) 列出 low/medium/high/xhigh/max，未列 ultra；API 文档与客户端枚举应分别记录，实际派发先检查当前工具，不能将其中一份目录当成所有入口通用。

[子代理文档](https://learn.chatgpt.com/docs/agent-configuration/subagents) 说明省略模型与推理设置会继承父代理，也建议按任务选择模型和可支持推理档。本 Skill 的 Luna/xhigh、6.1 Sol/high、Astra/high 与 deep_comparison→max 是本地策略，不宣称官方要求固定采用这些组合。模型能力档不是价格或身份认证；同类任务无需强制混用模型。执行与审计入口见 [派发协议](dispatch-protocol.md)。

## 官方来源与优先级

[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)；[Config basics](https://learn.chatgpt.com/docs/config-file/config-basic)；[Skills](https://learn.chatgpt.com/docs/build-skills)。

配置层级（高到低）：CLI override > 受信项目配置（近目录优先）> profile 文件 > user config > cloud defaults > system > builtin。子代理先解析 explicit spawn > agents defaults > parent，再加载 role 文件覆盖 model/effort，最后重施父级实时权限 override。当前 app 工具与公开源码可能不同版，实际 schema 优先。

源码核对 openai/codex@a6bd19261c30ce0a0225fe90e646822d29916f11：
- [child_config.rs](https://github.com/openai/codex/blob/a6bd19261c30ce0a0225fe90e646822d29916f11/codex-rs/core/src/agent/child_config.rs) 的 resolve/apply 路径。
- [spawn.rs](https://github.com/openai/codex/blob/a6bd19261c30ce0a0225fe90e646822d29916f11/codex-rs/core/src/tools/handlers/multi_agents_v2/spawn.rs) 只有 agent_type 选择角色，task_name 是路径。
- [config/mod.rs](https://github.com/openai/codex/blob/a6bd19261c30ce0a0225fe90e646822d29916f11/codex-rs/core/src/config/mod.rs) 与 [权限文档](https://learn.chatgpt.com/docs/permissions)：文件沙箱与外部工具权限分开。公开 main 的核查不等于本机二进制精确源码构建溯源。

## Superpowers 适配

参考 obra/superpowers@8ca22dba9a94f28898bbce59f2537ff4d87c747d，以下是独立适配规则，不修改/复制上游 Skill：

- [subagent-driven-development](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/subagent-driven-development/SKILL.md)：新上下文、明确边界、按难度选能力、避免便宜模型反复耗时。
- [systematic-debugging](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/systematic-debugging/SKILL.md)：调查→假设→最小验证→修复。
- [requesting-code-review](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/requesting-code-review/SKILL.md)：独立上下文审查真实改动。
- [verification-before-completion](https://github.com/obra/superpowers/blob/8ca22dba9a94f28898bbce59f2537ff4d87c747d/skills/verification-before-completion/SKILL.md)：完成结论以新鲜证据为依据。

按用户要求，不采用上游每子任务必审、最终必最强、五轮修复和自动清理工作目录等完整流程。这里普通任务交付边界统一审查、高风险提前审查、最多三轮，不做分支合并或清理。本文件记录来源；未来升级应复核差异，不能未经审查自动覆盖本地行为。
