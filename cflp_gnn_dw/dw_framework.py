"""
Generic Dantzig-Wolfe Column Generation Framework.

LP solver: scipy.optimize.linprog (HiGHS backend) for RMP — SCIP cannot
reliably return duals after solve since it frees the LP. SCIP is used only
for the final binary MILP via solve_final_milp().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np


@dataclass
class Column:
    block_id: int
    obj_val: float
    linking_coeffs: Dict[int, float] = field(default_factory=dict)
    var_values: Dict[str, float] = field(default_factory=dict)
    lambda_var = None  # set by solve_final_milp()


class GenericDW(ABC):
    def __init__(self, name: str = "GenericDW"):
        self.name = name
        self.num_blocks = 0
        self.linking_names: List[str] = []
        self.linking_rhs: List[float] = []
        self.linking_sense: List[str] = []
        self.columns: List[List[Column]] = []

        self.iterations = 0
        self.lb_history: List[float] = []

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def get_num_blocks(self) -> int:
        ...

    @abstractmethod
    def build_linking_specs(self) -> List[dict]:
        """
        Return [{"name": str, "rhs": float, "sense": str}, ...].
        sense is 'E', 'L', or 'G'.
        """
        ...

    @abstractmethod
    def build_pricing_model(self, block_id: int):
        """
        Build and return a pricing model for block_id.
        Return type is problem-specific (e.g. pyscipopt Model, or None
        if using a custom solver in solve_pricing).
        """
        ...

    @abstractmethod
    def update_pricing_objective(self, model, block_id: int,
                                 linking_duals: List[float],
                                 convexity_dual: float) -> None:
        """
        Update pricing model objective for current dual values.
        """
        ...

    @abstractmethod
    def extract_column_from_pricing(self, block_id: int, model) -> Optional[Column]:
        """
        Extract a Column from the solved pricing model, or None.
        """
        ...

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup_rmp(self):
        self.num_blocks = self.get_num_blocks()
        specs = self.build_linking_specs()
        for sp in specs:
            self.linking_names.append(sp["name"])
            self.linking_rhs.append(sp["rhs"])
            self.linking_sense.append(sp.get("sense", "E"))

        self.columns = [[] for _ in range(self.num_blocks)]

    # ------------------------------------------------------------------
    # Column management
    # ------------------------------------------------------------------

    def add_column(self, column: Column) -> None:
        self.columns[column.block_id].append(column)

    def add_zero_column(self, block_id: int) -> None:
        zero_coeffs = {idx: 0.0 for idx in range(len(self.linking_names))}
        self.add_column(Column(block_id, obj_val=0.0, linking_coeffs=zero_coeffs))

    # ------------------------------------------------------------------
    # RMP LP via scipy (HiGHS)
    # ------------------------------------------------------------------

    def solve_rmp_lp(self, big_m: float = 1e6) -> Optional[Dict]:
        """
        Solve the RMP LP relaxation via scipy linprog (HiGHS backend).
        Adds artificial variables on linking constraints to guarantee feasibility.
        Returns {"linking_duals": [...], "convexity_duals": [...], "lb": float}.
        """
        from scipy.optimize import linprog

        n_linking = len(self.linking_names)
        n_blocks = self.num_blocks
        n_cols = sum(len(cols) for cols in self.columns)

        # Map column index -> (block_id, Column)
        col_meta = []
        for blk in range(n_blocks):
            for col in self.columns[blk]:
                col_meta.append((blk, col))

        n_total = n_cols + n_linking  # + artificial variables

        # Objective: lambda objective + big-M for artificials
        c = np.zeros(n_total)
        for j, (_, col) in enumerate(col_meta):
            c[j] = col.obj_val
        for i in range(n_linking):
            c[n_cols + i] = big_m

        # Build equality constraints: linking + convexity
        A_eq_rows = []
        b_eq = []

        # Linking constraints
        for idx in range(n_linking):
            row = np.zeros(n_total)
            for j, (_, col) in enumerate(col_meta):
                row[j] = col.linking_coeffs.get(idx, 0.0)
            row[n_cols + idx] = 1.0  # artificial
            A_eq_rows.append(row)
            b_eq.append(self.linking_rhs[idx])

        # Convexity constraints
        for blk in range(n_blocks):
            row = np.zeros(n_total)
            for j, (b, _) in enumerate(col_meta):
                if b == blk:
                    row[j] = 1.0
            A_eq_rows.append(row)
            b_eq.append(1.0)

        A_eq = np.array(A_eq_rows) if A_eq_rows else None
        b_eq = np.array(b_eq) if b_eq else None

        bounds = [(0, None)] * n_total

        result = linprog(c, A_eq=A_eq, b_eq=b_eq,
                         bounds=bounds, method='highs')

        if not result.success:
            return None

        # Extract duals from linprog result margins
        eq_marg = result.eqlin.marginals

        pi = [0.0] * n_linking
        mu = [0.0] * n_blocks

        # First n_linking equality rows = linking constraints
        for i in range(n_linking):
            pi[i] = eq_marg[i] if i < len(eq_marg) else 0.0

        # Next n_blocks equality rows = convexity constraints
        for blk in range(n_blocks):
            idx = n_linking + blk
            mu[blk] = eq_marg[idx] if idx < len(eq_marg) else 0.0

        return {"linking_duals": pi, "convexity_duals": mu, "lb": result.fun}

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def solve_pricing(self, block_id: int, duals: Dict) -> Optional[Column]:
        model = self.pricing_models[block_id]
        pi = duals["linking_duals"]
        mu = duals["convexity_duals"][block_id]
        # Free previous transform so we can modify objective and re-solve
        try:
            model.freeTransform()
        except Exception:
            pass
        self.update_pricing_objective(model, block_id, pi, mu)
        model.optimize()

        if model.getStatus() != "optimal":
            return None

        return self.extract_column_from_pricing(block_id, model)

    def compute_reduced_cost(self, block_id: int, column: Column,
                             duals: Dict) -> float:
        pi = duals["linking_duals"]
        mu = duals["convexity_duals"][block_id]
        rc = column.obj_val
        for cidx, coeff in column.linking_coeffs.items():
            rc -= pi[cidx] * coeff
        rc -= mu
        return rc

    # ------------------------------------------------------------------
    # CG loop
    # ------------------------------------------------------------------

    def run_column_generation(self, max_iter: int = 500,
                              tol: float = 1e-6) -> Optional[Dict]:
        print(f"Starting CG (max_iter={max_iter}, tol={tol})...")
        print(f"  Blocks: {self.num_blocks}")

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

    # ------------------------------------------------------------------
    # Final MILP (SCIP)
    # ------------------------------------------------------------------

    def solve_final_milp(self, time_limit: float = None,
                         mip_gap: float = 1e-4) -> Dict:
        """
        Build a SCIP MILP with binary lambda variables from all generated
        columns. This is a one-shot solve, no iterative column generation.
        """
        from pyscipopt import Model, quicksum

        print("Solving final MILP...")

        milp = Model(f"{self.name}_MILP")
        milp.hideOutput()
        milp.setMinimize()

        col_lam_pairs = []
        for blk_cols in self.columns:
            for idx, col in enumerate(blk_cols):
                lam = milp.addVar(
                    f"lambda_{col.block_id}_{idx}",
                    vtype="B", obj=col.obj_val
                )
                col_lam_pairs.append((col, lam))

        # Linking constraints
        for idx, name in enumerate(self.linking_names):
            terms = []
            for col, lam in col_lam_pairs:
                coeff = col.linking_coeffs.get(idx, 0.0)
                if abs(coeff) > 1e-12:
                    terms.append(coeff * lam)
            lhs = quicksum(terms)
            rhs = self.linking_rhs[idx]
            sense = self.linking_sense[idx]
            if sense == 'E':
                milp.addCons(lhs == rhs, name=name)
            elif sense == 'G':
                milp.addCons(lhs >= rhs, name=name)
            else:
                milp.addCons(lhs <= rhs, name=name)

        # Convexity constraints
        for blk in range(self.num_blocks):
            terms = []
            for col, lam in col_lam_pairs:
                if col.block_id == blk:
                    terms.append(lam)
            lhs = quicksum(terms)
            milp.addCons(lhs == 1.0, name=f"convexity_{blk}")

        if time_limit:
            milp.setRealParam("limits/time", time_limit)
        milp.setRealParam("limits/gap", mip_gap)

        milp.optimize()
        status = milp.getStatus()

        # Store lambda var references for reconstruct_solution
        for col, lam in col_lam_pairs:
            col.lambda_var = lam
        self._milp_model = milp

        return {
            "status": status,
            "obj_val": milp.getObjVal() if status == "optimal" else None,
            "gap": milp.getGap() if status == "optimal" else None,
        }

    def reconstruct_solution(self) -> Dict[str, float]:
        """Reconstruct original variable values from lambda solution."""
        var_values: Dict[str, float] = {}
        for blk_cols in self.columns:
            for col in blk_cols:
                if col.lambda_var is not None:
                    try:
                        lam_val = self._milp_model.getVal(col.lambda_var)
                    except Exception:
                        lam_val = 0.0
                    if lam_val > 0.5:
                        for vname, val in col.var_values.items():
                            var_values[vname] = var_values.get(vname, 0.0) + val * lam_val
        return var_values
