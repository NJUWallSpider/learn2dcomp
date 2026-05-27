"""
Build GAP graph dataset from .txt instances.

For each instance:
  1. Load GAPInstance, build SCIP model, solve to optimality
  2. Extract variable/constraint labels from optimal solution
  3. Use GraphExtractor to build bipartite HeteroData (no SCIP needed for topology)
  4. Add Laplacian PE, save as .pt

Usage:
    python 02_generate_dataset.py --problem gap [--jobs N]
"""
import os
import glob
import torch
import argparse
import sys
from pathlib import Path
import concurrent.futures
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from gap_model import GAPInstance, build_scip_model, extract_labels
from graph_utils import GraphExtractor
from data_process import add_laplacian_pe
import config


def process_single_file(args):
    fpath, processed_dir = args
    try:
        inst = GAPInstance(fpath)

        # Solve for labels
        model, x = build_scip_model(inst)
        model.hideOutput()
        model.optimize()

        var_labels = None
        con_labels = None
        if model.getStatus() == "optimal":
            x_sol = {}
            for i in range(inst.n_jobs):
                for j in range(inst.n_machines):
                    x_sol[(i, j)] = model.getVal(x[(i, j)])
            var_labels, con_labels = extract_labels(inst, x_sol)

        # Extract graph (no SCIP needed)
        extractor = GraphExtractor(inst)
        data = extractor.extract(var_labels=var_labels, con_labels=con_labels)

        # Positional encoding
        data = add_laplacian_pe(data, k=config.MODEL_PARAMS.get('pe_dim', 8))

        # Save
        name = Path(fpath).stem
        save_path = processed_dir / f"{name}.pt"
        torch.save(data, save_path)

        return True, fpath

    except Exception as e:
        return False, f"{fpath}: {e}"


def process_dataset(problem='gap', split='train', n_jobs=64):
    raw_dir = config.RAW_DATA_DIR / problem / split
    processed_dir = config.PROCESSED_DATA_DIR / problem / split

    if not raw_dir.exists():
        print(f"Raw data directory {raw_dir} does not exist.")
        return

    os.makedirs(processed_dir, exist_ok=True)

    files = glob.glob(str(raw_dir / "*.txt"))
    print(f"Found {len(files)} instances in {raw_dir}. Processing with {n_jobs} workers...")

    tasks = [(f, processed_dir) for f in files]

    with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
        results = list(tqdm(executor.map(process_single_file, tasks), total=len(tasks)))

    errors = [res[1] for res in results if not res[0]]
    if errors:
        print(f"Encountered {len(errors)} errors:")
        for err in errors[:10]:
            print(err)
        if len(errors) > 10:
            print("... ({len(errors) - 10} more)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default='gap')
    parser.add_argument('--jobs', type=int, default=64, help='Number of parallel workers')
    parser.add_argument('--split', type=str, default=None, help='Process only this split (train/valid/test/large)')
    args = parser.parse_args()

    if args.split:
        process_dataset(args.problem, args.split, n_jobs=args.jobs)
    else:
        for split in ['train', 'valid', 'test', 'large']:
            process_dataset(args.problem, split, n_jobs=args.jobs)
