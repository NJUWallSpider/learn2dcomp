"""
Generate GAP instances using Chu & Beasley (1997) Type A-E distributions.

Usage:
    python 01_generate_instances.py gap [-s SEED]
"""
import argparse
import numpy as np
import shutil
from pathlib import Path
import config
from gap_generator import generate_gap_lp


def generate_split(rng, specs, out_dir):
    """Generate LP files for a data split."""
    if out_dir.exists():
        if not specs.get('overwrite', False):
            print(f"  skipping, {out_dir} exists (overwrite=False)")
            return
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_instances = specs['n_instances']
    types = specs.get('types', ['A'])
    na_min = specs['n_agents_min']
    na_max = specs['n_agents_max']
    nt_min = specs['n_tasks_min']
    nt_max = specs['n_tasks_max']

    for idx in range(n_instances):
        gap_type = types[idx % len(types)]
        na = int(rng.integers(na_min, na_max + 1))
        nt = int(rng.integers(nt_min, nt_max + 1))
        lp_str = generate_gap_lp(na, nt, rng, gap_type)
        fname = f"a{na}_t{nt}_type{gap_type}_{idx + 1}.lp"
        (out_dir / fname).write_text(lp_str)
    print(f"  {n_instances} instances → {out_dir}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('problem', choices=['gap'])
    parser.add_argument('-s', '--seed', type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    for name, specs in config.GAP_GEN.items():
        if specs.get('n_instances', 0) == 0:
            continue
        out_dir = config.RAW_DATA_DIR / args.problem / name
        generate_split(rng, specs, out_dir)
    print("Done.")
