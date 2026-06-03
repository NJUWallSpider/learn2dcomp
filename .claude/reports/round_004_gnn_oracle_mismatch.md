# Round 004 — GNN ≠ Oracle 根因定位 (T-003)

**日期**: 2026-05-27
**工人**: worker-beta
**任务**: T-003 — 调查 a13_t42_typeB_57 上 GNN(353) ≠ Oracle(334)

---

## 根因定位

**根因**: `06_eval_instances.py` 中的 `reassign_noise_points()` 先于 `graph_voting_reassignment()` 运行，
盲目按嵌入距离将噪声变量分配到最近的簇中心，导致不合理的簇合并。

## 详细分析

### 实例数据

- 实例: a13_t42_typeB_57 (13 agents × 42 tasks = 546 binary variables)
- Gurobi optimal: 334
- DW Oracle: 334 ✓ (13 blocks, one per agent)
- DW GNN: 353 ✗ (+5.7%)

### 当前 DBSCAN 运行结果 (eps=0.221, eps_scale=2.0)

原始 DBSCAN 输出:
- 11 个簇 (agents 1-11 各独立成簇)
- **86 个噪声点** (agents 0 和 12 — 共 2×42=84 变量 — 全部被标为 -1)

### Pipeline A (04_test.py: DBSCAN → graph_voting_reassignment, NO reassign_noise_points)

`graph_voting_reassignment(threshold=1.0)` 利用约束结构:
- `cap_0` 和 `cap_12` 的所有邻居变量均为噪声 → UNDETERMINED
- 噪声变量 x_0_j 连接的 `assign_j` 有多个不同簇的邻居 → LINKING
- Rule 2 (Master Default): agents 0,12 被分配到新簇 11

**结果**: 12 个簇，噪声点形成独立簇，不破坏现有簇

### Pipeline B (06_eval_instances.py: DBSCAN → reassign_noise → graph_voting)

`reassign_noise_points()` 计算每个噪声点到各簇中心的欧氏距离，分配到最近的:
- **agents 0 和 12 的 86 个噪声点全部被分配到 agent 6 的簇 (cluster 5)**
- 簇 5 变成 3-agent 合并: agents [0, 6, 12]
- `graph_voting_reassignment` 发现 0 噪声点，提前返回，无法修正

**结果**: 11 个簇，3-agent 合并的簇 (126 vars) 结构不合理

### DW 影响

GAP DW 中每个 subproblem 是一个 knapsack:
- Oracle: 13 个子问题，每个 42 vars → 小 knapsack，易求解
- GNN (Pipeline B): 11 个子问题，其中一个 126 vars → 大 knapsack，求解更难
- 合并 3 个 agent 会创建更难的分支定界搜索空间 → CG 找不到更好的列 → 最终 MIP 间隙更大 (353 vs 334)

## Fix 方案

**推荐方案 A** (最简单): 从 `06_eval_instances.py` 移除 `reassign_noise_points()` 调用

理由:
- `graph_voting_reassignment` 已经能正确处理所有噪声点（基于约束结构，而非盲目距离）
- 04_test 已验证 graph_voting 可让噪声点形成独立簇
- 当前 reassign_noise → graph_voting 的顺序是反的：应该先结构后距离

**修改位置**: `06_eval_instances.py` 第 157 行，删除:
```python
pred_labels = utilities.reassign_noise_points(val_embeddings, pred_labels)
```

**替代方案 B**: 调换顺序 — graph_voting 先于 reassign_noise
- graph_voting 基于约束结构处理噪声 → reassign_noise 处理剩余
- 改动更大，但保留了 reassign_noise 作为安全网

## 验证计划

1. 修改 06_eval_instances.py，删除 reassign_noise_points 调用
2. 对该实例重新生成分解 JSON
3. 运行 07_solve_decomposition.py 确认 DW GNN = DW Oracle = 334
4. 批量验证 100 个测试实例，确保没有回归

## 修改文件

| 文件 | 改动 |
|------|------|
| 06_eval_instances.py | 删除 reassign_noise_points 调用 (第 157 行) |

## 给下一轮的经验

1. **noise_point 处理要关注结构**: 嵌入距离只是近似，约束结构才是真实的分解依据。reassign_noise 适合作为最后一步（在 graph_voting 之后），而不是第一步。
2. **06_eval 和 04_test 应统一后处理**: 两个脚本做类似的事但细节不同，增加了不一致性风险。长期应抽象为共享函数。
3. **eps_scale=2.0 偏大**: 当前 eps=0.22 (base=0.11 × 2.0) 将 13 个 agent 中的 2 个全部标为噪声。考虑降低为 1.0-1.5。
