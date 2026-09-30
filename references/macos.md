# macOS 版安装与验证

仅适用于 macOS 的 zsh/bash。Windows 使用 [Windows 版](windows.md)，两版共用路由和角色规则，不共用平台命令。需要 Git、Python 3.11+；先确认 `git --version`、`python3 --version` 可运行，不假定系统已经提供所需版本。

若 `python3 --version` 低于 3.11，先检查已有的合适解释器。Apple silicon 上可检查 `/opt/homebrew/bin/python3.12`，确认版本后将下文 `python3`（包括 uv 的 `--python` 参数）替换为该绝对路径；不要假定该路径一定存在，也不必改动系统 Python 或全局 PATH。

## 首次安装

主目录为 `${CODEX_HOME:-$HOME/.codex}/skills/native-dev-workflow`，共享发现入口为 `$HOME/.agents/skills/native-dev-workflow`。只保留一份技能，通过符号链接共享；已有目录、文件或失效链接都应先检查并备份。

下面代码在子 shell 中执行，失败即停止，不改动当前终端的选项：

```sh
(
  set -eu
  codex_root="${CODEX_HOME:-$HOME/.codex}"
  skill_root="$codex_root/skills/native-dev-workflow"
  shared_root="$HOME/.agents/skills"
  shared_skill="$shared_root/native-dev-workflow"
  if [ -e "$skill_root" ] || [ -L "$skill_root" ] || [ -e "$shared_skill" ] || [ -L "$shared_skill" ]; then
    printf '%s\n' '目标已存在；先检查和备份。' >&2
    exit 1
  fi
  mkdir -p "$codex_root/skills" "$shared_root"
  git clone https://github.com/a897003365-max/native-dev-workflow.git "$skill_root"
  ln -s "$skill_root" "$shared_skill"
)
```

`CODEX_HOME` 若自定义，应为实际绝对路径。安装后用 `test -L` 和 `readlink` 核验共享入口指向主目录，并比较两个入口的 `SKILL.md` 哈希；macOS 可用 `shasum -a 256`。不要使用 macOS 系统工具未必提供的 `readlink -f`。新任务加载后再确认 Skill 发现状态。

## 路径与权限

- 引用所有 shell 路径变量，保留文件名大小写，不假定磁盘一定忽略大小写。
- 使用 `python3 -X utf8 -B`；JSON 写成 UTF-8 无 BOM。不要运行 PowerShell、`New-Item -ItemType Junction` 或 Windows 盘符路径。
- 主目录修改后，符号链接读取相同文件，无独立副本需要同步；移动主目录前核验并更新链接目标。
- 当前原生工具、模型目录、并发上限、沙箱与外部写入权限都须实时核验，不沿用 Windows 会话状态；只读提示不等于强制只读隔离。
- 模型、速度偏好、职责、失败预算及审查要求以 [SKILL.md](../SKILL.md) 为唯一共同来源。macOS 不另外覆盖模型、速度或推理档，也不修改全局权限。

## 运行路由与验证

```sh
codex_root="${CODEX_HOME:-$HOME/.codex}"
skill_root="$codex_root/skills/native-dev-workflow"
python3 -X utf8 -B -m unittest discover -s "$skill_root/tests" -v
python3 -X utf8 -B "$skill_root/scripts/workflow.py" "$skill_root/references/task.example.json"
```

第二条命令只验证示例路由。实际委派时，将最后一个参数替换为本任务已填写的 JSON 绝对路径。每条验证分别检查退出码，前一步失败时停止依赖步骤。

若已安装 `uv` 且本机具有系统 `skill-creator`，使用隔离依赖进行格式校验：

```sh
uv run --no-project --with pyyaml --python python3 python -X utf8 -B "$codex_root/skills/.system/skill-creator/scripts/quick_validate.py" "$skill_root"
```

回滚时先确认共享入口确为指向主目录的符号链接，只移除链接本身；将主目录移到技能发现路径外备存，不递归删除链接指向的目录。共同验收和升级要求见 [操作说明](operations.md)。

2026-09-30 在真实 macOS arm64 上验证：现有安装从 `9f72a3c` 快进更新到 `3822e56`；共享入口的符号链接目标与两入口 SKILL.md SHA-256 一致。使用已安装的 Python 3.12.13，19 项路由测试、示例路由与隔离 PyYAML 格式校验均通过。默认 `python3` 为 3.9.6，因此完整功能应使用已核验的 3.11+ 解释器。

本次是现有安装更新验证，未执行首次克隆安装，也未重跑真实 Executor/Reviewer 冒烟；不据此证明模型、Fast 或沙箱实际生效。
