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
    # Variable features (24 dims, Gasse et al. NeurIPS 2019 standard)
    # ------------------------------------------------------------------
    def get_variable_features(self):
        C = self.costs      # (n_jobs, n_machines) = (n, m)
        W = self.weights
        caps = self.capacities

        max_abs_obj = max(C.max(), 1.0)
        max_deg = 2.0  # GAP: every variable appears in exactly 2 constraints
        n_vars = self.n_vars
        n_cons = self.n_conss

        feats = np.zeros((self.n_vars, 24), dtype=np.float32)

        # Precompute per-machine and per-job statistics
        for i in range(self.n):
            costs_i = C[i, :]
            for j in range(self.m):
                idx = i * self.m + j
                c = C[i, j]
                w = W[i, j]
                cap_j = caps[j]

                # Column data (coefficients for this variable)
                col_vals = np.array([1.0, w])
                c_min = col_vals.min(); c_max = col_vals.max()
                c_mean = col_vals.mean(); c_std = col_vals.std(ddof=0) if len(col_vals) > 1 else 0.0

                # Connected constraints: assign_i (sense '=') and cap_j (sense '<')
                n_eq = 1  # assign
                n_le = 1  # cap
                n_conn = 2
                rhs_vals = np.array([1.0, cap_j])

                feats[idx, 0] = _preprocess_val(c)            # 0: obj
                feats[idx, 1] = 1.0                            # 1: is_bin
                feats[idx, 2] = 0.0                            # 2: is_int
                feats[idx, 3] = 0.0                            # 3: is_cont
                feats[idx, 4] = 1.0                            # 4: has_lb
                feats[idx, 5] = 1.0                            # 5: has_ub
                feats[idx, 6] = 0.0                            # 6: range (ub-lb=0, log can't handle; use 0)
                feats[idx, 7] = 2.0                            # 7: degree
                feats[idx, 8] = _preprocess_val(c_min)         # 8: c_min
                feats[idx, 9] = _preprocess_val(c_max)         # 9: c_max
                feats[idx, 10] = _preprocess_val(c_mean)       # 10: c_mean
                feats[idx, 11] = _preprocess_val(c_std)        # 11: c_std
                feats[idx, 12] = n_le / n_conn                 # 12: frac_le
                feats[idx, 13] = n_eq / n_conn                 # 13: frac_eq
                feats[idx, 14] = 0.0                           # 14: frac_ge
                feats[idx, 15] = _preprocess_val(rhs_vals.min())  # 15: rhs_min
                feats[idx, 16] = _preprocess_val(rhs_vals.max())  # 16: rhs_max
                feats[idx, 17] = _preprocess_val(2.0)          # 17: log_deg
                feats[idx, 18] = 2.0 / n_cons                  # 18: deg/n_cons
                feats[idx, 19] = 2.0 / max_deg                 # 19: deg/max_deg
                feats[idx, 20] = 1.0 if c > 0 else (0.0 if c == 0 else -1.0)  # 20: obj_sign
                feats[idx, 21] = 1.0 if c != 0 else 0.0        # 21: has_obj
                feats[idx, 22] = c / max_abs_obj                # 22: norm_obj
                feats[idx, 23] = idx / max(n_vars, 1)           # 23: positional

        return torch.tensor(feats, dtype=torch.float)

    # ------------------------------------------------------------------
    # Constraint features (18 dims, Gasse et al. NeurIPS 2019 standard)
    # ------------------------------------------------------------------
    def get_constraint_features(self):
        C = self.costs
        W = self.weights
        caps = self.capacities

        max_abs_rhs = max(max(caps), 1.0)
        n_cons = self.n_conss
        n_vars = self.n_vars
        m = self.m
        obj_vec = C.flatten()  # all costs as a flat vector

        feats = np.zeros((self.n_conss, 18), dtype=np.float32)

        # Assignment constraints (index 0..n-1)
        for i in range(self.n):
            # Row data: m coefficients of 1.0
            row_vals = np.ones(m)
            r_min = 1.0; r_max = 1.0; r_mean = 1.0; r_std = 0.0
            row_norm = np.sqrt(m)
            # Cosine similarity with objective
            obj_slice = C[i, :]
            dot_val = np.dot(row_vals, obj_slice)
            obj_norm = max(np.linalg.norm(obj_vec), 1e-9)
            rn = max(row_norm, 1e-9)
            cos_sim = dot_val / (rn * obj_norm)
            # All connected vars are binary
            frac_bin = 1.0; frac_int = 0.0; frac_cont = 0.0
            # Shared constraints: each assign_i shares vars with all cap_j
            n_shared = m
            shared_ratio = n_shared / (n_cons - 1) if n_cons > 1 else 0.0

            feats[i, 0] = 0.0                                    # 0: rhs (preprocessed, 1 → log(2)≈0.69, use 0 for simplicity)
            feats[i, 1] = 0.0                                    # 1: sense_le
            feats[i, 2] = 0.0                                    # 2: sense_ge
            feats[i, 3] = 1.0                                    # 3: sense_eq
            feats[i, 4] = m / n_vars                             # 4: density
            feats[i, 5] = cos_sim                                 # 5: cos_sim
            feats[i, 6] = _preprocess_val(r_min)                 # 6: row_min
            feats[i, 7] = _preprocess_val(r_max)                 # 7: row_max
            feats[i, 8] = _preprocess_val(r_mean)                # 8: row_mean
            feats[i, 9] = _preprocess_val(r_std)                 # 9: row_std
            feats[i, 10] = frac_bin                               # 10: frac_bin
            feats[i, 11] = frac_int                               # 11: frac_int
            feats[i, 12] = frac_cont                              # 12: frac_cont
            feats[i, 13] = _preprocess_val(row_norm)              # 13: row_norm
            feats[i, 14] = float(n_shared)                        # 14: n_shared
            feats[i, 15] = shared_ratio                           # 15: shared_ratio
            feats[i, 16] = 1.0 / max_abs_rhs if max_abs_rhs > 0 else 0.0  # 16: norm_rhs
            feats[i, 17] = 0.0 if row_norm < 1e-9 else 1.0 / row_norm      # 17: rhs/rownorm

        # Capacity constraints (index n..n+m-1)
        for j in range(self.m):
            idx = self.n + j
            # Row data: n coefficients = weights[:,j]
            row_vals = W[:, j].copy()
            r_min = row_vals.min(); r_max = row_vals.max()
            r_mean = row_vals.mean()
            r_std = row_vals.std(ddof=0) if len(row_vals) > 1 else 0.0
            row_norm = np.linalg.norm(row_vals)
            dot_val = np.dot(row_vals, C[:, j])
            obj_norm = max(np.linalg.norm(obj_vec), 1e-9)
            cos_sim = dot_val / (row_norm * obj_norm) if row_norm > 1e-9 else 0.0
            frac_bin = 1.0; frac_int = 0.0; frac_cont = 0.0
            n_shared = self.n  # shares vars with all assign constraints
            shared_ratio = n_shared / (n_cons - 1) if n_cons > 1 else 0.0
            cap_j = caps[j]

            feats[idx, 0] = _preprocess_val(cap_j)               # 0: rhs
            feats[idx, 1] = 1.0                                    # 1: sense_le
            feats[idx, 2] = 0.0                                    # 2: sense_ge
            feats[idx, 3] = 0.0                                    # 3: sense_eq
            feats[idx, 4] = self.n / n_vars                        # 4: density
            feats[idx, 5] = cos_sim                                # 5: cos_sim
            feats[idx, 6] = _preprocess_val(r_min)                # 6: row_min
            feats[idx, 7] = _preprocess_val(r_max)                # 7: row_max
            feats[idx, 8] = _preprocess_val(r_mean)               # 8: row_mean
            feats[idx, 9] = _preprocess_val(r_std)                # 9: row_std
            feats[idx, 10] = frac_bin                              # 10: frac_bin
            feats[idx, 11] = frac_int                              # 11: frac_int
            feats[idx, 12] = frac_cont                             # 12: frac_cont
            feats[idx, 13] = _preprocess_val(row_norm)             # 13: row_norm
            feats[idx, 14] = float(n_shared)                       # 14: n_shared
            feats[idx, 15] = shared_ratio                          # 15: shared_ratio
            feats[idx, 16] = cap_j / max_abs_rhs                   # 16: norm_rhs
            feats[idx, 17] = cap_j / row_norm if row_norm > 1e-9 else 0.0  # 17: rhs/rownorm

        return torch.tensor(feats, dtype=torch.float)

    # ------------------------------------------------------------------
    # Edges (6 dims: coeff_log, norm_r, norm_c, sign, norm_row_max, norm_col_max)
    # ------------------------------------------------------------------
    def get_edges(self):
        total_edges = self.n_vars * 2
        edge_index = np.zeros((2, total_edges), dtype=np.int64)
        edge_attr = np.zeros((total_edges, 6), dtype=np.float32)

        # Precompute row norms (per constraint) and col norms (per variable)
        row_norms = np.zeros(self.n_conss)
        col_norms = np.zeros(self.n_vars)
        row_max = np.ones(self.n_conss)
        col_max = np.ones(self.n_vars)
        for i in range(self.n):
            for j in range(self.m):
                v = i * self.m + j
                w = self.weights[i, j]
                row_norms[i] += 1.0  # assign
                row_norms[self.n + j] += w * w
                col_norms[v] += 1.0 + w * w
                row_max[i] = max(row_max[i], 1.0)
                row_max[self.n + j] = max(row_max[self.n + j], w)
                col_max[v] = max(col_max[v], max(1.0, w))
        row_norms = np.sqrt(np.maximum(row_norms, 1e-9))
        col_norms = np.sqrt(np.maximum(col_norms, 1e-9))

        for i in range(self.n):
            for j in range(self.m):
                var_idx = i * self.m + j
                assign_idx = i
                cap_idx = self.n + j
                w = float(self.weights[i, j])
                rn_a = row_norms[assign_idx]
                rn_c = row_norms[cap_idx]
                cn = col_norms[var_idx]
                rm_a = row_max[assign_idx]
                rm_c = row_max[cap_idx]
                cm = col_max[var_idx]

                e1, e2 = var_idx * 2, var_idx * 2 + 1

                # Edge to assign constraint (coeff=1)
                edge_index[0, e1] = var_idx
                edge_index[1, e1] = assign_idx
                edge_attr[e1, 0] = _preprocess_val(1.0)
                edge_attr[e1, 1] = 1.0 / rn_a
                edge_attr[e1, 2] = 1.0 / cn
                edge_attr[e1, 3] = 1.0
                edge_attr[e1, 4] = 1.0 / rm_a
                edge_attr[e1, 5] = 1.0 / cm

                # Edge to capacity constraint (coeff=weight)
                edge_index[0, e2] = var_idx
                edge_index[1, e2] = cap_idx
                edge_attr[e2, 0] = _preprocess_val(w)
                edge_attr[e2, 1] = w / rn_c
                edge_attr[e2, 2] = w / cn
                edge_attr[e2, 3] = 1.0 if w > 0 else (-1.0 if w < 0 else 0.0)
                edge_attr[e2, 4] = w / rm_c if rm_c > 1e-9 else 0.0
                edge_attr[e2, 5] = w / cm if cm > 1e-9 else 0.0

        return (torch.tensor(edge_index, dtype=torch.long),
                torch.tensor(edge_attr, dtype=torch.float))

    # ------------------------------------------------------------------
    # Build HeteroData
    # ------------------------------------------------------------------
    def extract(self, var_labels=None, con_labels=None):
        data = HeteroData()

        edge_index, edge_attr = self.get_edges()

        data['variable'].x = self.get_variable_features()
        data['variable'].num_nodes = self.n_vars
        data['constraint'].x = self.get_constraint_features()
        data['constraint'].num_nodes = self.n_conss

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
