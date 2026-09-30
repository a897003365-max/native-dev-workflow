# native-dev-workflow

用于 Codex 的轻量多 Agent 开发 Skill：主 Agent 按任务语义评估难度、风险与验证条件，按需委派原生子代理，独立审查后验收。

## 按平台选择版本

在目标目录不存在时执行；已有安装请先检查改动并备份，不覆盖现有文件。

| 版本入口 | 命令环境 | 共享发现方式 |
| --- | --- | --- |
| [Windows 版安装与验证](references/windows.md) | PowerShell，`python` | NTFS Junction 目录联接 |
| [macOS 版安装与验证](references/macos.md) | zsh/bash，`python3` | `ln -s` 符号链接 |

两版明确分开安装说明、路径处理和验证命令，共用 `SKILL.md`、`routing.json`、路由脚本和测试，避免两套规则逐渐不一致。Skill 按实际主机选择平台入口；不要在 macOS 执行 PowerShell，也不要把 Windows 路径传入 macOS shell。

显式调用：`$native-dev-workflow 帮我实现……`。

若希望普通开发需求自动采用，可自行在适用的 `AGENTS.md` 中加入简短入口，指向安装目录的 `SKILL.md`。不要替换整个全局规则文件。新任务加载后确认 Skill 已被发现。

## 工作方式

- 极小任务直接处理；有独立交付价值时才委派。
- L1/L2/L3 难度、失败风险和验证环境分别判断。
- 主模型与子代理保持同系列；职责与模型能力档分开。
- 每次派发 message 展开共同行为、一个角色指令和任务契约；task_name 不代表角色已生效。
- 独立 Reviewer 检查实际产物，主 Agent 负责最终整合与验收。
- 同根因连续两次失败停止原方案，默认最多三轮自动修复。

当前示例映射（使用前核实当前工具支持情况）：

| 主模型系列 | 经济档 | 标准档 | 强能力档 |
| --- | --- | --- | --- |
| 5.6 | Luna / xhigh | Terra / medium | Sol / high |
| 6 | Luna / xhigh | Sol / high | Astra / high |

映射位于 `routing.json`，不是 Codex 原生配置文件。速度默认跟随主模型，只有 `gpt-6-luna` 默认请求 Fast；当前原生工具不支持逐子代理速度参数，记录为未应用/未知，不能据此声称已验证继承或已开启加速。只读角色也不代表强制权限隔离。

## 检查

路由脚本使用 Python 标准库，不发模型请求，不创建 Agent。

执行对应平台文档中的“运行路由与验证”。Windows 版使用 `python -X utf8 -B`，macOS 版使用 `python3 -X utf8 -B`。两版均要求 Python 3.11+；不要将命令名存在当成运行环境可用的证明。

Windows 下的路由测试已通过；macOS 文档已完成静态检查，尚未在真实 Mac 上执行安装和验证。

`parent_model` 必须来自主任务实际运行配置；示例 JSON 仅用于演示。离线路由检查不能替代真实子代理调用或业务验收。

完整规则见 [SKILL.md](SKILL.md)，安装验证与回滚见 [操作说明](references/operations.md)，官方文档、Superpowers 和角色参考来源见 Skill 与 [来源记录](references/environment.md)。不附带或安装参考仓库的角色 TOML，不修改全局权限。
