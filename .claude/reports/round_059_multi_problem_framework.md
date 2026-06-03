# round_059: generalize GNN framework to multi-problem support

## Changes

### New files
- `solvers/rmf_generator.py` — RMF (multi-commodity flow) instance generator, extracted from `01_generate_rmf_instances.py` for importability

### Modified files

**config.py** — Added `ProblemSpec` dataclass and `PROBLEM_REGISTRY` dict. Each problem registers its generation spec, generate function, parse_model, solve_dw, and parse_dims callables. Added `RMF_GEN` config for the 8 RMF instances. Added `get_problem()`, `get_registered_problems()` helpers. All existing `GAP_GEN` and `TRAIN_PARAMS` kept unchanged.

**gcg_interface.py** — Replaced GAP-specific `gnn_to_dec(json, n_agents, n_tasks)` with problem-agnostic `gnn_to_dec(json_path, mps_path)`. The new version loads the MPS model via Gurobi and infers constraint-to-block assignments from the variable-to-subproblem mapping in the decomposition JSON. Old GAP-specific logic preserved as internal `_gnn_to_dec_gap()`. Verified: produces identical .dec output for GAP (13 blocks, cap_i in blocks, assign_j in master).

**01_generate_instances.py** — Now supports both `gap` and `rmf` via `choices`. Dispatches to problem-specific generators. Default still `'gap'`.

**01_generate_rmf_instances.py** — Refactored to delegate to `solvers/rmf_generator.py`. Standalone mode still works.

**03_train_gnn.py** — Added `--problem` CLI arg (default from config). Model saved as `best_model_{problem}.pth`.

**04_test.py** — Added `--problem` CLI arg.

**05_visualize_embeddings.py** — Added `--problem` CLI arg.

**06_eval_instances.py** — Added `--problem` CLI arg.

**07_solve_decomposition.py** — Added `--problem` with choices. Non-GAP problems get Gurobi direct only; DW sections skip with informative message. All GAP logic preserved.

**07b_gcg_comparison.py** — Updated `gnn_to_dec` call to new 2-arg signature. Removed GAP-specific `parse_gap_dims_from_name` usage. Added `--problem` with choices.

**08_train_cg_predictor.py** — Added `--problem` CLI arg. Results CSV path uses `{problem}_dw_results.csv`. Per-type breakdown (typeA-E) only runs for GAP.

**09_train_stage2.py** — Added `--problem` CLI arg. Model paths use `problem` variable.

## Verification
- `python 01_generate_instances.py gap -s 42` — works (identical to before)
- `python 01_generate_instances.py rmf` — dispatches to RMF generator, skips existing LPs
- Generic `gnn_to_dec` produces identical .dec output for GAP (13 blocks, cap_i constraints in blocks, assign_j in master)
- Generic `gnn_to_dec` works for RMF (infers constraint-to-block from variable decomposition)
- All imports verified on server (config, gcg_interface, solvers.*, data_process, gnn_model)
- `07b_gcg_comparison.py --problem rmf` runs without crash (0 decompositions found — expected, no GNN trained for RMF yet)
- `--help` shows correct problem choices on all scripts

## Deferred
- RMF DW solver (`solvers/rmf_dw.py`) — shortest-path pricing for MCF
- RMF model parsing for DW evaluation
- These will be added in a follow-up round
