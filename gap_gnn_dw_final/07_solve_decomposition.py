"""
Solve GAP using GNN-predicted decomposition as warm-start for DW column generation.

Compares:
  (A) GNN warm-start → DW CG → final MILP
  (B) SCIP direct solve of compact formulation

Usage:
    python 07_solve_decomposition.py --instance data/raw/gap/test/1.txt
                                     [--warmstart results/decomposition_output/1.json]
                                     [--output-csv results/dw_results.csv]
"""
import sys
import time
import json
import argparse
from pathlib import Path
from typing import Optional, Dict

sys.path.insert(0, str(Path(__file__).parent))

from gap_model import GAPInstance, build_scip_model
from gap_cg import GAPColumnGenerator


def solve_direct(inst: GAPInstance) -> Dict:
    """Solve GAP compact formulation directly with SCIP."""
    t0 = time.time()
    model, _ = build_scip_model(inst)
    model.hideOutput()
    model.optimize()
    elapsed = time.time() - t0

    status = model.getStatus()
    return {
        "direct_status": status,
        "direct_obj": model.getObjVal() if status == "optimal" else None,
        "direct_time": elapsed,
    }


def solve_dw(inst: GAPInstance, warmstart_json: Optional[str] = None,
             max_iter: int = 500, tol: float = 1e-6,
             milp_time_limit: float = None) -> Dict:
    """Run DW column generation with optional GNN warm-start."""
    cg = GAPColumnGenerator(inst)
    cg.setup_rmp()

    # Warm-start from GNN decomposition
    warmstart_cols = 0
    if warmstart_json:
        with open(warmstart_json, 'r') as f:
            decomp = json.load(f)

        # Expected format: {"assignment": {job_id: machine_id, ...}}
        assignment_raw = decomp.get("assignment", {})
        if assignment_raw:
            assignment = {int(k): int(v) for k, v in assignment_raw.items()}
            warmstart_cols = cg.warmstart_from_assignment(assignment)

    # CG phase
    t0 = time.time()
    cg_result = cg.run_column_generation(max_iter=max_iter, tol=tol)
    cg_time = time.time() - t0

    if cg_result is None:
        return {
            "cg_status": "rmp_failed",
            "cg_iterations": 0,
            "cg_lb": None,
            "cg_time": cg_time,
            "milp_status": None,
            "milp_obj": None,
            "milp_gap": None,
            "milp_time": 0.0,
            "total_columns": sum(len(cols) for cols in cg.columns),
            "warmstart_columns": warmstart_cols,
        }

    # Final MILP phase
    t1 = time.time()
    milp_result = cg.solve_final_milp(time_limit=milp_time_limit)
    milp_time = time.time() - t1

    return {
        "cg_status": cg_result["status"],
        "cg_iterations": cg_result["iterations"],
        "cg_lb": cg_result["lb"],
        "cg_time": cg_time,
        "milp_status": milp_result["status"],
        "milp_obj": milp_result["obj_val"],
        "milp_gap": milp_result["gap"],
        "milp_time": milp_time,
        "total_columns": sum(len(cols) for cols in cg.columns),
        "warmstart_columns": warmstart_cols,
    }


def solve_single_instance(inst_path: str, warmstart_json: Optional[str] = None,
                          max_iter: int = 500, milp_time_limit: float = None) -> Dict:
    """Solve one GAP instance: direct SCIP + DW CG."""
    inst = GAPInstance(inst_path)
    inst_name = Path(inst_path).stem

    print(f"\n{'='*60}")
    print(f"Instance: {inst_name} ({inst.n_jobs} jobs x {inst.n_machines} machines)")
    print(f"{'='*60}")

    # Direct solve
    print("\n--- SCIP Direct Solve ---")
    direct = solve_direct(inst)
    print(f"  Status: {direct['direct_status']}, Obj: {direct['direct_obj']}, "
          f"Time: {direct['direct_time']:.2f}s")

    # DW solve
    print("\n--- DW Column Generation ---")
    dw = solve_dw(inst, warmstart_json=warmstart_json,
                  max_iter=max_iter, milp_time_limit=milp_time_limit)
    print(f"  CG: {dw['cg_status']}, {dw['cg_iterations']} iters, "
          f"LB={dw['cg_lb']}, time={dw['cg_time']:.2f}s")
    print(f"  MILP: {dw['milp_status']}, obj={dw['milp_obj']}, "
          f"gap={dw['milp_gap']}, time={dw['milp_time']:.2f}s")
    print(f"  Columns: {dw['total_columns']} (warmstart: {dw['warmstart_columns']})")

    # Compute optimality gap
    gap_to_optimal = None
    if direct["direct_obj"] is not None and dw["milp_obj"] is not None:
        gap_to_optimal = abs(dw["milp_obj"] - direct["direct_obj"]) / max(1e-6, abs(direct["direct_obj"]))

    return {
        "instance": inst_name,
        "n_jobs": inst.n_jobs,
        "n_machines": inst.n_machines,
        **direct,
        **dw,
        "gap_to_optimal": gap_to_optimal,
    }


def main():
    parser = argparse.ArgumentParser(
        description="GAP DW decomposition solver with GNN warm-start"
    )
    parser.add_argument('--instance', type=str, default=None,
                        help='Path to single .txt instance')
    parser.add_argument('--instance-dir', type=str, default=None,
                        help='Path to directory of .txt instances')
    parser.add_argument('--warmstart-dir', type=str, default=None,
                        help='Directory of GNN decomposition JSON files')
    parser.add_argument('--output-csv', type=str, default=None,
                        help='Path to output results CSV')
    parser.add_argument('--max-cg-iter', type=int, default=500)
    parser.add_argument('--milp-time-limit', type=float, default=None)
    parser.add_argument('--no-csv', action='store_true',
                        help='Print results but do not save to CSV')
    args = parser.parse_args()

    if args.instance:
        instances = [args.instance]
    elif args.instance_dir:
        instances = sorted([str(p) for p in Path(args.instance_dir).glob("*.txt")])
    else:
        # Default: test set
        test_dir = Path(__file__).parent / "data" / "raw" / "gap" / "test"
        instances = sorted([str(p) for p in test_dir.glob("*.txt")])

    if not instances:
        print("No instances found.")
        return

    warmstart_dir = None
    if args.warmstart_dir:
        warmstart_dir = Path(args.warmstart_dir)

    results = []
    for inst_path in instances:
        inst_name = Path(inst_path).stem

        ws_json = None
        if warmstart_dir:
            json_path = warmstart_dir / f"{inst_name}_decomposition.json"
            if json_path.exists():
                ws_json = str(json_path)
            else:
                print(f"  Warning: warmstart JSON not found for {inst_name}")

        try:
            result = solve_single_instance(
                inst_path,
                warmstart_json=ws_json,
                max_iter=args.max_cg_iter,
                milp_time_limit=args.milp_time_limit
            )
            results.append(result)
        except Exception as e:
            print(f"Error solving {inst_name}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    if results:
        print(f"\n{'='*60}")
        print(f"Summary ({len(results)} instances)")
        print(f"{'='*60}")

        cg_iters = [r["cg_iterations"] for r in results if r["cg_status"] == "converged"]
        dw_feasible = [r for r in results if r["milp_status"] == "optimal"]

        if cg_iters:
            print(f"  Avg CG iterations: {sum(cg_iters) / len(cg_iters):.1f}")
        if dw_feasible:
            avg_gap = sum(r.get("gap_to_optimal", 0) or 0 for r in dw_feasible) / len(dw_feasible)
            print(f"  DW MILP solved: {len(dw_feasible)}/{len(results)}")
            print(f"  Avg optimality gap: {avg_gap:.6f}")

        # Save CSV
        if args.output_csv and not args.no_csv:
            import csv
            output_path = Path(args.output_csv)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if results:
                with open(output_path, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=results[0].keys())
                    writer.writeheader()
                    writer.writerows(results)
            print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
