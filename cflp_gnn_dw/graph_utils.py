"""
Graph extraction for GAP — builds bipartite variable-constraint HeteroData
directly from GAPInstance data (no SCIP query needed for topology).

Variable nodes: x_{i,j} (i=job, j=machine), n = n_jobs * n_machines
Constraint nodes: assign_i (i=job) + cap_j (j=machine), m = n_jobs + n_machines
Edges: x_{i,j} → assign_i (coeff 1), x_{i,j} → cap_j (coeff w_{i,j})
"""
import torch
import numpy as np
from torch_geometric.data import HeteroData


def _preprocess_val(x):
    """Log-transform for large magnitudes: sign(x) * log(1 + |x|)."""
    if abs(x) < 1e-9:
        return 0.0
    return np.sign(x) * np.log(1.0 + abs(x))


class GraphExtractor:
    """
    Extracts a bipartite HeteroData graph from a GAP instance.
    Optional: provide var_labels and con_labels from the optimal solution.
    """

    def __init__(self, instance):
        self.n = instance.n_jobs          # jobs
        self.m = instance.n_machines      # machines
        self.n_vars = self.n * self.m     # one variable per (job, machine) pair
        self.n_conss = self.n + self.m    # assign_i + cap_j
        self.costs = instance.costs
        self.weights = instance.weights
        self.capacities = instance.capacities

    # ------------------------------------------------------------------
    # Variable features (8 dims)
    # ------------------------------------------------------------------
    def get_variable_features(self):
        C = self.costs
        W = self.weights
        cap = self.capacities

        cost_max = C.max()
        weight_max = W.max()

        feats = np.zeros((self.n_vars, 8), dtype=np.float32)

        for i in range(self.n):
            costs_i = C[i, :]
            mean_cost_i = costs_i.mean()
            cheapest = costs_i.min()

            for j in range(self.m):
                idx = i * self.m + j
                c = C[i, j]
                w = W[i, j]
                cj = cap[j]

                feats[idx, 0] = c / cost_max                                      # normalized cost
                feats[idx, 1] = w / weight_max                                    # normalized weight
                feats[idx, 2] = min(w / max(cj, 1), 1.0)                         # fit ratio
                feats[idx, 3] = _preprocess_val(c - mean_cost_i)                  # cost deviation
                feats[idx, 4] = 1.0 if abs(c - cheapest) < 1e-9 else 0.0          # is cheapest for job
                feats[idx, 5] = _preprocess_val(w - W[:, j].mean())               # weight deviation
                feats[idx, 6] = (cj - w) / max(cj, 1)                             # capacity slack ratio
                feats[idx, 7] = 2.0  # degree (always 2 for GAP: assign + cap)

        return torch.tensor(feats, dtype=torch.float)

    # ------------------------------------------------------------------
    # Constraint features (6 dims)
    # ------------------------------------------------------------------
    def get_constraint_features(self):
        C = self.costs
        W = self.weights
        cap = self.capacities
        cap_max = cap.max()

        feats = np.zeros((self.n_conss, 6), dtype=np.float32)

        for i in range(self.n):
            feats[i, 0] = 1.0                          # RHS = 1 (assignment)
            feats[i, 1] = 1.0                          # sense_E
            feats[i, 2] = 0.0                          # sense_L
            feats[i, 3] = 1.0 / self.m                 # density
            feats[i, 4] = _preprocess_val(C[i, :].mean())  # avg cost for this job
            feats[i, 5] = 0.0                          # type: 0 = assignment

        for j in range(self.m):
            idx = self.n + j
            feats[idx, 0] = _preprocess_val(cap[j] / cap_max)   # RHS (normalized)
            feats[idx, 1] = 0.0                                 # not equality
            feats[idx, 2] = 1.0                                 # sense_L
            feats[idx, 3] = 1.0 / self.n                        # density
            feats[idx, 4] = _preprocess_val(W[:, j].sum() / max(cap[j], 1))  # capacity utilization
            feats[idx, 5] = 1.0                                 # type: 1 = capacity

        return torch.tensor(feats, dtype=torch.float)

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------
    def get_edges(self):
        """
        Each variable x_{i,j} connects to two constraints:
          - assign_i  (constr index = i)
          - cap_j     (constr index = n + j)
        """
        total_edges = self.n_vars * 2
        edge_index = np.zeros((2, total_edges), dtype=np.int64)
        edge_attr = np.zeros((total_edges, 2), dtype=np.float32)

        for i in range(self.n):
            for j in range(self.m):
                var_idx = i * self.m + j
                assign_idx = i
                cap_idx = self.n + j

                e1 = var_idx * 2
                e2 = e1 + 1

                # Edge: variable -> assignment constraint (coeff = 1)
                edge_index[0, e1] = var_idx
                edge_index[1, e1] = assign_idx
                edge_attr[e1, 0] = 1.0
                edge_attr[e1, 1] = 0.0  # edge type: assign

                # Edge: variable -> capacity constraint (coeff = weight)
                edge_index[0, e2] = var_idx
                edge_index[1, e2] = cap_idx
                edge_attr[e2, 0] = self.weights[i, j]
                edge_attr[e2, 1] = 1.0  # edge type: capacity

        return (torch.tensor(edge_index, dtype=torch.long),
                torch.tensor(edge_attr, dtype=torch.float))

    # ------------------------------------------------------------------
    # Build HeteroData
    # ------------------------------------------------------------------
    def extract(self, var_labels=None, con_labels=None):
        data = HeteroData()

        edge_index, edge_attr = self.get_edges()

        data['variable'].x = self.get_variable_features()
        data['constraint'].x = self.get_constraint_features()

        data['variable', 'connected_to', 'constraint'].edge_index = edge_index
        data['variable', 'connected_to', 'constraint'].edge_attr = edge_attr

        # Reverse edges
        rev_index = edge_index.flip(0)
        data['constraint', 'rev_connected_to', 'variable'].edge_index = rev_index
        data['constraint', 'rev_connected_to', 'variable'].edge_attr = edge_attr

        # Names
        data.var_names = [f"x_{i}_{j}" for i in range(self.n) for j in range(self.m)]
        data.con_names = (
            [f"assign_{i}" for i in range(self.n)] +
            [f"cap_{j}" for j in range(self.m)]
        )

        # Labels
        if var_labels is not None:
            var_y = []
            for i in range(self.n):
                for j in range(self.m):
                    var_y.append(var_labels.get((i, j), -1))
            data['variable'].y = torch.tensor(var_y, dtype=torch.long)

        if con_labels is not None:
            con_y = []
            for name in data.con_names:
                con_y.append(con_labels.get(name, -1))
            data['constraint'].y = torch.tensor(con_y, dtype=torch.long)

        return data
