# Round 001 — 初始 Bug 修复与基础设施搭建

**日期**: 2026-05-26 ~ 2026-05-27
**背景**: 项目从 CFLP 切换到 GAP，GNN+DW 流水线首次端到端运行后出现两个严重问题。

---

## 做了什么

### 1. 修复 GAP 容量过低导致实例过于简单（Nodes=1.0）

**根因**: `solvers/gap_generator.py` 的 `_compute_capacities()` 使用公式
`b_i = α × total_weight / n_agents`，`total_weight = Σ_i Σ_j w_ij` 是所有权重的
总和（含所有 agent），但每个 task 只分配到其中一个 agent。导致实例的 total capacity
远超实际需要的 weight。

**具体数据**: 15 agents × 54 tasks, avg weight 13:
- 旧公式: capacity = 0.60 × 10530 / 15 = 421 per agent → 总容量 6315
- 实际需分配 ≈ 54 × 13 = 702 → 利用率仅 ~11%
- 结果: LP relaxation 天然整数，Gurobi 全部在 root node 求解（Nodes=1.0）

**修复**: 改为 tightness 公式：
`b_i = tightness × (n_tasks / n_agents) × avg_weight`
- tightness ∈ {1.20, 1.30}（Type B 更紧，其余 1.30）
- 新公式对任意 agent 数量保持一致的紧度

**注意**: 需要重新运行 `01_generate_instances.py` 才能生效。

### 2. 修复 DW 列生成 "要么 gap=0 要么 gap=inf"

**根因分析**（两个独立问题）:

**问题 A — gap=inf（RMP LP 在第一轮迭代返回 INFEASIBLE）**:
- `config.py` 中 `artificial_cost=1e6` 太大，与真实 cost（1-100）差异 4 个数量级
- Gurobi 双单纯形法（Method=1）遇到数值困难，错误地报告 INFEASIBLE
- LP 阶段失败后，`generic_dw.py` 仍然调用 `finalize_mip()`（移除人工列、切换到 BINARY）
  → MIP 必然 INFEASIBLE
- 修复: artificial_cost 从 1e6 降到 1e3，LP 失败时跳过 MIP phase

**问题 B — gap=0 但 DW 解与 Gurobi 直接求解不同**:
- `a15_t53_typeB_22`: Gurobi=352, DW=523（DW 更差）
- `a15_t53_typeD_34`: Gurobi=3336, DW=271（DW 更好，但对 Type D 来说 271 不可能
  低于 53×56≈2968 的理论下界，说明可能是数据不一致）
- 怀疑根因: `parse_gap_lp()` 用正则从 LP 文件提取数据，Gurobi Direct 读 MPS
  文件，中间可能存在不一致
- 修复: 改为 `parse_gap_gurobi()` 用 Gurobi 直接读 MPS 文件提取数据，保证和
  Gurobi Direct 使用完全相同的数据

### 3. 搭建轮次报告系统

- 创建 `.claude/reports/` 目录
- 配置 `CLAUDE.md` 中 Claude 准则，强制每轮写报告、启动时读上一轮报告
- 五项准则: 实事求是、轮次报告、基础设施、项目知识、代码规范

### 4. 同步更新 report.html

- 更新了容量公式描述（α → tightness）
- 更新了 artificial_cost 值
- 更新了 DW 错误处理说明
- 更新了数据提取方式（正则解析 LP → Gurobi 读 MPS）

---

## 修改文件清单

| 文件 | 改动类型 | 内容 |
|------|----------|------|
| `solvers/gap_generator.py` | 修改 | 容量公式从 α 改为 tightness |
| `config.py` | 修改 | artificial_cost: 1e6 → 1e3 |
| `generic_dw.py` | 修改 | LP 失败时跳过 MIP phase，区分 INFEASIBLE/NUMERIC |
| `07_solve_decomposition.py` | 修改 | 新增 parse_gap_gurobi()，从 MPS 提取数据，清理 LP 引用 |
| `CLAUDE.md` | 新建+修改 | 基础设施说明 + Claude 准则 + 轮次报告系统 |
| `.claude/reports/round_001_initial_bugfixes.md` | 新建 | 本报告 |
| `report.html` | 修改 | 同步更新容量公式、DW 参数、数据提取方式等描述 |
| `run_guide.html` | 修改 | 添加 CLAUDE.md 引用 |

---

## 未解决问题

1. **DW 解与 Gurobi 直接求解的目标值差异是否已修复**: 改了数据提取方式后没有
   重新跑验证。下一轮应先跑几个实例确认 data consistency 问题已解决。
2. **tightness 值是否合理**: 1.20/1.30 是理论推测，没有跑过实验验证实例是否
   适度困难。可能出现太紧（全部 infeasible）或仍然太松。
3. **GNN DW 与 Oracle DW 总是给出完全相同的结果**: 日志中两者的 Obj、CG iters
   完全一致，说明 GNN 学到的就是"每 agent 一个 subproblem"。需要确认这是否为
   预期行为，以及 GNN 在非 GAP 问题上的表现。
4. **debug_*.py 文件未清理**: 仓库根目录有 6 个 debug 文件，如果不再需要应删除。

---

## 给下一轮的经验教训

1. **DW 的 artificial_cost 不能太大**: 1e6 在 GAP 场景下（cost 1-100）会导致
   数值问题。1e3 应该是安全的上限。遇到 INFEASIBLE 先怀疑数值问题，不要假设
   模型真的不可行。
2. **不要混合数据来源**: 之前 Gurobi Direct 读 MPS、DW 正则解析 LP，两个路径
   提取同一问题的数据。任何两边不一致的风险都直接导致对比无效。一律用 Gurobi
   读同一个文件（MPS）。
3. **容量公式的选择有陷阱**: 旧公式 `αΣw/m` 在 m 变化时紧度不同——agent 越多
   越松。Cross-scale 训练（m∈[5,16]）尤其需要 scale-invariant 的公式。
4. **看数字要有敏感性**: Nodes=1.0 在 795 变量的 MIP 上出现，应该立刻怀疑
   约束太松。Obj=271 而 Type D 理论下界 >2968，应立刻怀疑数据不一致。
