"""
GAP (Generalized Assignment Problem) — problem definition, DP knapsack,
SCIP compact model, and optimal label extraction.
"""
import numpy as np
from pyscipopt import Model


class GAPInstance:
    """Efficient container for GAP instance data using NumPy."""

    def __init__(self, file_path):
        self.file_path = file_path
        self.n_jobs = 0
        self.n_machines = 0
        self.costs = None      # (n_jobs, n_machines)
        self.weights = None    # (n_jobs, n_machines)
        self.capacities = None # (n_machines,)

        self._load(file_path)

    def _load(self, file_path):
        with open(file_path, 'r') as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

        self.n_jobs, self.n_machines = map(int, lines[0].split())

        self.costs = np.zeros((self.n_jobs, self.n_machines))
        for i in range(self.n_jobs):
            self.costs[i] = list(map(float, lines[1 + i].split()))

        offset = 1 + self.n_jobs
        self.weights = np.zeros((self.n_jobs, self.n_machines))
        for i in range(self.n_jobs):
            self.weights[i] = list(map(float, lines[offset + i].split()))

        offset += self.n_jobs
        self.capacities = np.array(list(map(float, lines[offset].split())))

    def to_text(self):
        """Serialize back to the file format string."""
        lines = [f"{self.n_jobs} {self.n_machines}"]
        for i in range(self.n_jobs):
            lines.append(" ".join(str(self.costs[i, j]) for j in range(self.n_machines)))
        for i in range(self.n_jobs):
            lines.append(" ".join(str(self.weights[i, j]) for j in range(self.n_machines)))
        lines.append(" ".join(str(self.capacities[j]) for j in range(self.n_machines)))
        return "\n".join(lines)


class KnapsackDPSolver:
    """0-1 knapsack via dynamic programming, for DW pricing subproblems."""

    def __init__(self, profits, weights, capacity):
        self.profits = np.asarray(profits, dtype=float)
        self.weights = np.asarray(weights, dtype=float)
        self.capacity = capacity
        self.n_items = len(profits)
        self.best_value = 0.0
        self.selected = []

    def solve(self):
        n = self.n_items
        C = int(self.capacity)
        w_int = self.weights.astype(int)
        p = self.profits

        # 2D DP: dp[i][w] = max value using first i items with capacity w
        dp = np.zeros((n + 1, C + 1), dtype=float)

        for i in range(1, n + 1):
            wi = w_int[i - 1]
            pi = p[i - 1]
            for w in range(C + 1):
                dp[i, w] = dp[i - 1, w]  # skip item
                if w >= wi:
                    dp[i, w] = max(dp[i, w], dp[i - 1, w - wi] + pi)

        self.best_value = dp[n, C]

        # Reconstruct by tracing back through the DP table
        w = C
        for i in range(n, 0, -1):
            wi = w_int[i - 1]
            if w >= wi and dp[i, w] == dp[i - 1, w - wi] + p[i - 1]:
                self.selected.append(i - 1)
                w -= wi

        self.selected.sort()
        return self.best_value, self.selected


def build_scip_model(instance, name="GAP"):
    """Build SCIP compact model for a GAP instance."""
    model = Model(name)
    model.hideOutput()

    n = instance.n_jobs
    m = instance.n_machines

    x = {}
    for i in range(n):
        for j in range(m):
            var = model.addVar(f"x_{i}_{j}", vtype="B", obj=instance.costs[i, j])
            x[i, j] = var

    model.setMinimize()

    # Assignment constraints: sum_j x[i,j] = 1
    for i in range(n):
        vars_i = [x[i, j] for j in range(m)]
        coeffs = [1.0] * m
        model.addCons(
            sum(c * v for c, v in zip(coeffs, vars_i)) == 1,
            name=f"assign_{i}"
        )

    # Capacity constraints: sum_i w[i,j] * x[i,j] <= c[j]
    for j in range(m):
        vars_j = [x[i, j] for i in range(n)]
        coeffs = [instance.weights[i, j] for i in range(n)]
        model.addCons(
            sum(c * v for c, v in zip(coeffs, vars_j)) <= instance.capacities[j],
            name=f"cap_{j}"
        )

    return model, x


def extract_labels(instance, x_sol):
    """
    Extract training labels from an optimal solution.

    Returns:
        var_labels: dict {(i,j): label} — label = j (machine) if x[i,j]=1, else -1
        con_labels: dict {con_name: label} — assignment → -2 (LINKING), capacity → j (LOCAL)
    """
    n = instance.n_jobs
    m = instance.n_machines

    var_labels = {}
    for i in range(n):
        for j in range(m):
            val = x_sol.get((i, j), 0.0)
            var_labels[(i, j)] = j if val > 0.5 else -1

    con_labels = {}
    for i in range(n):
        con_labels[f"assign_{i}"] = -2  # LINKING
    for j in range(m):
        con_labels[f"cap_{j}"] = j      # LOCAL (machine j)

    return var_labels, con_labels
