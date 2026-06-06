"""
GAP Column Generation Solver — pure Dantzig-Wolfe decomposition.

One block per machine: pricing subproblem is a 0-1 knapsack solved via DP.
RMP LP: scipy.optimize.linprog (HiGHS).  Final MILP: SCIP.

Usage:
    python gap_cg.py --instance data/raw/gap/test/1.txt [--max-iter 500]
"""
import sys
import time
import argparse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from pyscipopt import Model
from dw_framework import GenericDW, Column
from gap_model import GAPInstance, KnapsackDPSolver, build_scip_model


class GAPColumnGenerator(GenericDW):
    """GAP DW solver: DP knapsack pricing, scipy LP RMP, SCIP final MILP."""

    def __init__(self, instance: GAPInstance):
        self.inst = instance
        self._pricing_vars = {}
        self.pricing_models = []
        super().__init__(name="GAP_CG")

    # ------------------------------------------------------------------
    # Abstract implementations
    # ------------------------------------------------------------------

    def get_num_blocks(self) -> int:
        return self.inst.n_machines

    def build_linking_specs(self) -> list:
        return [
            {"name": f"assign_{i}", "rhs": 1.0, "sense": "E"}
            for i in range(self.inst.n_jobs)
        ]

    def build_pricing_model(self, block_id: int):
        """SCIP model for block j: 0-1 knapsack (used only for SCIP pricing)."""
        j = block_id
        m = Model(f"pricing_{j}")
        m.hideOutput()
        m.setMinimize()

        x_vars = {}
        for i in range(self.inst.n_jobs):
            x_vars[i] = m.addVar(f"x_{i}_{j}", vtype="B", obj=0.0)

        lhs = sum(self.inst.weights[i, j] * x_vars[i] for i in range(self.inst.n_jobs))
        m.addCons(lhs <= self.inst.capacities[j], name=f"knap_cap_{j}")

        self._pricing_vars[block_id] = x_vars
        return m

    def update_pricing_objective(self, model, block_id: int,
                                 linking_duals: list,
                                 convexity_dual: float) -> None:
        j = block_id
        x_vars = self._pricing_vars[block_id]
        expr = 0.0
        for i in range(self.inst.n_jobs):
            expr += (self.inst.costs[i, j] - linking_duals[i]) * x_vars[i]
        model.setObjective(expr, sense='minimize', clear=True)

    def extract_column_from_pricing(self, block_id: int, model) -> Optional[Column]:
        j = block_id
        x_vars = self._pricing_vars[block_id]
        return self._column_from_selected(
            block_id,
            [i for i in range(self.inst.n_jobs) if model.getVal(x_vars[i]) > 0.5]
        )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup_rmp(self):
        super().setup_rmp()
        # Initial columns: greedy knapsack per block (profit = -cost[i,j])
        for j in range(self.num_blocks):
            col = self._solve_knapsack_column(j, [
                -self.inst.costs[i, j] for i in range(self.inst.n_jobs)
            ])
            self.add_column(col)

        # Cache pricing models for SCIP-based pricing
        for blk in range(self.num_blocks):
            self.pricing_models.append(self.build_pricing_model(blk))

    # ------------------------------------------------------------------
    # DP pricing
    # ------------------------------------------------------------------

    def _solve_knapsack_column(self, block_id: int, profits: list) -> Column:
        j = block_id
        solver = KnapsackDPSolver(
            profits,
            [self.inst.weights[i, j] for i in range(self.inst.n_jobs)],
            self.inst.capacities[j]
        )
        solver.solve()
        return self._column_from_selected(block_id, solver.selected)

    def _column_from_selected(self, block_id: int, selected: list) -> Column:
        j = block_id
        linking_coeffs = {}
        obj_val = 0.0
        var_values = {}
        for i in selected:
            linking_coeffs[i] = 1.0
            obj_val += self.inst.costs[i, j]
            var_values[f"x_{i}_{j}"] = 1.0
        return Column(block_id, obj_val=obj_val,
                      linking_coeffs=linking_coeffs,
                      var_values=var_values)

    def solve_pricing_dp(self, block_id: int, duals: dict) -> Column:
        """DP knapsack pricing: max Σ (π_i - c[i,j]) * x_i."""
        j = block_id
        pi = duals["linking_duals"]
        profits = [pi[i] - self.inst.costs[i, j] for i in range(self.inst.n_jobs)]
        return self._solve_knapsack_column(block_id, profits)

    # ------------------------------------------------------------------
    # CG loop
    # ------------------------------------------------------------------

    def run_column_generation(self, max_iter: int = 500,
                              tol: float = 1e-6) -> dict:
        print(f"GAP DW Column Generation")
        print(f"  Instance: {self.inst.n_jobs} jobs x {self.inst.n_machines} machines")
        print(f"  max_iter={max_iter}, tol={tol}")

        t0 = time.time()

        for iteration in range(max_iter):
            self.iterations = iteration + 1

            duals = self.solve_rmp_lp()
            if duals is None:
                print(f"  RMP solve failed at iter {iteration}")
                return {"status": "rmp_failed", "iterations": iteration}

            self.lb_history.append(duals["lb"])
            new_columns = 0
            best_rc = 0.0

            for blk in range(self.num_blocks):
                column = self.solve_pricing_dp(blk, duals)
                if column is not None:
                    rc = self.compute_reduced_cost(blk, column, duals)
                    if rc < -tol:
                        self.add_column(column)
                        new_columns += 1
                        best_rc = min(best_rc, rc)

            if iteration % 20 == 0 or (new_columns > 0 and iteration < 20):
                print(f"  Iter {iteration}: LB={duals['lb']:.2f}, "
                      f"new_cols={new_columns}, best_rc={best_rc:.4f}")

            if new_columns == 0:
                elapsed = time.time() - t0
                print(f"  Converged: {iteration + 1} iters, "
                      f"LB={duals['lb']:.2f}, time={elapsed:.1f}s")
                return {
                    "status": "converged",
                    "iterations": iteration + 1,
                    "lb": duals["lb"],
                    "time": elapsed,
                }

        elapsed = time.time() - t0
        print(f"  Max iter ({max_iter}) reached, time={elapsed:.1f}s")
        return {
            "status": "max_iter",
            "iterations": max_iter,
            "lb": self.lb_history[-1] if self.lb_history else None,
            "time": elapsed,
        }

    # ------------------------------------------------------------------
    # Warm-start
    # ------------------------------------------------------------------

    def warmstart_from_assignment(self, machine_assignment: dict):
        """
        Add columns from a predicted assignment.
        machine_assignment: {job_id: machine_id}
        """
        machines = {j: [] for j in range(self.num_blocks)}
        for job, machine in machine_assignment.items():
            machines[machine].append(job)

        added = 0
        for j, jobs in machines.items():
            if jobs:
                col = self._column_from_selected(j, jobs)
                # Check feasibility (respect knapsack capacity)
                total_weight = sum(self.inst.weights[i, j] for i in jobs)
                if total_weight <= self.inst.capacities[j] + 1e-6:
                    self.add_column(col)
                    added += 1

        print(f"  Warm-started with {added} columns from GNN assignment")
        return added


# =====================================================================
# CLI
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="GAP Column Generation Solver")
    parser.add_argument('--instance', type=str, required=True,
                        help='Path to .txt instance file')
    parser.add_argument('--max-iter', type=int, default=500,
                        help='Max CG iterations')
    parser.add_argument('--tol', type=float, default=1e-6,
                        help='Reduced cost tolerance')
    parser.add_argument('--milp-time-limit', type=float, default=None,
                        help='Final MILP time limit (seconds)')
    parser.add_argument('--no-milp', action='store_true',
                        help='Skip final MILP, only run CG LP')
    args = parser.parse_args()

    inst = GAPInstance(args.instance)
    cg = GAPColumnGenerator(inst)
    cg.setup_rmp()

    # CG phase
    result = cg.run_column_generation(max_iter=args.max_iter, tol=args.tol)
    if result is None:
        print("CG failed.")
        return 1

    # Compare with direct SCIP solve
    print(f"\n--- Direct SCIP Solve ---")
    t0 = time.time()
    model, _ = build_scip_model(inst)
    model.hideOutput()
    model.optimize()
    direct_obj = model.getObjVal() if model.getStatus() == "optimal" else None
    direct_time = time.time() - t0
    print(f"  Status: {model.getStatus()}, Obj: {direct_obj}, Time: {direct_time:.1f}s")

    if not args.no_milp:
        print(f"\n--- Final MILP ---")
        milp_result = cg.solve_final_milp(time_limit=args.milp_time_limit)
        print(f"  Status: {milp_result['status']}, Obj: {milp_result['obj_val']}, "
              f"Gap: {milp_result['gap']}")

        if milp_result["status"] == "optimal":
            solution = cg.reconstruct_solution()
            n_assigned = sum(1 for v in solution.values() if v > 0.5)
            print(f"  Jobs assigned: {n_assigned}/{inst.n_jobs}")

    print(f"\n--- Summary ---")
    print(f"  CG LB: {result['lb']:.2f} ({result['iterations']} iters, {result.get('time', 0):.1f}s)")
    if direct_obj:
        print(f"  Direct SCIP: {direct_obj:.2f} ({direct_time:.1f}s)")
    if not args.no_milp and milp_result["status"] == "optimal":
        print(f"  DW MILP: {milp_result['obj_val']} (gap={milp_result['gap']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
