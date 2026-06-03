---
name: project-architecture
description: Complete understanding of learn2dcomp codebase — data flow, key files, known bugs, and dispatch system
metadata:
  type: project
---

# learn2dcomp 项目架构全图

## 数据流（7 步流水线）

```
01_generate_instances.py → data/mps/gap/{split}/*.mps
02_generate_dataset.py   → data/processed/gap/{split}/*.pt (含 GCG oracle 标签)
03_train_gnn.py           → models/best_model_gap.pth
04_test.py                → models/cluster_outputs/{split}/*.json (聚类指标 ARI/NMI/PCR)
06_eval_instances.py      → results/decomposition_output/*.json (GNN 分解，供 DW 使用)
07_solve_decomposition.py → results/gap_dw_results.csv (Gurobi vs DW Oracle vs DW GNN)
```

Why: Pipeline order matters for dependency tracking. Steps 04 and 06 are independent; 07 depends on 06.

## 核心文件

| 文件 | 职责 |
|------|------|
| `solvers/gap_generator.py` | GAP 实例生成，5 种类型 (A-E)，tightness 公式 |
| `solvers/gap_dw.py` | GAP DW 列生成：RMP + knapsack pricing |
| `generic_dw.py` | 通用 DW 框架：CG loop + MIP finalize |
| `data_process.py` | 数据集加载 + collate_fn + Laplacian PE |
| `gnn_model.py` | GraphTransformer (HeteroConv) + SupCon Loss |
| `utilities.py` | DBSCAN + graph voting + 各类工具函数 |
| `07_solve_decomposition.py` | 三方法对比：Gurobi Direct / DW Oracle / DW GNN |

## 已知问题（按严重程度排序）

1. **实例太容易**：100% NodeCount=1.0，tightness 公式已改但实例未重新生成
2. **DW artificial_cost**：config 中已设为 1e3，但 `GAPDWSolver.__init__` 默认值仍是 1e6。`07_solve_decomposition.py:479` 从 config 读取，所以正确传递。但直接创建 `GAPDWSolver` 不传 artificial_cost 会出问题
3. **DW-Gurobi 目标值不一致**：5 实例测试后 DW Oracle 匹配了 Gurobi（4/4），但 GNN 有 1 例不匹配 (a13_t42_typeB_57: 353 vs 334)
4. **GNN Oracle 等价性**：GNN 和 Oracle 结果在当前测试中大部分一致，但上述异常需要调查

## 调度系统

- `.claude/dispatch/BOARD.md`：任务主板，7 个任务，4 个工人 slot
- `.claude/dispatch/WORKER_PROTOCOL.md`：工人 11 步循环
- `.claude/dispatch/DISPATCHER.md`：调度员 11 步巡检（每分钟）
- CronCreate：`* * * * *` 触发调度员巡检

## 关键依赖链
T-001 (生成实例) → T-005 (构建数据集) → T-006 (训练) → T-007 (全流程评估)
