# Project: learn2dcomp — GNN-based MIP Decomposition

---

以下准则适用于本项目中**每一个** Claude Code 会话。

### 原则 0：实事求是，不胡乱推测

- **修改前先验证**：任何对代码逻辑的改动，必须先阅读相关文件、追踪数据流、
  确认根因，再动手改。不允许"可能"、"应该"式的推测性修改。
- **用证据说话**：说一个 bug 存在，就要能指出具体哪个文件、哪一行、什么条件
  下触发。说一个修复有效，就要能给出验证结果。
- **怀疑自己的修复**：改完代码后，主动考虑"这个改动在什么情况下会出错"。
  如果答不上来，说明还没理解透。
- **宁可多读少改**：花 20 分钟读代码 + 1 分钟改一行，好过花 1 分钟猜 + 20
  分钟来回修。在没读懂之前，不瞎改。

### 原则 1：每一轮都要写轮次报告

- **轮次结束**：当你完成了一组相关的任务，在 `.claude/reports/` 下写一个报告
  文件，命名格式为 `round_XXX_简述.md`（编号递增）。
- **报告内容**：本轮做了什么、发现了哪些问题、还有哪些问题未解决、给下一轮的
  经验教训。要具体，不要写空话。

### 原则 2：每一轮启动前先读上一轮报告

- **启动时**：检查 `.claude/reports/` 目录，找到编号最大的报告文件并阅读。
- 如果报告中提到了未解决的问题，优先处理。

### 原则 3：基础设施规则

- **编辑本地文件**：所有文件修改都在本地进行，由 mutagen 自动同步到服务器。
  禁止直接在服务器上编辑文件。
- **代码在服务器运行**：所有 Python 脚本、训练、评估均通过 `ssh V100` 在
  服务器上执行。服务器项目路径：`/home/ycliu/projects/learn2dcomp`。
- **长时间任务用 tmux**：任何预计运行超过 2 分钟的任务，必须在 tmux 会话中
  启动。
- **运行前确认同步**：如果刚修改过文件，先确认 mutagen 已同步再运行。
- **服务器 git 状态忽略**：服务器的 git tree 一直显示 `origin`，这是已知问题，
  不影响文件同步和执行。不要试图修理它。

### 原则 4：项目知识

- **config.py 是唯一配置来源**：所有参数（训练超参、路径、GCG 参数等）都在
  `config.py` 中。不要在脚本里硬编码参数。
- **MPS 是数据唯一来源**：Step 7 的 GCG 求解从 MPS 文件提取数据（`gnn_to_dec` 通过
  Gurobi 读取 MPS 推断 constraint-to-block 关系），不是从 LP 文件正则解析。
- **GAP 容量公式**：当前使用 tightness 公式（见 `solvers/gap_generator.py`），
  不是旧的 α 公式。tightness ∈ {0.50（仅 Type B）, 1.30}。

### 原则 5：代码修改规范

- **不引入半成品**：不改一半留一半。
- **不为了"以后可能需要"而改**：只解决当前明确的问题。
- **清理调试代码**：如果写了临时调试脚本，在不再需要时删除它们。
- **Commit message 写清楚 why**：不只写 what，要写为什么改。

---

## 绝对安全 — 零容忍（最高优先级）

### Tier 1 — 绝对禁止

| # | 规则 | 说明 |
|----|------|------|
| R1 | 禁止 `git push --force` | 任何分支、任何情况下不得 force push |
| R2 | 禁止 `git reset --hard` | 不得丢弃未提交修改 |
| R3 | 禁止 `git branch -D` | 不得强制删除分支 |
| R4 | 禁止 `rm -rf` / `rm -r` | 删除目录必须先 `ls -la` 确认内容 |
| R5 | 禁止修改 git config | 不得运行任何 `git config` 命令 |
| R6 | 禁止跳过 hooks | 不得使用 `--no-verify`、`--no-gpg-sign` |
| R7 | 禁止 `git commit --amend` 已推送的 commit | 只能 amend 未推送的本地 commit |
| R8 | 禁止操作远程仓库 | 不得添加/删除/重命名 remote |
| R9 | 禁止在服务器上执行删除命令 | `rm`、`mv`（覆盖）、`> file`、`chmod`、`chown` 一律禁止在 `ssh V100` 中执行 |
| R10 | 禁止 `git checkout -- .` / `git restore .` / `git clean -f` | 不得丢弃工作区修改 |

### Tier 2 — 数据资产保护

以下文件/目录**严禁删除、覆盖、移动**：

| 受保护对象 | 路径模式 | 原因 |
|------------|----------|------|
| MPS 实例文件 | `data/mps/**/*.mps` | 唯一数据来源，不可再生 |
| 训练好的模型 | `models/*.pth`, `models/*.pt` | 训练耗时数小时 |
| 数据集文件 | `data/*.pt`, `data/*.pkl`, `data/*.json` | 从 MPS 构建，不可再生 |
| 配置文件 | `config.py` | 唯一配置来源 |
| 轮次报告 | `.claude/reports/*.md` | 项目知识积累 |
| 源代码 | `*.py`, `solvers/*.py` | 不可恢复 |

**删除任何文件前必须做 3 件事**：
1. `ls -la <文件路径>` — 确认文件存在且是你要删的文件
2. 对照上表，确认该文件不在受保护列表中
3. 如果是 `.py` 文件，用 `grep` 确认没有其他文件 `import` 它

### Tier 3 — 服务器安全

- 永远不在服务器上执行破坏性操作：`rm`、`mv`（覆盖）、`> file`、`dd`、`chmod`、`chown`
- tmux 会话结束必须 `exit`，不残留空会话
- 不杀别人的进程：`kill`、`pkill`、`killall` 禁止使用
- 不修改服务器配置：`.bashrc`、`.profile`、`crontab`、Python 环境

### Tier 4 — 操作前验证（三步安检）

```
第 1 步 — 确认目标：我要改什么？哪个文件、哪个函数、哪一行？
第 2 步 — 确认影响：改了这个会影响什么？其他哪些文件依赖它？
第 3 步 — 确认安全：改错了怎么恢复？有 git 备份吗？
```

---

## 定期 Commit

- 每轮任务结束后 commit，格式：`round_XXX: <简述>`
- 至少每小时一次 commit
- commit 前先 review：`git diff --staged`
- 只 commit 相关文件：用 `git add <具体文件>` 而不是 `git add -A` 或 `git add .`

---

## Infrastructure: local edit + remote execution

本项目使用 **mutagen** 实时同步本地 Mac 与 GPU 服务器。

1. **本地编辑文件** — mutagen 自动同步到服务器
2. **服务器运行代码** — `ssh V100`（`ycliu@v100`），项目路径 `/home/ycliu/projects/learn2dcomp`
3. 服务器 git tree 显示 `origin` 而非实际分支 — 忽略，不影响同步和执行

### 连接服务器

```
ssh V100
```

### 正确 Python

服务器有 3 个 Python，**只用 `/opt/miniconda3/bin/python3`（3.13.5）**——有 numpy、torch、gurobipy：

| Python | 有 numpy/torch/gurobipy? |
|--------|--------------------------|
| `/opt/miniconda3/bin/python3` (3.13.5) | **Yes** |
| `/usr/bin/python3` (3.12.3) | No |
| `/opt/gurobi1203/linux64/bin/python3.11` | 只有 gurobipy |

不要用裸 `python3` / `python`，非登录 shell 找不到正确环境。

### 运行方式

**多行 Python（推荐 — 零转义问题）**：
```bash
ssh V100 /opt/miniconda3/bin/python3 << 'PYEOF'
import os
os.chdir('/home/ycliu/projects/learn2dcomp')
import config
# 任意复杂代码
PYEOF
```

**单行 Python**：
```bash
ssh V100 "/opt/miniconda3/bin/python3 -c \"...\""
```

**长时间任务（>2 min）— tmux**：
```bash
ssh V100 -t "tmux new -s <session_name>"
```
在 tmux 内：
```bash
cd ~/projects/learn2dcomp
/opt/miniconda3/bin/python3 02_generate_dataset.py --problem gap --jobs 32
```
重新连接：`ssh V100 -t "tmux attach -t <session_name>"`

### 常用命令

| 任务 | 命令 |
|------|------|
| 检查同步状态 | `mutagen sync list` |
| 快速远程检查 | `ssh V100 "/opt/miniconda3/bin/python3 -c \"print('hello')\""` |
| 生成实例 | tmux → `cd ~/projects/learn2dcomp && /opt/miniconda3/bin/python3 01_generate_instances.py gap` |
| 构建数据集 | tmux → `cd ~/projects/learn2dcomp && /opt/miniconda3/bin/python3 02_generate_dataset.py --problem gap --jobs 32` |
| 训练模型 | tmux → `cd ~/projects/learn2dcomp && /opt/miniconda3/bin/python3 03_train_gnn.py` |
| 生成 GNN 分解 | tmux → `cd ~/projects/learn2dcomp && /opt/miniconda3/bin/python3 06_eval_instances.py --problem gap` |
| 求解（3-branch） | tmux → `cd ~/projects/learn2dcomp && /opt/miniconda3/bin/python3 07_solve_decomposition.py --problem gap --split test` |

### 环境

- 正确 Python：`/opt/miniconda3/bin/python3`（3.13.5）— 有 numpy、torch、gurobipy
- 服务器上 GCG solver 可用：`gcg`
- 不需要 virtualenv — 服务器环境已预配置
