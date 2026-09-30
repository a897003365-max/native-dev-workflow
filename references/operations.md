# 使用、验证与回滚

安装后下一轮可用；新任务加载时确认发现列表。默认允许按描述自动选择，也可输入 `$native-dev-workflow 修复……`。本次安装没有向全局 AGENTS 添加强制入口。当前会话可按绝对路径显式读取，不把文件存在当作发现已验证。映射只影响新派发，不改变主 Agent 或已启动子代理。

本 Skill 自动发现开启（默认），不需要服务、数据库、依赖安装或角色变体。路由脚本是标准库 Python 3；`--role-config` 需要 Python 3.11+ 的 tomllib，建议使用 Python 3.11 或更新版本。

离线检查：
```powershell
$codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
$skillRoot = Join-Path $codexRoot 'skills/native-dev-workflow'
python -X utf8 -B -m unittest discover -s (Join-Path $skillRoot 'tests') -v
python -X utf8 -B (Join-Path $skillRoot 'scripts/workflow.py') (Join-Path $skillRoot 'references/task.example.json')
uv run --no-project --with pyyaml python -X utf8 -B (Join-Path $codexRoot 'skills/.system/skill-creator/scripts/quick_validate.py') $skillRoot
```
这证明结构化路由规则，不证明主 Agent 语义判断必然正确或真实子代理模型已生效。真实冒烟须单独完成原生派发→Executor→新上下文 Reviewer→主 Agent 检查实际文件与测试，绑定快照。不要为覆盖全部模型组合批量调用。

Skill 校验器需要 PyYAML，而路由运行不需要。上述 `uv run --no-project --with pyyaml` 为校验器提供隔离依赖，不修改全局 Python。Windows 默认 GBK 会导致中文 JSON 读取失败，所有 Python 入口都保留 `-X utf8`；不要修改系统区域或全局编码配置。

可配置 routing.json 中 families 下每系列的三个能力档和 max_fix_rounds。任务输入必须填主任务实际 `parent_model`，未知模型会拒绝派发；主任务切换系列后重新路由，升级保持同系列。修改映射必须先在当前工具/catalog 验证名称和推理支持，保留来源及运行证据。aliases 仅填已核验网关映射，不凭名称猜。无网关证据保持空映射、真实上游未知。

安装前备份将修改的本地规则。任务记录、配置备份和真实会话证据保留在仓库外，不公开凭据或个人路径；`references/evidence-path.txt` 为可选本地记录，已被 Git 忽略。验收证据绑定实际 commit 或文件哈希。

回滚：本次未修改全局 AGENTS 或主配置。先检查 `.agents/skills/native-dev-workflow` 的 `LinkType` 和 `Target`，确认是指向主版本的目录联接后，只移除联接本身，不递归删除目标。再将主版本移到 skills 目录外备存；操作前确认绝对路径范围，避免覆盖已有备份。重开任务，并保留安装报告与文件哈希。若以后自行添加 AGENTS 入口，只移除对应入口，不覆盖其他规则。目录联接及升级说明见 [Windows 本地适配](windows.md)。
