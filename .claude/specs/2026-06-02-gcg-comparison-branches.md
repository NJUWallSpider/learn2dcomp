# GCG Comparison: 3-Branch DW Solving Pipeline

**Date**: 2026-06-02  
**Status**: Approved → Implementation

## Goal

Compare three GAP solving approaches on the same test instances:

| Branch | Description | Solver |
|--------|-------------|--------|
| 1 | Original MIP solved directly | Gurobi |
| 2 | GNN decomposition → GCG solves via DW | GCG (pre-specified decomp) |
| 3 | Original MIP → GCG auto-detects + solves | GCG (auto detect) |

## Architecture

```
MPS file ──┬── Branch 1: gp.read() → model.optimize() → Gurobi metrics
           │
           ├── Branch 2: GNN JSON → .dec mapping → gcg -f .mps -d .dec → parse stdout
           │
           └── Branch 3: gcg -f .mps → detect → optimize → parse stdout
```

## GNN Variable Decomposition → GCG Constraint Decomposition

- GNN outputs `{subproblem_id: [x_i_j, ...]}`  (variable-level)
- GCG `.dec` format assigns **constraints** to blocks / master
- For GAP:
  - Each GNN subproblem k → GCG block k containing `cap_i` for agents i whose variables are majority-assigned to k
  - All `assign_j` constraints → MASTERCONSS
  - Edge case: if agent i's vars span multiple subproblems, assign `cap_i` to the block with most of its vars

## New Files

- `07b_gcg_comparison.py` — main comparison script
- Extend `gcg_interface.py` — add `gnn_to_dec()` and `run_gcg_solve()`

## CSV Output

Columns: Instance,
Gurobi_Obj, Gurobi_Gap, Gurobi_Time, Gurobi_Nodes,
GCG_GNN_Obj, GCG_GNN_Gap, GCG_GNN_Time, GCG_GNN_CGIters, GCG_GNN_Nodes,
GCG_GNN_Blocks, GCG_GNN_LPBound,
GCG_Auto_Obj, GCG_Auto_Gap, GCG_Auto_Time, GCG_Auto_CGIters, GCG_Auto_Nodes,
GCG_Auto_Blocks, GCG_Auto_LPBound, GCG_Auto_DetectTime

## GCG Output Parsing

GCG stdout contains after `optimize`:
- `Primal Bound` / `Dual Bound` → objective and bound
- `Gap` → MIP gap
- `Solving Time` → total time
- Block count → from .dec or detect output

Use regex to extract structured metrics.
