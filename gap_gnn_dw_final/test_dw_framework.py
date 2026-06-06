"""
Test GenericDW framework with a GAPDW concrete class using DP-based pricing.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from pyscipopt import Model
from dw_framework import GenericDW, Column
from gap_model import GAPInstance, KnapsackDPSolver


class GAPDW(GenericDW):
    """GAP Dantzig-Wolfe decomposition: one block per machine."""

    def __init__(self, instance: GAPInstance, use_dp: bool = True):
        self.inst = instance
        self.use_dp = use_dp
        self.pricing_models = []  # for SCIP-based pricing
        self._pricing_vars = {}   # block_id -> dict of SCIP var refs
        super().__init__(name="GAPDW")

    def get_num_blocks(self) -> int:
        return self.inst.n_machines

    def build_linking_specs(self) -> list:
        specs = []
        for i in range(self.inst.n_jobs):
            specs.append({
                "name": f"assign_{i}",
                "rhs": 1.0,
                "sense": "E",
            })
        return specs

    def build_pricing_model(self, block_id: int):
        """Build SCIP model for block j: 0-1 knapsack."""
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

    def update_pricing_objective(self, model: Model, block_id: int,
                                 linking_duals: list, convexity_dual: float) -> None:
        j = block_id
        x_vars = self._pricing_vars[block_id]
        expr = 0.0
        for i in range(self.inst.n_jobs):
            expr += (self.inst.costs[i, j] - linking_duals[i]) * x_vars[i]
        model.setObjective(expr, sense='minimize', clear=True)

    def extract_column_from_pricing(self, block_id: int, model: Model) -> Column:
        j = block_id
        x_vars = self._pricing_vars[block_id]

        linking_coeffs = {}
        obj_val = 0.0
        var_values = {}

        for i in range(self.inst.n_jobs):
            val = model.getVal(x_vars[i])
            if val > 0.5:
                linking_coeffs[i] = 1.0
                obj_val += self.inst.costs[i, j]
                var_values[f"x_{i}_{j}"] = 1.0

        return Column(block_id, obj_val=obj_val,
                      linking_coeffs=linking_coeffs,
                      var_values=var_values)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup_rmp(self):
        super().setup_rmp()
        # Build initial columns: solve knapsack with negative costs as profits
        for j in range(self.num_blocks):
            profits = [-self.inst.costs[i, j] for i in range(self.inst.n_jobs)]
            weights = [self.inst.weights[i, j] for i in range(self.inst.n_jobs)]
            solver = KnapsackDPSolver(profits, weights, self.inst.capacities[j])
            solver.solve()
            col = self._column_from_selected(j, solver.selected)
            self.add_column(col)

        # Build pricing models for SCIP-based pricing
        for blk in range(self.num_blocks):
            self.pricing_models.append(self.build_pricing_model(blk))

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

    # ------------------------------------------------------------------
    # DP-based pricing
    # ------------------------------------------------------------------

    def solve_pricing_dp(self, block_id: int, duals: dict) -> Column:
        j = block_id
        pi = duals["linking_duals"]
        # Profit = π_i - c[i,j] (maximize reduced cost reduction)
        profits = [pi[i] - self.inst.costs[i, j] for i in range(self.inst.n_jobs)]
        weights = [self.inst.weights[i, j] for i in range(self.inst.n_jobs)]

        solver = KnapsackDPSolver(profits, weights, self.inst.capacities[j])
        solver.solve()
        return self._column_from_selected(block_id, solver.selected)

    # ------------------------------------------------------------------
    # CG loop (override for DP support)
    # ------------------------------------------------------------------

    def run_column_generation(self, max_iter: int = 500,
                              tol: float = 1e-6) -> dict:
        print(f"Starting GAP-DW CG (max_iter={max_iter}, tol={tol})")
        print(f"  Jobs: {self.inst.n_jobs}, Machines: {self.inst.n_machines}")
        print(f"  DP pricing: {self.use_dp}")

        for iteration in range(max_iter):
            self.iterations = iteration + 1

            duals = self.solve_rmp_lp()
            if duals is None:
                print(f"  RMP solve failed at iter {iteration}")
                return None

            self.lb_history.append(duals["lb"])
            new_columns = 0
            best_rc = 0.0

            for blk in range(self.num_blocks):
                if self.use_dp:
                    column = self.solve_pricing_dp(blk, duals)
                else:
                    column = self.solve_pricing(blk, duals)

                if column is not None:
                    rc = self.compute_reduced_cost(blk, column, duals)
                    if rc < -tol:
                        self.add_column(column)
                        new_columns += 1
                        best_rc = min(best_rc, rc)

            if iteration % 10 == 0 or new_columns > 0:
                print(f"  Iter {iteration}: LB={duals['lb']:.4f}, "
                      f"new={new_columns}, best_rc={best_rc:.6f}")

            if new_columns == 0:
                print(f"  Converged after {iteration + 1} iters. LB={duals['lb']:.4f}")
                return {
                    "status": "converged",
                    "iterations": iteration + 1,
                    "lb": duals["lb"],
                }

        print(f"  Max iter reached ({max_iter})")
        return {
            "status": "max_iter",
            "iterations": max_iter,
            "lb": self.lb_history[-1] if self.lb_history else None,
        }


# =====================================================================
# Tests
# =====================================================================

def test_dp_cg():
    """Test DW framework with DP pricing on a real GAP instance."""
    test_dir = Path(__file__).parent / "data" / "raw" / "gap" / "test"
    files = sorted(test_dir.glob("*.txt"))
    if not files:
        print("No test instances found!")
        return False

    fpath = files[0]
    print(f"Testing with: {fpath.name}")
    inst = GAPInstance(str(fpath))
    print(f"  n_jobs={inst.n_jobs}, n_machines={inst.n_machines}")

    # Test DP pricing
    print("\n--- Testing DP-based CG ---")
    gap_dw = GAPDW(inst, use_dp=True)
    gap_dw.setup_rmp()

    cg_result = gap_dw.run_column_generation(max_iter=200)
    if cg_result is None:
        print("CG FAILED!")
        return False
    print(f"CG result: {cg_result}")

    # Test final MILP
    print("\n--- Testing Final MILP ---")
    milp_result = gap_dw.solve_final_milp(time_limit=30)
    print(f"MILP result: {milp_result}")

    if milp_result["status"] == "optimal":
        solution = gap_dw.reconstruct_solution()
        n_assigned = sum(1 for v in solution.values() if v > 0.5)
        print(f"Solution: {n_assigned} jobs assigned out of {inst.n_jobs}")
        for vname, val in sorted(solution.items()):
            if val > 0.5:
                print(f"  {vname} = {val}")
    else:
        print("MILP not solved to optimality (this is OK for CG convergence test)")

    return True


def test_scip_pricing():
    """Test DW framework with SCIP pricing (not DP)."""
    test_dir = Path(__file__).parent / "data" / "raw" / "gap" / "test"
    files = sorted(test_dir.glob("*.txt"))
    if not files:
        print("No test instances found!")
        return False

    fpath = files[0]
    print(f"\n--- Testing SCIP-based pricing with: {fpath.name} ---")

    inst = GAPInstance(str(fpath))
    gap_dw = GAPDW(inst, use_dp=False)
    gap_dw.setup_rmp()

    cg_result = gap_dw.run_column_generation(max_iter=200)
    if cg_result is None:
        print("CG FAILED!")
        return False
    print(f"CG result: {cg_result}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: DP-based CG")
    print("=" * 60)
    ok1 = test_dp_cg()

    if ok1:
        print("\n" + "=" * 60)
        print("Test 2: SCIP-based CG (pricing via SCIP)")
        print("=" * 60)
        ok2 = test_scip_pricing()
    else:
        ok2 = False

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
    print("=" * 60)
