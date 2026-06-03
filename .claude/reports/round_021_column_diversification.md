# Round 021 — DW Column Diversification for MIP Phase

**日期**: 2026-05-27
**工人**: worker-alpha
**任务**: 调查 CG iters=0 根因，改善 MIP 阶段列多样性

---

## 做了什么

### 1. 新增 `_dp_mincost_knapsack()` 方法

DP 背包求解器，要求至少选择 1 个 task（排除空解）。
普通 `_dp_knapsack` 在正成本下返回空解（cost=0 最优），
diversification 需要非空的多 task 模式。

### 2. MIP 阶段列多样化（`finalize_mip()`）

在 CG LP 收敛后、MIP 求解前，为每个 agent 添加 2 种多 task 列：
- **Max-tasks 列**：以 unit profit 解背包，尽量多覆盖 task
- **Min-cost 列**：以原始成本解背包，要求至少选 1 个 task

目的：CG 初始列只有单 task 模式，MIP 阶段每个 agent 最多覆盖 1 个 task，
无法满足 task 覆盖约束。多样化列让每个 agent 有多 task 选项。

### 3. MIP 参数调整

- `Presolve = -1`（auto）：CG 结束后人工列已正确惩罚，可安全启用 presolve
- `MIPFocus = 1`：优先找可行解而非证明最优性

### 4. `_SubGAPDWSolver.finalize_mip()` 覆盖

`_SubGAPDWSolver` 使用 per-subproblem 数据（`sub_cost_vec` 等），
需要覆盖 `finalize_mip()` 以使用本地 task 索引。

### 5. 移除的方案

- **_build_greedy_mip_start()**：构建的 MIP start 不可行
  （多 agent 可能覆盖同一 task → 约束违反），反而让 Gurobi 找不到解
- **NoRelHeurTime**：未改善 MIP 求解速度，浪费 CG 后的剩余时间
- **Multi-task 初始列**：在 `build_rmp()` 中添加多 task 初始列会导致
  CG 立即收敛（0 迭代），阻止 CG 探索更好的列
  （a13_t50_typeC_28: CG=69→0, obj=4144→4171，gap 5.6%→6.3%）

---

## 验证结果

| 实例 | Gurobi | DW Oracle | CG iters | Art vars | 时间 | Gap |
|------|--------|-----------|----------|----------|------|-----|
| a13_t50_typeC_28 | 3925 | 4144 | 69 | 0 | 14s | 5.6% |
| a15_t63_typeC_83 | 4908 | TIME_LIMIT | 0 | 0 | 124s | — |
| a16_t82_typeC_8 | 6430 | TIME_LIMIT | 0 | 0 | 127s | — |

a15_t63_typeC_83 手动测试（300s time limit）：
- MIP 找到 10 个可行解，obj=5660，gap=15.3%，ObjBound=5124.7

---

## 核心发现

### CG iters=0 的根因

CG 迭代 0 意味着 LP 松弛在初始列集上已达到最优。
初始列（空列 + 单 task 列 + 人工列）足以让 LP 通过分数 λ 满足所有约束。
LP 对偶变量使所有可能模式的 reduced cost ≥ 0 → 无新列生成。

**这不是 DP 定价的 bug，而是 DW 的积分间隙（integrality gap）。**
LP 最优列集 ≠ 整数最优列集。

### DW vs Gurobi Direct

| 实例 | Gurobi Direct | DW Oracle | DW 更慢？ |
|------|-------------|-----------|----------|
| a13_t50_typeC_28 | < 120s (optimal) | 14s (5.6% gap) | 更快 |
| a15_t63_typeC_83 | < 120s (optimal) | > 300s (15.3% gap) | 更慢 |
| a16_t82_typeC_8 | < 120s (optimal) | > 300s | 更慢 |

DW 的优势在于分解后子问题更小，但 RMP MIP（set partitioning 结构）
可能比原始 GAP MIP 更难。这违背了 DW 分解的初衷。

### 为什么 RMP MIP 这么难

- 原始 GAP：15 agents × 63 tasks = 945 个 x_ij 变量，Gurobi 轻松求解
- RMP MIP：~200 个列变量，但 set partitioning 结构（每 agent 选 1 个模式、
  每 task 恰好覆盖 1 次）对 B&B 极不友好
- Gurobi 的 presolve/cuts 对原始 GAP 的 assignment 结构有特殊处理，
  但对 set partitioning 没有

---

## 局限性

1. **CG iters=0 实例**：多样化列不足以保证 120s 内找到 MIP 可行解
2. **DW 比 Gurobi 慢**：对于 Gurobi 能在 root node 求解的实例，DW 没有优势
3. **根本解决方案**：branch-and-price（B&B 树中生成列）才能真正解决积分间隙

---

## 给下一轮的建议

1. **接受 DW 的限制**：DW 不适用于 Gurobi 能轻松求解的实例，
   只对真正需要分解的大规模实例（100+ agents）有价值
2. **Branch-and-price**：在 B&B 节点中调用定价 → 真正的 DW 整数解
3. **考虑替代方案**：直接用 Gurobi 求解原始 MIP（对于 ≤ 100 agents 的实例）
4. **GNN 分解的价值**：当前 GNN 分解 = 自然分解（按 agent 分块），
   没有体现 GNN 的优势。需要研究非按 agent 的分解方式
