# round_031: V100 服务器 Python 命令行执行可靠性测试

**日期**: 2026-05-28
**目的**: 找出 AI 通过 SSH 在 V100 服务器上执行 Python 代码时 100% 可靠的方法

---

## 根因分析

### 服务器上有 3 个 Python

| Python 路径 | 版本 | 有 numpy/torch/gurobipy? | 备注 |
|-------------|------|--------------------------|------|
| `/usr/bin/python3` | 3.12.3 | 无（系统 Python） | 非登录 shell 的默认 python3 |
| `/opt/gurobi1203/linux64/bin/python3.11` | 3.11.4 | 只有 gurobipy（且需 LD_LIBRARY_PATH） | Gurobi 自带 |
| **`/opt/miniconda3/bin/python3`** | **3.13.5** | **全有** (numpy 2.2.5, torch 2.8.0+cu129, gurobipy 12.0.3) | **→ 这是正确的 Python** |

### 为什么 AI 执行会失败（三条根因）

1. **`python` 不存在。** 服务器只有 `python3`。AI 习惯写 `python -c "..."`，直接报 command not found。

2. **`python3` 指向系统 Python，没有科学计算包。**
   - `ssh V100` 启动的是非登录、非交互式 shell
   - `/etc/profile.d/conda.sh` 不会被 source（它只在 login shell 中生效）
   - 所以 `python3` → `/usr/bin/python3`（没有 numpy/torch）
   - SSH 还会把你本地 Mac 的 PATH 转发到服务器，进一步搅乱环境

3. **引号转义在多层级 shell 中必然出错。**
   - 本地 zsh 解析第一层引号 → 传给 SSH → 服务器 bash 解析第二层 → 传给 Python
   - 含 `"` 和 `'` 混用的代码几乎不可能正确转义

---

## 可靠执行方法（按推荐程度排序）

### 方法 1：Heredoc + 绝对路径（强烈推荐，最可靠）

适用于多行 Python 代码。**单引号引起来的 delimiter 确保 shell 不做任何展开，绝对路径确保使用正确的 Python。**

```bash
ssh V100 /opt/miniconda3/bin/python3 << 'PYEOF'
import sys, os, numpy as np, torch

os.chdir('/home/ycliu/projects/learn2dcomp')
sys.path.insert(0, '.')

import config
print(f'DATA_DIR: {config.DATA_DIR}')
print(f'numpy: {np.__version__}')
print(f'torch: {torch.__version__}')

# 任意复杂的代码都可以，包括 $ ` " ' 等特殊字符
data = {"key": "value", "nested": [1, 2, 3]}
print(data)
PYEOF
```

✅ **优点**：零转义问题；可以写任意复杂代码；shell 不做任何变量展开
✅ **验证结果**：通过

### 方法 2：-c + 双引号外层 + 单引号内层（推荐用于简单一行）

```bash
ssh V100 "/opt/miniconda3/bin/python3 -c \"print('hello'); import numpy; print(numpy.__version__)\""
```

✅ **优点**：简洁；适合单行
⚠️ **局限**：代码里不能有双引号（除非转义）；多行时排版混乱
✅ **验证结果**：通过

### 方法 3：-c + 单引号外层 + 双引号内层

```bash
ssh V100 '/opt/miniconda3/bin/python3 -c "print(\"hello\"); import numpy; print(numpy.__version__)"'
```

✅ **优点**：外部单引号防止本地 shell 展开 `$`
⚠️ **局限**：代码里的双引号需要全部转义成 `\"`，AI 容易搞错
✅ **验证结果**：基本通过（双引号多的代码容易写错转义）

### 方法 4：Login Shell（备选，但不推荐）

```bash
ssh V100 "/bin/bash -l -c \"python3 -c 'print(42)'\""
```

⚠️ **问题**：两层 `-c` 导致引号转义雪上加霜，AI 几乎一定会搞错

---

## 会失败的方法（禁止使用）

| 方法 | 为什么失败 |
|------|-----------|
| `ssh V100 python -c "..."` | `python` 不存在 |
| `ssh V100 python3 -c "import numpy"` | 系统 Python，无 numpy |
| `ssh V100 "python3 -c 'x = \"it\\'s fine\"'"` | 单引号转义地狱 |
| `ssh V100 python3 << EOF` (无引号) | shell 会对 `$` 做变量展开 |
| `ssh V100 /opt/gurobi1203/linux64/bin/python3.11 -c "..."` | 无 numpy/torch，gurobipy 还要额外设 LD_LIBRARY_PATH |

---

## 黄金法则

```
1. 永远用绝对路径 /opt/miniconda3/bin/python3，别用 python3 或 python
2. 多行代码用 heredoc << 'PYEOF'（delimiter 必须加引号）
3. 一行代码用 -c，外层双引号、内层单引号
4. cd 到项目目录后再 import config（或在代码里 os.chdir() + sys.path.insert()）
```

---

## 测试覆盖

| 测试项 | 结果 |
|--------|------|
| `/usr/bin/python3 -c` 基本执行 | ✅ |
| `/usr/bin/python3 -c import numpy` | ❌ 无 numpy |
| `/opt/gurobi1203/.../python3.11 -c import gurobipy` | ❌ 缺 LD_LIBRARY_PATH |
| `/opt/gurobi1203/.../python3.11` + LD_LIBRARY_PATH | ✅ gurobipy 可用 |
| `/opt/miniconda3/bin/python3 -c` | ✅ 全包可用 |
| `/opt/miniconda3/bin/python3 << 'PYEOF'` | ✅ 完美（黄金标准）|
| `/opt/miniconda3/bin/python3 -c "..'.."` | ✅ |
| `/opt/miniconda3/bin/python3 -c '..\"..'` | ✅ |
| `/bin/bash -l -c` login shell | ✅ 但引号复杂 |
| 单引号内部嵌套转义单引号 | ❌ bash 解析失败 |
| `python` (不带版本号) | ❌ command not found |
| 默认 `python3` (非登录 shell) | ⚠️ 能跑但无科学计算包 |

---

## 给下一轮的建议

1. AI agent 如果要执行 Python 代码，必须明确写出 `/opt/miniconda3/bin/python3`，不能依赖 `python3` 的 PATH 解析
2. 优先使用 heredoc 而非 `-c`，避免引号转义问题
3. 可以在本地 `~/.ssh/config` 的 V100 Host 段加 `SetEnv` 或者在服务器 `~/.bashrc` 里加 conda 初始化——但这可能会影响其他行为，不建议随意改
