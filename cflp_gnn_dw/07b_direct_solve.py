"""
Direct SCIP solve of GAP compact formulation (baseline for DW comparison).

Usage:
    python 07b_direct_solve.py --instance data/raw/gap/test/1.txt
    python 07b_direct_solve.py --instance-dir data/raw/gap/test --output-csv results/direct_solve.csv
"""
import sys
import time
import csv
import argparse
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).parent))

from gap_model import GAPInstance, build_scip_model


def solve_single(inst: GAPInstance, time_limit: float = None,
                 mip_gap: float = 1e-4) -> Dict:
    """Solve one GAP instance with SCIP."""
    model, x = build_scip_model(inst)
    model.hideOutput()

    if time_limit:
        model.setRealParam("limits/time", time_limit)
    model.setRealParam("limits/gap", mip_gap)

    t0 = time.time()
    model.optimize()
    elapsed = time.time() - t0

    status = model.getStatus()
    obj = model.getObjVal() if status == "optimal" else None

    # Count assignments
    assignments = {}
    n_assigned = 0
    if status == "optimal":
        for i in range(inst.n_jobs):
            for j in range(inst.n_machines):
                try:
                    val = model.getVal(x[i, j])
                except Exception:
                    val = 0.0
                if val > 0.5:
                    assignments[i] = j
                    n_assigned += 1

    return {
        "instance": Path(inst.file_path).stem,
        "n_jobs": inst.n_jobs,
        "n_machines": inst.n_machines,
        "status": status,
        "obj_val": obj,
        "solve_time": elapsed,
        "n_assigned": n_assigned,
    }


def main():
    parser = argparse.ArgumentParser(
        description="SCIP direct solve baseline for GAP"
    )
    parser.add_argument('--instance', type=str, default=None,
                        help='Path to single .txt instance')
    parser.add_argument('--instance-dir', type=str, default=None,
                        help='Directory of .txt instances')
    parser.add_argument('--output-csv', type=str, default=None,
                        help='Save results to CSV')
    parser.add_argument('--time-limit', type=float, default=600,
                        help='Solver time limit per instance (seconds)')
    parser.add_argument('--mip-gap', type=float, default=1e-4,
                        help='MIP optimality gap tolerance')
    args = parser.parse_args()

    if args.instance:
        instances = [args.instance]
    elif args.instance_dir:
        instances = sorted([str(p) for p in Path(args.instance_dir).glob("*.txt")])
    else:
        test_dir = Path(__file__).parent / "data" / "raw" / "gap" / "test"
        instances = sorted([str(p) for p in test_dir.glob("*.txt")])

    if not instances:
        print("No instances found.")
        return

    results = []
    for i, inst_path in enumerate(instances):
        print(f"[{i+1}/{len(instances)}] {Path(inst_path).name}...", end=" ")
        try:
            inst = GAPInstance(inst_path)
            result = solve_single(inst, time_limit=args.time_limit,
                                  mip_gap=args.mip_gap)
            results.append(result)
            print(f"obj={result['obj_val']}, time={result['solve_time']:.2f}s, "
                  f"status={result['status']}")
        except Exception as e:
            print(f"ERROR: {e}")

    # Summary
    solved = [r for r in results if r["status"] == "optimal"]
    print(f"\n{'='*40}")
    print(f"Solved: {len(solved)}/{len(results)}")
    if solved:
        avg_time = sum(r["solve_time"] for r in solved) / len(solved)
        print(f"Avg time: {avg_time:.2f}s")

    # Save
    if args.output_csv and results:
        output_path = Path(args.output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        print(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
