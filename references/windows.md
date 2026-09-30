# Windows 版安装与验证

仅适用于 Windows / PowerShell。macOS 使用 [macOS 版](macos.md)，两版共用路由和角色规则，不共用平台命令。需要 Git、Python 3.11+；先确认实际 Python 可运行，避免仅命中 WindowsApps 别名。

## 首次安装

仅在两个目标位置都不存在时执行；已有文件或链接先检查并备份，不覆盖。

```powershell
$ErrorActionPreference = 'Stop'
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillRoot = Join-Path $codexRoot 'skills/native-dev-workflow'
$sharedRoot = Join-Path $env:USERPROFILE '.agents/skills'
$sharedSkill = Join-Path $sharedRoot 'native-dev-workflow'
if ((Get-Item -LiteralPath $skillRoot -Force -ErrorAction SilentlyContinue) -or (Get-Item -LiteralPath $sharedSkill -Force -ErrorAction SilentlyContinue)) { throw '目标已存在；先检查和备份。' }
git clone https://github.com/a897003365-max/native-dev-workflow.git $skillRoot
if ($LASTEXITCODE -ne 0) { throw '克隆失败，停止安装。' }
New-Item -ItemType Directory -Path $sharedRoot -Force | Out-Null
New-Item -ItemType Junction -Path $sharedSkill -Target $skillRoot
```

安装后核验共享入口的 `LinkType` 为 `Junction`、`Target` 指向主目录，且两个入口的 `SKILL.md` SHA-256 相同。新任务加载后再确认 Skill 发现状态。

## 路径与运行方式

- 主版本：`$env:CODEX_HOME/skills/native-dev-workflow`；未设置 `CODEX_HOME` 时使用 `$env:USERPROFILE/.codex/skills/native-dev-workflow`。
- 共享发现路径：`$env:USERPROFILE/.agents/skills/native-dev-workflow`，通过 NTFS Junction 指向主版本，无独立副本或同步脚本。主版本修改后共享入口立即读取相同文件。迁移主版本位置时重新核验联接目标。
- 使用 PowerShell 的 `Join-Path`、`Test-Path -LiteralPath` 和带引号的路径；不执行 `ln -s`、`mkdir -p` 或将 Windows 路径送入 WSL Bash。
- Python 3.11+；本机默认编码为 GBK，命令统一使用 `python -X utf8 -B`。`python3` 可能仅是 WindowsApps 别名，不能凭存在判断可运行。
- JSON 任务文件保存为 UTF-8 无 BOM。PowerShell 7 可使用 `Set-Content -Encoding utf8NoBOM`；Windows PowerShell 5.1 使用 `[IO.File]::WriteAllText($taskPath, $json, [Text.UTF8Encoding]::new($false))`。
- 从任意工作目录运行时，脚本、测试目录和任务文件都传绝对路径。脚本默认根据自身位置读取 `routing.json`。
- 普通路由只用标准库；Skill 格式校验通过 `uv run --no-project --with pyyaml python -X utf8 -B ...` 提供隔离依赖。

## 原生委派边界

- 每次使用重新读取当前 `collaboration.spawn_agent` schema；`routing.json` 只是本 Skill 的参数建议，不能代替当前模型目录，也不能把主配置默认模型当作实际主模型。
- 并发上限以当前工具为准；主 Agent 和已有活动子代理均占名额，不将某次会话的上限写成所有 Windows 环境的能力。
- 不用 `create_thread` 代替内部子代理。模型覆盖使用 `fork_turns="none"`，完整历史 fork 不覆盖模型和推理档。
- 当前没有逐子代理 Fast、角色选择器或只读沙箱参数。Fast 仅是未应用的偏好；角色提示不能形成权限隔离。高风险审查继续遵守主 Skill 的边界要求。
- 读取当前会话的沙箱、审批策略和工具 schema；不预设完整访问，也不添加当前工具禁止的提权参数，不为运行本 Skill 修改全局权限。
- 若主任务实际模型无法观测，报告未知并暂停依赖该身份的路由；示例 `parent_model` 不可用作本机身份凭证。

## 来源与升级

本地适配基于 `a897003365-max/native-dev-workflow` commit `9f72a3cde589177dd6dbdfe4bd3b54d2b766e12c`。差异范围包括 `SKILL.md`、`README.md`、`references/operations.md`、本文件、`routing.json`，以及路由脚本和测试中的速度偏好默认值解析；升级时一并比较这些本地调整。

升级时先保留当前安装快照，再将新上游下载到单独暂存目录，对比上述文件，保留仍适用的 Windows 命令和工具约束。不要用上游文件直接覆盖本地适配。以两条发现路径的 `SKILL.md` SHA-256 一致、目录联接目标正确、操作说明中的测试与格式校验通过作为安装验证；这不等同于真实业务任务和各模型调用验证。

## 运行路由与验证

从任何目录执行前先定义路径；Python 命令失败时读取错误并停止依赖步骤。

```powershell
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillRoot = Join-Path $codexRoot 'skills/native-dev-workflow'
python -X utf8 -B -m unittest discover -s (Join-Path $skillRoot 'tests') -v
python -X utf8 -B (Join-Path $skillRoot 'scripts/workflow.py') (Join-Path $skillRoot 'references/task.example.json')
```

第二条命令只验证示例路由。实际委派时，将最后一个参数替换为本任务已填写的 JSON 绝对路径。

若已安装 `uv` 且本机具有系统 `skill-creator`，使用隔离依赖进行格式校验：

```powershell
uv run --no-project --with pyyaml python -X utf8 -B (Join-Path $codexRoot 'skills/.system/skill-creator/scripts/quick_validate.py') $skillRoot
```

记录真实退出码；示例参数、模型名或工具描述不能证明实际调用成功。回滚与共同验收要求见 [操作说明](operations.md)。
