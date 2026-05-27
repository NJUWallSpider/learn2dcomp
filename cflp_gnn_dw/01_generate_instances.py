"""
Generate random GAP instances → data/raw/gap/{train,valid,test,...}/

Usage:
    python 01_generate_instances.py gap [-s SEED]
"""
import os
import argparse
import numpy as np
import shutil
import config


def generate_gap_instance(rng, filename, n_jobs, n_machines,
                          cost_range=(1, 50), weight_range=(1, 20),
                          capacity_ratio=0.6):
    """
    Generate a random GAP instance.

    Costs and weights are drawn uniformly from the given ranges.
    Capacities are set uniformly so that total_capacity = capacity_ratio * total_weight.
    """
    c_min, c_max = cost_range
    w_min, w_max = weight_range

    costs = rng.integers(c_min, c_max + 1, size=(n_jobs, n_machines))
    weights = rng.integers(w_min, w_max + 1, size=(n_jobs, n_machines))

    # Uniform capacity per machine
    total_weight_per_machine = weights.sum(axis=0)
    capacities = (total_weight_per_machine * capacity_ratio).astype(int)

    # Ensure each job can fit on at least one machine (minimum capacity >= min weight per job)
    for j in range(n_machines):
        min_needed = weights[:, j].min()
        if capacities[j] < min_needed:
            capacities[j] = min_needed

    with open(filename, 'w') as f:
        f.write(f"{n_jobs} {n_machines}\n")
        for i in range(n_jobs):
            f.write(" ".join(str(costs[i, j]) for j in range(n_machines)) + "\n")
        for i in range(n_jobs):
            f.write(" ".join(str(weights[i, j]) for j in range(n_machines)) + "\n")
        f.write(" ".join(str(capacities[j]) for j in range(n_machines)) + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'problem',
        help='Problem type (gap).',
        choices=['gap'],
    )
    parser.add_argument(
        '-s', '--seed',
        help='Random seed (default 0).',
        type=int,
        default=0,
    )
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    generation_specs = config.GAP_GEN
    base_dir = config.RAW_DATA_DIR / args.problem

    print(f"Generating instances for: {args.problem}")

    for name, specs in generation_specs.items():
        n_instances = specs.get('n_instances', 0)
        if n_instances == 0:
            continue

        instance_dir = base_dir / name
        print(f"  {n_instances} instances → {instance_dir}")

        if not specs.get('overwrite', False) and instance_dir.exists():
            print(f"    skipping, directory already exists (overwrite=False).")
            continue

        if instance_dir.exists():
            shutil.rmtree(instance_dir)
        os.makedirs(instance_dir, exist_ok=True)

        for idx in range(n_instances):
            filename = instance_dir / f"{idx + 1}.txt"
            generate_gap_instance(
                rng, str(filename),
                n_jobs=specs['n_jobs'],
                n_machines=specs['n_machines'],
                cost_range=specs.get('cost_range', (1, 50)),
                weight_range=specs.get('weight_range', (1, 20)),
                capacity_ratio=specs.get('capacity_ratio', 0.6),
            )

        print(f"    done.")

    print("All done.")
