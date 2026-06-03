"""
Generate synthetic MIP/LP instances for registered problem types.

Usage:
    python 01_generate_instances.py gap
    python 01_generate_instances.py gap -s 42
    python 01_generate_instances.py rmf
"""

import os
import argparse
import numpy as np
import config


def generate_gap_set(rng, specs, out_dir):
    """Generate GAP LP files. (Thin wrapper preserving original logic.)"""
    import shutil
    from solvers.gap_generator import generate_gap_instance

    if out_dir.exists():
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    n_instances = specs['n_instances']
    n_agents_min = specs['n_agents_min']
    n_agents_max = specs['n_agents_max']
    n_tasks_min = specs['n_tasks_min']
    n_tasks_max = specs['n_tasks_max']
    types = specs.get('types', ['A'])

    for idx in range(n_instances):
        gap_type = types[idx % len(types)]
        na = int(rng.integers(n_agents_min, n_agents_max + 1))
        nt = int(rng.integers(n_tasks_min, n_tasks_max + 1))
        lp_str = generate_gap_instance(
            n_agents=na, n_tasks=nt, rng=rng, gap_type=gap_type,
        )
        filepath = out_dir / f"a{na}_t{nt}_type{gap_type}_{idx + 1}.lp"
        filepath.write_text(lp_str)
        if (idx + 1) % 100 == 0:
            print(f"  generated {idx + 1}/{n_instances}...")


def generate_rmf_set(rng, specs, out_dir):
    """Generate RMF LP files from GAMS data."""
    from solvers.rmf_generator import generate_rmf_instances
    grid_dir = config.PROJECT_ROOT / "grid"
    out_dir.mkdir(parents=True, exist_ok=True)
    files = specs.get('files', [])
    generate_rmf_instances(grid_dir, out_dir, files)


# Register problem generators keyed by problem name.
GENERATORS = {
    'gap': generate_gap_set,
    'rmf': generate_rmf_set,
}


if __name__ == '__main__':
    known = list(GENERATORS)
    parser = argparse.ArgumentParser()
    parser.add_argument('problem', choices=known, default='gap', nargs='?')
    parser.add_argument('-s', '--seed', type=int, default=0)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    spec = config.get_problem(args.problem)
    gen_fn = GENERATORS[args.problem]
    gen_spec = spec.gen_spec
    base_dir = config.RAW_DATA_DIR / args.problem

    print(f"Generating {args.problem} instances (seed={args.seed})")
    for split_name, split_specs in gen_spec.items():
        if not split_specs:
            continue
        out_dir = base_dir / split_name
        print(f"  {split_name} → {out_dir}")
        gen_fn(rng, split_specs, out_dir)

    print("done.")
