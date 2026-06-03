# Round 058: 3-Branch GCG Comparison Pipeline

## Changes

- **New**: `07b_gcg_comparison.py` — end-to-end 3-branch comparison script
  - Branch 1: Gurobi direct (same as 07 baseline)
  - Branch 2: GNN decomposition → GCG solves via DW
  - Branch 3: GCG auto-detects decomposition and solves
  - Outputs CSV with full statistics: Obj, DualBound, Gap, Time, Nodes, MasterLPIters, Blocks, Solutions
  - Incremental CSV write (survives crashes)

- **Extended**: `gcg_interface.py`
  - `gnn_to_dec()` — maps GNN variable-level decomposition to GCG constraint-level .dec format
    - Handles edge cases: unassigned agents, master variables, multi-subproblem agent splitting
  - `run_gcg_solve()` — subprocess wrapper for GCG with optional pre-specified .dec, parses stdout
    - Extracts Primal/Dual Bound, Gap, Nodes, Master LP iterations, Block count, Solutions found

- **Git cleanup**: committed 303 accumulated files (dispatch system restructuring, knowledge base, reports)

## Test Results (10 instances, 60s time limit)

| Branch | Avg Obj | Avg Time | Avg Blocks |
|--------|---------|----------|------------|
| Gurobi | 2743.6 | 2.8s | — |
| GCG (GNN) | 2743.6 | 7.9s | 13.0 |
| GCG (auto) | 2743.6 | 7.8s | 13.0 |

All three branches found identical optimal solutions on all 10 test instances.

## Key Design Decisions

- **Constraint mapping**: GNN variable clusters → constraint blocks via majority vote per agent
- **GCG invocation**: stdin command pipe (not `-f` + `-c` which are mutually exclusive)
- **No GenericDW subclass**: GCG is a self-contained solver, not compatible with the abstract CG loop

## Next Steps

- Run full benchmark on all test instances with longer time limits
- Compare GNN vs GCG decomposition quality (are the blocks structurally different?)
- Consider GCG's advanced decomposition detection for non-GAP problems

## Lessons

- GCG's `set limits/time N` enters a submenu when piped via stdin; use `set limits time N` (space syntax)
- GCG `-q` flag suppresses ALL output including solve statistics — omit it for parsing
- The GNN correctly recovers the natural agent-based decomposition for GAP (13 blocks = 13 agents)
