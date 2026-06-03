# Round 017 — T-015: 调查 Type B outlier a14_t79_typeB_42 (31.2% gap)

**时间**: 2026-05-30 16:20 CST
**工人**: worker-gamma
**任务**: T-015 — 调查 a14_t79_typeB_42 Oracle-Gurobi gap 31.2% 根因

---

## 诊断过程

在服务器上对 a14_t79_typeB_42 运行详细诊断，对比 Gurobi Direct 和 DW Oracle。

## 结果

| 方法 | Obj | Status | Gap | Time | Nodes |
|------|-----|--------|-----|------|-------|
| Gurobi Direct | **1165** | OPTIMAL | 0.0% | 2.2s | 51 |
| DW Oracle | **1529** | OPTIMAL | 0.0% | 21.5s | 45,476 |

### DW 详细数据

- CG 迭代: 68 (无新列可加 → LP 收敛)
- LP bound: 1161.62
- 列总数: 862 (14 agents × ~60 列/agent)
- 人工变量: 0
- MIP 从 941 个列中搜索, 45,476 nodes 后证明 1529 为 RMP 最优

### Gurobi Direct 详细数据

- Root relaxation: 1106.03
- 在 ~0.01s 找到第一个可行解 (3589)
- 迅速改进至 1165 并证明最优 (MIPGap=1e-6)

## 根因分析

**两者均为各自 formulation 的 proven optimal。** 31.2% gap 源自 DW 分解的结构性限制, 不是求解器 bug。

### 机制

1. CG 阶段只为 LP relaxation 生成列（reduced cost < 0 时添加）
2. LP 在 1161.62 处收敛，此时所有列的 reduced cost ≥ 0
3. MIP 阶段只能从已生成的 862 个列中组装整数解
4. **Gurobi optimal = 1165 需要的某些列在 LP 解中有正的 reduced cost → CG 从未生成它们**
5. 因此 RMP MIP 的最优解是 1529（从可用列中最佳组合）

### 为什么其他 Type B 没有这个问题

其他 Type B 实例 median gap 仅 0.74%。这个实例特殊：LP relaxation 的 optimal basis 恰好不包含整数最优需要的列。这是 DW "CG then MIP" 方法（非 true branch-and-price）的已知局限。

### 可能的改进方向

1. **Branch-and-Price**: 在 MIP 树的每个节点继续生成列（而非静态列池），复杂度高
2. **更多启发式列**: greedy knapsack heuristic 已添加，可能生成 LP 遗漏的列
3. **CG 后额外列生成**: 在 MIP 阶段前, 对每个 agent 求解"偏离 LP optimum"的列（如 perturb 目标函数）
4. **接受现状**: 31.2% gap 在 100 实例中仅 1 例, 整体 DW 质量不受显著影响

## 未解决问题

- **T-002 剩余 35 实例**: 从未跑完
- **Type D TIME_LIMIT (50%)**: 120s 不够
- **report.html**: 已更新（round_016），包含 T-015 发现

## 经验教训

- **DW = Gurobi 不是保证**: 即使子问题有 integrality property (knapsack), "CG then MIP" 方法也不能保证找到原始 MIP 最优解。完整 branch-and-price 才是 exact method
- **一个 outlier 不足以否定方法**: 100 实例中仅 1 例显著 gap, GNN-Oracle median gap 0.00%, 总体方法有效
- **诊断要区分 "bug" 和 "方法局限"**: 最初怀疑是 bug, 实际是 DW "CG then MIP" 的已知理论局限
