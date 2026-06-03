"""
Build the GNN dataset from GAP .lp files.

For each instance:
  1. Load .lp into Gurobi, write .mps
  2. Run GCG on the .mps to get decomposition (.dec)
  3. Parse .dec → constraint-to-block assignments → infer variable labels
  4. Extract bipartite graph (GraphExtractor) → HeteroData .pt

Usage:
    python 02_generate_dataset.py --problem gap --split train
    python 02_generate_dataset.py --problem gap --jobs 32
"""

import os
import glob
import argparse
import sys
import concurrent.futures
from pathlib import Path
from tqdm import tqdm

import torch
import numpy as np
import gurobipy as gp

sys.path.append(str(Path(__file__).parent))
from gcg_interface import run_gcg, parse_dec
from data_process import add_laplacian_pe, add_block_pe
import config

# ---------------------------------------------------------------------------
# Graph extraction (reused from the original 02_generate_dataset.py)
# ---------------------------------------------------------------------------

def preprocess_val(x):
    if np.abs(x) < 1e-9:
        return 0.0
    return np.sign(x) * np.log(1 + np.abs(x))


class GraphExtractor:
    """
    Extract bipartite (variable-constraint) graph from a Gurobi model.

    Feature dimensions (matching Gasse et al. NeurIPS 2019 standards):
      Variables: 24 dims (objective, bounds, type, coefficient stats,
                          constraint-type ratios, RHS stats, degree info,
                          normalized objective, positional)
      Constraints: 18 dims (RHS, sense, density, cosine sim, coeff stats,
                            variable-type ratios, row norm, sharing, norm RHS)
      Edges: 6 dims (coeff log, row-norm, col-norm, sign, row-max-norm, col-max-norm)
    """

    def __init__(self, model):
        self.model = model
        self.model.update()
        self.vars = model.getVars()
        self.conss = model.getConstrs()
        self.n_vars = len(self.vars)
        self.n_conss = len(self.conss)
        self.A = model.getA()
        # Precompute globals reused by edge extraction
        self._compute_global_stats()

    def _compute_global_stats(self):
        A_csr = self.A.tocsr()
        A_csc = self.A.tocsc()

        # Row norms & stats
        self._row_data = []
        self._row_max = np.zeros(self.n_conss)
        for i in range(self.n_conss):
            row = A_csr[i]
            d = row.data if row.nnz > 0 else np.array([])
            self._row_data.append(d)
            self._row_max[i] = np.max(np.abs(d)) if len(d) > 0 else 1.0

        # Col norms & stats
        self._col_data = []
        self._col_max = np.zeros(self.n_vars)
        for j in range(self.n_vars):
            col = A_csc[:, j]
            d = col.data if col.nnz > 0 else np.array([])
            self._col_data.append(d)
            self._col_max[j] = np.max(np.abs(d)) if len(d) > 0 else 1.0

        # Max obj value for normalization
        obj_abs = [abs(v.Obj) for v in self.vars]
        self._max_abs_obj = max(obj_abs) if obj_abs else 1.0
        if self._max_abs_obj < 1e-9:
            self._max_abs_obj = 1.0

        # Max RHS for normalization
        rhs_abs = [abs(c.RHS) for c in self.conss]
        self._max_abs_rhs = max(rhs_abs) if rhs_abs else 1.0
        if self._max_abs_rhs < 1e-9:
            self._max_abs_rhs = 1.0

        # Global degree stats (populated after edges are built)
        self._var_degrees = np.zeros(self.n_vars)
        self._max_var_degree = 1.0

        # Variable type per constraint
        var_types = np.array([
            0.0 if v.VType == 'B' else (1.0 if v.VType == 'I' else 2.0)
            for v in self.vars
        ])

    def get_variable_features(self):
        A_csc = self.A.tocsc()
        feats = []

        for j, v in enumerate(self.vars):
            obj = v.Obj
            p_obj = preprocess_val(obj)
            vtype = v.VType
            is_bin = 1.0 if vtype == 'B' else 0.0
            is_int = 1.0 if vtype == 'I' else 0.0
            is_cont = 1.0 if vtype == 'C' else 0.0
            lb, ub = v.LB, v.UB
            has_lb = 1.0 if lb > -1e20 else 0.0
            has_ub = 1.0 if ub < 1e20 else 0.0
            if has_lb and has_ub:
                b_range = ub - lb
            elif has_lb:
                b_range = 1e2
            elif has_ub:
                b_range = 1e2
            else:
                b_range = 1e3
            p_range = preprocess_val(b_range)
            degree = 0.0  # placeholder

            # Coefficient stats for this column
            col_d = self._col_data[j]
            if len(col_d) > 0:
                c_min = np.min(col_d)
                c_max = np.max(col_d)
                c_mean = np.mean(col_d)
                c_std = np.std(col_d) if len(col_d) > 1 else 0.0
            else:
                c_min = c_max = c_mean = c_std = 0.0

            # Constraint-type ratios: what fraction of connected cons are ≤, =, ≥
            col_indices = A_csc[:, j].indices
            n_conn = len(col_indices)
            if n_conn > 0:
                cons_for_var = [self.conss[i] for i in col_indices]
                n_le = sum(1 for c in cons_for_var if c.Sense == '<')
                n_eq = sum(1 for c in cons_for_var if c.Sense == '=')
                n_ge = sum(1 for c in cons_for_var if c.Sense == '>')
                frac_le = n_le / n_conn
                frac_eq = n_eq / n_conn
                frac_ge = n_ge / n_conn
                rhs_vals = [c.RHS for c in cons_for_var]
                rhs_min = min(rhs_vals)
                rhs_max = max(rhs_vals)
            else:
                frac_le = frac_eq = frac_ge = 0.0
                rhs_min = rhs_max = 0.0

            # Objective info
            obj_sign = 1.0 if obj > 0 else (0.0 if obj == 0 else -1.0)
            has_obj = 1.0 if obj != 0 else 0.0
            norm_obj = obj / self._max_abs_obj

            feats.append([
                # basic (8)
                p_obj, is_bin, is_int, is_cont, has_lb, has_ub, p_range, degree,
                # coefficient distribution (4)
                preprocess_val(c_min), preprocess_val(c_max),
                preprocess_val(c_mean), preprocess_val(c_std),
                # constraint-type fractions (3)
                frac_le, frac_eq, frac_ge,
                # RHS stats (2)
                preprocess_val(rhs_min), preprocess_val(rhs_max),
                # degree info (3)
                0.0, 0.0, 0.0,  # placeholder: log(1+deg), deg/n_conss, deg/max_deg
                # objective info (3)
                obj_sign, has_obj, norm_obj,
                # positional (1)
                j / max(self.n_vars, 1),
            ])
        return torch.tensor(feats, dtype=torch.float)

    def get_constraint_features(self):
        obj_vec = np.array([v.Obj for v in self.vars])
        obj_norm = np.linalg.norm(obj_vec)
        if obj_norm < 1e-9:
            obj_norm = 1.0
        A_csr = self.A.tocsr()
        feats = []

        # Precompute variable type fractions per constraint
        var_types = np.array([
            0.0 if v.VType == 'B' else (1.0 if v.VType == 'I' else 2.0)
            for v in self.vars
        ])

        for i, c in enumerate(self.conss):
            rhs = c.RHS
            sense = c.Sense
            sense_le = 1.0 if sense == '<' else 0.0
            sense_ge = 1.0 if sense == '>' else 0.0
            sense_eq = 1.0 if sense == '=' else 0.0
            p_rhs = preprocess_val(rhs)

            row = A_csr[i]
            n_nz = row.nnz
            density = n_nz / self.n_vars if self.n_vars > 0 else 0.0

            row_data = row.data if n_nz > 0 else np.array([])
            row_indices = row.indices

            # Cosine similarity
            dot_prod = np.sum(row_data * obj_vec[row_indices]) if n_nz > 0 else 0.0
            row_norm_sq = np.sum(row_data ** 2) if n_nz > 0 else 0.0
            row_norm = np.sqrt(row_norm_sq) if row_norm_sq > 1e-9 else 1.0
            cos_sim = dot_prod / (row_norm * obj_norm)

            # Coefficient stats
            if n_nz > 0:
                r_min = np.min(row_data)
                r_max = np.max(row_data)
                r_mean = np.mean(row_data)
                r_std = np.std(row_data) if n_nz > 1 else 0.0
            else:
                r_min = r_max = r_mean = r_std = 0.0

            # Variable type fractions in this constraint
            if n_nz > 0:
                vtypes_in_row = var_types[row_indices]
                n_bin = np.sum(vtypes_in_row == 0.0)
                n_int = np.sum(vtypes_in_row == 1.0)
                n_cont = np.sum(vtypes_in_row == 2.0)
                frac_bin = n_bin / n_nz
                frac_int = n_int / n_nz
                frac_cont = n_cont / n_nz
            else:
                frac_bin = frac_int = frac_cont = 0.0

            # Normalized RHS
            norm_rhs = rhs / self._max_abs_rhs
            rhs_over_rownorm = abs(rhs) / row_norm if row_norm > 1e-9 else 0.0

            feats.append([
                # basic (6)
                p_rhs, sense_le, sense_ge, sense_eq, density, cos_sim,
                # coefficient distribution (4)
                preprocess_val(r_min), preprocess_val(r_max),
                preprocess_val(r_mean), preprocess_val(r_std),
                # variable-type fractions (3)
                frac_bin, frac_int, frac_cont,
                # row norm (1)
                preprocess_val(row_norm),
                # constraint sharing (2) — placeholder: filled later
                0.0, 0.0,
                # normalized RHS (2)
                norm_rhs, rhs_over_rownorm,
            ])
        return torch.tensor(feats, dtype=torch.float)

    def get_edges(self):
        A_coo = self.A.tocoo()

        # Row norms
        r_sq = self.A.copy()
        r_sq.data **= 2
        row_norms = np.array(r_sq.sum(axis=1)).flatten()
        row_norms = np.sqrt(row_norms)
        row_norms[row_norms < 1e-9] = 1.0

        # Col norms
        c_sq = self.A.copy()
        c_sq.data **= 2
        col_norms = np.array(c_sq.sum(axis=0)).flatten()
        col_norms = np.sqrt(col_norms)
        col_norms[col_norms < 1e-9] = 1.0

        edge_indices = []
        edge_attrs = []
        for k in range(len(A_coo.data)):
            r = A_coo.row[k]
            c = A_coo.col[k]
            val = A_coo.data[k]
            edge_indices.append([c, r])

            p_coeff = preprocess_val(val)
            norm_r = val / row_norms[r]
            norm_c = val / col_norms[c]
            sign = 1.0 if val > 0 else (-1.0 if val < 0 else 0.0)
            norm_row_max = val / self._row_max[r] if self._row_max[r] > 1e-9 else 0.0
            norm_col_max = val / self._col_max[c] if self._col_max[c] > 1e-9 else 0.0

            edge_attrs.append([p_coeff, norm_r, norm_c, sign, norm_row_max, norm_col_max])

        edge_index = torch.tensor(edge_indices, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_attrs, dtype=torch.float)
        # Update degree info
        if edge_index.numel() > 0:
            self._var_degrees = torch.bincount(
                edge_index[0], minlength=self.n_vars
            ).float().numpy()
            self._max_var_degree = max(self._var_degrees.max(), 1.0)
        return edge_index, edge_attr

    def _add_homophilic_edges(self, data):
        """Add var↔var and con↔con edges based on 2-hop connectivity.

        var↔var: two variables share at least one constraint.
        con↔con: two constraints share at least one variable.
        """
        var_to_con_edge = data['variable', 'connected_to', 'constraint'].edge_index
        n_vars = data['variable'].x.shape[0]
        n_cons = data['constraint'].x.shape[0]

        if var_to_con_edge.numel() == 0:
            data['variable', 'shares_constraint_with', 'variable'].edge_index = \
                torch.empty((2, 0), dtype=torch.long)
            data['constraint', 'shares_variable_with', 'constraint'].edge_index = \
                torch.empty((2, 0), dtype=torch.long)
            return

        # Build sparse E: n_vars × n_cons
        indices = var_to_con_edge
        values = torch.ones(indices.shape[1], dtype=torch.float32)
        E = torch.sparse_coo_tensor(indices, values, (n_vars, n_cons)).coalesce()

        # var↔var: A_var = E @ E^T, remove diagonal
        A_var = torch.sparse.mm(E, E.t()).coalesce()
        vv_indices = A_var.indices()
        vv_mask = vv_indices[0] != vv_indices[1]
        var_var_edges = vv_indices[:, vv_mask]

        # con↔con: A_con = E^T @ E, remove diagonal
        A_con = torch.sparse.mm(E.t(), E).coalesce()
        cc_indices = A_con.indices()
        cc_mask = cc_indices[0] != cc_indices[1]
        con_con_edges = cc_indices[:, cc_mask]

        data['variable', 'shares_constraint_with', 'variable'].edge_index = var_var_edges
        data['constraint', 'shares_variable_with', 'constraint'].edge_index = con_con_edges

    def extract(self):
        from torch_geometric.data import HeteroData
        data = HeteroData()

        # 1. Edges
        edge_index, edge_attr = self.get_edges()

        # 2. Variable features
        var_feats = self.get_variable_features()
        # Backfill degree-dependent placeholders (indices 7, 17, 18, 19)
        deg = self._var_degrees
        max_deg = self._max_var_degree
        for j in range(self.n_vars):
            var_feats[j, 7] = float(deg[j])
            var_feats[j, 17] = float(preprocess_val(deg[j]))
            var_feats[j, 18] = float(deg[j] / self.n_conss) if self.n_conss > 0 else 0.0
            var_feats[j, 19] = float(deg[j] / max_deg)
        data['variable'].x = var_feats

        # 3. Constraint features
        con_feats = self.get_constraint_features()
        # Backfill constraint sharing placeholders (indices 14, 15)
        # Build var→con mapping
        var_to_cons = {j: set() for j in range(self.n_vars)}
        if edge_index.numel() > 0:
            for k in range(edge_index.shape[1]):
                v = int(edge_index[0, k])
                c = int(edge_index[1, k])
                var_to_cons[v].add(c)
        for i in range(self.n_conss):
            shared = set()
            row = self.A.tocsr()[i]
            for v_idx in row.indices:
                shared.update(var_to_cons.get(int(v_idx), set()))
            shared.discard(i)
            n_shared = len(shared)
            con_feats[i, 14] = float(n_shared)
            con_feats[i, 15] = float(n_shared / (self.n_conss - 1)) if self.n_conss > 1 else 0.0
        data['constraint'].x = con_feats

        # 4. Topology
        data['variable', 'connected_to', 'constraint'].edge_index = edge_index
        data['variable', 'connected_to', 'constraint'].edge_attr = edge_attr
        data['constraint', 'rev_connected_to', 'variable'].edge_index = edge_index.flip(0)
        data['constraint', 'rev_connected_to', 'variable'].edge_attr = edge_attr

        # 5. Homophilic edges (var↔var, con↔con via 2-hop)
        self._add_homophilic_edges(data)

        # 6. Positional encoding
        data = add_laplacian_pe(data, k=config.MODEL_PARAMS.get('pe_dim', 8))

        # 7. Block-structure PE (Louvain communities)
        data = add_block_pe(data, k=config.MODEL_PARAMS.get('block_pe_dim', 8))

        data.var_names = [v.VarName for v in self.vars]
        data.con_names = [c.ConstrName for c in self.conss]
        return data


# ---------------------------------------------------------------------------
# Label generation from GCG decomposition
# ---------------------------------------------------------------------------

def infer_variable_labels_from_dec(model, dec_info):
    """
    Given a Gurobi model and parsed .dec info, assign each variable a label:
      0            → master / linking variable (appears in ≥2 blocks or only master)
      block_id     → belongs exclusively to that subproblem block
    """
    n_vars = len(model.getVars())
    n_conss = len(model.getConstrs())

    # Build: constraint_name -> set of block ids (0 = master)
    con_to_blocks = {}
    for name in dec_info['master_conss']:
        con_to_blocks.setdefault(name, set()).add(0)
    for bid, names in dec_info['block_conss'].items():
        for name in names:
            con_to_blocks.setdefault(name, set()).add(bid)

    # For constraints NOT mentioned in .dec (unassigned), GCG's CONSDEFAULTMASTER=1
    # puts them in master (block 0). We mirror that.
    for c in model.getConstrs():
        if c.ConstrName not in con_to_blocks:
            con_to_blocks[c.ConstrName] = {0}

    # Get sparse A matrix to map variables → constraints
    A = model.getA()         # shape (n_conss, n_vars)
    A_csc = A.tocsc()        # CSC for fast column access

    var_labels = np.full(n_vars, -1, dtype=int)

    for var_idx in range(n_vars):
        col_start = A_csc.indptr[var_idx]
        col_end = A_csc.indptr[var_idx + 1]
        if col_start == col_end:
            var_labels[var_idx] = 0     # isolated → master
            continue

        involved_blocks = set()
        for ptr in range(col_start, col_end):
            con_idx = A_csc.indices[ptr]
            c_name = model.getConstrs()[con_idx].ConstrName
            involved_blocks.update(con_to_blocks.get(c_name, {0}))

        involved_blocks.discard(0)      # remove master
        if len(involved_blocks) == 1:
            var_labels[var_idx] = list(involved_blocks)[0]
        else:
            var_labels[var_idx] = 0     # multiple blocks or only master → master

    return torch.tensor(var_labels, dtype=torch.long)


# ---------------------------------------------------------------------------
# Build Gurobi model from GAP .lp (Gurobi reads LP natively)
# ---------------------------------------------------------------------------

def build_gap_model(lp_path):
    """Read GAP LP file into a Gurobi model."""
    model = gp.read(str(lp_path))
    model.setParam('OutputFlag', 0)
    return model


# ---------------------------------------------------------------------------
# Single-file worker
# ---------------------------------------------------------------------------

def process_single_file(args_tuple):
    lp_path, mps_dir, dec_dir, processed_dir, gcg_binary, gcg_timelimit = args_tuple
    lp_path = Path(lp_path)
    instance_name = lp_path.stem

    try:
        # 1. Build model & write MPS
        model = build_gap_model(lp_path)
        mps_path = Path(mps_dir) / f"{instance_name}.mps"
        model.write(str(mps_path))

        # 2. Run GCG
        dec_path = Path(dec_dir) / f"{instance_name}.dec"
        gcg_ok = run_gcg(mps_path, dec_path, gcg_binary, gcg_timelimit)

        # 3. Parse .dec → labels. Skip instance if GCG failed.
        if gcg_ok and dec_path.exists():
            dec_info = parse_dec(dec_path)
        else:
            model.dispose()
            return False, f"{lp_path}: GCG failed, skipping (no ground truth decomposition)"

        # 4. Extract graph & assign labels
        extractor = GraphExtractor(model)
        data = extractor.extract()
        data['variable'].y = infer_variable_labels_from_dec(model, dec_info)

        # 5. Save
        save_path = Path(processed_dir) / f"{instance_name}.pt"
        torch.save(data, save_path)

        model.dispose()
        return True, lp_path

    except Exception as e:
        return False, f"{lp_path}: {e}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_dataset(problem='gap', split='train', n_jobs=64):
    raw_dir = config.RAW_DATA_DIR / problem / split
    mps_dir = config.MPS_DATA_DIR / problem / split
    dec_dir = config.DECOMP_DIR / problem / split
    processed_dir = config.PROCESSED_DATA_DIR / problem / split

    if not raw_dir.exists():
        print(f"Raw data directory {raw_dir} does not exist.")
        return

    for d in [mps_dir, dec_dir, processed_dir]:
        os.makedirs(d, exist_ok=True)

    files = sorted(glob.glob(str(raw_dir / "*.lp")))
    print(f"Found {len(files)} instances in {raw_dir}.")
    print(f"Using GCG binary: '{config.GCG_BINARY}'")
    print(f"Processing with {n_jobs} workers...")

    tasks = [(f, mps_dir, dec_dir, processed_dir,
              config.GCG_BINARY, config.GCG_TIME_LIMIT) for f in files]

    with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
        results = list(tqdm(executor.map(process_single_file, tasks),
                           total=len(tasks)))

    successes = sum(1 for r in results if r[0])
    errors = [r[1] for r in results if not r[0]]
    print(f"Processed: {successes}/{len(files)} succeeded, {len(errors)} skipped")
    if errors:
        gcg_fails = sum(1 for e in errors if "GCG failed" in str(e))
        other_fails = len(errors) - gcg_fails
        if gcg_fails:
            print(f"  GCG failures (no ground truth): {gcg_fails}")
        if other_fails:
            print(f"  Other errors: {other_fails}")
            for err in errors[:5]:
                if "GCG failed" not in str(err):
                    print(f"    {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default='gap')
    parser.add_argument('--split', type=str, default=None,
                        help='Process a single split (train/valid/test). '
                             'If omitted, process all.')
    parser.add_argument('--jobs', type=int, default=32)
    args = parser.parse_args()

    splits = [args.split] if args.split else ['train', 'valid', 'test']
    for s in splits:
        process_dataset(args.problem, s, n_jobs=args.jobs)
