# Round 010 — T-015: Type B Outlier 根因分析

**日期**: 2026-05-30
**工人**: worker-assistant
**任务**: T-015 — 调查 a14_t79_typeB_42 Oracle-Gurobi gap 31.2%

---

## 结果

### 实例数据
| 指标 | Gurobi | DW Oracle | DW GNN |
|------|--------|-----------|--------|
| Obj | 1165 | 1529 | 1529 |
| Time | 2.2s | 82.4s | 63.2s |
| Nodes | 51 | — | — |
| CG iters | — | 68 | 68 |

Gap: (1529-1165)/1165 = **31.2%**

### 根因

**Oracle 和 GNN 分解 100% 相同（1106/1106 变量分配完全一致）。**

这说明 31.2% gap **不是 GNN 的问题**，Oracle（GCG）得到完全相同的 DW 结果。

两种分解都是 agent-disjoint 结构（每个 agent 一个子问题，14 agents = 13 subproblems + 1 master）。列生成独立地为每个 agent 生成分配列，RMP 组合这些列。在这种分解下，task coupling 约束导致 RMP 的整数最优解与原始问题最优解之间存在积分间隙（integrality gap）。

### 为什么 a14_t79_typeB_42 是 outlier？

在所有 Type B 实例中，a14_t79_typeB_42 的 gap 最大（31.2% vs 第二名 13.1%）：
- 14 agents, 79 tasks, NodeCount=51
- 其他类似规模的 Type B（a14_t87_typeB_2: 14a/87t gap=1.5%, a15_t86_typeB_47: 15a/86t gap=0.6%）
- 差异在于**实例特定的 cost/capacity 结构**，而非分解质量

### 结论

**不是 bug，是 DW 方法对此实例的固有限制。** 列生成 + agent-based decomposition 对于 GAP 是启发式方法，不可能对所有实例精确。这个 31.2% gap 实例揭示了当前分解策略的边界。

改善方向（非本轮范围）：
- 尝试不同分解策略（task-based 或 hybrid）
- 增加 branch-and-price 而非仅 RMP MIP
- 对该实例单独调整 artificial_cost 或 CG 参数

---

## Type B 全貌

11/18 Type B 实例 gap<1%（61%），仅 a14_t79_typeB_42 显著异常（31.2%），其余在 0.1%-13.1% 之间。
