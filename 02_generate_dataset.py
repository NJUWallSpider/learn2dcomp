import os
import glob
from data_process import add_laplacian_pe
import torch
import numpy as np
import config
from pathlib import Path
from torch_geometric.data import HeteroData
import gurobipy as gp
import argparse
import sys
import concurrent.futures
from tqdm import tqdm

# Import CFLP directly. Ensure current dir is in path.
sys.path.append(str(Path(__file__).parent))
from UFLP_gurobi import DataLoader, build_model

def preprocess_val(x):
    """
    Log-transform for large magnitudes: sign(x) * log(1 + |x|)
    """
    if np.abs(x) < 1e-9:
        return 0.0
    return np.sign(x) * np.log(1 + np.abs(x))

class GraphExtractor:
    def __init__(self, model):
        self.model = model
        self.model.update()

        # Access variables and constraints
        self.vars = model.getVars()
        self.conss = model.getConstrs()
        self.n_vars = len(self.vars)
        self.n_conss = len(self.conss)

        # Get constraint matrix A (rows=conss, cols=vars)
        # Gurobi returns this as a scipy sparse matrix
        self.A = model.getA()

    def get_variable_features(self):
        """
        Extract variable features from Gurobi vars.
        1. Obj Coeff
        2. Type (Binary, Integer, Continuous)
        3. Has Lower/Upper Bound
        4. Bound Range
        5. Degree (placeholder, updated later)
        """
        feats = []
        for v in self.vars:
            # 1. Obj Coeff
            obj = v.Obj
            p_obj = preprocess_val(obj)

            # 2. Type
            vtype = v.VType
            is_bin = 1.0 if vtype == 'B' else 0.0
            is_int = 1.0 if vtype == 'I' else 0.0
            is_cont = 1.0 if vtype == 'C' else 0.0

            # 3. Bounds
            lb = v.LB
            ub = v.UB
            inf = gp.GRB.INFINITY

            # Gurobi default infinite bounds are 1e100 usually, check distinctively
            has_lb = 1.0 if lb > -1e20 else 0.0 # -inf is usually -1e100
            has_ub = 1.0 if ub < 1e20 else 0.0

            # 4. Range
            if has_lb and has_ub:
                b_range = ub - lb
            elif has_lb:
                b_range = 1e2
            elif has_ub:
                b_range = 1e2
            else:
                b_range = 1e3
            p_range = preprocess_val(b_range)

            # Degree (placeholder)
            degree = 0.0

            feats.append([p_obj, is_bin, is_int, is_cont, has_lb, has_ub, p_range, degree])

        return torch.tensor(feats, dtype=torch.float)

    def get_constraint_features(self):
        """
        Extract constraint features from Gurobi conss.
        1. RHS Value (normalized)
        2. Sense (<=, >=, =)
        3. Density
        4. Cosine Similarity (between constraint row and obj vector)
        """
        feats = []

        # Get objective vector for cosine similarity
        obj_vec = np.array([v.Obj for v in self.vars])
        obj_norm = np.linalg.norm(obj_vec)
        if obj_norm < 1e-9:
            obj_norm = 1.0

        # We can iterate through constraints or use matrix operations.
        # Iterating is safer for RHS/Sense which are not in matrix A.
        # But for Cosine Sim, matrix rows are better.

        # Convert A to CSR for efficient row slicing
        A_csr = self.A.tocsr()

        for i, c in enumerate(self.conss):
            # 1. RHS & Sense
            rhs = c.RHS
            sense = c.Sense

            sense_le = 0.0
            sense_ge = 0.0
            sense_eq = 0.0

            if sense == '<':
                sense_le = 1.0
            elif sense == '>':
                sense_ge = 1.0
            elif sense == '=':
                sense_eq = 1.0

            p_rhs = preprocess_val(rhs)

            # Row vector from matrix A
            row = A_csr[i]

            # 2. Density
            n_nz = row.nnz
            density = n_nz / self.n_vars

            # 3. Cosine Similarity
            # row is sparse. dense obj_vec.
            # dot product: sum(row_k * obj_k)
            # row indices: row.indices, row data: row.data
            dot_prod = 0.0
            row_norm_sq = 0.0

            if n_nz > 0:
                row_data = row.data
                row_indices = row.indices

                # Manual dot product for sparse row vs dense obj vector
                # Or just use matrix multiplication if efficient, but loop is fine for extraction
                dot_prod = np.sum(row_data * obj_vec[row_indices])
                row_norm_sq = np.sum(row_data ** 2)

            row_norm = np.sqrt(row_norm_sq)
            if row_norm < 1e-9:
                cos_sim = 0.0
            else:
                cos_sim = dot_prod / (row_norm * obj_norm)

            feats.append([p_rhs, sense_le, sense_ge, sense_eq, density, cos_sim])

        return torch.tensor(feats, dtype=torch.float)

    def get_edges(self):
        """
        Extract edges from sparse matrix A.
        Features:
        1. Coefficient
        2. Norm Row
        3. Norm Col
        """
        # A is (n_conss, n_vars)
        # Convert to COO for easy iteration
        A_coo = self.A.tocoo()

        # Calculate norms
        # Row norms
        row_norms = np.zeros(self.n_conss)
        # Col norms
        col_norms = np.zeros(self.n_vars)

        # We can compute norms faster using scipy/numpy
        # Row norms: sqrt(sum(x^2, axis=1))
        # Note: A is sparse.

        # A.power(2) elementwise square
        # sum(axis=1) sums rows
        r_sq = self.A.copy()
        r_sq.data **= 2
        row_norms = np.array(r_sq.sum(axis=1)).flatten() # returns matrix (n_conss, 1)
        row_norms = np.sqrt(row_norms)

        c_sq = self.A.copy()
        c_sq.data **= 2
        col_norms = np.array(c_sq.sum(axis=0)).flatten()
        col_norms = np.sqrt(col_norms)

        # Avoid div zero
        row_norms[row_norms < 1e-9] = 1.0
        col_norms[col_norms < 1e-9] = 1.0

        # Build edge list
        # Variable index is col, Constraint index is row
        # PyG Edge Index: [source, target]
        # Let's say: Variable -> Constraint
        # Source: A_coo.col (vars), Target: A_coo.row (conss)

        edge_indices = []
        edge_attrs = []

        rows = A_coo.row
        cols = A_coo.col
        data = A_coo.data

        for k in range(len(data)):
            r = rows[k] # constraint
            c = cols[k] # variable
            val = data[k]

            edge_indices.append([c, r])

            p_coeff = preprocess_val(val)
            norm_r = val / row_norms[r]
            norm_c = val / col_norms[c]

            edge_attrs.append([p_coeff, norm_r, norm_c])

        edge_index = torch.tensor(edge_indices, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_attrs, dtype=torch.float)

        return edge_index, edge_attr

    def generate_variable_labels(self):
        """
        Generate variable labels based on variable names.
        Master variables (y, z) -> 0
        Subproblem variables (x) -> subproblem ID (starting from 1)
        """
        labels = []
        for v in self.vars:
            name = v.VarName
            if "master" in name:
                labels.append(0)
            elif "subproblem" in name:
                # Format: subproblem_{i}_x_{i}_{j}
                try:
                    parts = name.split('_')
                    # parts[1] is the facility index 'i'
                    sub_id = int(parts[1])
                    labels.append(sub_id)
                except:
                    # Fallback
                    labels.append(-1)
            else:
                labels.append(-1)
        return torch.tensor(labels, dtype=torch.long)

    def generate_constraint_labels(self):
        """
        Generate constraint labels for DW decomposition.
        - LINKING (-2): disjunction constraints that couple multiple subproblems
        - Master (0): master-problem-only constraints (e.g. y+z==1)
        - Subproblem k (k>=1): demand constraints belonging to subproblem k (customer k)
        """
        labels = []
        for c in self.conss:
            name = c.ConstrName
            if "disjunction" in name:
                labels.append(-2)  # LINKING
            elif "demand" in name:
                try:
                    # Gurobi names: "demand[1]", "demand[2]", ...
                    sub_id = int(name.split("[")[1].split("]")[0])
                    labels.append(sub_id)
                except:
                    labels.append(-1)
            else:
                labels.append(0)  # Master block
        return torch.tensor(labels, dtype=torch.long)

    def extract(self):
        data = HeteroData()

        # 1. Edges
        edge_index, edge_attr = self.get_edges()

        # 2. Variable Features
        var_feats = self.get_variable_features()
        # Update degree
        if edge_index.numel() > 0:
            degrees = torch.bincount(edge_index[0], minlength=self.n_vars).float()
            var_feats[:, -1] = degrees

        data['variable'].x = var_feats

        # 3. Constraint Features
        con_feats = self.get_constraint_features()
        data['constraint'].x = con_feats

        # 4. Topology
        data['variable', 'connected_to', 'constraint'].edge_index = edge_index
        data['variable', 'connected_to', 'constraint'].edge_attr = edge_attr

        # Reverse edges
        data['constraint', 'rev_connected_to', 'variable'].edge_index = edge_index.flip(0)
        data['constraint', 'rev_connected_to', 'variable'].edge_attr = edge_attr

        data = add_laplacian_pe(data, k=config.MODEL_PARAMS.get('pe_dim', 8))

        # 5. Variable Labels
        data['variable'].y = self.generate_variable_labels()

        # 6. Constraint Labels (NEW — for DW decomposition multi-task learning)
        data['constraint'].y = self.generate_constraint_labels()

        # 7. Variable / Constraint Names
        data.var_names = [v.VarName for v in self.vars]
        data.con_names = [c.ConstrName for c in self.conss]

        return data

def process_single_file(args):
    """
    Worker function to process a single file.
    """
    fpath, mps_dir, processed_dir = args
    try:
        # Use CFLP loader and builder
        data_loader = DataLoader(fpath)
        model = build_model(data_loader)

        # 2. Save to .mps file
        instance_name = os.path.splitext(os.path.basename(fpath))[0]
        mps_path = os.path.join(mps_dir, f"{instance_name}.mps")
        model.write(mps_path)

        extractor = GraphExtractor(model)
        data = extractor.extract()

        # Save
        name = Path(fpath).stem
        save_path = processed_dir / f"{name}.pt"
        torch.save(data, save_path)

        # Dispose model to free memory
        model.dispose()
        return True, fpath

    except Exception as e:
        return False, f"{fpath}: {str(e)}"

def process_dataset(problem='facilities', split='train', n_jobs=64):
    raw_dir = config.RAW_DATA_DIR / problem / split
    mps_dir = config.MPS_DATA_DIR / problem / split
    processed_dir = config.PROCESSED_DATA_DIR / problem / split

    if not raw_dir.exists():
        print(f"Raw data directory {raw_dir} does not exist.")
        return

    os.makedirs(mps_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    files = glob.glob(str(raw_dir / "*.txt"))
    print(f"Found {len(files)} instances in {raw_dir}. Processing with {n_jobs} workers...")

    tasks = [(fpath, mps_dir, processed_dir) for fpath in files]

    # Use ProcessPoolExecutor for parallel processing
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
        results = list(tqdm(executor.map(process_single_file, tasks), total=len(tasks)))

    # Check errors
    errors = [res[1] for res in results if not res[0]]
    if errors:
        print(f"Encountered {len(errors)} errors:")
        for err in errors[:10]:
            print(err)
        if len(errors) > 10:
            print("...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default='facilities')
    parser.add_argument('--jobs', type=int, default=64, help='Number of parallel jobs')
    args = parser.parse_args()

    # Process train, valid, test
    for split in ['train', 'valid', 'test']:
        process_dataset(args.problem, split, n_jobs=args.jobs)
