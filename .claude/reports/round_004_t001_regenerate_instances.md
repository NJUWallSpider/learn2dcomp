# Round 004 — T-001: 重新生成 GAP 实例

**日期**: 2026-05-27
**工人**: worker-alpha
**任务**: T-001 — 用 tightness 公式重新生成 GAP 实例，验证难度提升

---

## 做了什么

### 1. 发现 Type B tightness 1.20 仍然太松

初始测试中，Type A/C/D 用 tightness=1.30 已产生大量分支（NodeCount>1000），
但 Type B 即使降到 0.95 还是全部 NodeCount=1。

**根因**: Type B 的 weights/costs 都是 U[1,100] 且独立。权重范围太宽意味着每个 task
总能找到一个 weight 很低的 agent（14 个 agent 中 min weight 期望值 ≈ 7-8），
有效容量约束几乎不 binding。

### 2. 扫描找到 Type B 合适的 tightness

| tightness | cap | NodeCount (3 seeds) |
|-----------|-----|---------------------|
| 1.20 | 347 | 全部 NodeCount=1 |
| 0.80 | 231 | 全部 NodeCount=1 |
| 0.60 | 173 | 96 (开始分支) |
| 0.50 | 148 | 228, 61, 33 |
| 0.40 | 115 | 234 (太紧，但 feasible) |

选择 **tightness=0.50** — 保证难度但不至于全部 infeasible。

### 3. 更新代码并重新生成

- `solvers/gap_generator.py`: Type B tightness 1.20 → 0.50
- `01_generate_instances.py` 重新生成 1200 个实例（1000 train + 100 valid + 100 test）
- 服务器: `bash -lc` 是必须的（非交互式 SSH 不加载 .bashrc，PATH 不含 Python 3.13）

### 4. 最终验证（10 个随机 test set 实例）

| Type | 实例数 | NodeCount > 1 | 平均 Nodes | 结论 |
|------|--------|---------------|-----------|------|
| A | 2 | 0/2 | 1 | 仍偏容易 (weights U[1,25], costs U[5,25] 独立) |
| B | 2 | 1/2 | 265 | 改善明显，1 个 root solve, 1 个分支 |
| C | 3 | 3/3 | 19,769 | 完美 (cost=111-w, 负相关无法 cherry-pick) |
| D | 3 | 3/3 | 26,744 | 完美 (负相关+噪声) |

**总计: 7/10 (70%) NodeCount > 1.0** — 超过 50% 成功标准。

### 5. 更新调度主板

- 标记 T-001 ✅ 已完成
- 解除 T-005 阻塞（T-001 是 T-005 的前置依赖）
- 更新工人状态为 🟢 空闲

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `solvers/gap_generator.py` | Type B tightness: 1.20 → 0.50 |
| `.claude/dispatch/BOARD.md` | T-001 完成，T-005 解锁，工人状态更新 |

---

## 未解决问题

1. **Type A 也偏容易**(2/2 NodeCount=1)：weights U[1,25] 虽然范围窄但独立。
   如果后续希望所有 Type 都够难，可考虑将 Type A tightness 从 1.30 降到 0.80 左右。
2. **train/valid 集规模更小**(5-12 agents, 40-100 tasks)，难度可能低于 test 集。
   需要实际跑 Gurobi 验证。
3. **tightness 值可能需要根据反馈再微调**：如果后续训练发现很多 infeasible 实例,
   可适当提高；如果仍然太容易，可继续降低。

---

## 给下一轮的经验教训

1. **服务器 Python 需要用 `bash -lc`**：`ssh V100` 非交互式时不加载 .bashrc，
   Python 3.13 (with numpy, gurobi) 只在 login shell 中可用。命令模板：
   `ssh V100 "bash -lc 'cd ~/projects/learn2dcomp && python script.py'"`
2. **Type B 是特例**：weights/costs U[1,100] 独立意味着永远可以 cherry-pick
   低 weight 的 agent。需要非常 aggressive 的 tightness（0.50 或更低）。
3. **负相关(Type C/D)天然困难**：因为低 cost = 高 weight，无法同时优化两者，
   形成 genuine trade-off。如果以后加新 Type，负相关是"免费"的难度来源。
4. **CLAUDE.md 需要更新服务器 Python 路径**：当前写的是 `python3`，实际应该是
   `bash -lc 'python'` 或直接 `python`。
