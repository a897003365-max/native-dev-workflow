# 使用、验证与回滚

日常直接提出开发需求。全局 AGENTS 的短入口要求按需使用本 Skill；重开一个任务可刷新发现。当前会话可按绝对路径显式读取，不假设目录增加就热加载。也可输入 `$native-dev-workflow 修复……`。映射只影响新派发，不改变主 Agent 或已启动子代理。

本 Skill 自动发现开启（默认），不需要服务、数据库、依赖安装或角色变体。路由脚本是标准库 Python 3；`--role-config` 需要 Python 3.11+ 的 tomllib，建议使用 Python 3.11 或更新版本。

离线检查：
```sh
python3 -m unittest discover -s ~/.codex/skills/native-dev-workflow/tests -v
python3 ~/.codex/skills/native-dev-workflow/scripts/workflow.py ~/.codex/skills/native-dev-workflow/references/task.example.json
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py ~/.codex/skills/native-dev-workflow
```
这证明结构化路由规则，不证明主 Agent 语义判断必然正确或真实子代理模型已生效。真实冒烟须单独完成原生派发→Executor→新上下文 Reviewer→主 Agent 检查实际文件与测试，绑定快照。不要为覆盖全部模型组合批量调用。

若 Skill 校验器报 `ModuleNotFoundError: yaml`，这是校验工具的环境缺依赖，不是路由运行依赖。如果已安装 uv，可运行 `uv run --no-project --with pyyaml python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py ~/.codex/skills/native-dev-workflow`，使用临时依赖环境，避免修改全局 Python。

可配置 routing.json 中 families 下每系列的三个能力档和 max_fix_rounds。任务输入必须填主任务实际 `parent_model`，未知模型会拒绝派发；主任务切换系列后重新路由，升级保持同系列。修改映射必须先在当前工具/catalog 验证名称和推理支持，保留来源及运行证据。aliases 仅填已核验网关映射，不凭名称猜。无网关证据保持空映射、真实上游未知。

安装前备份将修改的本地规则。任务记录、配置备份和真实会话证据保留在仓库外，不公开凭据或个人路径；`references/evidence-path.txt` 为可选本地记录，已被 Git 忽略。验收证据绑定实际 commit 或文件哈希。

回滚：先对比当前 AGENTS 与备份；若有后续修改，仅移除 `BEGIN NATIVE-DEV-WORKFLOW` 到 `END NATIVE-DEV-WORKFLOW` 区块，不覆盖其他修改。将 `~/.codex/skills/native-dev-workflow` 移到 skills 目录外备存，并移走 `~/.agents/skills/native-dev-workflow` 符号链接（如果存在且指向该目录）。重开任务。保留 workflow-evidence 以便追溯。主配置、旧 Skills、模型/provider 未变。
