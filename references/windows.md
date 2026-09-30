# Windows 本地适配

## 路径与运行方式

- 主版本：`$env:CODEX_HOME/skills/native-dev-workflow`；未设置 `CODEX_HOME` 时使用 `$env:USERPROFILE/.codex/skills/native-dev-workflow`。
- 共享发现路径：`$env:USERPROFILE/.agents/skills/native-dev-workflow`，通过 NTFS Junction 指向主版本，无独立副本或同步脚本。主版本修改后共享入口立即读取相同文件。迁移主版本位置时重新核验联接目标。
- 使用 PowerShell 的 `Join-Path`、`Test-Path -LiteralPath` 和带引号的路径；不执行 `ln -s`、`mkdir -p` 或将 Windows 路径送入 WSL Bash。
- Python 3.11+；本机默认编码为 GBK，命令统一使用 `python -X utf8 -B`。`python3` 可能仅是 WindowsApps 别名，不能凭存在判断可运行。
- JSON 任务文件保存为 UTF-8 无 BOM。PowerShell 7 可使用 `Set-Content -Encoding utf8NoBOM`；Windows PowerShell 5.1 使用 `[IO.File]::WriteAllText($taskPath, $json, [Text.UTF8Encoding]::new($false))`。
- 从任意工作目录运行时，脚本、测试目录和任务文件都传绝对路径。脚本默认根据自身位置读取 `routing.json`。
- 普通路由只用标准库；Skill 格式校验通过 `uv run --no-project --with pyyaml python -X utf8 -B ...` 提供隔离依赖。

## 原生委派边界

- 每次使用重新读取当前 `collaboration.spawn_agent` schema；`routing.json` 只是本 Skill 的参数建议。当前允许的模型/推理组合与原仓库映射一致，保留原映射，不把主配置默认模型当作当前实际主模型。
- 安装环境公开的并发上限为 4 个活动 Agent，包含主 Agent；因此最多同时安排 3 个子代理，已有活动子代理也占名额。其他会话以实时工具限制为准。
- 不用 `create_thread` 代替内部子代理。模型覆盖使用 `fork_turns="none"`，完整历史 fork 不覆盖模型和推理档。
- 当前没有逐子代理 Fast、角色选择器或只读沙箱参数。Fast 仅是未应用的偏好；角色提示不能形成权限隔离。高风险审查继续遵守主 Skill 的边界要求。
- 当前会话是完整文件访问权限，且不支持命令审批提权参数；不添加 `sandbox_permissions`、不修改全局权限来运行本 Skill。
- 若主任务实际模型无法观测，报告未知并暂停依赖该身份的路由；示例 `parent_model` 不可用作本机身份凭证。

## 来源与升级

本地适配基于 `a897003365-max/native-dev-workflow` commit `9f72a3cde589177dd6dbdfe4bd3b54d2b766e12c`。差异范围包括 `SKILL.md`、`README.md`、`references/operations.md`、本文件、`routing.json`，以及路由脚本和测试中的速度偏好默认值解析；升级时一并比较这些本地调整。

升级时先保留当前安装快照，再将新上游下载到单独暂存目录，对比上述文件，保留仍适用的 Windows 命令和工具约束。不要用上游文件直接覆盖本地适配。以两条发现路径的 `SKILL.md` SHA-256 一致、目录联接目标正确、操作说明中的测试与格式校验通过作为安装验证；这不等同于真实业务任务和各模型调用验证。
