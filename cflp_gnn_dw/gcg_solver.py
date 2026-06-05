"""
GAP GCG Solver — unified solver supporting 3 modes with SCIP/GCG.

Modes:
  - direct:    PySCIPOpt compact model, solve directly
  - gcg_gnn:   PyGCGOpt + GNN decomposition → GCG column generation
  - gcg_auto:  PyGCGOpt auto-detection → GCG column generation

Usage:
    from gcg_solver import GCGSolver
    solver = GCGSolver(mode="gcg_gnn", time_limit=600)
    result = solver.solve(instance, decomposition_json=decomp)
"""
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from gap_model import GAPInstance, build_scip_model


# ---------------------------------------------------------------------------
# GCGSolver — wraps 3 modes in one class
# ---------------------------------------------------------------------------

class GCGSolver:
    MODE_DIRECT  = "direct"
    MODE_GCG_GNN = "gcg_gnn"
    MODE_GCG_AUTO = "gcg_auto"

    def __init__(self, mode: str = MODE_DIRECT,
                 time_limit: float = 600,
                 mip_gap: float = 1e-4,
                 verbose: bool = False,
                 gcg_params: Optional[Dict] = None):
        if mode not in (self.MODE_DIRECT, self.MODE_GCG_GNN, self.MODE_GCG_AUTO):
            raise ValueError(f"Unknown mode: {mode}")
        self.mode = mode
        self.time_limit = time_limit
        self.mip_gap = mip_gap
        self.verbose = verbose
        self.gcg_params = gcg_params or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(self, instance,
              decomposition_json: Optional[dict] = None) -> dict:
        """Solve one GAP instance in the configured mode.

        Args:
            instance: GAPInstance object.
            decomposition_json: required for gcg_gnn mode; the JSON dict
                from 06_eval_instances.py or baseline_metis.py.

        Returns:
            Dict with keys: mode, status, obj_val, solve_time, gap,
            n_iterations, n_nodes, n_assigned.
        """
        if self.mode == self.MODE_DIRECT:
            return self._solve_direct(instance)
        elif self.mode == self.MODE_GCG_GNN:
            if decomposition_json is None:
                raise ValueError("decomposition_json required for gcg_gnn mode")
            return self._solve_gcg(instance, decomposition_json)
        elif self.mode == self.MODE_GCG_AUTO:
            return self._solve_gcg(instance, None)

    # ------------------------------------------------------------------
    # Mode 1 — SCIP Direct (same pygcgopt.Model as GCG, no decomposition)
    # ------------------------------------------------------------------

    def _solve_direct(self, instance: GAPInstance) -> dict:
        from pygcgopt import Model as GCGModel

        model = GCGModel("GAP_Direct")
        model.hideOutput()

        n, m = instance.n_jobs, instance.n_machines
        x = {}
        for i in range(n):
            for j in range(m):
                x[i, j] = model.addVar(
                    f"x_{i}_{j}", vtype="B",
                    obj=instance.costs[i, j]
                )
        model.setMinimize()
        for i in range(n):
            model.addCons(sum(x[i, j] for j in range(m)) == 1)
        for j in range(m):
            model.addCons(
                sum(instance.weights[i, j] * x[i, j] for i in range(n))
                <= instance.capacities[j]
            )

        self._apply_gcg_params(model)  # same as GCG modes for fairness
        model.setRealParam("limits/time", self.time_limit)
        model.setRealParam("limits/gap", self.mip_gap)

        t0 = time.time()
        model.optimize()
        elapsed = time.time() - t0

        status = model.getStatus()
        obj_val = model.getObjVal() if status == "optimal" else None
        gap = model.getGap() if status == "optimal" else None

        # Count actual assignments
        n_assigned = 0
        if status == "optimal":
            for i in range(instance.n_jobs):
                for j in range(instance.n_machines):
                    try:
                        if model.getVal(x[i, j]) > 0.5:
                            n_assigned += 1
                    except Exception:
                        pass

        n_nodes = None
        try:
            n_nodes = model.getNTotalNodes()
        except Exception:
            pass

        return {
            "mode": self.MODE_DIRECT,
            "status": status,
            "obj_val": obj_val,
            "solve_time": elapsed,
            "gap": gap,
            "n_assigned": n_assigned,
            "n_nodes": n_nodes,
            "n_iterations": None,
        }

    # ------------------------------------------------------------------
    # Mode 2/3 — GCG (shared)
    # ------------------------------------------------------------------

    def _solve_gcg(self, instance: GAPInstance,
                   decomposition_json: Optional[dict]) -> dict:
        """Build a pygcgopt Model, optionally apply decomposition, and solve."""
        from pygcgopt import Model as GCGModel

        model = GCGModel("GAP_GCG")
        model.hideOutput()

        n, m = instance.n_jobs, instance.n_machines

        # --- Variables ---
        x = {}
        for i in range(n):
            for j in range(m):
                x[i, j] = model.addVar(
                    f"x_{i}_{j}", vtype="B",
                    obj=instance.costs[i, j]
                )
        model.setMinimize()

        # --- Constraints (store by name for decomposition mapping) ---
        cons_map = {}

        # Assignment constraints → linking (master)
        for i in range(n):
            cons = model.addCons(
                sum(x[i, j] for j in range(m)) == 1,
                name=f"assign_{i}"
            )
            cons_map[f"assign_{i}"] = cons

        # Capacity constraints → per-machine blocks
        for j in range(m):
            cons = model.addCons(
                sum(instance.weights[i, j] * x[i, j] for i in range(n))
                <= instance.capacities[j],
                name=f"cap_{j}"
            )
            cons_map[f"cap_{j}"] = cons

        # --- Apply decomposition if provided (gcg_gnn mode) ---
        if decomposition_json is not None:
            self._apply_decomposition_from_json(model, cons_map,
                                                 decomposition_json)

        # --- GCG parameters ---
        self._apply_gcg_params(model)

        if self.time_limit:
            model.setRealParam("limits/time", self.time_limit)
        model.setRealParam("limits/gap", self.mip_gap)

        # --- Solve ---
        t0 = time.time()
        model.optimize()
        elapsed = time.time() - t0

        return self._extract_gcg_results(model, elapsed)

    # ------------------------------------------------------------------
    # Decomposition mapping: GNN/METIS JSON → GCG
    # ------------------------------------------------------------------

    def _apply_decomposition_from_json(
        self, model, cons_map: dict, decomp_json: dict
    ) -> None:
        """Convert GNN decomposition JSON to GCG block structure.

        Expected JSON format (from 06_eval_instances.py):
        {
          "constraint_decomposition": {
            "linking_constraints": ["assign_0", ...],
            "block_assignments": {"cap_0": 0, "cap_1": 1, ...}
          }
        }
        """
        con_decomp = decomp_json.get("constraint_decomposition", {})
        if not con_decomp:
            if self.verbose:
                print("  No constraint_decomposition in JSON, skipping")
            return

        linking_names = set(con_decomp.get("linking_constraints", []))
        block_assignments = con_decomp.get("block_assignments", {})

        # --- Master constraints ---
        master_conss = []
        for name in sorted(linking_names):
            if name in cons_map:
                master_conss.append(cons_map[name])

        # --- Group block constraints by block_id ---
        from collections import defaultdict
        block_groups = defaultdict(list)
        for con_name, block_id in block_assignments.items():
            if con_name in cons_map:
                block_groups[int(block_id)].append(cons_map[con_name])

        # Sort blocks, build ordered list
        block_lists = [
            block_groups[bid] for bid in sorted(block_groups.keys())
        ]

        # Catch-all: constraints not placed anywhere
        placed = set(linking_names) | set(block_assignments.keys())
        unplaced = [c for name, c in cons_map.items() if name not in placed]
        if unplaced:
            block_lists.append(unplaced)

        if not block_lists:
            if self.verbose:
                print("  No blocks found — GCG will auto-detect")
            return

        # --- Apply to GCG model ---
        model.addDecompositionFromConss(master_conss, *block_lists)

        if self.verbose:
            n_master = len(master_conss)
            n_blocks = len(block_lists)
            sizes = [len(bl) for bl in block_lists]
            print(f"  GCG decomposition: {n_master} master + {n_blocks} "
                  f"blocks (sizes {sizes})")

    # ------------------------------------------------------------------
    # GCG parameters
    # ------------------------------------------------------------------

    def _apply_gcg_params(self, model) -> None:
        """Apply GCG-specific parameters."""
        defaults = {
            "presolving/maxrounds": 20,
            "propagating/maxrounds": 100,
            "separating/maxrounds": 100,
        }
        merged = {**defaults, **self.gcg_params}
        for param, value in merged.items():
            try:
                model.setParam(param, value)
            except Exception:
                if self.verbose:
                    print(f"  Warning: could not set param '{param}'")

    # ------------------------------------------------------------------
    # Results extraction
    # ------------------------------------------------------------------

    def _extract_gcg_results(self, model, elapsed: float) -> dict:
        status = model.getStatus()
        obj_val = model.getObjVal() if status == "optimal" else None
        gap = model.getGap() if status == "optimal" else None

        n_iterations = None
        try:
            n_iterations = model.getNLimSolverCalls()
        except Exception:
            pass

        n_nodes = None
        try:
            n_nodes = model.getNTotalNodes()
        except Exception:
            pass

        mode_label = (
            self.MODE_GCG_GNN if self.mode == self.MODE_GCG_GNN
            else self.MODE_GCG_AUTO
        )

        return {
            "mode": mode_label,
            "status": status,
            "obj_val": obj_val,
            "solve_time": elapsed,
            "gap": gap,
            "n_assigned": None,
            "n_iterations": n_iterations,
            "n_nodes": n_nodes,
        }
