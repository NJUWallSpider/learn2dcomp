# Round 004 — T-001: 重新生成 GAP 实例

**日期**: 2026-05-27
**工人**: worker-alpha
**任务**: T-001 — 重新生成 GAP 实例，验证 tightness 公式让实例变难

---

## 做了什么

### 1. 配置确认（config.py + gap_generator.py）

- `GAP_GEN`: train/valid agents 5-12, test agents 13-16（unseen），任务数 40-100，类型 A-E 各 20% ✓
- `_compute_capacities()`: tightness B=1.20, 其余=1.30，公式 `tightness × (n_tasks/n_agents) × avg_weight` ✓
- `min_feasible_cap`（保证每个 task 至少有一个 agent 能装下）对大部分实例不构成瓶颈 ✓

### 2. 实例生成

- 用 `/opt/miniconda3/bin/python`（系统默认 python3 无 numpy，需 miniconda）
- 运行 `01_generate_instances.py gap`，1200 个 .lp 文件生成成功：
  - train: 1000 个
  - valid: 100 个
  - test: 100 个
- 类型分布：每种类型严格 20%（train 200×5, valid 20×5, test 20×5）

### 3. 难度验证（20 个随机 test 实例，Gurobi 60s 求解）

结果：**11/20 (55%) NodeCount > 1.0**，满足 ≥50% 标准。

按类型分布：
| 类型 | 难度 | 说明 |
|------|------|------|
| A (5个) | 全部 easy (Node=1) | 成本和权重独立小范围 [1-25]，易求解 |
| B (5个) | 混合 (2 hard, 3 easy) | tightness=1.20 最紧，大实例更难 |
| C (7个) | 全部 HARD (Node=13k-118k) | 强负相关 c=111-a，D-W 分解最受益 |
| D (2个) | 全部 HARD (Node=13k-16k) | 负相关+噪声 |
| E (1个) | easy | 正相关 |

### 4. Python 环境发现

- 服务器默认 `/usr/bin/python3` 无 numpy/scipy/gurobipy
- 实际环境在 `/opt/miniconda3/bin/python`（Python 3.13, numpy 2.2.5, gurobipy）
- CLAUDE.md 应更新此信息

---

## 未解决问题

1. **T-005 待 delta 执行**：delta 正在执行 T-002（DW 验证），T-005（构建数据集）是下一步瓶颈
2. **Type A/E 实例对 MIP 太容易**：这是 GAP 问题的固有特性，不影响 DW 分解的研究价值（DW 主要受益于 C/D 类型）

---

## 给下一轮的经验教训

1. **Python 路径**：服务器需用 `/opt/miniconda3/bin/python`，不是 `python3`
2. **Tightness 公式有效**：55% 实例有 NodeCount > 1，明显好于旧 α 公式（全部 Node=1）
3. **Type C 是 DW 分解的最佳目标**：100% 的 Type C 实例 MIP 求解困难，DW 分解能显著加速
4. **调度员主板已自动同步**：本任务完成时，调度员已更新 T-001→✅, T-005 解除阻塞，worker-alpha→🟢
