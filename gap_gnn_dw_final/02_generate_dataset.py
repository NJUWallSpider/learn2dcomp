"""
Build GNN dataset from GAP .lp files using GCG detection labels.

For each instance:
  1. Load .lp with PyGCGOpt → run detection (short time limit) → get .dec
  2. Parse .dec → constraint-to-block assignments → infer variable labels
  3. Build bipartite graph (GraphExtractor) → save .pt

Usage:
    python 02_generate_dataset.py --problem gap --split train
"""
import os
import glob
import argparse
import sys
from pathlib import Path
from tqdm import tqdm

import torch
import numpy as np

sys.path.append(str(Path(__file__).parent))
from gcg_interface import detect_decomposition, parse_dec
from gap_generator import generate_gap_txt
from gap_model import GAPInstance
from graph_utils import GraphExtractor
from data_process import add_laplacian_pe, add_block_pe
import config


def process_single_lp(lp_path, dec_dir, processed_dir):
    """Run GCG detection on one LP file, extract labels, save .pt."""
    fname = Path(lp_path).stem
    pt_path = processed_dir / f"{fname}.pt"
    if pt_path.exists():
        return True, f"{fname} (cached)"

    try:
        # 1. Run GCG detection → .dec
        dec_path = detect_decomposition(lp_path, dec_dir / fname,
                                         time_limit=3)
        if dec_path is None:
            return False, f"{fname}: GCG detection failed"

        # 2. Parse .dec → constraint labels
        parsed = parse_dec(dec_path)
        con_label = parsed['con_label']

        # 3. Infer variable labels from constraint labels
        #    x_i_j: assign_j is always MASTER; cap_i's label determines block
        #    For GAP, cap_i label = block_id (1..N). assign_j label = -2 (master)
        #    Variable x_i_j belongs to block_id of cap_i
        lp_text = Path(lp_path).read_text()
        from gap_generator import parse_lp_dims
        na, nt = parse_lp_dims(lp_text)

        # Build variable→block mapping
        var_labels = {}
        for i in range(na):
            block_id = con_label.get(f"cap_{i}", -2)
            for j in range(nt):
                vname = f"x_{i}_{j}"
                var_labels[vname] = block_id if block_id >= 0 else -1

        # 4. Build GAPInstance from .lp (convert to txt, load)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.txt', mode='w', delete=False) as tf:
            from gap_generator import lp_to_txt
            lp_to_txt(lp_text, tf.name)

        inst = GAPInstance(tf.name)
        os.unlink(tf.name)

        # Variable labels as dict (i,j) → label
        var_labels_idx = {}
        for i in range(na):
            block_id = con_label.get(f"cap_{i}", -2)
            for j in range(nt):
                var_labels_idx[(j, i)] = block_id if block_id >= 0 else -1

        # Constraint labels for HeteroData
        con_labels_data = {}
        for con_name, label in con_label.items():
            con_labels_data[con_name] = label

        # 5. Build graph
        extractor = GraphExtractor(inst)
        data = extractor.extract(var_labels=var_labels_idx,
                                  con_labels=con_labels_data)
        data = add_laplacian_pe(data, k=config.MODEL_PARAMS.get('pe_dim', 8))
        data = add_block_pe(data, k=config.MODEL_PARAMS.get('block_pe_dim', 8))
        data.var_names = [f"x_{i}_{j}" for i in range(na) for j in range(nt)]
        data.con_names = (
            [f"cap_{i}" for i in range(na)] +
            [f"assign_{j}" for j in range(nt)]
        )

        torch.save(data, pt_path)

        # O3: Data augmentation — machine permutation invariance
        # Generate 2 augmented copies with permuted machine indices
        aug_count = 2
        for aug in range(aug_count):
            aug_name = f"{fname}_aug{aug}"
            aug_pt = processed_dir / f"{aug_name}.pt"
            if aug_pt.exists():
                continue
            # Permute machine indices
            perm = list(range(na))
            np.random.seed(hash(fname + str(aug)) % 2**31)
            np.random.shuffle(perm)
            inv_perm = np.argsort(perm)
            # Create permuted instance
            aug_inst_file = str(Path(tempfile.gettempdir()) / f"aug_{aug_name}.txt")
            aug_inst = _permute_instance(inst, perm)
            # Permute labels accordingly
            aug_var_labels = {}
            for (j, i), label in var_labels_idx.items():
                new_label = inv_perm[label] if label >= 0 else label
                aug_var_labels[(j, inv_perm[i])] = new_label
            aug_con_labels = {}
            for con_name, label in con_labels_data.items():
                if label >= 0 and con_name.startswith("cap_"):
                    aug_con_labels[f"cap_{inv_perm[label]}"] = label
                else:
                    aug_con_labels[con_name] = label
            # Build augmented graph
            aug_extractor = GraphExtractor(aug_inst)
            aug_data = aug_extractor.extract(var_labels=aug_var_labels,
                                              con_labels=aug_con_labels)
            aug_data = add_laplacian_pe(aug_data, k=config.MODEL_PARAMS.get('pe_dim', 8))
            aug_data = add_block_pe(aug_data, k=config.MODEL_PARAMS.get('block_pe_dim', 8))
            torch.save(aug_data, aug_pt)

        return True, fname

    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"{fname}: {e}"


def process_dataset(problem='gap', split='train', n_jobs=1):
    raw_dir = config.RAW_DATA_DIR / problem / split
    processed_dir = config.PROCESSED_DATA_DIR / problem / split
    dec_base_dir = config.DATA_DIR / "decompositions" / problem / split

    if not raw_dir.exists():
        print(f"Raw data directory {raw_dir} does not exist.")
        return

    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(dec_base_dir, exist_ok=True)

    files = sorted(glob.glob(str(raw_dir / "*.lp")))
    done = set(p.stem for p in processed_dir.glob("*.pt"))
    todo = [f for f in files if Path(f).stem not in done]
    skipped = len(files) - len(todo)
    if skipped:
        print(f"Found {len(files)}, {skipped} done, {len(todo)} to process.")
    else:
        print(f"Found {len(files)} instances. Processing...")

    for fpath in tqdm(todo):
        ok, msg = process_single_lp(fpath, dec_base_dir, processed_dir)
        if not ok:
            print(f"  SKIP: {msg}")


def _permute_instance(inst, perm):
    """Return a new GAPInstance with machine indices permuted."""
    import copy
    new_inst = copy.deepcopy(inst)
    na = new_inst.n_machines
    nt = new_inst.n_jobs
    # Permute costs and weights columns
    new_inst.costs = new_inst.costs[:, perm]
    new_inst.weights = new_inst.weights[:, perm]
    new_inst.capacities = new_inst.capacities[perm]
    return new_inst


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default='gap')
    parser.add_argument('--split', type=str, default=None)
    args = parser.parse_args()

    if args.split:
        process_dataset(args.problem, args.split)
    else:
        for split in ['train', 'valid', 'test']:
            process_dataset(args.problem, split)
