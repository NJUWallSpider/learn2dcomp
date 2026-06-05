"""Convert OR-Library .txt GAP instances to .lp format for our pipeline."""
import sys
from pathlib import Path
from gap_model import GAPInstance
from gap_generator import generate_gap_lp
import numpy as np


def txt_to_lp(txt_path, lp_path):
    inst = GAPInstance(txt_path)
    na = inst.n_machines   # agents = machines
    nt = inst.n_jobs       # tasks = jobs
    rng = np.random.default_rng(0)
    # Use _generate_gap_data to create the structured instance, then overwrite
    # with actual values. But simpler: just write LP directly from inst data
    lp = _build_lp_from_instance(inst)
    Path(lp_path).write_text(lp)


def _build_lp_from_instance(inst):
    n_agents = inst.n_machines
    n_tasks = inst.n_jobs
    costs = inst.costs.T   # (n_machines, n_jobs) for lp format
    weights = inst.weights.T
    capacities = inst.capacities

    lines = [f"\\ OR-Library GAP — {n_agents} agents x {n_tasks} tasks",
             "Minimize"]
    obj_terms = []
    for i in range(n_agents):
        for j in range(n_tasks):
            c = costs[i, j]
            if c != 0:
                sign = " + " if c >= 0 else " - "
                obj_terms.append(f"{sign}{abs(int(c))} x_{i}_{j}")
    obj_str = "".join(obj_terms)
    if obj_str.startswith(" + "): obj_str = obj_str[3:]
    lines.append("  " + obj_str)

    lines.append("Subject To")
    for j in range(n_tasks):
        terms = " + ".join(f"x_{i}_{j}" for i in range(n_agents))
        lines.append(f"  assign_{j}: {terms} = 1")
    for i in range(n_agents):
        nz = [(j, weights[i, j]) for j in range(n_tasks) if weights[i, j] != 0]
        if nz:
            terms = " + ".join(f"{int(w)} x_{i}_{j}" for j, w in nz)
            lines.append(f"  cap_{i}: {terms} <= {int(capacities[i])}")

    lines.append("Bounds")
    for i in range(n_agents):
        for j in range(n_tasks):
            lines.append(f"  0 <= x_{i}_{j} <= 1")

    lines.append("Binaries")
    var_names = [f"x_{i}_{j}" for i in range(n_agents) for j in range(n_tasks)]
    line = "  "
    for v in var_names:
        if len(line) + len(v) + 1 > 250:
            lines.append(line.rstrip())
            line = "   " + v + " "
        else:
            line += v + " "
    lines.append(line.rstrip())
    lines.append("End")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", help="Directory of .txt GAP instances")
    parser.add_argument("output_dir", help="Output directory for .lp files")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(Path(args.input_dir).glob("*.txt")):
        out_path = out_dir / f.with_suffix(".lp").name
        txt_to_lp(str(f), str(out_path))
        print(f"  {f.name} -> {out_path.name}")
    print(f"Done. {len(list(Path(args.input_dir).glob('*.txt')))} converted.")
